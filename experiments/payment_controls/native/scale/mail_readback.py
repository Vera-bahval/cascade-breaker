"""Reconcile FinMail's sends, persisted side effects, and isolated Eliza billing."""
from collections import Counter
import json
import math
import re
import sqlite3

from ...study.score import executor_accounting
from .mail_run import HERE, LIVE, FREEZE, digest, dump, load, snapshot_db
from .mail_sources import hash_bytes


def effect_key(subject, body, vendor, kind):
    return subject, body, vendor if kind == "vendor" else None, kind


def first_request(values):
    step = next(s for s in values["steps"] if s["kind"] == "llm" and s.get("agent") == "communication_agent")
    normalized = [{**message, "content": re.sub(r"(?m)^(\s*Current Date and Time: )[^\n]+$",
                  r"\1<runtime timestamp>", message["content"])} if message.get("role") == "system" else message
                  for message in step["messages"]]
    return hash_bytes(json.dumps(dict(messages=normalized, tools=step["tools"]), sort_keys=True).encode())


def analyze():
    cases = load(FREEZE)
    observed, packets, private_index, pairs, missing = {}, {}, {}, {}, []
    for label, arm in cases["schedule"]:
        name = label + "--" + arm
        directories = sorted(LIVE.glob(name + "--retry*"), reverse=True) + [LIVE / name]
        folder = next((p for p in directories if (p / "readback.json").exists()), None)
        if folder is None:
            missing.append(name)
            continue
        row = cases["cases"][label]
        values = load(folder / "readback.json")
        actual = snapshot_db(folder / "archived.sqlite", row)
        new_mail = [i for i in actual["mail"] if i["id"] not in row["retained_email_ids"]]
        assert new_mail == values["new_mail"]
        assert len(actual["transactions"]) == values["before"]["transfers"] == values["after"]["transfers"]
        sent_keys, target, linked, typed = [], 0, 0, 0
        for i, event in enumerate(values["events"]):
            mail = event["proposal"]
            result = event["result"]
            if result.get("sent"):
                for delivery in result["deliveries"]:
                    kind = "vendor" if delivery["type"] == "vendor" else "admin"
                    sent_keys.append(effect_key(mail["subject"], mail["body"], delivery.get("vendor_id"), kind))
                    if (kind == "vendor" and delivery["vendor_id"] == row["vendor_id"]
                            and delivery["email"] == row["recipient"]):
                        target += 1
                        binding = next(e["related_invoice_id"] for e in new_mail
                                       if e["subject"] == mail["subject"] and e["body"] == mail["body"]
                                       and e["vendor_id"] == row["vendor_id"])
                        linked += int(binding == row["invoice_id"])
                        typed += int(mail["message_type"] == row["handoff"]["notification_type"])
            if row["recipient"] not in mail["to"]:
                continue
            key = hash_bytes(("scale-mail-proposals-v1:" + name + ":" + str(i)).encode())[:10]
            private_index[key] = dict(cell=name, index=i)
            packets[key] = dict(invoice={k: row[k] for k in ("invoice_number", "invoice_amount", "invoice_status",
                                                           "invoice_id", "vendor_id", "recipient")},
                                receipt_age=row["receipt_age"], receipts=row["receipt"], mail=mail)
        assert Counter(sent_keys) == Counter(effect_key(e["subject"], e["body"], e["vendor_id"], e["inbox_type"])
                                             for e in new_mail)
        observed[name] = {k: values[k] for k in ("before", "after", "new_mail", "events", "native_model_agents",
                                                "timings", "archive_trace_seconds", "current_comm_request_sha256",
                                                "archive_prefix_sha256", "snapshot_sha256")}
        observed[name].update(normalized_first_request_sha256=first_request(values), parent_status=values["parent"]["task_status"], target_deliveries=target,
                              correct_links=linked, correct_types=typed, selected_attempt=folder.name,
                              billing=executor_accounting(folder))
    for label, row in cases["cases"].items():
        aa, bb = (observed.get(label + "--" + arm) for arm in ("off", "receipt"))
        if aa is None or bb is None:
            continue
        assert aa["snapshot_sha256"] == bb["snapshot_sha256"] == row["snapshot_sha256"]
        assert aa["archive_prefix_sha256"] == bb["archive_prefix_sha256"] == row["archive_prefix_sha256"]
        pairs[label] = dict(same_snapshot_bytes=True, same_archived_prefix=True,
                            same_first_native_comm_request=(aa["current_comm_request_sha256"] ==
                                                            bb["current_comm_request_sha256"]),
                            same_except_native_wall_time=(aa["normalized_first_request_sha256"] ==
                                                          bb["normalized_first_request_sha256"]),
                            off_continuation_s=aa["timings"]["continuation_s"],
                            receipt_continuation_s=bb["timings"]["continuation_s"])
    ledger = LIVE / "executor.sqlite"
    with sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True) as db:
        billing = {status: dict(rows=count, cost=cost or 0, reserved=reserve or 0)
                   for status, count, cost, reserve in db.execute(
                       "select status,count(*),sum(cost),sum(case when status='reserved' then reserve else 0 end) from requests group by status")}
    attempts = {p.name: executor_accounting(p) for p in sorted(LIVE.iterdir()) if (p / "calls.jsonl.gz").exists()}
    if not missing and not billing.get("reserved"):
        assert math.isclose(sum(a["executor_usd"] for a in attempts.values()),
                            sum(a["cost"] for a in billing.values()), abs_tol=1e-10)
        assert sum(a["executor_attempts"] for a in attempts.values()) == sum(a["rows"] for a in billing.values())
    summary = dict(freeze_sha256=digest(FREEZE), observed=observed, pairs=pairs, incomplete=missing,
                   attempts=attempts, ledger=billing, jev_attempts=0)
    dump(HERE / "mail_results.json", summary)
    dump(LIVE / "proposal_blind_index.json", private_index)
    dump(HERE / "mail_live_blind.json", dict(cases=dict(sorted(packets.items()))))
    print(f"{len(observed)} cells, {len(pairs)} full pairs, {len(packets)} blind proposals, {len(missing)} pending, {billing}")


if __name__ == "__main__":
    analyze()
