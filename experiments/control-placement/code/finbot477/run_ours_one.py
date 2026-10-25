"""Run ONE of our invoices (from our_scenarios.json) through new FinBot on the trusted vendor; token accounting + cap."""
import asyncio, json, sys, time
from datetime import UTC, datetime, timedelta
sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import openai.resources.responses as R
PRICE_IN, PRICE_OUT, CAP = 0.15/1e6, 0.60/1e6, 0.03
stats = {"calls": 0, "in": 0, "out": 0}
_orig = R.AsyncResponses.create
async def counted(self, *a, **kw):
    if stats["in"]*PRICE_IN + stats["out"]*PRICE_OUT >= CAP: raise RuntimeError("per-invoice cap reached")
    r = await _orig(self, *a, **kw); stats["calls"] += 1
    if getattr(r, "usage", None): stats["in"] += r.usage.input_tokens; stats["out"] += r.usage.output_tokens
    return r
R.AsyncResponses.create = counted
import cascade_failure_demo as demo
sc = json.load(open(sys.argv[1]))[int(sys.argv[2])]
async def main():
    await demo._ensure_event_bus()
    today = datetime.now(UTC)
    payload = {"invoice_number": f"INV-2026-{1000+int(sys.argv[2]):04d}", "amount": float(sc["amount"]),
               "description": sc["desc"], "invoice_date": today.strftime("%Y-%m-%d"),
               "due_date": (today + timedelta(days=30)).strftime("%Y-%m-%d")}
    t = time.time()
    await demo._run_scenario(1, f"{sc['id']} ({sc['truth']})", payload)
    cost = stats["in"]*PRICE_IN + stats["out"]*PRICE_OUT
    print(f"\n== LLM calls: {stats['calls']}, tokens in/out: {stats['in']}/{stats['out']}, cost ≈ ${cost:.4f}, time {time.time()-t:.0f}s")
    print("COST_USD", round(cost, 5))
asyncio.run(main())
