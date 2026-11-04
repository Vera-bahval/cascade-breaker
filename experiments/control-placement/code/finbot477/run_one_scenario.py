"""Run ONE of Vera's cascade scenarios with token accounting and a hard budget cap. Does not modify FinBot code."""
import asyncio, sys, time
sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import openai.resources.responses as R
PRICE_IN, PRICE_OUT, BUDGET = 0.15/1e6, 0.60/1e6, float(sys.argv[2]) if len(sys.argv) > 2 else 0.10
stats = {"calls": 0, "in": 0, "out": 0}
_orig = R.AsyncResponses.create
async def counted(self, *a, **kw):
    cost = stats["in"]*PRICE_IN + stats["out"]*PRICE_OUT
    if cost >= BUDGET:
        raise RuntimeError(f"budget cap ${BUDGET} reached")
    r = await _orig(self, *a, **kw)
    stats["calls"] += 1
    u = getattr(r, "usage", None)
    if u: stats["in"] += u.input_tokens; stats["out"] += u.output_tokens
    return r
R.AsyncResponses.create = counted
import cascade_failure_demo as demo
async def main(idx):
    await demo._ensure_event_bus()
    vid = demo._ensure_demo_vendor()
    title, payload = demo._scenarios()[idx-1]
    t = time.time()
    await demo._run_scenario(vid, f"Scenario {idx}: {title}", payload)
    cost = stats["in"]*PRICE_IN + stats["out"]*PRICE_OUT
    print(f"\n== LLM calls: {stats['calls']}, tokens in/out: {stats['in']}/{stats['out']}, cost ≈ ${cost:.4f}, time {time.time()-t:.0f}s")
asyncio.run(main(int(sys.argv[1])))
