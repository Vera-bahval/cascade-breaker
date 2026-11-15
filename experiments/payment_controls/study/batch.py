"""Execute a frozen family schedule in isolated processes; collect summary without gold."""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import random
import sqlite3
import subprocess
import sys

from .enforce import ARMS
from .live import ROOT


def jobs(folder, split):
    if split=="transfer":
        return [(c,a,f) for c in ("chat-transfer","onboarding-transfer") for a in ("off","late-hybrid")
                for f in ("authorized","withheld")]
    with (folder/f"schedule.{split}.csv").open() as stream:
        rows=list(csv.DictReader(stream))
    if not rows or len({r["case"] for r in rows})!=len(rows) or any(r["split"]!=split for r in rows):
        raise ValueError("Invalid blinded schedule")
    return [(r["channel"],a,r["case"]) for r in rows for a in ARMS]


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("split",choices=("cal","test","transfer"))
    cli.add_argument("corpus",type=Path)
    cli.add_argument("--workers",type=int,default=4)
    args=cli.parse_args()
    folder=args.corpus.resolve()
    if args.split=="test":
        release=json.loads((folder/"launch.json").read_text())
        if not release["eligible"] or release["cases"]!=len(jobs(folder,args.split))//7:
            raise ValueError("Blind release and budget sizing required before test")
    queue=jobs(folder,args.split)
    random.Random(1703).shuffle(queue)
    runtime=ROOT/".runtime/payment-controls-chp3/study-live"
    logs=runtime/"batch-logs"
    logs.mkdir(parents=True,exist_ok=True)
    def execute(job):
        name="-".join(job)+"-v3"
        if (runtime/name/"summary.json").is_file():return "complete"
        env=dict(os.environ,FINBOT_STUDY_PHASE={"cal":"development","test":"test","transfer":"transfer"}[args.split])
        if args.split!="transfer":env["FINBOT_STUDY_INPUT"]=str(folder/f"inputs.{args.split}.jsonl")
        if job[1] in ("off","early-rules","late-rules"):
            env.pop("TYPESAFE_API_KEY",None)
        with (logs/(name+".log")).open("xb") as log:
            result=subprocess.run([sys.executable,"-m","experiments.payment_controls.study.live",*job],
                                  cwd=ROOT,env=env,stdout=log,stderr=log)
        if result.returncode == 0:
            entries = runtime/name/"jev-requests.jsonl"
            if entries.exists():
                with entries.open() as stream, sqlite3.connect(runtime/"jev.sqlite") as db:
                    for row in map(json.loads,stream):
                        receipt = db.execute("SELECT status,cost FROM requests WHERE id=?", (row["id"],)).fetchone()
                        if receipt is None or receipt[0]!="complete" or receipt[1] is None:
                            raise RuntimeError(f"Unreconciled official Jev request in {name}")
        if result.returncode:
            raise RuntimeError(f"Incomplete episode {name}. Check ledger before resumption")
        return "complete"
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        # Bound in-flight work at an accounting failure.
        for offset in range(0,len(queue),args.workers):
            list(pool.map(execute,queue[offset:offset+args.workers]))
            print(min(len(queue),offset+args.workers),"/",len(queue),flush=True)


if __name__=="__main__":
    main()
