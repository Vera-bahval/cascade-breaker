"""Summarise a batch of API MAST runs: oracle outcomes, how far each chain went, latency and cost.

    python scenarios/analyze_mast.py scenarios/results/api-mast/<batch>            # table per scenario
    python scenarios/analyze_mast.py scenarios/results/api-mast/<batch> --runs     # one line per run
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def tool_calls(traces: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for t in traces.values() for s in (t or {}).get("steps", []) if s["kind"] == "tool"]


def args(step: dict[str, Any]) -> dict[str, Any]:
    a = step.get("arguments") or {}
    return json.loads(a) if isinstance(a, str) else a


def cost(traces: dict[str, Any]) -> float:
    return sum(((s.get("usage") or {}).get("cost") or 0.0)
               for t in traces.values() for s in (t or {}).get("steps", []) if s["kind"] == "llm")


def chain(run: dict[str, Any]) -> dict[str, Any]:
    """How far the trigger's workflows went, read from tool calls, not from agent prose."""
    calls = tool_calls(run.get("traces") or {})
    names = [c["name"] for c in calls]
    statuses = [args(c) for c in calls if c["name"] == "update_vendor_status"]
    events = run.get("events") or []
    return {
        "chat_wf": len(run.get("chat_workflows") or []),
        "approved": sum(c["name"] == "update_invoice_status" and args(c).get("status") == "approved" for c in calls),
        "fraud_flag": [args(c).get("recommended_action") for c in calls if c["name"] == "flag_invoice_for_review"],
        "to_payments": names.count("delegate_to_payments"),
        "transfers": names.count("finstripe__create_transfer"),
        "sysutils": sum("systemutils" in e["event_type"] or "systemutils" in str(e.get("tool_name"))
                        for e in events if e["event_type"].endswith("mcp_tool_call_start")),
        "vendor_status": [(s.get("status"), s.get("trust_level")) for s in statuses],
    }


def load(batch: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(batch.glob("S*-r*.json"))]


def per_run(runs: list[dict[str, Any]]) -> None:
    for r in runs:
        if r.get("error"):
            print(f"{r['scenario']:6} ERROR {r['error'][:100]}")
            continue
        print(f"{r['scenario']:6} pre={int(r['precondition_ok'])} ok={int(r['oracle_ok'])} "
              f"t={r['trigger_s']:6.0f}s ${cost(r.get('traces') or {}):.4f} {chain(r)} "
              f"{[c['value'] for c in r['oracle']]}")


def table(runs: list[dict[str, Any]]) -> None:
    by = defaultdict(list)
    for r in runs:
        by[r["scenario"]].append(r)
    print("| id | MAST | n | prec. ok | oracle ok | chat wf | approved | to payments | transfers | trigger s (med) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for sid in sorted(by):
        rs = [r for r in by[sid] if not r.get("error")]
        errs = len(by[sid]) - len(rs)
        ch = [chain(r) for r in rs]
        med = statistics.median([r["trigger_s"] for r in rs]) if rs else float("nan")
        print(f"| {sid} | {','.join(by[sid][0]['mast'])} | {len(rs)}{f' (+{errs} err)' if errs else ''} "
              f"| {sum(r['precondition_ok'] for r in rs)} | {sum(r['oracle_ok'] for r in rs)} "
              f"| {sum(c['chat_wf'] for c in ch)} | {sum(c['approved'] for c in ch)} "
              f"| {sum(c['to_payments'] for c in ch)} | {sum(c['transfers'] for c in ch)} | {med:.0f} |")

    print()
    ok = [r for r in runs if not r.get("error")]
    for label, keep in (("all runs", lambda r: True), ("precondition held", lambda r: r["precondition_ok"])):
        sel = [r for r in ok if keep(r)]
        neg = [r for r in sel if r["variant"] == "negative"]
        pos = [r for r in sel if r["variant"] == "positive"]
        harm = sum(not r["oracle_ok"] for r in neg)
        fail = sum(not r["oracle_ok"] for r in pos)
        lo, hi = wilson(harm, len(neg))
        plo, phi = wilson(fail, len(pos))
        print(f"{label}: harm on N {harm}/{len(neg)} = {harm / max(len(neg), 1):.0%} [{lo:.0%}-{hi:.0%}]; "
              f"P failed {fail}/{len(pos)} = {fail / max(len(pos), 1):.0%} [{plo:.0%}-{phi:.0%}]")
    for kind in ("chat", "onboarding"):
        sel = [r for r in ok if r["kind"] == kind and r["variant"] == "negative"]
        print(f"  {kind}: harm on N {sum(not r['oracle_ok'] for r in sel)}/{len(sel)}")
    trig = [r["trigger_s"] for r in ok]
    costs = [cost(r.get("traces") or {}) for r in ok]
    setup_costs = [cost(r.get("setup_traces") or {}) for r in ok]
    if trig:
        q = statistics.quantiles(trig, n=20)
        print(f"trigger latency: p50 {statistics.median(trig):.0f} s, p95 {q[-1]:.0f} s")
        print(f"workflow cost per run (trigger): mean ${statistics.mean(costs):.4f}, "
              f"setup mean ${statistics.mean(setup_costs):.4f}; chat LLM calls are not traced")
    print(f"errors: {len(runs) - len(ok)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batch", type=Path)
    parser.add_argument("--runs", action="store_true")
    args_ = parser.parse_args()
    runs = load(args_.batch)
    per_run(runs) if args_.runs else table(runs)


if __name__ == "__main__":
    main()
