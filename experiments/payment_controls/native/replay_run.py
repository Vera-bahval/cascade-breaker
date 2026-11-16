"""Evaluate exactly the published pre-action packets with the same official Jev client."""
import asyncio
import csv
import json
import sys
import time
from pathlib import Path
from experiments.payment_controls.study.enforce import StudyVerifier
from experiments.payment_controls.live_smoke import ROOT
from experiments.local_guards_archive_comparison.eliza import Ledger


async def main():
    sys.path.insert(0,str(ROOT/"finbot"))
    here=Path(__file__).resolve().parent
    source=json.loads((here/"replay_packets.json").read_text())
    base=ROOT/".runtime/payment-controls-chp3/study-live"
    dest=base/"native-replay"
    dest.mkdir(mode=0o700,exist_ok=True)
    ledger=Ledger(base/"jev.sqlite",1.9)
    out=here/"replay_results.csv"
    if out.exists():raise ValueError("Existing replay results")
    results=[]
    for item in source:
        v=StudyVerifier("early-model",{},dest,ledger)
        start=time.monotonic()
        res=await v.resolve(item["id"],item["packet"],"review","model_only")
        elapsed=time.monotonic()-start
        rule=item["rule"]
        local=rule["decision"] if isinstance(rule,dict) else rule
        local=local.upper()
        defer=local in ("UNKNOWN","REVIEW","DEFER")
        results.append(dict(id=item["id"],group=item["group"],point=item["point"],gold=item["gold"],rules=local,
                            jev=res.decision.upper(),hybrid=res.decision.upper() if defer else local,
                            jev_seconds=elapsed,jev_usd=res.cost_usd,hybrid_model_calls=int(defer),
                            hybrid_model_usd=res.cost_usd if defer else 0))
    with out.open("x") as f:
        w=csv.DictWriter(f,fieldnames=results[0],lineterminator="\n");w.writeheader();w.writerows(results)


if __name__=="__main__":asyncio.run(main())
