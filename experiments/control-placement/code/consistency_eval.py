"""
Сравнение УРОВНЕЙ контроля (главный вопрос проекта) на записанных живых трейсах.

Механизмы x уровни:
  rules  — правила-сверки, каждое на тех уровнях, где ему хватает видимости (consistency_check.RULE_LEVELS);
  llm    — LLM-проверка согласованности (consistency_check.CONSISTENCY_PROMPT), один промпт на всех уровнях;
  уровни — boundary (после каждого бота, обрыв на первой сработавшей границе), orchestrator, final.

Берём трейсы, которые шли в оплату (Approval = approve): только там проверка что-то решает.
Вредные — деньги ушли зря (естественные каскады и подложенные ошибки); честные — контроль для FPR.
Не больше CAP трейсов на сценарий, чтобы повторы одного счёта не раздували выборку.

Метрики: поймано (по трейсам и по сценариям), ложные остановки честных, вызовы модели на трейс,
добавочная задержка, сэкономленная задержка при раннем обрыве, поймано по месту рождения ошибки.
Сохраняет runs/consistency_<дата>.json и дописывает строки в runs/results_log.csv.

ПЛАТНО. Сначала:  .venv/bin/python code/consistency_eval.py --dry   (покажет объём и цену)
Потом:            .venv/bin/python code/consistency_eval.py
"""
from __future__ import annotations
import argparse
import csv
import glob
import json
import math
import os
import time
from collections import defaultdict

import consistency_check as cc
from guardrail_compare import LOG, LOG_FIELDS
from llm_guardrail import Guard, MODEL

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = {"stand_live_20260926_141935.json", "stand_live_20260926_142318.json"}  # артефактный и пробный
CAP = 3
BUDGET = 0.25
EST_CALL_USD = 0.00018          # оценка: ~1000 токенов на вход, ~60 на выход


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def fmt(k, n):
    if not n:
        return "—"
    lo, hi = wilson(k, n)
    return f"{k}/{n} {k / n:.0%} [{lo:.0%}–{hi:.0%}]"


def load_traces():
    per_scenario = defaultdict(list)
    for path in sorted(glob.glob(os.path.join(HERE, "runs", "stand_live_*.json"))):
        if os.path.basename(path) in SKIP:
            continue
        for r in json.load(open(path)):
            if r["fallback_agents"] or r["llm_errors"] or "approval" not in r["responses"]:
                continue
            appr = next((s for s in r["trace"]["steps"] if s["agent"] == "Approval"), None)
            if not (appr and appr["success"] and appr["data"].get("decision") == "approve"):
                continue
            if r["group"] not in ("cascade", "control"):
                continue
            r["_file"] = os.path.basename(path)
            r["_origin"] = (r.get("fault_step") or "natural") if r["group"] == "cascade" else "-"
            if r["group"] == "cascade" and not r.get("fault_applied"):
                r["_origin"] = "natural"
            per_scenario[(r["_file"], r["id"])].append(r)
    return [r for rs in per_scenario.values() for r in rs[:CAP]]


def agent_latency_after(r, edge):
    order = ["Validator", "RiskAnalyzer", "Approval"]
    later = order[order.index(cc.EDGE_AGENT[edge]) + 1:]
    return sum(s["latency_s"] for s in r["trace"]["steps"] if s["agent"] in later)


def evaluate(r, guard):
    out = {}
    # boundary: по порядку, обрыв на первой сработавшей границе
    calls, lat, stop_edge, reason = 0, 0.0, None, None
    for edge in cc.EDGES:
        if edge not in r["responses"]:
            continue
        v = guard.check(cc.boundary_context(r, edge), prompt=cc.CONSISTENCY_PROMPT, budget=BUDGET)
        calls, lat = calls + 1, lat + v["latency_s"]
        if v["block"]:
            stop_edge, reason = edge, v["reason"]
            break
    out["llm_boundary"] = dict(block=stop_edge is not None, edge=stop_edge, calls=calls, latency=lat,
                               saved=agent_latency_after(r, stop_edge) if stop_edge else 0.0, reason=reason)
    for level, ctx in (("orchestrator", cc.orchestrator_context(r)), ("final", cc.final_context(r))):
        v = guard.check(ctx, prompt=cc.CONSISTENCY_PROMPT, budget=BUDGET)
        out[f"llm_{level}"] = dict(block=v["block"], edge=None, calls=1, latency=v["latency_s"],
                                   saved=0.0, reason=v["reason"])
    edge = cc.rules_boundary_edge(r)
    out["rules_boundary"] = dict(block=edge is not None, edge=edge, calls=0, latency=0.0,
                                 saved=agent_latency_after(r, edge) if edge else 0.0,
                                 reason=",".join(cc.rules_at(r, "boundary")) or None)
    for level in ("orchestrator", "final"):
        fired = cc.rules_at(r, level)
        out[f"rules_{level}"] = dict(block=bool(fired), edge=None, calls=0, latency=0.0, saved=0.0,
                                     reason=",".join(fired) or None)
    return out


VARIANTS = ["rules_boundary", "rules_orchestrator", "rules_final",
            "llm_boundary", "llm_orchestrator", "llm_final"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="только посчитать объём и цену, без вызовов")
    args = ap.parse_args()

    traces = load_traces()
    harm = [r for r in traces if r["group"] == "cascade"]
    hon = [r for r in traces if r["group"] == "control"]
    max_calls = sum(len([e for e in cc.EDGES if e in r["responses"]]) + 2 for r in traces)
    print(f"Трейсов в оплату: {len(traces)} (вредных {len(harm)}, честных {len(hon)}); "
          f"по месту рождения ошибки: {dict(sorted(defaultdict(int, {o: sum(r['_origin'] == o for r in harm) for o in {r['_origin'] for r in harm}}).items()))}")
    print(f"Вызовов модели не больше {max_calls}, цена не больше ~${max_calls * EST_CALL_USD:.2f} (предел ${BUDGET})")
    if args.dry:
        return

    guard = Guard()
    for i, r in enumerate(traces, 1):
        r["_v"] = evaluate(r, guard)
        if i % 20 == 0:
            print(f"  проверено {i}/{len(traces)}, потрачено ${guard.spent:.3f}", flush=True)

    scen = lambda rs: {(r["_file"], r["id"]) for r in rs}
    print(f"\n{'вариант':<20}{'поймано (трейсы)':<26}{'поймано (сценарии, всегда)':<28}"
          f"{'ложные: честные сценарии':<26}{'вызовов/трейс':<14}{'+задержка, с':<13}{'сэконом., с'}")
    summary = {}
    for var in VARIANTS:
        tp = sum(r["_v"][var]["block"] for r in harm)
        hs = scen(harm)
        caught_always = sum(all(r["_v"][var]["block"] for r in harm if (r["_file"], r["id"]) == s) for s in hs)
        hns = scen(hon)
        fp_sc = sum(any(r["_v"][var]["block"] for r in hon if (r["_file"], r["id"]) == s) for s in hns)
        calls = sum(r["_v"][var]["calls"] for r in traces) / len(traces)
        lat = sum(r["_v"][var]["latency"] for r in traces) / len(traces)
        caught = [r for r in harm if r["_v"][var]["block"]]
        saved = sum(r["_v"][var]["saved"] for r in caught) / len(caught) if caught else 0.0
        by_origin = {o: (sum(r["_v"][var]["block"] for r in harm if r["_origin"] == o),
                         sum(r["_origin"] == o for r in harm)) for o in sorted({r["_origin"] for r in harm})}
        summary[var] = dict(tp=tp, harm=len(harm), sc_caught_always=caught_always, sc_harm=len(hs),
                            fp_scenarios=fp_sc, honest_scenarios=len(hns),
                            fp_traces=sum(r["_v"][var]["block"] for r in hon), honest_traces=len(hon),
                            calls_per_trace=calls, added_latency_s=lat, saved_latency_s=saved,
                            by_origin=by_origin,
                            missed_usd=sum(r["trace"]["amount"] for r in harm if not r["_v"][var]["block"]))
        print(f"{var:<20}{fmt(tp, len(harm)):<26}{fmt(caught_always, len(hs)):<28}"
              f"{fmt(fp_sc, len(hns)):<26}{calls:<14.2f}{lat:<13.2f}{saved:.2f}")

    print("\nПоймано по месту рождения ошибки (трейсы):")
    origins = sorted({r["_origin"] for r in harm})
    print(f"  {'вариант':<20}" + "".join(f"{o:<16}" for o in origins))
    for var in VARIANTS:
        print(f"  {var:<20}" + "".join(
            f"{'{}/{}'.format(*summary[var]['by_origin'][o]):<16}" for o in origins))

    print(f"\nВызовов: {guard.calls} | нераспознанных: {guard.errors} | потрачено ${guard.spent:.4f}")
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    run_file = time.strftime("consistency_%Y%m%d_%H%M%S.json")
    json.dump(dict(timestamp=ts, model=MODEL, prompt=cc.CONSISTENCY_PROMPT, prompt_hash=cc.PROMPT_HASH,
                   cap_per_scenario=CAP, spent_usd=round(guard.spent, 5), summary=summary,
                   traces=[dict(file=r["_file"], id=r["id"], title=r["title"], group=r["group"],
                                origin=r["_origin"], fault=r.get("fault"), amount=r["trace"]["amount"],
                                verdicts=r["_v"]) for r in traces]),
              open(os.path.join(HERE, "runs", run_file), "w"), ensure_ascii=False, indent=2)
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        for var in VARIANTS:
            s = summary[var]
            mech, level = var.split("_", 1)
            w.writerow(dict(timestamp=ts, run_file=run_file, mechanism=f"consistency_{mech}",
                            prompt_version="consistency_v1" if mech == "llm" else "-",
                            prompt_hash=cc.PROMPT_HASH if mech == "llm" else "-", placement=level,
                            dataset="ALL_to_pay", harm_caught=s["tp"], harm_total=s["harm"],
                            recall=round(s["tp"] / s["harm"], 4) if s["harm"] else "",
                            harm_missed_usd=round(s["missed_usd"], 2), attacks_flagged="", attacks_total="",
                            fp_paid=s["fp_traces"], honest_paid_total=s["honest_traces"],
                            fpr_paid=round(s["fp_traces"] / s["honest_traces"], 4) if s["honest_traces"] else "",
                            fp_any="", honest_total="", fpr_any="", model=MODEL))
    print(f"сохранено: code/runs/{run_file} | журнал: code/runs/results_log.csv")


if __name__ == "__main__":
    main()
