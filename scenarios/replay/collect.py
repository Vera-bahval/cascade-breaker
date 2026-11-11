"""Replay a guard on saved runs: one verdict per control point, no FinBot run.

For every saved run the script rebuilds what the live guard runtime would have seen at each
control point (payload, database snapshot at that moment, workflow steps so far), asks the
verifier for a verdict and writes one table with all verdicts. sets.py then scores every set of
points from that table without any further LLM calls.

    cd finbot
    uv run python ../scenarios/replay/collect.py direct/baseline-ds1 \
        --out ../docs/results/llm-guard-replay-direct.json

The guard is the LLM consistency check (finbot/probe/guards/llm.py): one LLM call at temperature 0 with the payment
policy and a short guidance for the point. Without --verifier llm every verdict is "allow", which
checks that the replay rebuilds the baseline. Verdicts are cached next to --out, so an
interrupted run resumes where it stopped.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import glob
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "finbot"))
RESULTS = ROOT / "scenarios" / "results" / "unified"

MODEL = "meta-llama/llama-3.3-70b-instruct"
STATE_CHANGING = {"update_invoice_status", "flag_invoice_for_review", "update_vendor_risk"}
PAYMENT = {"finstripe__create_transfer", "process_payment"}
P2_GROUP = {"invoice_agent": "P2a", "fraud_agent": "P2b", "payments_agent": "P2c"}
WORKFLOW_STRIDE = 100_000  # keeps steps of several workflows of one run in order


def initial_state(run: dict, steps: list[dict], invoice_id: int) -> dict:
    """Database state before the workflow: vendor from the 'before' snapshot, the trigger invoice
    as the invoice agent first read it."""
    vendor = copy.deepcopy(run["before"]["vendors"]["current"])
    invoice = copy.deepcopy(next(i for i in run["after"]["invoices"] if i["id"] == invoice_id))
    first_read = next(
        (s for s in steps if s["kind"] == "tool" and s["name"] == "get_invoice_details"
         and s["arguments"].get("invoice_id") == invoice_id and isinstance(s.get("output"), dict)),
        None,
    )
    invoice["status"] = first_read["output"]["status"] if first_read else "submitted"
    transactions = [dict(t, vendor_id=vendor["id"]) for t in run["before"].get("transactions", [])]
    return {"invoice": invoice, "vendor": vendor, "transactions": transactions}


def apply_write(state: dict, step: dict) -> None:
    """Apply the effect of one successful write tool call to the rebuilt state."""
    out = step.get("output")
    if step.get("error") or not isinstance(out, dict) or out.get("error"):
        return
    name = step["name"]
    if name == "update_invoice_status" and out.get("invoice_id") == state["invoice"]["id"]:
        state["invoice"]["status"] = out["status"]
    elif name == "update_vendor_risk":
        state["vendor"]["risk_level"] = out["risk_level"]
    elif name == "finstripe__create_transfer":
        state["transactions"].append({
            "transfer_id": out["transfer_id"], "invoice_id": step["arguments"].get("invoice_id"),
            "amount": out["amount"], "status": out["status"], "vendor_id": state["vendor"]["id"],
        })
    elif name == "process_payment" and out.get("invoice_id") == state["invoice"]["id"]:
        state["invoice"]["status"] = out["status"]


def control_points(run: dict):
    """Yield one dict per check the live runtime would make in this run."""
    ref = (run.get("refs") or {}).get("invoices", {}).get("T")
    for index, (workflow, trace) in enumerate((run.get("traces") or {}).items()):
        steps = trace["steps"]
        invoice_id = (trace.get("task_data") or {}).get("invoice_id") or (ref or {}).get("id")
        if invoice_id is None:
            continue
        try:
            state = initial_state(run, steps, invoice_id)
        except StopIteration:
            continue
        offset = index * WORKFLOW_STRIDE
        delegations: dict[str, list[dict]] = {}
        for s in steps:
            if s["kind"] == "tool" and s["agent"] == "orchestrator_agent" and s["name"].startswith("delegate_to_"):
                delegations.setdefault(s["name"][len("delegate_to_"):], []).append(s)
        seen_delegations, occurrences = Counter(), Counter()

        def point(group, name, seq, payload, trace_upto=None):
            occurrences[name] += 1
            upto = trace_upto if trace_upto is not None else seq - 1
            return {
                "workflow": workflow, "group": group, "point": name, "occurrence": occurrences[name],
                "seq": offset + seq, "payload": payload, "db_snapshot": copy.deepcopy(state),
                "trace_so_far": [x for x in steps if x["seq"] <= upto],
            }

        submitted = {k: state["invoice"].get(k) for k in (
            "id", "invoice_number", "amount", "description", "invoice_date", "due_date", "vendor_id")}
        submitted["status"] = "submitted"
        yield point("P0", "P0.input", -1, submitted)
        for s in steps:
            if s["kind"] == "delegation":
                target = s["target"]
                nth = seen_delegations[target]
                seen_delegations[target] += 1
                calls = delegations.get(target, [])
                args = calls[nth]["arguments"] if nth < len(calls) else {"task_description": s["task_description"]}
                yield point("P1", f"P1.delegate_to_{target}", s["seq"],
                            {"tool": f"delegate_to_{target}", "arguments": args})
            elif s["kind"] == "tool":
                name, agent = s["name"], s["agent"]
                if agent == "orchestrator_agent" and name.startswith("delegate_to_"):
                    worker = name[len("delegate_to_"):] + "_agent"
                    summary = next((x for x in reversed(steps) if x["kind"] == "summary" and x["agent"] == worker
                                    and x["seq"] < s["seq"]), None)
                    if worker in P2_GROUP and summary:
                        yield point(P2_GROUP[worker], f"P2.{worker}", s["seq"],
                                    {"agent": worker, "task_status": summary.get("task_status"),
                                     "task_summary": summary.get("task_summary")}, trace_upto=s["seq"])
                elif agent == "orchestrator_agent" and name == "complete_task":
                    yield point("P5", "P5.final", s["seq"], {"tool": name, "arguments": s["arguments"]})
                elif name in PAYMENT and agent == "payments_agent":
                    yield point("P4", f"P4.{name}", s["seq"], {"tool": name, "arguments": s["arguments"]})
                elif name in STATE_CHANGING and agent != "orchestrator_agent":
                    yield point("P3", f"P3.{name}", s["seq"], {"tool": name, "arguments": s["arguments"]})
                apply_write(state, s)


_client = None


async def ask_llm_guard(point: dict) -> dict:
    global _client
    from finbot.config import settings
    from finbot.probe.guards.base import GuardContext
    from finbot.probe.guards.llm import V3_SYSTEM, VERDICT_SCHEMA, consistency_prompt
    from openai import AsyncOpenAI

    if _client is None:
        kwargs = {"api_key": settings.OPENAI_API_KEY}
        if settings.OPENAI_BASE_URL:
            kwargs["base_url"] = settings.OPENAI_BASE_URL
        _client = AsyncOpenAI(**kwargs)
    context = GuardContext(run_id=point["workflow"], point=point["point"], agent=None, payload=point["payload"],
                           db_snapshot=point["db_snapshot"], trace_so_far=point["trace_so_far"])
    started = time.perf_counter()
    response = await _client.chat.completions.create(
        model=MODEL, temperature=0.0,
        messages=[{"role": "system", "content": V3_SYSTEM}, {"role": "user", "content": consistency_prompt(context)}],
        response_format={"type": "json_schema", "json_schema": {**VERDICT_SCHEMA, "strict": True}},
        extra_body={"usage": {"include": True}},
    )
    verdict = json.loads(response.choices[0].message.content or "{}")
    usage = response.usage
    return {
        "decision": verdict["decision"], "reason": (verdict.get("reason") or "")[:300],
        "latency_ms": (time.perf_counter() - started) * 1000,
        "tokens_in": usage.prompt_tokens, "tokens_out": usage.completion_tokens,
        "cost_usd": float(getattr(usage, "cost", 0) or 0),
    }


async def verdict_for(kind: str, key: str, point: dict, cache: dict, cache_file: Path, gate: asyncio.Semaphore):
    if kind == "none":
        return {"decision": "allow", "reason": "", "latency_ms": 0, "cost_usd": 0, "tokens_in": 0, "tokens_out": 0}
    if key in cache:
        return cache[key]
    async with gate:
        for attempt in range(5):
            try:
                result = await ask_llm_guard(point)
                break
            except Exception:  # rate limits and timeouts: back off and retry
                if attempt == 4:
                    raise
                await asyncio.sleep(2 ** attempt)
    result["key"] = key
    cache[key] = result
    with cache_file.open("a") as f:
        f.write(json.dumps(result) + "\n")
    return result


def harm_step(run: dict) -> int | None:
    """Sequence number of the first transfer in a harmful run (negative scenario, oracle failed)."""
    if run["variant"] != "negative" or run["oracle_ok"]:
        return None
    for index, trace in enumerate((run.get("traces") or {}).values()):
        for s in trace["steps"]:
            if s["kind"] == "tool" and s["name"] == "finstripe__create_transfer":
                return index * WORKFLOW_STRIDE + s["seq"]
    return None


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("batch", nargs="+", help="run folders under scenarios/results/unified, e.g. direct/baseline-ds1")
    parser.add_argument("--verifier", default="none", choices=["none", "llm"])
    parser.add_argument("--limit", type=int, help="first N runs of each batch")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    cache_file = args.out.with_suffix(".cache.jsonl")
    cache: dict[str, dict] = {}
    if cache_file.exists():
        for line in cache_file.read_text().splitlines():
            row = json.loads(line)
            cache[row["key"]] = row
    gate = asyncio.Semaphore(args.workers)

    runs, counts = [], Counter()
    for batch in args.batch:
        files = sorted(glob.glob(str(RESULTS / batch / "*.json")))[: args.limit]
        for path in files:
            run = json.loads(Path(path).read_text())
            if run.get("run_error") or not run.get("precondition_ok", True):
                continue
            name = Path(path).name
            amount = None
            for trace in (run.get("traces") or {}).values():
                for s in trace["steps"]:
                    if s["kind"] == "tool" and s["name"] == "finstripe__create_transfer":
                        amount = s["arguments"].get("amount")
            record = {"batch": batch, "name": name, "variant": run["variant"], "oracle_ok": run["oracle_ok"],
                      "harm_seq": harm_step(run), "amount": amount, "wall_s": run.get("trigger_s") or 0, "checks": []}
            for p in control_points(run):
                counts[p["group"]] += 1
                key = f"{batch}/{name}/{p['workflow']}/{p['point']}#{p['occurrence']}"
                task = asyncio.ensure_future(verdict_for(args.verifier, key, p, cache, cache_file, gate))
                record["checks"].append({"group": p["group"], "point": p["point"], "seq": p["seq"], "task": task})
            runs.append(record)
    total = sum(counts.values())
    print("checks:", dict(counts), "total", total, flush=True)

    async def progress():
        while True:
            await asyncio.sleep(60)
            done = sum(1 for r in runs for c in r["checks"] if "task" in c and c["task"].done())
            print(f"  done {done}/{total}", flush=True)

    ticker = asyncio.ensure_future(progress())
    errors = 0
    for record in runs:
        for check in record["checks"]:
            try:
                v = await check.pop("task")
                check.update({k: v[k] for k in ("decision", "reason", "latency_ms", "cost_usd", "tokens_in", "tokens_out")})
            except Exception as e:  # keep going; failed checks are listed and can be re-run from the cache
                errors += 1
                check.update({"decision": "error", "reason": str(e)[:200], "latency_ms": 0, "cost_usd": 0,
                              "tokens_in": 0, "tokens_out": 0})
    ticker.cancel()
    args.out.write_text(json.dumps(runs))
    print("written", args.out, "runs", len(runs), "errors", errors)


if __name__ == "__main__":
    asyncio.run(main())
