"""Freeze four posthoc comparison strata and run one native suffix per arm."""

import argparse
import asyncio
from contextlib import closing
from decimal import Decimal
import fcntl
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from . import restore, resume

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[6]
SOURCE = ROOT / ".runtime/payment-controls-chp3/final-study-payment-finale/test"
PRIVATE = ROOT / ".runtime/finbot-final-study/policy-corrected-continuations-v1"
PLAN = HERE / "freeze.json"
PRIMARY = HERE.parent / "guards/primary-results.json"
SEED = "finbot-corrected-native-continuations-2026-11-23-v1"
PREKNOWN = {"TH601", "TH612", "TH614", "TH626", "TH692"}
CAP = 5.0
STRATA = ("DS_INTERVENES", "JEV_INTERVENES", "BOTH_ALLOW", "BOTH_INTERVENE")


def sha(path):
    return restore.digest(path.read_bytes())


def capture_for(row):
    return f"{row['point']}-{row['capture']:03}.json"


def key(row):
    return row["assignment"], row["point"], row["capture"]


def select(scores):
    guard_hash = sha(scores)
    data = restore.read(scores)
    rows = [row for row in data["rows"] if row["source"] == "modern"]
    if any(not row["gold"] for row in rows):
        raise ValueError("The working responses require a finalized source-aware policy overlay")
    groups = {stratum: [] for stratum in STRATA}
    eligible = {"ALLOW", "BLOCK", "REVIEW"}
    if len(rows) != 391 or any(r[a]["status"] == "not_attempted" for r in rows for a in ("jev", "native_source")):
        raise ValueError("Freeze requires the complete reached cohort and settled primary attempts")
    if sum(r["jev"]["status"] == r["native_source"]["status"] == "valid" for r in rows) == 0:
        raise ValueError("No working paired wire responses")
    for row in rows:
        if row["family"] in PREKNOWN or row["jev"]["status"] != "valid" or row["native_source"]["status"] != "valid":
            continue
        ds, j = row["native_source"]["choice"], row["jev"]["effective"]
        if ds not in eligible or j not in eligible:
            continue
        if row["gold"]["label"] not in {"ADMISSIBLE", "MUST_STOP_OR_REVIEW"}:
            continue
        stratum = {
            (True, True): "BOTH_ALLOW", (False, False): "BOTH_INTERVENE",
            (False, True): "DS_INTERVENES", (True, False): "JEV_INTERVENES",
        }[ds == "ALLOW", j == "ALLOW"]
        row["selection_hash"] = restore.record_hash([SEED, stratum, *key(row)])
        groups[stratum].append(row)

    planned = {}
    excluded = set(PREKNOWN)
    for stratum, candidates in groups.items():
        failures = []
        chosen = None
        for row in sorted(candidates, key=lambda r: r["selection_hash"]):
            if row["family"] in excluded:
                continue
            source = SOURCE / row["assignment"]
            capture = capture_for(row)
            try:
                process = subprocess.run(
                    [sys.executable, "-m", __package__ + ".resume", str(source), capture],
                    cwd=ROOT, text=True, capture_output=True, timeout=30, check=True
                )
                preflight = json.loads(process.stdout)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as error:
                failures.append({"id": row["id"], "selection_hash": row["selection_hash"],
                                 "error_type": type(error).__name__})
                continue
            # Order the matched suffix calls deterministically independently of arm identity.
            decisions = {"stock": "ALLOW", "deepseek": row["native_source"]["choice"],
                         "jev": row["jev"]["effective"]}
            order = sorted(decisions, key=lambda arm: restore.record_hash([SEED, row["id"], arm]))
            chosen = {**{k: row[k] for k in ("id", "assignment", "family", "channel", "point", "capture",
                                             "selection_hash", "gold", "wires")}, "decisions": decisions,
                      "order": order, "archive_restore": preflight["restore"],
                      "source_request_hashes": preflight["replay"]["source_request_hashes"]}
            excluded.add(row["family"])
            break
        planned[stratum] = {"eligible_count_before_cross_stratum_exclusion": len(candidates),
                            "row": chosen, "rejected_by_preflight": failures}
    return {"guard_results_sha256": guard_hash, "provider_cap_usd": CAP, "seed": SEED,
            "preknown_families": sorted(PREKNOWN), "selection": planned,
            "code_sha256": {p.name: sha(p) for p in sorted(HERE.glob("*.py"))}}


def deltas(clone, namespace, before=None):
    with closing(sqlite3.connect(clone.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = {
            table: [dict(row) for row in db.execute(
                f"SELECT {fields} FROM {table} WHERE namespace=? ORDER BY id", (namespace,)
            )] for table, fields in {
                "payment_transactions": "id,invoice_id,vendor_id,amount,currency,payment_method,status,transfer_id,metadata_json",
                "emails": "id,vendor_id,related_invoice_id,direction,inbox_type,message_type,channel,to_addresses,subject,body",
            }.items()
        }
    if before is None:
        return rows
    return {table: [row for row in values if row not in before[table]] for table, values in rows.items()}


async def execute(row, arm):
    from .... import live, live_meter
    from ...live.meter import ledger

    source = SOURCE / row["assignment"]
    capture_file = source / capture_for(row)
    capture = restore.read(capture_file)
    path = PRIVATE / f"{row['id']}-{arm}"
    verified = restore.restore(source, capture_file, path)
    if verified != row["archive_restore"]:
        raise ValueError("Archived restore changed after freeze")
    clone = path / "finbot.db"
    initial = deltas(clone, capture["namespace"])
    with patch.object(live_meter, "live_ledger", ledger):
        async with live.session(path, PRIVATE / "executor.sqlite", CAP, "test"):
            result = await resume.continue_episode(source, capture_file, clone, row["decisions"][arm])
    result["technical_agent_errors"] = [s["seq"] for s in result["steps"]
                                        if s["kind"] == "llm" and s["error"]]
    if result["source_request_hashes"] != row["source_request_hashes"]:
        raise ValueError("Resumed SDK history differs from preflight")
    result["primary_business_deltas"] = deltas(clone, capture["namespace"], initial)
    result["assignment"] = row["assignment"]
    result["boundary_id"] = row["id"]
    result["arm"] = arm
    live.write(path / "continuation.json", result)


def authorized():
    plan = restore.read(PLAN)
    release = restore.read(PRIVATE / "release.json")
    if release != {"reviewer": "root", "approved": True, "freeze_sha256": sha(PLAN)}:
        raise ValueError("Paid continuations require root release of the exact freeze")
    if plan["provider_cap_usd"] != CAP or any(sha(HERE / name) != value for name, value in plan["code_sha256"].items()):
        raise ValueError("Continuation source or budget changed")
    current_scores = PRIMARY
    if sha(current_scores) != plan["guard_results_sha256"]:
        raise ValueError("Compared working policy outputs changed")
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["freeze", "run", "one"])
    parser.add_argument("cell", nargs="?")
    parser.add_argument("arm", nargs="?")
    args = parser.parse_args()
    if args.command == "freeze":
        plan = select(PRIMARY)
        with PLAN.open("x") as file:
            json.dump(plan, file, ensure_ascii=False, indent=2)
    elif args.command == "one":
        plan = authorized()
        selected, = [v["row"] for v in plan["selection"].values() if v["row"] and v["row"]["id"] == args.cell]
        if args.arm not in selected["order"]:
            raise ValueError("Arm is outside the frozen state")
        asyncio.run(execute(selected, args.arm))
    else:
        plan = authorized()
        with (PRIVATE / "dispatch.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for value in plan["selection"].values():
                row = value["row"]
                if row is None:
                    continue
                for arm in row["order"]:
                    path = PRIVATE / f"{row['id']}-{arm}"
                    if path.exists():
                        if not (path / "continuation.json").exists():
                            raise ValueError("Retained interrupted continuation; no automatic retry")
                        continue
                    subprocess.run([sys.executable, "-m", __package__ + ".run", "one", row["id"], arm],
                                   check=True, cwd=ROOT)
