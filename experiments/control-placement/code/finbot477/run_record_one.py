"""Run ONE invoice with FULL recording of every model call (input, output items incl. reasoning summary, usage).
For gpt-5* models: drop temperature, request reasoning summaries. Does not modify FinBot code.
usage: run_record_one.py <scenarios.json> <idx> <calls_out.jsonl>"""
import asyncio, json, sys, time
from datetime import UTC, datetime, timedelta
sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import openai.resources.responses as R
CAP = 0.05
stats = {"calls": 0, "cost": 0.0}
OUT = sys.argv[3]
_orig = R.AsyncResponses.create
def dump(o):
    try: return o.model_dump()
    except Exception: return str(o)
async def recorded(self, *a, **kw):
    if stats["cost"] >= CAP: raise RuntimeError("per-invoice cap reached")
    model = kw.get("model", "")
    if "gpt-5" in model:
        kw.pop("temperature", None)
        kw["reasoning"] = {"effort": "low", "summary": "auto"}
    r = await _orig(self, *a, **kw)
    stats["calls"] += 1
    u = getattr(r, "usage", None)
    c = getattr(u, "cost", None) if u else None
    if c is None and u:
        c = u.input_tokens * 0.15e-6 + u.output_tokens * 0.60e-6
    stats["cost"] += c or 0
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps({"call": stats["calls"], "model": model, "temperature": kw.get("temperature"), "input": kw.get("input"),
                            "output": [dump(o) for o in (r.output or [])], "usage": dump(u) if u else None},
                           ensure_ascii=False, default=str) + "\n")
    return r
R.AsyncResponses.create = recorded
import cascade_failure_demo as demo
sc = json.load(open(sys.argv[1]))[int(sys.argv[2])]
async def main():
    await demo._ensure_event_bus()
    today = datetime.now(UTC)
    payload = {"invoice_number": f"INV-2026-{1000+int(sys.argv[2]):04d}", "amount": float(sc["amount"]), "description": sc["desc"],
               "invoice_date": today.strftime("%Y-%m-%d"), "due_date": (today + timedelta(days=30)).strftime("%Y-%m-%d")}
    t = time.time()
    await demo._run_scenario(1, f"{sc['id']} ({sc['truth']})", payload)
    print(f"\n== LLM calls: {stats['calls']}, cost ≈ ${stats['cost']:.4f}, time {time.time()-t:.0f}s")
    print("COST_USD", round(stats["cost"], 5))
asyncio.run(main())
