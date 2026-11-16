"""Run complete case blocks; the first stage can collect OFF packets alone."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import random
import sqlite3
import subprocess
import sys
from .provider import HERE, PRIVATE, ROOT
from .route import ARMS

RUNTIME=ROOT/".runtime/payment-controls-chp3/study-live"
VERSION="overnight-route-v1"


def folder(f,arm):
    return RUNTIME/f"{f['channel']}-{arm}-{f['id']}-{VERSION}"


def one(f,arm,structured=False):
    dest=folder(f,arm)
    if structured:
        dest=dest.with_name(dest.name.removesuffix(VERSION)+"structured-v1")
    if (dest/"summary.json").exists():
        return
    if dest.exists() and any(dest.iterdir()):raise RuntimeError("Incomplete episode: "+dest.name)
    args=[sys.executable,"-m","experiments.payment_controls.native.overnight.live",
          "--channel",f["channel"],"--arm",arm,"--case",f["id"],"--fixtures",str(HERE/"fixtures.json")]
    if structured:args.append("--structured")
    env=dict(os.environ)
    if arm not in ("overnight-model-v1","overnight-hybrid-v1"):env.pop("TYPESAFE_API_KEY",None)
    (PRIVATE/"logs").mkdir(exist_ok=True,parents=True)
    with (PRIVATE/"logs"/(dest.name+".log")).open("ab") as log:
        subprocess.run(args,cwd=ROOT,env=env,stdout=log,stderr=log,check=True,timeout=550)
    if not (dest/"summary.json").exists():raise ValueError("Missing result "+dest.name)


def main(stage):
    fixtures={f["id"]:f for f in json.loads((HERE/"fixtures.json").read_text())}
    ids=json.loads((HERE/"live_selection.json").read_text())
    assert isinstance(ids,list) and 1<=len(ids)<=8 and len(set(ids))==len(ids)
    if stage=="structured":
        for idx in (ids[1],ids[2]):
            one(fixtures[idx],ARMS[0],structured=True)
        return
    rng=random.Random(1711)
    jobs=[]
    for idx in ids:
        arms=list(ARMS[1:]);rng.shuffle(arms)
        jobs.extend((fixtures[idx],a) for a in ([ARMS[0]] if stage=="baseline" else arms))
    if stage=="routes" and not all((folder(fixtures[k],ARMS[0])/"summary.json").is_file() for k in ids):
        raise RuntimeError("Baseline incomplete")
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i in range(0,len(jobs),3):
            with sqlite3.connect((RUNTIME/"executor.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as db:
                cost,=db.execute("select coalesce(sum(coalesce(cost,reserve)),0) from requests").fetchone()
            if cost+0.20>4.8:
                print("Budget boundary",flush=True);break
            list(pool.map(lambda job:one(*job),jobs[i:i+3]))
            print(stage,min(i+3,len(jobs)),len(jobs),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("baseline","routes","structured"))
    main(p.parse_args().stage)
