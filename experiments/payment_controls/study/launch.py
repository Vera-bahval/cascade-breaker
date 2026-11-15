"""Freeze the primary contrast and admit a closed schedule using calibration totals only."""
import csv
import hashlib
import io
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

from .score import load, summarize, ROOT


def bind(path,content):
    if path.exists() and path.read_bytes()!=content:
        raise ValueError(f"Frozen artifact changed: {path.name}")
    if not path.exists():
        with path.open("xb") as f:f.write(content)


def digest(data):return hashlib.sha256(data).hexdigest()


def launch(folder):
    manifest=json.loads((folder/"manifest.json").read_text())
    candidate=manifest["selected_preset"]
    if not candidate:raise ValueError("No independent preset")
    selected=manifest["candidates"][candidate]
    raw=(folder/selected["schedule"]).read_bytes()
    for name in ("inputs.cal.jsonl","inputs.test.jsonl","schedule.cal.csv",selected["schedule"]):
        if digest((folder/name).read_bytes())!=manifest["private_artifacts_sha256"][name]:
            raise ValueError("Corpus hash mismatch")
    schedule=[r for r in csv.DictReader(io.StringIO(raw.decode())) if r["split"]=="test"]
    inputs={r["case"] for r in map(json.loads,(folder/"inputs.test.jsonl").read_text().splitlines())}
    if inputs!={r["case"] for r in schedule} or len(inputs)!=len(schedule):raise ValueError("Unbound test schedule")
    cal=load(folder,"cal")
    results=summarize(cal)
    def primary(stage):
        s=results[stage+"-hybrid"]
        return s["wrong_block"]+s["excess_review"],s["unsafe"],s["usd"],stage
    point=min(("early","late"),key=primary)
    channel_cost=defaultdict(lambda:defaultdict(list))
    for r in cal:
        for provider in ("executor_usd","guard_usd"):
            channel_cost[r["channel"]][provider].append(r[provider])
    root=ROOT/".runtime/payment-controls-chp3"
    def charged(path,table):
        with sqlite3.connect(f"file:{path}?mode=ro",uri=True) as db:
            rows=db.execute("SELECT status,cost FROM "+table).fetchall()
        if any(status not in ("complete","completed") or cost is None for status,cost in rows):
            raise ValueError("Await reconciliation of pending charges")
        return sum(cost for _,cost in rows)
    prior={"executor_usd":sum(charged(root/p,"requests") for p in ("eliza/ledger.sqlite","live/executor.sqlite","study-live/executor.sqlite")),
           "guard_usd":sum(charged(root/p,"requests") for p in ("jev/ledger.sqlite","live/live-jev.sqlite","study-live/jev.sqlite"))}
    projected={k:sum(7*mean(channel_cost[r["channel"]][k]) for r in schedule)*1.25 for k in prior}
    eligible=all(prior[k]+projected[k]<=limit for k,limit in (("executor_usd",30),("guard_usd",10)))
    out=io.StringIO()
    writer=csv.DictWriter(out,fieldnames=["case","channel","split"])
    writer.writeheader()
    writer.writerows(schedule)
    schedule_bytes=out.getvalue().encode()
    frozen=dict(eligible=eligible,cases=len(schedule),candidate=selected["candidate_id"],primary=point,
                prior=prior,projected_with_headroom=projected,schedule_sha256=digest(schedule_bytes),
                inputs_sha256=digest((folder/"inputs.test.jsonl").read_bytes()),calibration_cases=len(cal)//7)
    bind(folder/"launch.json",(json.dumps(frozen,indent=2)+"\n").encode())
    if eligible:bind(folder/"schedule.test.csv",schedule_bytes)
    print(json.dumps(frozen,indent=2))


if __name__=="__main__":
    launch(Path(sys.argv[1]).resolve())
