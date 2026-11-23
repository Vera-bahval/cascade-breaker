"""Verify paid executor and verifier ledgers against retained episode receipts."""
from collections import Counter, defaultdict
from contextlib import closing
import gzip
from hashlib import sha256
import json
from math import isclose
import sqlite3

from .. import jev, live
from .live import run
from .panel import prefraud


def billing(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return {key: (status, reserve, cost) for key, status, reserve, cost in db.execute(
            "SELECT id,status,reserve,cost FROM requests")}


def settle(entries, ident, charge, *, interrupted=False):
    status, reserve, billed = entries.pop(ident)
    allowed = {"unknown"} if interrupted else {"complete", "completed"}
    if status not in allowed or charge != billed or charge > reserve + 1e-9:
        raise ValueError("Charge differs from the provider ledger")
    return charge


def replay_jev(private, entries, dest, arm, selections, counts):
    observations = dest / "verifier.json"
    total = 0
    for row in live.read(observations) if observations.exists() else []:
        packet, record = row["packet"], row["result"]
        counts[(arm, row["point"], row["outcome"])] += 1
        if record is None:
            continue
        point = packet["checkpoint"]
        if (arm, point) not in {("B", "P1"), ("C", "P4")}:
            raise ValueError("Jev called outside the assigned placement boundary")
        selected = selections[point]
        expected = jev.wire(jev.packet_body(packet, selected["question"], selected["fraud"]))
        req = private / "jev" / "attempts" / packet["id"] / (record["occurrence"] + ".request")
        if sha256(expected).hexdigest() != record["request_sha256"] or req.read_bytes() != expected:
            raise ValueError("Observed Jev wire differs from frozen placement")
        total += settle(entries, packet["id"], record["cost_usd"])

    pre = dest / "pre-fraud-jev.jsonl"
    if pre.exists():
        packets = {r["owner"]: r["packet"] for r in run.jsonl(dest / "pre-fraud-packets.jsonl")}
        for row in run.jsonl(pre):
            record = row.get("result")
            counts[(arm, "pre_fraud_raw", record["decision"] if record else "ERROR")] += 1
            counts[(arm, "pre_fraud_effective", row["action"])] += 1
            if record is None:
                continue
            if arm != "E":
                raise ValueError("Jev pre-Fraud called outside E")
            expected = jev.wire(prefraud.body(packets[row["owner"]]))
            req = private / "jev" / (record["occurrence"] + ".request")
            if sha256(expected).hexdigest() != record["request_sha256"] or req.read_bytes() != expected:
                raise ValueError("Observed Jev wire differs from frozen pre-Fraud intake")
            total += settle(entries, record["occurrence"], record["cost_usd"])
    return total


def reconcile():
    private = run.PRIVATE
    freeze = run.approved()
    folder = private / "test"
    plan = run.collect(freeze)
    eliza = billing(folder / "executor.sqlite")
    guard = billing(private / "jev/ledger.sqlite")
    initial = defaultdict(set)
    by_arm = defaultdict(Counter)
    checkpoints = Counter()
    verifier = Counter()
    for group in freeze["groups"]:
        cell = group["cell"]
        for arm in group["arms"]:
            for retry in range(run.RETRY_MAX + 1):
                name = run.name_for(cell, arm, retry)
                dest = folder / name
                state = run.status(folder, cell, arm, retry)
                if state == "unstarted":
                    continue
                summary = by_arm[(cell["kind"], arm)]
                summary["retry" if retry else "first"] += 1
                summary[state] += 1
                calls = dest / "calls.jsonl.gz"
                cost = count = 0
                interrupted_charges = {}
                if calls.exists():
                    with gzip.open(calls, "rt") as stream:
                        for row in map(json.loads, stream):
                            if row["case_id"] != name:
                                raise ValueError("Eliza receipt belongs to another assignment")
                            ident = row["attempt_id"]
                            if row["event"] == "response" and row.get("http_status") == 200 and (
                                eliza.get(ident, (None,))[0] == "unknown" and "cost" in row.get("body", {})
                            ):
                                interrupted_charges[ident] = row["body"]["cost"]
                            if row["event"] == "accounting":
                                cost += settle(eliza, ident, row["eliza_cost_usd"])
                                count += 1
                for ident, quoted in interrupted_charges.items():
                    summary["eliza_failed_response_charge_usd"] += settle(eliza, ident, quoted, interrupted=True)
                summary["eliza_usd"] += cost
                summary["requests"] += count
                summary["jev_usd"] += replay_jev(private, guard, dest, arm, freeze["model"], verifier)
                if state != "terminal":
                    continue
                record = live.read(dest / "episode.json")
                if record["cell"] != cell or record["arm"] != arm or record["attempt"] != retry:
                    raise ValueError("Terminal episode differs from the frozen assignment")
                operational = record["operational"]
                if not isclose(cost, operational["eliza_usd"], abs_tol=1e-9) or count != operational["requests"]:
                    raise ValueError("Episode summary differs from its transport ledger")
                initial[cell["source_cell"]].add(record["initial_state_sha256"])
                for trace in record["traces"].values():
                    for row in trace["steps"]:
                        if row.get("kind") == "finale_boundary":
                            checkpoints[(arm, row["point"])] += 1
                        elif row.get("kind") == "finale_payment_stop":
                            checkpoints[(arm, row["point"] + "_stop")] += 1
    if any(len(values) != 1 for values in initial.values()):
        raise ValueError("Independent attempts disagree on normalized initial state")
    remaining = lambda book: {
        "settled_unlinked": sum(cost for _, _, cost in book.values() if cost is not None),
        "reserved_unlinked": sum(reserve for _, reserve, cost in book.values() if cost is None),
        "request_count_unlinked": len(book),
    }
    return {"freeze_sha256": live.digest(run.PLAN), "model": freeze["model"],
            "assignments": plan["summary"], "meters": plan["meter"],
            "normalized_initial_families": len(initial),
            "cost_by_kind_arm": {".".join(k): dict(v) for k, v in by_arm.items()},
            "checkpoints": {".".join(k): v for k, v in checkpoints.items()},
            "verifier": {".".join(k): v for k, v in verifier.items()},
            "remaining_eliza": remaining(eliza), "remaining_jev": remaining(guard)}


if __name__ == "__main__":
    print(json.dumps(reconcile(), indent=2, sort_keys=True))
