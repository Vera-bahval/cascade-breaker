"""Rebuild restart effects and costs from recorded native traces and read-only SQLite."""
from collections import Counter
from contextlib import closing
import gzip
from hashlib import sha256
import json
import sqlite3

from . import restart as r
from ..checkpoint.live_audit import accounting, query


def old_state(relative):
    db = (r.WORK.parent / relative / "finbot.db").resolve()
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
        inv, = conn.execute("SELECT namespace, status, amount FROM invoices WHERE amount IN (2800, 4900)")
        notices = conn.execute("SELECT message_type FROM emails WHERE direction='outbound' AND inbox_type='vendor'").fetchall()
        transfers = conn.execute("SELECT namespace, amount, currency, status, transfer_id FROM payment_transactions").fetchall()
        assert all(t[0] == inv[0] for t in transfers)
    return {"database_relative_path": str(db.relative_to(r.WORK.parent)), "namespace_sha256": sha256(inv[0].encode()).hexdigest(),
            "invoice_status": inv[1], "amount": inv[2], "completed_transfers": sum(t[3] == "completed" for t in transfers),
            "receipt_sha256": [sha256(t[4].encode()).hexdigest() for t in transfers], "mail_types": [m[0] for m in notices]}


def rebuild():
    freeze = r.load(r.FREEZE)
    assert freeze == r.plan()
    historical = [old_state(name) for name in (
        "native-confirmation-live/TH510@B--hybrid",
        "native-confirmation-live-recovery/TH510@B--hybrid",
        "native-confirmation-live-recovery/TH510@B--rules",
        "native-confirmation-compatible-live/P4900-base@B--rules",
        "native-confirmation-compatible-live-rules-replica/P4900-base@B--rules")]
    assert len({x["namespace_sha256"] for x in historical}) == len(historical)
    assert len({rid for x in historical for rid in x["receipt_sha256"]}) == 4
    raw = query(r.WORK / "executor.sqlite", "SELECT id,reserve,cost,status FROM requests")
    requests = {row["id"]: row for row in raw}
    attributed = set()
    rows = []
    summaries = {}
    for dest in sorted(p for p in r.WORK.iterdir() if p.is_dir() and "--" in p.name):
        _, fault, arm, mode = dest.name.split("--")
        resumed = dest / "retry_trace.json"
        before = r.load(dest / "reopened.json")
        init = r.load(dest / "initial_trace.json")
        key = r.load(dest / "key.json")
        assert len(before["invoice"]) == 1 and before["invoice"][0]["namespace"] == key["namespace"]
        assert len(before["transfers"]) == (fault != "before_transfer")
        assert not before["mail"]
        calls = dest / "calls.jsonl.gz"
        evidence = [dest / "initial_trace.json", dest / "reopened.json"]
        if resumed.exists():
            result = r.effects(dest, fault, arm, mode == "live")
            assert result == r.load(dest / "effects.json")
            evidence.append(resumed)
        else:
            result = {"case": key["ref"].removeprefix("INV-RESTART-"), "fault": fault, "arm": arm,
                      "live": mode == "live", "error": "no continuation trace", "complete": False}
        if calls.exists():
            with gzip.open(calls, "rt") as stream:
                events = [json.loads(line) for line in stream]
            ids = {e["attempt_id"] for e in events if e["event"] == "request"}
            assert ids <= requests.keys() and not (attributed & ids)
            attributed |= ids
            result["eliza"] = accounting([requests[i] for i in sorted(ids)])
            evidence.append(calls)
        for event in init:
            if event.get("name") == "finstripe__create_transfer":
                assert event["output"] == r.load(dest / "receipt.json")
                evidence.append(dest / "receipt.json")
        result["evidence_sha256"] = {p.name: sha256(p.read_bytes()).hexdigest() for p in evidence}
        rows.append(result)
        key = "/".join((mode, fault, arm))
        group = summaries.setdefault(key, Counter())
        group["cells"] += 1
        group["complete"] += result["complete"]
        group["new_transfers"] += result.get("new_transfers", 0)
        group["duplicates_simulated_usd"] += result.get("duplicate_simulated_usd", 0)
        group["precise_notice"] += result.get("precise_notice", False)
        group["technical"] += bool(result.get("error"))
    # An interruption may precede the attempt-event write. Keep all reservations in the cap.
    unattributed = accounting([requests[i] for i in sorted(requests.keys() - attributed)])
    bill = accounting(raw)
    assert bill["billed_usd"] + bill["pending_reserve_usd"] <= r.CAP
    return {"historical_checkpoints": historical, "groups": summaries, "rows": rows,
            "eliza": bill, "unattributed_eliza": unattributed, "jev_requests": 0}


if __name__ == "__main__":
    print(json.dumps(rebuild(), indent=2, sort_keys=True))
