"""
CascadeLab LIVE-FULL-227-REC — серия ВОССТАНОВЛЕНИЯ LIVE-FULL-227 (24.11.2026).

Перезапуск ТОЛЬКО испорченных назначений LIVE-FULL-227 (агент получил сбой вызова LLM / 429 → «stalled»; или живой M3b
не ответил → error→ALLOW). Всё остальное — без изменений: те же сценарии, промпты, конфигурации C0–C3, стенд, модели,
провайдеры, fail-open M3b (`runner_live227.py` и `series_parallel.py` НЕ меняются, sha сверяется с манифестом
LIVE-FULL-227). Исходная серия и её манифест не трогаются: всё пишется в runs/LIVE-FULL-227-REC.

Изменено только правило пригодности (поверх series_parallel.validate):
  VA1  у агента «LLM call failed» (в т. ч. 429 engine_overloaded)                       → technical_invalid
  VA2  агент «stalled» при сбое вызова LLM (причина — провайдер)                        → technical_invalid
       («stalled» без сбоя LLM — поведение агента, пригоден; записывается в notes)
  VG1  живой M3b (enforce содержит M3b) не ответил: вердикт error→ALLOW                 → technical_invalid
       (поведение fail-open сохранено; такой прогон просто не засчитывается и заменяется)
Нагрузка: ≤ 2 воркера, разнос старта 10 с; после каждого прогона с 429 — общая пауза COOLDOWN_S × (подряд),
STOP при OVERLOAD_STREAK прогонах с 429 подряд или доле 429 > OVERLOAD_SHARE после OVERLOAD_MIN прогонов.
Замены: до 2 на назначение (__repl1, __repl2), всего ≤ --auto-repl.

  cd CascadeLab/iv_lab && ../../finbot-pr477/.venv/bin/python series_rec227.py <режим>
  режимы: select | selftest_rec | freeze <cap_usd> | status | run <usd> [--workers 2] [--auto-repl N]
"""
from __future__ import annotations

import csv
import json
import os
import random
import re
import sys
import tempfile
import threading
import time
from collections import Counter

LAB = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LAB)
import series_parallel as S  # noqa: E402   (не меняется)
from series_parallel import I, RR, SF, SeriesLock, _append, _read_jsonl  # noqa: E402

PARENT_ID = "LIVE-FULL-227"
PARENT_MANIFEST = os.path.join(S.MANIFESTS, f"{PARENT_ID}.json")
PARENT_SHA_PREFIX = "ccf70a652f9c3953"
SERIES_ID = "LIVE-FULL-227-REC"
MANIFEST = os.path.join(S.MANIFESTS, f"{SERIES_ID}.json")
HOOK_PORT_BASE = 8795                    # не пересекается с 8791–8794 исходной серии и с портами стенда
MAX_WORKERS = 2
MAX_REPL_PER_JOB = 2
COOLDOWN_S = 120
OVERLOAD_STREAK = 3
OVERLOAD_SHARE, OVERLOAD_MIN = 0.20, 20
SEED = "LIVE-FULL-227-REC-20261124"

ELIGIBILITY_ADDED = ["VA1 сбой вызова LLM у агента (LLM call failed, в т. ч. 429) → technical_invalid",
                     "VA2 агент stalled при сбое вызова LLM (провайдер) → technical_invalid; stalled без сбоя — пригоден, в notes",
                     "VG1 живой M3b не ответил (error→ALLOW) → technical_invalid; fail-open сохранён"]
STOP_RULES = S.STOP_RULES + [f"{OVERLOAD_STREAK} прогона с 429 подряд (общая очередь)",
                             f"доля прогонов с 429 > {int(OVERLOAD_SHARE * 100)}% после {OVERLOAD_MIN}"]

_LLM_FAIL = re.compile(r"LLM call failed")
_429 = re.compile(r"LLM call failed: [^\n]*Error code: 429")
_STALLED = re.compile(r"Agent (\w+) stalled")


# ---------------------------------------------------------------- новая пригодность
def provider_faults(run_dir):
    sp = os.path.join(run_dir, "stdout.txt")
    out = open(sp, encoding="utf-8", errors="replace").read() if os.path.exists(sp) else ""
    rp = os.path.join(run_dir, "result.json")
    res = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}
    enf = ((res.get("job") or {}).get("enforce") or "")
    live_m3b = "M3b" in enf
    g_err = sum(1 for a in res.get("p4_attempts") or [] if str((a.get("m3b_v3") or {}).get("parse", "")).startswith("error"))
    return dict(llm_fail=len(_LLM_FAIL.findall(out)), llm_429=len(_429.findall(out)), stalled=_STALLED.findall(out),
                live_m3b=live_m3b, guard_err_live=g_err if live_m3b else 0, guard_err_shadow=0 if live_m3b else g_err)


def validate_rec(run_dir, providers=None):
    st, why = S.validate(run_dir, providers)
    why = list(why); notes = []
    f = provider_faults(run_dir)
    if f["llm_fail"]:
        why.append(f"VA1 сбой вызова LLM у агента ({f['llm_fail']}, из них 429: {f['llm_429']})")
        if f["stalled"]:
            why.append(f"VA2 stalled при сбое провайдера: {sorted(set(f['stalled']))}")
    elif f["stalled"]:
        notes.append(f"stalled без сбоя LLM: {sorted(set(f['stalled']))}")
    if f["guard_err_live"]:
        why.append(f"VG1 живой M3b не ответил: error→ALLOW ({f['guard_err_live']})")
    if f["guard_err_shadow"]:
        notes.append(f"тень M3b не ответила ({f['guard_err_shadow']}) — на исход не влияет")
    if not why:
        return "valid", [], notes, f
    if all(w.startswith("P2") for w in why):
        return "pending_provider", why, notes, f
    return "technical_invalid", why, notes, f


# ---------------------------------------------------------------- выбор 318 назначений из исходной серии
def parent_used_runs():
    """Как full227_analysis.collect: по каждому назначению — первый действующий пригодный прогон (run, затем __repl1)."""
    man = json.load(open(PARENT_MANIFEST, encoding="utf-8")); out = man["out_dir"]
    L = {r["run"]: r for r in _read_jsonl(os.path.join(out, "series_log.jsonl"))}
    res = S.load_resolutions(out)
    used = {}
    for j in man["jobs"]:
        for cand in (j["run"], j["run"] + "__repl1"):
            if cand in L and S.effective(L[cand], res) == "valid":
                used[j["run"]] = cand; break
    return man, used


def select_damaged():
    man, used = parent_used_runs()
    out = man["out_dir"]; sel = []
    for j in man["jobs"]:
        u = used.get(j["run"])
        if u is None:
            sel.append(dict(job=j, used=None, reason="нет пригодного прогона")); continue
        st, why, notes, f = validate_rec(os.path.join(out, "runs", u), None)
        if st == "technical_invalid":
            reason = "agent_llm_fail" if f["llm_fail"] else "live_m3b_error" if f["guard_err_live"] else "other:" + ";".join(why)
            sel.append(dict(job=j, used=u, reason=reason, why=why, llm_429=f["llm_429"]))
    return man, used, sel


def rec_jobs(sel):
    J = []
    for s in sel:
        j = dict(s["job"])
        j.update(assignment=j["run"], run=j["run"] + "__rec1", recovers=s["used"], recover_reason=s["reason"],
                 parent_order_index=j["order_index"])
        J.append(j)
    random.Random(SEED).shuffle(J)
    for i, j in enumerate(J, 1):
        RR.validate_job(j); j["order_index"] = i
    return J


def code_hashes():
    h = S.code_hashes(); h["series_rec227"] = SF._sha(os.path.abspath(__file__))
    return h


def freeze(cap_usd, path=None, out_dir=None, sel=None):
    path = path or MANIFEST
    if os.path.exists(path):
        raise SystemExit("⛔ манифест уже существует (неизменяемый)")
    parent = json.load(open(PARENT_MANIFEST, encoding="utf-8")); psha = SF._sha(PARENT_MANIFEST)
    if not psha.startswith(PARENT_SHA_PREFIX):
        raise SystemExit("⛔ манифест LIVE-FULL-227 изменён")
    h = code_hashes()
    diff = [k for k, v in parent["sha256"].items() if h.get(k) != v]
    if diff:
        raise SystemExit(f"⛔ код/данные отличаются от LIVE-FULL-227: {diff}")
    if sel is None:
        _, _, sel = select_damaged()
    jobs = rec_jobs(sel)
    keep = {k: parent[k] for k in ("configs", "levels", "provider_rule", "conv_task", "stand", "entry", "scenarios", "scripted_fraud",
                                   "mechanisms", "models", "guard", "temperature", "prompt_date")}
    man = dict(series_id=SERIES_ID, kind="recovery", parent=dict(series_id=PARENT_ID, manifest_sha256=psha),
               frozen_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), out_dir=out_dir or os.path.join(I.RUNS, SERIES_ID),
               purpose="Восстановление LIVE-FULL-227 до 908 технически пригодных прогонов: перезапуск только испорченных назначений",
               selection=dict(rule="использованный прогон назначения в LIVE-FULL-227 не проходит новую пригодность (VA1/VA2/VG1)",
                              n=len(jobs), by_reason=dict(Counter(j["recover_reason"] for j in jobs)),
                              by_config=dict(Counter(j["config"] for j in jobs))),
               parallel=dict(max_workers=MAX_WORKERS, hook_ports=f"{HOOK_PORT_BASE}–{HOOK_PORT_BASE + MAX_WORKERS - 1}", stagger_s=10,
                             cooldown_s=COOLDOWN_S, queue="атомарный захват (fcntl.flock), как series_parallel"),
               **keep, n_jobs=len(jobs), jobs=jobs,
               budget=dict(cap_usd=cap_usd, guard="как LIVE-FULL-227: учтено + резерв (per_run_cap + worst_call) на каждый идущий прогон ≤ лимит",
                           expected_usd=round(len(jobs) * 0.0037, 2)),
               validity_rules=S.VALIDITY_RULES + ELIGIBILITY_ADDED, stop_rules=STOP_RULES, replacements=f"до {MAX_REPL_PER_JOB} на назначение",
               unchanged=["сценарии", "промпты агентов и охранника", "конфигурации C0–C3", "стенд", "модели и провайдеры", "fail-open M3b",
                          "правила Fraud", "V2 только в тени"],
               sha256=h,
               analysis_plan=dict(primary=f"{PARENT_ID} analysis_plan без изменений (full227_analysis.py, sha {parent['analysis_plan']['script_sha256'][:16]}) "
                                          "на объединённом наборе 908 (combine227.py): назначение из REC, если перезапущено, иначе из исходной серии",
                                  exploratory="deep_analysis / clean_analysis и прочее — отдельно, с пометкой «разведочно»"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(man, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return path, SF._sha(path)


# ---------------------------------------------------------------- координатор
def chain(run):
    return [run] + [f"{run}__repl{k}" for k in range(1, MAX_REPL_PER_JOB + 1)]


def assignment_state(jobs, L, res):
    """По назначению: valid / pending / invalid(исчерпано) / open."""
    out = {}
    for j in jobs:
        effs = [S.effective(L[r], res) if r in L else None for r in chain(j["run"])]
        out[j["run"]] = ("valid" if "valid" in effs else "pending" if "pending_provider" in effs else
                         "open" if None in effs or not any(effs) else "invalid")
    return out


class RecCoordinator(S.Coordinator):
    def __init__(self, manifest_path, approved_usd, workers=2, auto_repl=0, stub=False, provider_fn=None, balance_fn=None,
                 stub_behavior="", wait_s=S.RESOLVE_WAIT_S, max_jobs=None, stub_env=None, cooldown_s=COOLDOWN_S, stagger_s=10,
                 fault_fn=None):
        assert 1 <= workers <= MAX_WORKERS, "воркеров 1–2"
        S.Coordinator.__init__(self, manifest_path, approved_usd, workers=workers, auto_repl=auto_repl, stub=stub, provider_fn=provider_fn,
                               balance_fn=balance_fn, stub_behavior=stub_behavior, wait_s=wait_s, max_jobs=max_jobs, stub_env=stub_env)
        self.overload_p = os.path.join(self.out, "overload.json")
        self.cooldown_s, self.stagger_s, self.fault_fn = cooldown_s, stagger_s, fault_fn

    def init(self):
        if not self.stub:
            bad = [k for k, v in code_hashes().items() if v != self.man["sha256"][k]]
            if bad:
                raise SystemExit(f"⛔ расхождение с манифестом: {bad}")
            if not SF._sha(PARENT_MANIFEST).startswith(PARENT_SHA_PREFIX):
                raise SystemExit("⛔ манифест LIVE-FULL-227 изменён")
        if self.approved > self.man["budget"]["cap_usd"] + 1e-9:
            raise SystemExit(f"⛔ лимит ${self.approved} больше cap ${self.man['budget']['cap_usd']}")
        ports = [HOOK_PORT_BASE + k for k in range(self.workers)]
        assert all(p not in (I.HOOK_PORT_ISO, I.FORBIDDEN_PORT) and I._port_free(p) for p in ports), f"порты трасс заняты: {ports}"
        self.parent_snap = self._parent_snapshot()
        self.snap0, self.db0 = I.snapshot_frozen(), SF._sha(I.DB_ISO)
        with SeriesLock(self.out):
            if not os.path.exists(self.led_p):
                json.dump(dict(actual_usage_cost=0.0, phantom_reserve=0.0, balance_start=round(self.balance_fn(), 6), balance_spent=0.0),
                          open(self.led_p, "w"), indent=1)
            if not os.path.exists(self.overload_p):
                json.dump(dict(streak=0, cooldown_until=0.0, n_runs=0, n_429=0), open(self.overload_p, "w"), indent=1)
            logged = {r["run"] for r in _read_jsonl(self.log_p)}
            infl = self._inflight(); led = self._ledger()
            for c in _read_jsonl(self.claims_p):
                if c["run"] not in logged and not (S._pid_alive(c["pid"]) and c["pid"] != os.getpid()):
                    _append(self.log_p, dict(run=c["run"], validity="technical_invalid", reasons=["I1 прерван: захвачен, записи нет"],
                                             recovered_on_resume=True, role=c.get("role"), worker=c.get("worker"),
                                             utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
                    led["phantom_reserve"] = round(led["phantom_reserve"] + self.reserve, 6); logged.add(c["run"])
                    infl.pop(c["run"], None)
            json.dump(led, open(self.led_p, "w"), indent=1); json.dump(infl, open(self.inflight_p, "w"), indent=1)
        old_p2 = [r["run"] for r in _read_jsonl(self.log_p) if r.get("validity") == "pending_provider"]
        if old_p2:
            S.resolve(self.out, old_p2, self.provider_fn, wait_s=0)

    def _parent_snapshot(self):
        p = json.load(open(PARENT_MANIFEST, encoding="utf-8"))["out_dir"]
        return {f: SF._sha(os.path.join(p, f)) for f in ("series_log.jsonl", "claims.jsonl", "ledger.json", "provider_resolution.jsonl",
                                                         "series_summary.json") if os.path.exists(os.path.join(p, f))}

    def claim(self, worker):
        while True:
            with SeriesLock(self.out):
                if os.path.exists(self.stop_p):
                    return None, "STOP"
                ov = json.load(open(self.overload_p))
                wait = ov["cooldown_until"] - time.time()
                if wait <= 0:
                    break
            time.sleep(min(wait, 5))
        with SeriesLock(self.out):
            if os.path.exists(self.stop_p):
                return None, "STOP"
            L = {r["run"]: r for r in _read_jsonl(self.log_p)}
            claimed = {c["run"] for c in _read_jsonl(self.claims_p)}
            led, infl = self._ledger(), self._inflight()
            committed = self._committed(led, infl)
            if committed + self.reserve > self.approved:
                return None, f"бюджет: учтено ${committed:.4f} (в т. ч. в работе {len(infl)}) + резерв ${self.reserve:.4f} > ${self.approved}"
            job = next((j for j in self.jobs if j["run"] not in L and j["run"] not in claimed), None)
            if job is None and self.auto_repl:
                res = S.load_resolutions(self.out)
                used = sum(1 for c in _read_jsonl(self.claims_p) if c.get("role") == "replacement")
                if used < self.auto_repl:
                    for j in self.jobs:
                        ch = chain(j["run"]); effs = [S.effective(L[r], res) if r in L else None for r in ch]
                        if "valid" in effs or "pending_provider" in effs:
                            continue
                        k = next((i for i, r in enumerate(ch) if r not in L and r not in claimed), None)
                        if k is None or k == 0 or any(ch[i] not in L for i in range(k)):
                            continue                         # цепочка исчерпана, либо предыдущий ещё идёт
                        job = dict(j, run=ch[k], role="replacement", replaces=ch[k - 1]); break
            if job is None:
                return None, "очередь пуста"
            _append(self.claims_p, dict(run=job["run"], worker=worker, pid=os.getpid(), role=job.get("role"),
                                        utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
            infl[job["run"]] = dict(worker=worker, reserve=self.reserve, utc=time.time())
            json.dump(infl, open(self.inflight_p, "w"), indent=1)
            self.peak_inflight = max(self.peak_inflight, len(infl)); self.peak_committed = max(self.peak_committed, committed + self.reserve)
            return job, None

    def complete(self, worker, job, rd, rj, prov, st, why, notes=(), faults=None):
        faults = faults or {}
        with SeriesLock(self.out):
            led, infl = self._ledger(), self._inflight()
            infl.pop(job["run"], None)
            if not rj:
                led["phantom_reserve"] = round(led["phantom_reserve"] + self.reserve, 6)
            led["actual_usage_cost"] = round(led["actual_usage_cost"] + float(rj.get("cost_usd") or 0), 6)
            led["phantom_reserve"] = round(led["phantom_reserve"] + float((rj.get("technical") or {}).get("phantom_reserve_usd") or 0), 6)
            json.dump(led, open(self.led_p, "w"), indent=1); json.dump(infl, open(self.inflight_p, "w"), indent=1)
            cls = RR.classify(rd) if rj else {}
            rec = dict(order_index=job["order_index"], run=job["run"], assignment=job["assignment"], recovers=job["recovers"],
                       recover_reason=job["recover_reason"], config=job.get("config"), scenario=job["scenario"], M1=job["M1"], M2=job["M2"],
                       enforce=job["enforce"], role=job.get("role", "new"), replaces=job.get("replaces"), worker=worker,
                       hook_port=HOOK_PORT_BASE + worker, validity=st, reasons=why, notes=list(notes),
                       faults={k: v for k, v in faults.items() if k != "stalled"}, stalled=sorted(set(faults.get("stalled") or [])),
                       providers=sorted({str(p["provider"]) for p in prov}), n_calls=rj.get("n_model_calls"),
                       cost_agents=rj.get("cost_agents_usd"), cost_guard=(rj.get("guard_stats") or {}).get("cost"), cost_usd=rj.get("cost_usd"),
                       cost_openrouter=round(sum(float(p.get("cost_openrouter") or 0) for p in prov), 6), tokens=rj.get("tokens"),
                       preliminary={k: cls.get(k) for k in ("outcome", "first_stop", "m1_triggered", "m1_outcome", "m2_applied", "hold_attempts",
                                                            "shadow_m3a", "shadow_m3b_v3", "shadow_m3b_v2", "blocked_attempts")},
                       series_version="rec227 v1", utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), ledger=dict(led))
            _append(self.log_p, rec)
            # перегрузка провайдера: общая пауза и стоп
            ov = json.load(open(self.overload_p)); ov["n_runs"] += 1
            if faults.get("llm_429"):
                ov["n_429"] += 1; ov["streak"] += 1; ov["cooldown_until"] = time.time() + self.cooldown_s * ov["streak"]
            elif st == "valid":
                ov["streak"] = 0
            json.dump(ov, open(self.overload_p, "w"), indent=1)
            hard = st == "technical_invalid"
            self.streak[worker] = self.streak.get(worker, 0) + 1 if hard else (0 if st == "valid" else self.streak.get(worker, 0))
            Ls = _read_jsonl(self.log_p); nb = sum(r["validity"] == "technical_invalid" for r in Ls)
            stop = (f"confirmed_wrong_provider в {job['run']}" if any(p["status"] == "confirmed_wrong_provider" for p in prov) else
                    f"{why} в {job['run']}" if any(w.startswith(("VR5", "PG1")) for w in why) else
                    f"перегрузка: {ov['streak']} прогона с 429 подряд" if ov["streak"] >= OVERLOAD_STREAK else
                    f"перегрузка: 429 в {ov['n_429']}/{ov['n_runs']}" if ov["n_runs"] >= OVERLOAD_MIN and ov["n_429"] / ov["n_runs"] > OVERLOAD_SHARE else
                    f"3 technical_invalid подряд у воркера {worker}" if self.streak[worker] >= 3 else
                    f"> 10% technical_invalid после {len(Ls)}" if len(Ls) >= 40 and nb / len(Ls) > 0.10 else None)
            if stop and not os.path.exists(self.stop_p):
                open(self.stop_p, "w").write(stop)
            print(f"[w{worker}] {len(Ls):4d}/{len(self.jobs)} {job['run']}: {st}{' ' + str(why) if why else ''} | ${rj.get('cost_usd') or 0:.4f} | "
                  f"{rec['preliminary'].get('outcome')} {rec['preliminary'].get('first_stop')}", flush=True)

    def worker(self, k):
        port = HOOK_PORT_BASE + k
        time.sleep(self.stagger_s * k)
        while True:
            job, why_none = self.claim(k)
            if job is None:
                return why_none
            rd = os.path.join(self.out, "runs", job["run"])
            if self.stub:
                RR.run_stub(job, os.path.join(self.out, "runs"), self.stub_behavior, run_name=job["run"], hook_port=port, extra_env=self.stub_env)
                if self.fault_fn:
                    self.fault_fn(job, rd)
            else:
                self._run_live(job, rd, port)
            rp = os.path.join(rd, "result.json")
            rj = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}
            prov = self.provider_fn(rd, job["model"])
            st, why, notes, faults = validate_rec(rd, prov)
            self.complete(k, job, rd, rj, prov, st, why, notes, faults)

    def run(self):
        self.init()
        reasons = []
        for rnd in range(MAX_REPL_PER_JOB + 2):
            if os.path.exists(self.stop_p):
                break
            th = [threading.Thread(target=lambda k=k: reasons.append(self.worker(k)), daemon=True) for k in range(self.workers)]
            [t.start() for t in th]
            while any(t.is_alive() for t in th):
                time.sleep(2)
                if not self.stub and int(time.time()) % 300 < 2:
                    b = self.balance_fn()
                    with SeriesLock(self.out):
                        led = self._ledger(); led["balance_spent"] = round(led["balance_start"] - b, 6); json.dump(led, open(self.led_p, "w"), indent=1)
            pend = [r["run"] for r in _read_jsonl(self.log_p) if r.get("validity") == "pending_provider"]
            if pend:
                S.resolve(self.out, pend, self.provider_fn, wait_s=self.wait_s)
            st = assignment_state(self.jobs, {r["run"]: r for r in _read_jsonl(self.log_p)}, S.load_resolutions(self.out))
            if not self.auto_repl or all(v in ("valid", "invalid") for v in st.values()):
                if all(v != "open" for v in st.values()):
                    break
        if not self.stub:
            b = self.balance_fn()
            with SeriesLock(self.out):
                led = self._ledger(); led["balance_spent"] = round(led["balance_start"] - b, 6); json.dump(led, open(self.led_p, "w"), indent=1)
        summary = self.summary(reasons)
        json.dump(summary, open(os.path.join(self.out, "series_summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("ИТОГ:", json.dumps(summary, ensure_ascii=False))
        return summary

    def summary(self, reasons=()):
        L = _read_jsonl(self.log_p); res = S.load_resolutions(self.out)
        st = assignment_state(self.jobs, {r["run"]: r for r in L}, res)
        return dict(series_id=self.man["series_id"], manifest_sha=self.msha, workers=self.workers,
                    stopped=open(self.stop_p).read() if os.path.exists(self.stop_p) else None, worker_exit=list(reasons),
                    peak_inflight=self.peak_inflight, peak_committed_usd=round(self.peak_committed, 6),
                    duplicates=len(L) - len({r["run"] for r in L}), assignments=len(self.jobs), assignment_state=dict(Counter(st.values())),
                    logged_runs=len(L), validity=dict(Counter(r["validity"] for r in L)),
                    reasons=dict(Counter(w.split(" ")[0] for r in L for w in r.get("reasons") or [])),
                    replacements=sum(1 for r in L if r.get("role") == "replacement"), provider_resolutions=len(res),
                    overload=json.load(open(self.overload_p)) if os.path.exists(self.overload_p) else None,
                    frozen_snapshot_unchanged=(self.snap0 == I.snapshot_frozen()) if hasattr(self, "snap0") else None,
                    db_iso_unchanged=(self.db0 == SF._sha(I.DB_ISO)) if hasattr(self, "db0") else None,
                    parent_unchanged=(self.parent_snap == self._parent_snapshot()) if hasattr(self, "parent_snap") else None, ledger=self._ledger(),
                    finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


# ---------------------------------------------------------------- selftest (без сети и затрат)
def selftest_rec():
    d = tempfile.mkdtemp(prefix="lf227rec_")
    R, ok = [], True

    def chk(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond); R.append((("OK  " if cond else "FAIL") + " " + name, detail))
    fake = lambda rd, mk: [dict(status="confirmed", provider="DeepInfra", model_served="m", cost_openrouter=0.0, tokens_in=1, tokens_out=1)]
    try:
        psha = SF._sha(PARENT_MANIFEST)
        parent = json.load(open(PARENT_MANIFEST, encoding="utf-8"))
        h = code_hashes()
        chk("R0 LIVE-FULL-227: манифест не изменён; runner_live227, series_parallel, сценарии, промпты, стенд, БД совпадают с его sha",
            psha.startswith(PARENT_SHA_PREFIX) and all(h.get(k) == v for k, v in parent["sha256"].items()),
            str([k for k, v in parent["sha256"].items() if h.get(k) != v]))
        man, used, sel = select_damaged()
        bc = Counter(s["reason"] for s in sel)
        # сверка с независимым разбором после серии (analysis/LIVE-FULL-227/llm_failures.csv + deep_runs.csv)
        A = os.path.join(LAB, "analysis", PARENT_ID)
        fails = {r["run"] for r in csv.DictReader(open(os.path.join(A, "llm_failures.csv"), encoding="utf-8-sig")) if int(r["llm_fail"]) > 0}
        gerr = {r["run"] for r in csv.DictReader(open(os.path.join(A, "deep_runs.csv"), encoding="utf-8-sig"))
                if r["config"] in ("C1", "C3") and r["guard_error"] == "True"} - fails
        mine = {s["used"] for s in sel}
        chk("R1 список: 908 назначений имеют пригодный прогон; новая пригодность отбрасывает ровно 318 = 301 (сбой LLM агента) + 17 (живой M3b)",
            len(used) == 908 and len(sel) == 318 and bc == {"agent_llm_fail": 301, "live_m3b_error": 17}, str(dict(bc)))
        chk("R2 список совпадает с независимым разбором (llm_failures.csv ∪ ошибки живого M3b) поштучно",
            mine == fails | gerr and len(fails) == 301 and len(gerr) == 17, f"Δ {len(mine ^ (fails | gerr))}")
        cfgc = Counter(s["job"]["config"] for s in sel)
        chk("R3 распределение по конфигурациям: C0 87, C1 87, C2 76, C3 68; 17 VG1 только в C1/C3",
            cfgc == {"C0": 87, "C1": 87, "C2": 76, "C3": 68} and all(s["job"]["config"] in ("C1", "C3") for s in sel if s["reason"] == "live_m3b_error"),
            str(dict(cfgc)))
        ok_rest = all(validate_rec(os.path.join(man["out_dir"], "runs", u), None)[0] == "valid" for a, u in used.items() if u not in mine)
        chk("R4 остальные 590 использованных прогонов проходят новую пригодность (без провайдерской проверки)", ok_rest)
        J = rec_jobs(sel)
        pj = {j["run"]: j for j in parent["jobs"]}
        same = all({k: j[k] for k in ("block", "scenario", "fraud", "handoff", "config", "M1", "M2", "enforce", "model", "rep")} ==
                   {k: pj[j["assignment"]][k] for k in ("block", "scenario", "fraud", "handoff", "config", "M1", "M2", "enforce", "model", "rep")} for j in J)
        chk("R5 задания восстановления: 318 уникальных, по одному на назначение; параметры совпадают с исходными; имена __rec1 не пересекаются с исходной серией",
            len(J) == 318 and len({j["run"] for j in J}) == 318 and len({j["assignment"] for j in J}) == 318 and same
            and not ({j["run"] for j in J} & {r["run"] for r in _read_jsonl(os.path.join(man["out_dir"], "series_log.jsonl"))}))
        # прогоны на заглушках
        mp, _ = freeze(2.0, path=os.path.join(d, "M.json"), out_dir=os.path.join(d, "series"), sel=sel)
        m = json.load(open(mp)); m["jobs"] = m["jobs"][:16]; json.dump(m, open(mp, "w"))
        snap_parent = None
        co = RecCoordinator(mp, 2.0, workers=2, auto_repl=4, stub=True, provider_fn=fake, balance_fn=lambda: 10.0, wait_s=0,
                            stub_behavior="orch_neutral+fraud_clean+pay_always", cooldown_s=0, stagger_s=0)
        s = co.run(); L = _read_jsonl(os.path.join(d, "series", "series_log.jsonl"))
        chk("R6 2 воркера, 16 заданий: каждое ровно один раз, все пригодны, порты 8795/8796, дублей 0, исходная серия не изменилась",
            len(L) == 16 and s["duplicates"] == 0 and s["assignment_state"] == {"valid": 16} and {r["hook_port"] for r in L} <= {8795, 8796}
            and {r["worker"] for r in L} == {0, 1} and s["parent_unchanged"], json.dumps(s["assignment_state"]))
        # подложенные сбои: 429 у агента, stalled, ошибка живого M3b, тень M3b, stalled без сбоя
        d2 = os.path.join(d, "f"); os.makedirs(d2); mp2 = os.path.join(d2, "M.json")
        jobs = json.load(open(os.path.join(d, "M.json")))["jobs"]
        live = [j for j in jobs if "M3b" in (j["enforce"] or "")][:1]; shadow = [j for j in jobs if "M3b" not in (j["enforce"] or "")][:3]
        pick = live + shadow
        m2 = dict(m, out_dir=os.path.join(d2, "series"), jobs=pick); json.dump(m2, open(mp2, "w"))
        plan = {pick[0]["run"]: "guard", pick[1]["run"]: "429", pick[2]["run"]: "shadow_guard", pick[3]["run"]: "stalled_natural"}
        LINE429 = ("LLM call failed: OpenAI chat failed: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429}}\n"
                   "Agent orchestrator_agent stalled: 2 consecutive text-only iterations\n")

        def inject(job, rd):
            kind = plan.get(job["run"]) if not job["run"].endswith(("__repl1", "__repl2")) else None
            if kind == "429":
                open(os.path.join(rd, "stdout.txt"), "a").write(LINE429)
            elif kind == "stalled_natural":
                open(os.path.join(rd, "stdout.txt"), "a").write("Agent orchestrator_agent stalled: 2 consecutive text-only iterations\n")
            elif kind in ("guard", "shadow_guard"):
                rp = os.path.join(rd, "result.json"); r = json.load(open(rp))
                if not r["p4_attempts"]:
                    r["p4_attempts"] = [dict(attempt=1, m3a="ALLOW", m3b_v3=dict(decision="ALLOW"), m3b_v2=dict(decision="ALLOW"), blocked_by=None, executed=True)]
                for a in r["p4_attempts"]:
                    a["m3b_v3"] = dict(decision="ALLOW", parsed=False, parse="error→ALLOW", reason=None, cost=0.0, provider=None)
                json.dump(r, open(rp, "w"))
        s2 = RecCoordinator(mp2, 2.0, workers=2, auto_repl=4, stub=True, provider_fn=fake, balance_fn=lambda: 10.0, wait_s=0,
                            stub_behavior="orch_neutral+fraud_clean+pay_always", cooldown_s=0, stagger_s=0, fault_fn=inject).run()
        L2 = {r["run"]: r for r in _read_jsonl(os.path.join(d2, "series", "series_log.jsonl"))}
        rk = lambda run: [w.split(" ")[0] for w in L2[run]["reasons"]]
        chk("R7 пригодность: 429 → VA1+VA2; ошибка живого M3b → VG1; оба technical_invalid и заменены __repl1 (пригодны); "
            "тень M3b с ошибкой и stalled без сбоя — пригодны, отмечены в notes",
            rk(pick[1]["run"]) == ["VA1", "VA2"] and rk(pick[0]["run"]) == ["VG1"]
            and L2[pick[1]["run"]]["validity"] == L2[pick[0]["run"]]["validity"] == "technical_invalid"
            and L2.get(pick[1]["run"] + "__repl1", {}).get("validity") == "valid" and L2.get(pick[0]["run"] + "__repl1", {}).get("validity") == "valid"
            and L2[pick[2]["run"]]["validity"] == "valid" and L2[pick[2]["run"]]["notes"] and L2[pick[3]["run"]]["validity"] == "valid"
            and L2[pick[3]["run"]]["notes"] and s2["assignment_state"] == {"valid": 4}, json.dumps({k: (v["validity"], v["reasons"]) for k, v in L2.items()}, ensure_ascii=False)[:600])
        # повторяющаяся перегрузка → общий STOP; пауза после 429
        d3 = os.path.join(d, "o"); os.makedirs(d3); mp3 = os.path.join(d3, "M.json")
        m3 = dict(m, out_dir=os.path.join(d3, "series"), jobs=jobs[:16]); json.dump(m3, open(mp3, "w"))
        all429 = lambda job, rd: open(os.path.join(rd, "stdout.txt"), "a").write(LINE429)
        t0 = time.time()
        s3 = RecCoordinator(mp3, 2.0, workers=2, auto_repl=10, stub=True, provider_fn=fake, balance_fn=lambda: 10.0, wait_s=0,
                            stub_behavior="orch_neutral+fraud_clean+pay_always", cooldown_s=1, stagger_s=0, fault_fn=all429).run()
        L3 = _read_jsonl(os.path.join(d3, "series", "series_log.jsonl"))
        chk(f"R8 перегрузка: 429 в каждом прогоне → STOP после {OVERLOAD_STREAK} подряд (± прогон в работе), новые задания не берутся; пауза после 429 соблюдена",
            s3["stopped"] and "перегрузка" in s3["stopped"] and len(L3) <= OVERLOAD_STREAK + 1 and time.time() - t0 >= 1 + 2,
            f"{s3['stopped']}; записей {len(L3)}; {time.time() - t0:.1f} с")
        # лимит замен: 2 на назначение, затем назначение «invalid», серия не зацикливается
        d4 = os.path.join(d, "x"); os.makedirs(d4); mp4 = os.path.join(d4, "M.json")
        m4 = dict(m, out_dir=os.path.join(d4, "series"), jobs=live[:1]); json.dump(m4, open(mp4, "w"))
        def always_guard(job, rd):                      # ошибка живого M3b в каждом прогоне цепочки, включая замены
            rp = os.path.join(rd, "result.json"); r = json.load(open(rp))
            r["p4_attempts"] = r["p4_attempts"] or [dict(attempt=1, m3a="ALLOW", m3b_v2=dict(decision="ALLOW"), blocked_by=None, executed=True)]
            for a in r["p4_attempts"]:
                a["m3b_v3"] = dict(decision="ALLOW", parsed=False, parse="error→ALLOW", reason=None, cost=0.0, provider=None)
            json.dump(r, open(rp, "w"))
        s4 = RecCoordinator(mp4, 2.0, workers=1, auto_repl=10, stub=True, provider_fn=fake, balance_fn=lambda: 10.0, wait_s=0,
                            stub_behavior="orch_neutral+fraud_clean+pay_always", cooldown_s=0, stagger_s=0, fault_fn=always_guard).run()
        L4 = _read_jsonl(os.path.join(d4, "series", "series_log.jsonl"))
        chk(f"R9 замены ограничены: {MAX_REPL_PER_JOB} на назначение (всего 3 прогона), затем назначение исчерпано; без дублей",
            len(L4) <= 1 + MAX_REPL_PER_JOB and [r["run"] for r in L4][:1] == [live[0]["run"]] and s4["duplicates"] == 0
            and (s4["assignment_state"] == {"invalid": 1} or s4["stopped"]), f"{[r['run'][-8:] for r in L4]} {s4['assignment_state']} {s4['stopped']}")
        # бюджет: единый, с резервом на идущие
        d5 = os.path.join(d, "b"); os.makedirs(d5); mp5 = os.path.join(d5, "M.json")
        m5 = dict(m, out_dir=os.path.join(d5, "series"), jobs=jobs[:16]); m5["budget"] = dict(m5["budget"], cap_usd=0.20); json.dump(m5, open(mp5, "w"))
        s5 = RecCoordinator(mp5, 0.20, workers=2, stub=True, provider_fn=fake, balance_fn=lambda: 10.0, wait_s=0,
                            stub_behavior="orch_neutral+fraud_clean+pay_always", stub_env=dict(RC_STUB_COST="0.001"), cooldown_s=0, stagger_s=0).run()
        chk("R10 единый бюджет: учтено + резерв на идущие ≤ $0,20 всё время; серия остановлена бюджетом",
            s5["ledger"]["actual_usage_cost"] <= 0.20 and s5["peak_committed_usd"] <= 0.20 + 1e-9 and any(str(x).startswith("бюджет") for x in s5["worker_exit"]),
            f"потрачено ${s5['ledger']['actual_usage_cost']:.4f}, пик ${s5['peak_committed_usd']:.4f}")
        # восстановление после сбоя координатора
        d6 = os.path.join(d, "r"); os.makedirs(os.path.join(d6, "series", "runs")); mp6 = os.path.join(d6, "M.json")
        m6 = dict(m, out_dir=os.path.join(d6, "series"), jobs=jobs[:4]); json.dump(m6, open(mp6, "w"))
        _append(os.path.join(d6, "series", "claims.jsonl"), dict(run=jobs[0]["run"], worker=0, pid=999999, role="new", utc="x"))
        s6 = RecCoordinator(mp6, 2.0, workers=2, auto_repl=2, stub=True, provider_fn=fake, balance_fn=lambda: 10.0, wait_s=0,
                            stub_behavior="orch_neutral+fraud_clean+pay_always", cooldown_s=0, stagger_s=0).run()
        L6 = _read_jsonl(os.path.join(d6, "series", "series_log.jsonl"))
        chk("R11 восстановление: захват без записи → I1 + резерв; заменён __repl1; не повторён; все 4 назначения пригодны",
            any(r["run"] == jobs[0]["run"] and r["reasons"][0].startswith("I1") for r in L6) and s6["assignment_state"] == {"valid": 4}
            and s6["duplicates"] == 0)
        FZ = {"LR-PILOT-1": "774689e63efbf52d", "LR-PILOT-2": "0fb67b95e221be11", "LR-L3B-1": "0f6f21fb9549c0bf", "LR-L3B-2": "16a4ec8cacb019eb",
              "LIVE-FULL-1": "c2a31dd8631ed36c", "LIVE-FULL-227": PARENT_SHA_PREFIX}
        chk("R12 замороженные манифесты не изменены (вкл. LIVE-FULL-227); LR-L3B-2 не возобновлялась",
            all(SF._sha(os.path.join(S.MANIFESTS, f"{k}.json")).startswith(v) for k, v in FZ.items())
            and len(_read_jsonl(os.path.join(LAB, "runs", "LR-L3B-2", "series_log.jsonl"))) == 10)
    except Exception as ex:
        import traceback
        ok = False; R.append(("FAIL исключение", f"{ex}\n{traceback.format_exc()[-2000:]}"))
    finally:
        print("\n".join(f"{a}  {b}" for a, b in R)); print("SELFTEST REC:", "OK" if ok else "FAIL", "| папка:", d)
    return ok


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "help"
    if mode == "select":
        man, used, sel = select_damaged()
        print(len(used), len(sel), dict(Counter(s["reason"] for s in sel)), dict(Counter(s["job"]["config"] for s in sel)))
    elif mode == "selftest_rec":
        sys.exit(0 if selftest_rec() else 1)
    elif mode == "freeze":
        print(freeze(float(sys.argv[2])))
    elif mode == "status":
        print(json.dumps(RecCoordinator(MANIFEST, 0.0, workers=1, stub=True).summary(), ensure_ascii=False, indent=1))
    elif mode == "run":
        a = sys.argv[3:]
        w = int(a[a.index("--workers") + 1]) if "--workers" in a else 2
        repl = int(a[a.index("--auto-repl") + 1]) if "--auto-repl" in a else 0
        RecCoordinator(MANIFEST, float(sys.argv[2]), workers=w, auto_repl=repl).run()
    else:
        print(__doc__)
