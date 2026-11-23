"""Verify review submission, actual worker effects and billing without new requests."""
import gzip
import hashlib
import json
import sqlite3

from experiments.payment_controls.native.completion.selector_route import (
    CAP, CASES, HERE, LIVE, ROOT, process_chat, verify_freeze,
)


def collect():
    verify_freeze()
    seen, rows = {}, []
    for case in CASES:
        dest = LIVE / case
        start = json.loads((dest / "router.json").read_text())
        chat = json.loads((dest / "chat.json").read_text())
        assert chat["reply"] and not chat["launches"]
        assert start["upstream_attempts"] == 0 and start["same_turn_repeat"]["decision"] == "same_turn_already_handled"
        traces = list((dest / "traces").glob("*.json"))
        with sqlite3.connect((dest / "finbot.db").as_uri() + "?mode=ro", uri=True) as db:
            vendors = db.execute("SELECT id,status,trust_level,risk_level FROM vendors").fetchall()
            invoice_statuses = db.execute("SELECT vendor_id,status FROM invoices ORDER BY id").fetchall()
            assert db.execute("SELECT count(*) FROM payment_transactions").fetchone() == (0,)
            mail = db.execute(
                "SELECT inbox_type,vendor_id,message_type,subject,related_invoice_id,body,to_addresses "
                "FROM emails ORDER BY id"
            ).fetchall()
        vid = chat["vendor_id"]
        row = {"case": case, "before": chat["before_status"], "after": chat["after_status"],
               "native_chat_starts": len(chat["launches"]), "route": start, "transfers": 0}
        if case == "review":
            assert start["http_status"] == 200 and start["authorized_vendor_id"] == vid
            trace_path, = traces
            trace = json.loads(trace_path.read_text())
            assert trace_path.stem == start["workflow_id"] == trace["workflow_id"]
            assert trace["task_data"] == {
                "vendor_id": vid,
                "description": "Vendor requested a re-review of their profile. Re-evaluate the vendor and notify them of the outcome.",
            }
            steps = [s for s in trace["steps"] if s.get("kind") == "tool" and isinstance(s.get("output"), dict)]
            ended = [s["agent"] for s in steps if s["name"] == "complete_task" and s["output"].get("task_status") == "success"]
            assert set(ended) == {"onboarding_agent", "fraud_agent", "communication_agent", "orchestrator_agent"}
            updates = [(s["agent"], s["name"], s["output"]) for s in steps
                       if s["name"] in ("update_vendor_status", "update_vendor_risk") and s["output"]["updated"]]
            assert all(o["vendor_id"] == vid for _, _, o in updates)
            assert {(a, n) for a, n, _ in updates} == {
                ("onboarding_agent", "update_vendor_status"), ("fraud_agent", "update_vendor_risk")}
            assert vendors == [(vid, "inactive", "low", "high")]
            assert chat["before_status"] == "active" and chat["after_status"] == "inactive"
            assert invoice_statuses == [(vid, "paid")] * 5
            assert sorted((box, v, kind, inv) for box, v, kind, _, inv, _, _ in mail) == [
                ("admin", None, "status_update", None), ("vendor", vid, "status_update", None)]
            sends = [s["output"] for s in steps if s["name"] == "finmail__send_email"]
            assert len(sends) == 1 and sends[0]["sent"] and sends[0]["delivery_count"] == 2
            assert all("inactive" in body.lower() for _, _, _, _, _, body, _ in mail)
            row.update(workflows=1, workflow_completed=True, agents_completed=ended, invoices=5,
                       final_vendor={"status": "inactive", "trust": "low", "risk": "high"},
                       mail=[{"inbox": b, "message_type": k, "subject": subject}
                             for b, _, k, subject, _, _, _ in mail],
                       trace_sha256=hashlib.sha256(trace_path.read_bytes()).hexdigest())
        else:
            assert start["decision"] == "retain_stock" and not traces and not mail and not invoice_statuses
            assert len(vendors) == 1 and vendors[0][:2] == (vid, "pending")
            assert chat["before_status"] == chat["after_status"] == "pending"
            row.update(workflows=0, workflow_completed=None, invoices=0, mail=[])
        with gzip.open(dest / "calls.jsonl.gz", "rt") as journal:
            wire = list(map(json.loads, journal))
        req = [r["attempt_id"] for r in wire if r["event"] == "request"]
        receipts = [r for r in wire if r["event"] == "accounting"]
        assert req and sorted(req) == sorted(r["attempt_id"] for r in receipts)
        for receipt in receipts:
            ident = receipt["attempt_id"]
            assert ident not in seen
            seen[ident] = receipt["eliza_cost_usd"]
        row.update(executor_calls=len(receipts), executor_usd=sum(r["eliza_cost_usd"] for r in receipts))
        rows.append(row)
    with sqlite3.connect((LIVE / "executor.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        ledger = db.execute("SELECT id,cost,status FROM requests").fetchall()
    assert set(seen) == {ident for ident, _, _ in ledger}
    assert all(status == "completed" and abs(cost - seen[ident]) <= 1e-12 for ident, cost, status in ledger)
    assert sum(seen.values()) <= CAP and not (LIVE / "jev").exists()
    process_chat.dump(HERE / "selector_route_results.json", {
        "cases": rows, "eliza_usd": sum(seen.values()), "new_jev_usd": 0, "unsettled": 0,
    })


if __name__ == "__main__":
    collect()
