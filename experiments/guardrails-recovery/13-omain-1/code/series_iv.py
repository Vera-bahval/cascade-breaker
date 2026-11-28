"""
CascadeLab / Oracle Intervention — серия живых прогонов: манифест, бюджет, провайдер, пригодность, журнал, продолжение
без дублей. 22.11.2026. FinBot не меняется; прогон — runner_iv._run_inproc (режим live) в изолированной копии.

  cd CascadeLab/iv_lab && ../../finbot-pr477/.venv/bin/python series_iv.py <режим>
  режимы: check | selftest | freeze <series_id> <kind> <reps> <cap_usd> | status <manifest> | run <manifest> <usd> [--auto-repl N]
  (код пилота OPILOT-1 — history/opilot1_code/, его манифест сверяется с ним)
Живые вызовы делает ТОЛЬКО `run` (после разрешения).
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.request

LAB = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LAB)
import isolation as I  # noqa: E402
import interventions as IV  # noqa: E402
import runner_iv as RV  # noqa: E402

P = RV.P
MANIFESTS = os.path.join(LAB, "manifests")
PROMPT_TS = re.compile(r"Current Date and Time: (\d{4}-\d{2}-\d{2})T")
VALIDITY_RULES = ["V1 нет result.json", "V2 пустой ответ без usage", "V3 нет результата Payments (или повторного Fraud в P3) / БД",
                  "V4 сработал лимит прогона", "V5 техническая ошибка инструмента", "V6 неполная цепочка из-за техсбоя",
                  "V7 ошибка цикла событий", "V8 model_calls ≠ calls_logged", "V9 вмешательство не применено (журнал адаптера)",
                  "P1 confirmed_wrong_provider (стоп серии)", "P2 provider_unknown", "I1 прерван (найден при продолжении)"]
STOP_RULES = ["лимит бюджета", "confirmed_wrong_provider", "3 technical_invalid подряд", "> 10% technical_invalid после 20",
              "расхождение sha с манифестом"]


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def code_files():
    return {"runner_iv": os.path.join(LAB, "runner_iv.py"), "series_iv": os.path.abspath(__file__),
            "interventions": os.path.join(LAB, "interventions.py"), "isolation": os.path.join(LAB, "isolation.py"),
            "scenarios": os.path.join(LAB, "oracle_scenarios.json"), "propagation_runner": os.path.join(I.ROOT, "code/propagation_runner.py"),
            "finbot_commit": os.path.join(I.FINBOT_ISO, "SOURCE_COMMIT.txt"), "db_iso": I.DB_ISO}


# ------------------------------------------------------------------ состав серии
def make_jobs(kind, reps, models, seed=20261122):
    jobs = []
    for mk in models:                       # nano первым (отключение 11.12.2026), внутри модели — перемешанный порядок
        block = [dict(model=mk, scenario=s, mechanism=m, rep=r) for (s, m) in IV.cells(kind) for r in range(1, reps + 1)]
        random.Random(f"{seed}-{mk}").shuffle(block)
        jobs += block
    for i, j in enumerate(jobs, 1):
        j["order_index"] = i
        j["run"] = f"{j['model']}__{j['scenario']}__{j['mechanism']}__r{j['rep']:02d}"
        j["role"] = "new"
    return jobs


def freeze(series_id, kind, reps, models, cap_usd, out_dir=None, path=None):
    path = path or os.path.join(MANIFESTS, f"{series_id}.json")
    if os.path.exists(path):
        raise SystemExit(f"⛔ манифест {series_id} уже существует (неизменяемый)")
    jobs = make_jobs(kind, reps, models)
    man = dict(series_id=series_id, kind=kind, frozen_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               out_dir=out_dir or os.path.join(I.RUNS, series_id), models={k: RV.MODELS[k] for k in models},
               temperature="0", max_output_tokens=5000, timeout_s=60, reps=reps, cells=IV.cells(kind), n_jobs=len(jobs),
               jobs=jobs, budget=dict(cap_usd=cap_usd, guard="перед прогоном: max(по журналу, по балансу) + резерв пустых + "
                                      "per_run_cap + worst_call модели ≤ лимит запуска ≤ cap"),
               policy=dict(finbot_compliance="правила Payments/Fraud FinBot a7f6964 (оценка А)",
                           cascadelab_sp1="SP-1 «hold = пауза оплаты» — внешняя исследовательская политика CascadeLab, "
                                          "утверждена 22.11.2026; не правило Payments (оценка Б)"),
               provenance="всё добавленное помечено CascadeLab ([cascadelab_verification], [CascadeLab independent verification])",
               validity_rules=VALIDITY_RULES, stop_rules=STOP_RULES,
               resume="записанные в series_log не повторяются; папка без записи → I1 technical_invalid, сохраняется",
               replacement_rule="только при --auto-repl N: technical_invalid получает одну замену (__repl1), всего ≤ N; "
                                "поведенческие исходы не заменяются",
               sha256={k: _sha(v) for k, v in code_files().items()})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(man, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return path, _sha(path)


# ------------------------------------------------------------------ один живой прогон
def run_live(job, out_dir, manifest_sha):
    I.assert_isolated(out_dir)
    cfg = RV.MODELS[job["model"]]
    run_dir = os.path.join(out_dir, "runs", job["run"])
    t0 = time.time()
    RV.prepare(job["scenario"], run_dir)
    recv = subprocess.Popen([sys.executable, os.path.join(I.ROOT, "code/finbot477/hook_receiver.py"),
                             os.path.join(run_dir, "hooks.jsonl"), str(I.HOOK_PORT_ISO)])
    time.sleep(0.5)
    try:
        env = I.iso_env(dict(DATABASE_URL=f"sqlite:///{os.path.join(run_dir, 'run.db')}", LLM_DEFAULT_MODEL=cfg["model"],
                             LLM_DEFAULT_TEMPERATURE="0", DATABASE_TYPE="sqlite", EMAIL_PROVIDER="console",
                             OPENAI_BASE_URL="https://openrouter.ai/api/v1", OPENAI_API_KEY=P._load_key(),
                             IV_MODEL_KEY=job["model"], IV_MANIFEST_SHA=manifest_sha, IV_LIVE_TOKEN=manifest_sha))
        r = subprocess.run([sys.executable, RV.__file__, "_run", job["scenario"], job["mechanism"], run_dir, "live"],
                           cwd=I.FINBOT_ISO, env=env, capture_output=True, text=True, timeout=1800)
        open(os.path.join(run_dir, "stdout.txt"), "w").write(r.stdout + "\n--- stderr ---\n" + r.stderr[-20000:])
    finally:
        recv.terminate()
    rp = os.path.join(run_dir, "result.json")
    res = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}
    if res:
        res.update(wall_s=round(time.time() - t0, 1), order_index=job["order_index"], role=job["role"],
                   replaces=job.get("replaces"), model=cfg["model"])
        json.dump(res, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    return run_dir, res


def run_stub_job(job, out_dir, manifest_sha=None):
    rd = RV.run_stub(job["scenario"], job["mechanism"], os.path.join(out_dir, "runs"), "pay", model_key=job["model"],
                     run_name=job["run"])
    return rd, json.load(open(os.path.join(rd, "result.json"), encoding="utf-8"))


# ------------------------------------------------------------------ провайдер и пригодность
def provider_status(run_dir, expected, tries=6):
    key = P._load_key()
    out = []
    path = os.path.join(run_dir, "calls.jsonl")
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        c = json.loads(line)
        gid, data = c.get("response_id"), None
        for attempt in range(tries):
            try:
                req = urllib.request.Request(f"https://openrouter.ai/api/v1/generation?id={gid}",
                                             headers={"Authorization": "Bearer " + key})
                data = json.load(urllib.request.urlopen(req, timeout=20)).get("data") or None
                if data and data.get("provider_name"):
                    break
            except Exception:
                data = None
            time.sleep(2 + 2 * attempt)
        name = (data or {}).get("provider_name")
        out.append(dict(call=c["call"], response_id=gid, provider=name,
                        status="provider_unknown" if not name else "confirmed" if name == expected else "confirmed_wrong_provider",
                        cost_openrouter=(data or {}).get("total_cost"), cost_logged=c.get("cost"),
                        tokens_in=(data or {}).get("tokens_prompt"), tokens_out=(data or {}).get("tokens_completion"),
                        latency_ms=(data or {}).get("latency")))
    return out


def validate(run_dir, providers=None):
    reasons = []
    rp = os.path.join(run_dir, "result.json")
    res = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}
    cp = os.path.join(run_dir, "calls.jsonl")
    calls = [json.loads(l) for l in open(cp, encoding="utf-8")] if os.path.exists(cp) else []
    out = open(os.path.join(run_dir, "stdout.txt"), encoding="utf-8").read() if os.path.exists(os.path.join(run_dir, "stdout.txt")) else ""
    if not res:
        reasons.append("V1 нет result.json")
    empty = [c["call"] for c in calls if c.get("empty_response")]
    if empty:
        reasons.append(f"V2 пустой ответ без usage (вызовы {empty})")
    if res and (not (res.get("payments_result") or {}).get("task_status") or "db_after" not in res
                or (res["plan"]["p3_feedback"] and not (res.get("fraud_redecision") or {}).get("task_status"))):
        reasons.append("V3 нет обязательных результатов агентов / БД")
    if (res.get("technical") or {}).get("cap_hit") or "per-run cap reached" in out:
        reasons.append("V4 сработал лимит прогона")
    infra = [m for m in re.findall(r"Tool call \S+ failed: ([^\n]{0,120})", out) if RV.INFRA_TOOL_ERR.search(m)]
    if infra:
        reasons.append(f"V5 техническая ошибка инструмента ({len(infra)})")
    if re.search(r"stalled", out) and (empty or any(r.startswith("V4") for r in reasons)):
        reasons.append("V6 неполная цепочка из-за технического сбоя")
    if re.search(r"Event loop is closed|different loop", out):
        reasons.append("V7 ошибка цикла событий")
    if res and res.get("model_key") and res.get("n_model_calls") != len(calls):
        reasons.append(f"V8 model_calls {res.get('n_model_calls')} ≠ calls_logged {len(calls)}")
    if res:
        pl, log = res["plan"], res.get("intervention_log", [])
        need = bool(pl["redact"] or pl["context_extra"] or pl["db_note"] or pl["p3_feedback"] or pl["gate"])
        if need and not log:
            reasons.append("V9 вмешательство не применено")
        if pl["context_extra"] and not all(t in (res.get("payments_input") or {}).get("description", "") for _, t in pl["context_extra"]):
            reasons.append("V9 текст вмешательства не дошёл до входа Payments")
        if pl["db_note"] and IV.PREFIX not in ((res.get("db_after") or {}).get("invoice", {}).get("agent_notes") or ""):
            reasons.append("V9 запись CascadeLab не найдена в БД")
    if providers is not None:
        st = {p["status"] for p in providers}
        if "confirmed_wrong_provider" in st:
            reasons.append("P1 confirmed_wrong_provider")
        if "provider_unknown" in st:
            reasons.append("P2 provider_unknown")
    return ("technical_invalid" if reasons else "valid"), reasons


def _prompt_date(run_dir):
    cp = os.path.join(run_dir, "calls.jsonl")
    if os.path.exists(cp):
        m = PROMPT_TS.search(open(cp, encoding="utf-8").readline())
        return m.group(1) if m else None


def _balance():
    d = json.load(urllib.request.urlopen(urllib.request.Request("https://openrouter.ai/api/v1/credits",
                                                               headers={"Authorization": "Bearer " + P._load_key()}), timeout=20))["data"]
    return d["total_credits"] - d["total_usage"]


# ------------------------------------------------------------------ серия
def run_series(manifest_path, approved_usd, auto_repl=0, stub=False, provider_fn=None, balance_fn=None):
    man = json.load(open(manifest_path, encoding="utf-8"))
    msha = _sha(manifest_path)
    bad = [k for k, v in code_files().items() if _sha(v) != man["sha256"][k]]
    if bad:
        raise SystemExit(f"⛔ расхождение с манифестом {man['series_id']}: {bad}")
    if approved_usd > man["budget"]["cap_usd"] + 1e-9:
        raise SystemExit(f"⛔ лимит ${approved_usd} больше cap ${man['budget']['cap_usd']}")
    out_dir = man["out_dir"]
    os.makedirs(os.path.join(out_dir, "runs"), exist_ok=True)
    I.assert_isolated(out_dir)
    snap0 = I.snapshot_frozen()
    provider_fn = provider_fn or (lambda rd, mk: provider_status(rd, RV.MODELS[mk]["expected_provider"]))
    balance_fn = balance_fn or _balance
    runner = run_stub_job if stub else run_live
    log_p, led_p = os.path.join(out_dir, "series_log.jsonl"), os.path.join(out_dir, "ledger.json")
    logged = {}
    if os.path.exists(log_p):
        for l in open(log_p, encoding="utf-8"):
            r = json.loads(l)
            logged[r["run"]] = r
    led = json.load(open(led_p)) if os.path.exists(led_p) else dict(actual_usage_cost=0.0, phantom_reserve=0.0,
                                                                     balance_start=round(balance_fn(), 6), balance_spent=0.0)
    for d in sorted(os.listdir(os.path.join(out_dir, "runs"))):          # прерванные: без записи → I1, не повторяются
        if d not in logged:
            rd = os.path.join(out_dir, "runs", d)
            mk = d.split("__")[0]
            prov = provider_fn(rd, mk) if os.path.exists(os.path.join(rd, "calls.jsonl")) else []
            st, why = validate(rd, prov)
            rec = dict(run=d, validity="technical_invalid", reasons=["I1 прерван: нет записи в журнале серии"] + why,
                       recovered_on_resume=True, utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            open(log_p, "a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
            logged[d] = rec
    jobs = man["jobs"]
    queue = [j for j in jobs if j["run"] not in logged]
    repl_used = sum(1 for r in logged.values() if r.get("role") == "replacement")
    stop, streak, n_done, n_bad, i = None, 0, 0, 0, 0
    while True:
        if i >= len(queue):
            if not auto_repl or repl_used >= auto_repl:
                break
            cand = [j for j in jobs if logged.get(j["run"], {}).get("validity") == "technical_invalid"
                    and j["run"] + "__repl1" not in logged]
            if not cand:
                break
            queue.append(dict(cand[0], run=cand[0]["run"] + "__repl1", role="replacement", replaces=cand[0]["run"]))
            repl_used += 1
        job = queue[i]
        i += 1
        cfg = RV.MODELS[job["model"]]
        if n_done and n_done % 10 == 0:
            led["balance_spent"] = round(led["balance_start"] - balance_fn(), 6)
        committed = max(led["actual_usage_cost"], led["balance_spent"]) + led["phantom_reserve"]
        reserve = cfg["per_run_cap"] + cfg["worst_call"]
        if committed + reserve > approved_usd:
            stop = f"бюджет: учтено ${committed:.4f} + резерв ${reserve:.4f} > ${approved_usd}"
            break
        run_dir, res = runner(job, out_dir, msha)
        n_done += 1
        prov = provider_fn(run_dir, job["model"])
        st, why = validate(run_dir, prov)
        tech = res.get("technical") or {}
        led["actual_usage_cost"] = round(led["actual_usage_cost"] + float(res.get("cost_usd") or 0), 6)
        led["phantom_reserve"] = round(led["phantom_reserve"] + float(tech.get("phantom_reserve_usd") or 0), 6)
        json.dump(led, open(led_p, "w"), indent=1)
        n_bad += st != "valid"
        streak = streak + 1 if st != "valid" else 0
        cls = RV.classify(run_dir) if res else {}
        rec = dict(order_index=job["order_index"], run=job["run"], model=job["model"], scenario=job["scenario"],
                   mechanism=job["mechanism"], rep=job["rep"], role=job["role"], replaces=job.get("replaces"),
                   validity=st, reasons=why, provider_statuses=sorted({p["status"] for p in prov}),
                   providers=sorted({str(p["provider"]) for p in prov}), n_calls=res.get("n_model_calls"),
                   cost_ledger=res.get("cost_usd"), cost_openrouter=round(sum(float(p.get("cost_openrouter") or 0) for p in prov), 6),
                   tokens_in=sum(int(p.get("tokens_in") or 0) for p in prov), tokens_out=sum(int(p.get("tokens_out") or 0) for p in prov),
                   wall_s=res.get("wall_s"), prompt_date=_prompt_date(run_dir),
                   preliminary=dict((k, cls.get(k)) for k in ("safety_outcome", "consistent_final_state", "finbot_compliance",
                                                             "finbot_violations", "transfers", "record_has_hold")),
                   utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), ledger=dict(led))
        open(log_p, "a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
        logged[job["run"]] = rec
        print(f"{len(logged):3d}/{len(jobs)} {job['run']}: {st}{' ' + str(why) if why else ''} | {rec['providers']} | "
              f"${res.get('cost_usd') or 0:.4f} | {cls.get('safety_outcome')} | учтено "
              f"${max(led['actual_usage_cost'], led['balance_spent']) + led['phantom_reserve']:.4f}", flush=True)
        if any(p["status"] == "confirmed_wrong_provider" for p in prov):
            stop = f"confirmed_wrong_provider в {job['run']}"
            break
        if streak >= 3:
            stop = "3 technical_invalid подряд"
            break
        if n_done >= 20 and n_bad / n_done > 0.10:
            stop = f"> 10% technical_invalid после {n_done}"
            break
    if not stub:
        led["balance_spent"] = round(led["balance_start"] - balance_fn(), 6)
        json.dump(led, open(led_p, "w"), indent=1)
    snap1 = I.snapshot_frozen()
    summary = dict(series_id=man["series_id"], manifest_sha=msha, stopped=stop, done_this_session=n_done,
                   technical_invalid_this_session=n_bad, frozen_snapshot_unchanged=(snap0 == snap1),
                   **status(manifest_path, quiet=True), ledger=led, finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    json.dump(summary, open(os.path.join(out_dir, "series_summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("ИТОГ:", json.dumps(summary, ensure_ascii=False))
    return summary


def status(manifest_path, quiet=False):
    man = json.load(open(manifest_path, encoding="utf-8"))
    log_p = os.path.join(man["out_dir"], "series_log.jsonl")
    L = [json.loads(l) for l in open(log_p, encoding="utf-8")] if os.path.exists(log_p) else []
    by = {r["run"]: r for r in L}
    ok = {j["run"] for j in man["jobs"] if by.get(j["run"], {}).get("validity") == "valid"
          or by.get(j["run"] + "__repl1", {}).get("validity") == "valid"}
    s = dict(assignments=len(man["jobs"]), logged_runs=len(L), valid_assignments=len(ok),
             technical_invalid_runs=sum(r["validity"] != "valid" for r in L),
             remaining_assignments=sum(1 for j in man["jobs"] if j["run"] not in by))
    if not quiet:
        print(json.dumps(s, ensure_ascii=False))
    return s


# ------------------------------------------------------------------ бесплатные проверки
def check():
    ok = True
    print("изоляция:", I.assert_isolated())
    snap = I.snapshot_frozen()
    print(f"слепок замороженных данных: {snap[1]} файлов, sha {snap[0][:16]}")
    models = {m["id"]: m for m in json.load(urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=30))["data"]}
    for mk, cfg in RV.MODELS.items():
        m = models.get(cfg["model"])
        ep = json.load(urllib.request.urlopen(f"https://openrouter.ai/api/v1/models/{cfg['model']}/endpoints", timeout=30))["data"]["endpoints"]
        want = cfg["provider"]["only"][0]
        e = [x for x in ep if x.get("tag") == want]
        good = bool(m) and bool(e) and "tools" in m["supported_parameters"]
        ok &= good
        print(f"{mk}: {cfg['model']} есть={bool(m)} expiration={m and m.get('expiration_date')} | эндпоинт {want}: "
              f"{[(x['provider_name'], x['pricing']['prompt'], x['pricing']['completion'], x['status']) for x in e]} | "
              f"tools={'tools' in m['supported_parameters']} temperature={'temperature' in m['supported_parameters']} | "
              f"лимит прогона ${cfg['per_run_cap']}, худший вызов ${cfg['worst_call']}")
    print("ИТОГ check:", "OK" if ok else "есть проблемы")


def selftest():
    """Без сети и затрат: учёт вызовов поверх заглушки, манифест, журнал, продолжение без дублей, замены, бюджет, стоп-правила."""
    import tempfile
    import shutil
    d = tempfile.mkdtemp(prefix="oracle_series_selftest_")
    try:
        mpath, msha = freeze("SELFTEST", "pilot", 1, ["nano", "flash"], 0.5, out_dir=os.path.join(d, "out"),
                             path=os.path.join(d, "SELFTEST.json"))
        man = json.load(open(mpath))
        print(f"манифест: {man['n_jobs']} назначений, ячеек {len(man['cells'])}, порядок: nano первым = "
              f"{man['jobs'][0]['model'] == 'nano' and man['jobs'][len(man['jobs']) // 2]['model'] == 'flash'}")
        okp = lambda rd, mk: [dict(call=json.loads(l)["call"], response_id="x", provider=RV.MODELS[mk]["expected_provider"],
                                   status="confirmed", cost_openrouter=0.0001, tokens_in=1000, tokens_out=50, latency_ms=1)
                              for l in open(os.path.join(rd, "calls.jsonl"))] if os.path.exists(os.path.join(rd, "calls.jsonl")) else []
        bal = lambda: 5.0
        small = dict(man, jobs=man["jobs"][:4])
        json.dump(small, open(mpath, "w"))
        # sha манифеста меняется — это нормально для теста; проверяем остальное
        print("== 1. ход серии на заглушке (4 назначения), учёт поверх заглушки")
        s = run_series(mpath, 0.5, stub=True, provider_fn=okp, balance_fn=bal)
        L = [json.loads(l) for l in open(os.path.join(man["out_dir"], "series_log.jsonl"))]
        rd0 = os.path.join(man["out_dir"], "runs", L[0]["run"])
        calls = [json.loads(l) for l in open(os.path.join(rd0, "calls.jsonl"))]
        print(f"   calls.jsonl: {len(calls)} вызовов, модель {set(c['model'] for c in calls)}, provider "
              f"{set(json.dumps(c['params']['extra_body']['provider']) for c in calls)}, сырые вход/выход: "
              f"{all('input' in c and 'output' in c for c in calls)}")
        print(f"   пригодны: {sum(r['validity'] == 'valid' for r in L)}/{len(L)}; предварительные исходы: "
              f"{[r['preliminary']['safety_outcome'] for r in L]}; слепок не изменился: {s['frozen_snapshot_unchanged']}")
        print("== 2. продолжение: прерванный + оставшиеся, без дублей")
        small["jobs"] = man["jobs"][:7]
        json.dump(small, open(mpath, "w"))
        os.makedirs(os.path.join(man["out_dir"], "runs", man["jobs"][4]["run"]))
        run_series(mpath, 0.5, stub=True, provider_fn=okp, balance_fn=bal)
        L = [json.loads(l) for l in open(os.path.join(man["out_dir"], "series_log.jsonl"))]
        runs = [r["run"] for r in L]
        print(f"   записей {len(L)}, дублей {len(runs) - len(set(runs))}, прерванный I1: {[r['run'] for r in L if r.get('recovered_on_resume')]}")
        print("== 3. замена по разрешению (--auto-repl 1)")
        run_series(mpath, 0.5, auto_repl=1, stub=True, provider_fn=okp, balance_fn=bal)
        L = [json.loads(l) for l in open(os.path.join(man["out_dir"], "series_log.jsonl"))]
        print(f"   замены: {[(r['run'], r['validity']) for r in L if r.get('role') == 'replacement']}")
        print("== 4. повторный запуск ничего не делает:", run_series(mpath, 0.5, auto_repl=1, stub=True, provider_fn=okp,
                                                                     balance_fn=bal)["done_this_session"] == 0)
        print("== 5. неизвестный провайдер: 3 подряд → стоп")
        small["jobs"] = man["jobs"][7:12]
        small["out_dir"] = os.path.join(d, "out2")
        json.dump(small, open(mpath, "w"))
        unk = lambda rd, mk: [dict(c, provider=None, status="provider_unknown") for c in okp(rd, mk)]
        s = run_series(mpath, 0.5, stub=True, provider_fn=unk, balance_fn=bal)
        print("   остановлено:", s["stopped"])
        print("== 6. неверный провайдер → немедленный стоп")
        small["out_dir"] = os.path.join(d, "out3")
        json.dump(small, open(mpath, "w"))
        wr = lambda rd, mk: [dict(c, provider="Other", status="confirmed_wrong_provider") for c in okp(rd, mk)]
        print("   остановлено:", run_series(mpath, 0.5, stub=True, provider_fn=wr, balance_fn=bal)["stopped"])
        print("== 7. бюджет: лимит меньше резерва → стоп до прогона")
        small["out_dir"] = os.path.join(d, "out4")
        json.dump(small, open(mpath, "w"))
        print("   остановлено:", run_series(mpath, 0.02, stub=True, provider_fn=okp, balance_fn=bal)["stopped"])
        print("== 8. прямой живой вызов без сверки манифеста отклоняется")
        rd = os.path.join(d, "direct")
        RV.prepare("K4E", rd)
        env = I.iso_env(dict(DATABASE_URL=f"sqlite:///{os.path.join(rd, 'run.db')}", OPENAI_API_KEY="x",
                             OPENAI_BASE_URL="https://example.invalid/v1", IV_MODEL_KEY="nano"))
        r = subprocess.run([sys.executable, RV.__file__, "_run", "K4E", "P0", rd, "live"], cwd=I.FINBOT_ISO, env=env,
                           capture_output=True, text=True)
        print("   отклонён:", "живой прогон только через series_iv.run_series" in (r.stdout + r.stderr))
    finally:
        shutil.rmtree(d)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "check":
        check()
    elif mode == "selftest":
        selftest()
    elif mode == "freeze":                    # freeze <series_id> <kind> <reps> <cap_usd>
        p, h = freeze(sys.argv[2], sys.argv[3], int(sys.argv[4]), ["nano", "flash"], float(sys.argv[5]))
        print("манифест:", p, "| sha", h[:16])
    elif mode == "freeze_pilot":
        p, h = freeze("OPILOT-1", "pilot", 3, ["nano", "flash"], float(sys.argv[2]))
        print("манифест:", p, "| sha", h[:16])
    elif mode == "status":
        status(sys.argv[2])
    elif mode == "run":
        n = int(sys.argv[sys.argv.index("--auto-repl") + 1]) if "--auto-repl" in sys.argv else 0
        run_series(sys.argv[2], float(sys.argv[3]), auto_repl=n)
