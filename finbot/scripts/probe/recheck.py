"""Re-run a verifier on the control-point contexts stored in recorded traces.

Each guard_context step holds exactly what the point saw (payload, database
snapshot); the trace before it is the history. This replays verifiers
without re-running any agent: free for V1/V2, a few verifier calls for V3/V4.

Uses: tuning a verifier on a debug trace, and the stage 4 stability check
(same inputs, repeated calls, how often the decision flips).

Usage (from repos/finbot-ctf):
    uv run python scripts/probe/recheck.py runs/debug-stage2.jsonl --verifier V3
    uv run python scripts/probe/recheck.py runs/shadow-main.jsonl --verifier V3 \
        --sample 60 --repeats 2 --out recheck/v3-stability.jsonl
"""

import argparse
import asyncio
import json
import logging
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# pylint: disable=wrong-import-position
# ruff: noqa: E402
from common import EXPERIMENT_DIR, append_spend, check_budget

from finbot.config import settings
from finbot.probe import ledger as probe_ledger
from finbot.probe.guards.base import GuardContext
from finbot.probe.guards.invariants import InvariantVerifier, TextRuleVerifier
from finbot.probe.guards.llm import ConsistencyVerifier, SelfConsistencyVerifier
from finbot.probe.roles import DEFAULT_ROLES_PATH, load_roles

VERIFIERS = {
    "V1": InvariantVerifier,
    "V2": TextRuleVerifier,
    "V3": ConsistencyVerifier,
    "V4": SelfConsistencyVerifier,
}


def contexts(path: Path) -> list[tuple[dict, GuardContext, str | None]]:
    """(run record, context, recorded decision of the same verifier) for every point."""
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            steps = rec["steps"]
            for step in steps:
                if step["kind"] != "guard_context":
                    continue
                ctx = GuardContext(
                    run_id=rec["run_id"], point=step["point"], agent=step.get("agent"),
                    payload=step["payload"], db_snapshot=step["db_snapshot"],
                    trace_so_far=steps[: step["seq"]],
                )
                out.append((rec, ctx, step["seq"]))
    return out


def recorded(rec: dict, context_seq: int, verifier: str) -> str | None:
    for s in rec["steps"]:
        if s["kind"] == "guard" and s["context_seq"] == context_seq and s["verifier"] == verifier:
            return s["decision"]
    return None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_file", help="path relative to experiments/finbot-probe")
    parser.add_argument("--verifier", choices=sorted(VERIFIERS), required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--sample", type=int, help="random sample of contexts (seeded)")
    parser.add_argument("--families", nargs="*", help="limit to point families, e.g. P2 P4")
    parser.add_argument("--out", help="output path relative to experiments/finbot-probe")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    logging.disable(logging.INFO)
    settings.CASCADE_PROBE_ROLES = str(DEFAULT_ROLES_PATH)
    items = contexts(EXPERIMENT_DIR / args.trace_file)
    if args.families:
        items = [i for i in items if i[1].family in set(args.families)]
    if args.sample and args.sample < len(items):
        items = random.Random(7).sample(items, args.sample)
    verifier = VERIFIERS[args.verifier]()
    llm = args.verifier in ("V3", "V4")
    if llm:
        per_call = 0.0004 if args.verifier == "V3" else 0.0012
        check_budget(forecast_usd=per_call * len(items) * args.repeats)

    rows = []
    with probe_ledger.open_ledger(load_roles().price_per_mtok) as ledger:
        for rec, ctx, seq in items:
            decisions = []
            reasons = []
            for _ in range(args.repeats):
                result = await verifier.check(ctx)
                decisions.append(result.decision)
                reasons.append(result.reason)
            row = {
                "run_id": rec["run_id"], "key": rec["key"], "set_name": rec["set_name"],
                "point": ctx.point, "context_seq": seq,
                "recorded": recorded(rec, seq, args.verifier),
                "decisions": decisions, "reasons": reasons,
            }
            rows.append(row)
            if not args.quiet:
                print(f"{rec['case_id']:<26} {ctx.point:<32} rec={row['recorded']} now={decisions} {reasons[0][:110]}")
    cost = ledger.totals()["cost_usd"]
    if llm:
        append_spend(f"recheck:{args.verifier}:{args.trace_file}", cost,
                     llm_calls=ledger.totals()["llm_calls"])
    flips = sum(len(set(r["decisions"])) > 1 for r in rows)
    changed = sum(r["recorded"] is not None and r["recorded"] != r["decisions"][0] for r in rows)
    blocks = sum(r["decisions"][0] == "block" for r in rows)
    print(f"{len(rows)} contexts, block {blocks}, changed vs recorded {changed}, "
          f"flipped across repeats {flips}, cost ${cost:.4f}")
    if args.out:
        out = EXPERIMENT_DIR / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
