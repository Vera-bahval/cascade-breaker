"""Execute a frozen family schedule in isolated processes; collect summary without gold."""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import json
from contextlib import closing
import os
from pathlib import Path
import random
import sqlite3
import subprocess
import sys

from .enforce import ARMS
from .live import ROOT


def method_fingerprint():
    digest=hashlib.sha256()
    sources=[*sorted((ROOT/"finbot/finbot").rglob("*.py")), *sorted((ROOT/"scenarios/runner").glob("*.py"))]
    sources.extend(ROOT/"experiments/payment_controls"/name for name in (
        "live_smoke.py","probe_models.py","study/live.py","study/enforce.py","study/development.py"))
    for path in sources:
        digest.update(path.relative_to(ROOT).as_posix().encode()+b"\0"+hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def check_jev(runtime, name):
    entries=runtime/name/"jev-requests.jsonl"
    if entries.exists():
        with entries.open() as stream, closing(sqlite3.connect(runtime/"jev.sqlite")) as db:
            for row in map(json.loads,stream):
                receipt=db.execute("SELECT status,cost FROM requests WHERE id=?",(row["id"],)).fetchone()
                if receipt is None or receipt[0]!="complete" or receipt[1] is None:
                    raise RuntimeError(f"Unreconciled official Jev request in {name}")


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
    fingerprint=None
    if args.split=="test":
        release=json.loads((folder/"launch.json").read_text())
        fingerprint=release["method_sha256"]
        if fingerprint!=method_fingerprint():raise ValueError("Frozen method changed")
        for filename, field in (("schedule.test.csv","schedule_sha256"),("inputs.test.jsonl","inputs_sha256")):
            if hashlib.sha256((folder/filename).read_bytes()).hexdigest()!=release[field]:
                raise ValueError("Blinded test inputs changed after freeze")
        if not release["eligible"] or release["cases"]!=len(jobs(folder,args.split))//7:
            raise ValueError("Blind release and budget sizing required before test")
    queue=jobs(folder,args.split)
    random.Random(1703).shuffle(queue)
    runtime=ROOT/".runtime/payment-controls-chp3/study-live"
    logs=runtime/"batch-logs"
    logs.mkdir(parents=True,exist_ok=True)
    def execute(job):
        name="-".join(job)+"-v3"
        marker=logs/(name+".sha256")
        if (runtime/name/"summary.json").is_file():
            if fingerprint and marker.read_text().strip()!=fingerprint:raise ValueError("Unbound stored method version")
            check_jev(runtime,name)
            return "complete"
        if fingerprint:
            if method_fingerprint()!=fingerprint:raise ValueError("Source drift before dispatch")
            with marker.open("x") as stream:stream.write(fingerprint+"\n")
        env=dict(os.environ,FINBOT_STUDY_PHASE={"cal":"development","test":"test","transfer":"transfer"}[args.split])
        if args.split!="transfer":env["FINBOT_STUDY_INPUT"]=str(folder/f"inputs.{args.split}.jsonl")
        if job[1] in ("off","early-rules","late-rules"):
            env.pop("TYPESAFE_API_KEY",None)
        with (logs/(name+".log")).open("xb") as log:
            result=subprocess.run([sys.executable,"-m","experiments.payment_controls.study.live",*job],
                                  cwd=ROOT,env=env,stdout=log,stderr=log)
        if result.returncode == 0:
            check_jev(runtime,name)
            if fingerprint and method_fingerprint()!=fingerprint:raise ValueError("Source drift during episode")
        if result.returncode == 0:
            with closing(sqlite3.connect(runtime/name/"finbot.db")) as db:
                if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] or db.execute("PRAGMA quick_check").fetchone()!=("ok",):
                    raise RuntimeError(f"Could not checkpoint {name}")
        if result.returncode:
            raise RuntimeError(f"Incomplete episode {name}. Check ledger before resumption")
        return "complete"
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        todo=iter(queue)
        pending={pool.submit(execute,job) for _,job in zip(range(args.workers),todo)}
        completed=0
        while pending:
            finished,pending=wait(pending,return_when=FIRST_COMPLETED)
            for task in finished:
                task.result()
                completed+=1
            for _,job in zip(finished,todo):
                pending.add(pool.submit(execute,job))
            if completed%20==0 or not pending:print(completed,"/",len(queue),flush=True)



if __name__=="__main__":
    main()
