"""Reconcile zero residual cost during quiescence and retain interrupted tasks in their arms."""
import gzip
import json
from pathlib import Path
import sqlite3
import sys

from .live import ROOT
from .enforce import ARMS

BASE=ROOT/".runtime/payment-controls-chp3"
LIVE=BASE/"study-live"


def reconcile(meters):
    observations=[json.loads(Path(f).read_text()) for f in meters]
    if len(observations)!=2 or observations[1]["time"]-observations[0]["time"]<45:
        raise ValueError("Two separated provider readbacks are required")
    # The final document preflight was immediately before the confirmation series.
    doc=BASE/"eliza"
    with gzip.open(doc/"preflight.jsonl.gz","rt") as stream:
        anchor=list(map(json.loads,stream))[-1]["remaining"]["monthly_usd"]
    doc_cost=sum(json.loads((doc/(item["receipt"]+".json")).read_text())["cost_usd"]
                 for item in json.loads((doc/"confirmation_observations.json").read_text()))
    with sqlite3.connect(LIVE/"executor.sqlite") as db:
        rows=db.execute("SELECT id,status,cost FROM requests").fetchall()
    unknown={k for k,status,cost in rows if status=="unknown" and cost is None}
    if not unknown or any(status not in ("unknown","completed") for _,status,_ in rows):
        raise ValueError("Expected drained workers and outstanding unknown requests")
    known=sum(cost or 0 for _,_,cost in rows)+doc_cost
    remaining=[r["remaining"]["monthly_usd"] for r in observations]
    if any(abs(anchor-value-known)>1e-8 for value in remaining):
        raise ValueError("Provider meter does not exactly explain known charges")
    legacy=ROOT.parents[1]/"deepseek-flash-control-placement/experiments/control-placement/deepseek_flash"
    sys.path.insert(0,str(legacy))
    from transport import Ledger
    ledger=Ledger(LIVE/"executor.sqlite",cap=29.85)
    for key in unknown:
        audit={"id":key,"original_reservation_status":"unknown","anchor_usd":anchor,
               "two_remaining_usd":remaining,"known_usd":known,"readback_times":[r["time"] for r in observations],
               "basis":"nonnegative charges; no residual on two monthly usage readbacks"}
        filename="timeout-"+key+".json"
        (LIVE/filename).write_text(json.dumps(audit,indent=2))
        ledger.reconcile(key,0,str(LIVE/filename))


def recover(folder):
    src=LIVE/folder
    if (src/"summary.json").exists():raise ValueError("Completed episode")
    with gzip.open(src/"calls.jsonl.gz","rt") as stream:
        calls=list(map(json.loads,stream))
    requests=[r["attempt_id"] for r in calls if r.get("event")=="request"]
    log=LIVE/"batch-logs"/(folder+".log")
    collateral="Unreconciled or failed request" in log.read_text()
    if not requests or not (collateral or any(r.get("event")=="error" and "Timeout" in str(r.get("error")) for r in calls)):
        raise ValueError("No documented executor timeout")
    with sqlite3.connect(LIVE/"executor.sqlite") as db:
        charges=[db.execute("SELECT status,cost FROM requests WHERE id=?",(k,)).fetchone() for k in requests]
    if any(r is None or r[0]!="completed" or r[1] is None for r in charges):
        raise ValueError("Pending accounting")
    traces=[json.loads(f.read_text()) for f in (src/"traces").glob("*.json")]
    guards=[{k:s.get(k) for k in ("point","decision","reason","cost_usd","latency_ms")}
            for tr in traces for s in tr["steps"] if s["kind"]=="guard"]
    chan,remaining=folder.split("-",1)
    arm,= [a for a in ARMS if remaining.startswith(a+"-")]
    family=remaining[len(arm)+1:].removesuffix("-v3")
    with sqlite3.connect(f"file:{src/'finbot.db'}?mode=ro",uri=True) as db:
        status=db.execute("SELECT status FROM vendors ORDER BY id DESC LIMIT 1").fetchone()
    log=LIVE/"batch-logs"/(folder+".log")
    row=dict(technical_basis="executor_timeout_or_interrupted_on_unsettled_charge",channel=chan,arm=arm,family=family,technical_executor=True,
             vendor_status=status[0] if status else None,workflow_count=len(traces),
             seconds=log.stat().st_mtime-src.stat().st_birthtime,executor_calls=len(requests),
             executor_usd=sum(r[1] for r in charges),guard=guards)
    with (src/"summary.json").open("x") as stream:json.dump(row,stream,indent=2)


if __name__=="__main__":
    if sys.argv[1]=="reconcile":reconcile(sys.argv[2:])
    elif sys.argv[1]=="retain":recover(sys.argv[2])
    else:raise ValueError("Choose reconcile or retain")
