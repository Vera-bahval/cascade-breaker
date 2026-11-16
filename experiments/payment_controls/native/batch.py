"""Run the frozen native diagnostic schedule. Each job uses a fresh FinBot process and database."""
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from experiments.payment_controls.study.batch import check_jev
from experiments.payment_controls.study.enforce import ARMS
from experiments.payment_controls.live_smoke import ROOT

HERE=Path(__file__).resolve().parent
RUNTIME=ROOT/".runtime/payment-controls-chp3/study-live"
VERSION="native1"


def run_one(job):
    channel,arm,family=job
    name="-".join((*job,VERSION))
    target=RUNTIME/name
    if (target/"summary.json").exists():
        check_jev(RUNTIME,name)
        return
    env={**os.environ,"FINBOT_NATIVE_FIXTURES":str(HERE/"fixtures.json"),"FINBOT_STUDY_PHASE":"development","FINBOT_STUDY_VERSION":VERSION}
    if arm=="off" or arm.endswith("rules"):env.pop("TYPESAFE_API_KEY",None)
    log=RUNTIME/"batch-logs"/(name+".log")
    with log.open("xb") as out:
        subprocess.run([sys.executable,"-m","experiments.payment_controls.study.live",channel,arm,family],
                       cwd=ROOT,env=env,stdout=out,stderr=out,check=True)
    check_jev(RUNTIME,name)


if __name__=="__main__":
    data=(HERE/"fixtures.json").read_bytes()
    freeze=json.loads((HERE/"diagnostic_freeze.json").read_text())
    if hashlib.sha256(data).hexdigest()!=freeze["fixtures_sha256"]:
        raise ValueError("Changed diagnostic fixtures")
    jobs=[(row["channel"],arm,row["id"]) for row in json.loads(data) for arm in ARMS]
    random.Random(1601).shuffle(jobs)
    with ThreadPoolExecutor(max_workers=3) as pool:
        for index in range(0,len(jobs),3):
            list(pool.map(run_one,jobs[index:index+3]))
            print(min(index+3,len(jobs)),len(jobs),flush=True)
