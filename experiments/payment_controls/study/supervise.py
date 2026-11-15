"""Drain interrupted batches, settle an exact zero meter residual, and resume the frozen queue."""
import gzip
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from experiments.local_guards_archive_comparison.eliza import metadata
from .live import ROOT
from .recover import LIVE, reconcile, recover


def accounting_status():
    with sqlite3.connect(LIVE/"executor.sqlite") as db:
        return dict(db.execute("SELECT status,count(*) FROM requests GROUP BY status").fetchall())


def readback(file):
    data=dict(time=time.time(),remaining=metadata()["remaining"])
    file.write_text(json.dumps(data))


def repair():
    counts=accounting_status()
    if counts.get("reserved"):
        raise ValueError("Executor still has in-flight reservations")
    if counts.get("unknown"):
        stamp=str(time.time_ns())
        previous=LIVE/f"meter-{stamp}-0.json"
        readback(previous)
        for i in range(1,6):
            time.sleep(50)
            current=LIVE/f"meter-{stamp}-{i}.json"
            readback(current)
            try:
                reconcile([previous,current])
                break
            except ValueError as exc:
                if str(exc)!="Provider meter does not exactly explain known charges" or i==5:raise
                previous=current
    preflight=LIVE/"preflight-denied-no-wire"
    preflight.mkdir(exist_ok=True)
    repaired=0
    for log in sorted((LIVE/"batch-logs").glob("*.log")):
        episode=LIVE/log.stem
        if not episode.exists() or (episode/"summary.json").is_file():continue
        text=log.read_text()
        if not any(reason in text for reason in ("Unreconciled or failed request","ReadTimeout","HTTP 504")):
            raise RuntimeError(f"Investigate {log.stem}")
        if (episode/"calls.jsonl.gz").exists():
            recover(episode.name)
        else:
            if (episode/"jev-requests.jsonl").exists():raise ValueError("Unexpected paid guard receipt before executor")
            suffix=str(time.time_ns())
            episode.rename(preflight/(episode.name+"-"+suffix))
            log.rename(preflight/(log.name+"-"+suffix))
            marker=log.with_suffix(".sha256")
            if marker.exists():marker.rename(preflight/(marker.name+"-"+suffix))
        repaired+=1
    if not repaired:
        raise ValueError("No recoverable interrupted episodes")


def main():
    args=list(sys.argv[1:])
    for _ in range(16):
        result=subprocess.run([sys.executable,"-m","experiments.payment_controls.study.batch",*args],cwd=ROOT)
        if result.returncode==0:return
        if accounting_status().get("unknown",0)>1 and "--workers" in args:
            idx=args.index("--workers")+1
            args[idx]=str(min(int(args[idx]),3))
        repair()
    raise RuntimeError("Repeated executor instability; inspect study before further expenditure")


if __name__=="__main__":
    main()
