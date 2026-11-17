"""Reconcile provider-specific ledgers, keeping experimental stages and failed attempts."""
import collections
import csv
import json
import math
import sqlite3
from .live_batch import RUNTIME
from .provider import PRIVATE,HERE


def main():
    before={"eliza":2.231345304,"jev":0.007708932}
    rows={}
    for provider in ("eliza","jev"):
        folder=PRIVATE/provider
        with sqlite3.connect((folder/"ledger.sqlite").as_uri()+"?mode=ro",uri=True) as db:
            charges={i:c for i,c,status in db.execute("select id,cost,status from requests") if status=="complete"}
            pending,reserve=db.execute("select count(*),coalesce(sum(reserve),0) from requests where status!='complete'").fetchone()
        totals=collections.defaultdict(float);counts=collections.Counter()
        ids=set()
        for path in folder.glob("*.json"):
            x=json.loads(path.read_text())
            if not math.isclose(charges[path.stem],x["usd"],abs_tol=1e-12):raise ValueError("Unbound charge")
            group=x["owner"].split('/')[0] if "-panel/" in x["owner"] else "live_decision"
            totals[group]+=x["usd"];counts[group]+=1;ids.add(path.stem)
        if ids!=set(charges):raise ValueError("Missing receipt")
        rows[provider]=dict(stage_usd=dict(totals),stage_calls=dict(counts),pending=pending,pending_reserve_usd=reserve)
    with sqlite3.connect((RUNTIME/"executor.sqlite").as_uri()+"?mode=ro",uri=True) as db:
        n,cost=db.execute("select count(*),sum(cost) from requests where status='completed'").fetchone()
        rows["eliza"]["pending_reserve_usd"]+=db.execute("select coalesce(sum(reserve),0) from requests where status!='completed'").fetchone()[0]
        rows["eliza"]["pending"]+=db.execute("select count(*) from requests where status!='completed'").fetchone()[0]
    rows["eliza"]["stage_usd"]["live_executor"]=cost-2.184350844
    rows["eliza"]["stage_calls"]["live_executor"]=n-4309
    for provider,x in rows.items():
        x["new_usd"]=round(sum(x["stage_usd"].values()),9)
        x["new_usd_upper"]=round(x["new_usd"]+x["pending_reserve_usd"],9)
        x["cumulative_usd"]=round(before[provider]+x["new_usd"],9)
    (HERE/"billing.json").write_text(json.dumps(rows,indent=2)+"\n")


if __name__=="__main__":main()
