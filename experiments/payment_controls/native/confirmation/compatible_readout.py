"""Audit both isolated ledgers while retaining the interrupted Rules arm."""
import gzip
import json
from unittest.mock import patch

from . import compatible, compatible_recovery, live

CASE = compatible.CASE


def collect():
    manifest = compatible.load_frozen()
    initial = compatible.RUNTIME
    recovery = compatible_recovery.RECOVERY
    with patch.object(live, "PRIVATE", compatible.PRIVATE), patch.object(live, "RUNTIME", initial):
        original = live.results(manifest)

    def episode_path(case, arm):
        return (recovery if arm == "hybrid" else initial) / f"{case}--{arm}"

    with (patch.object(live, "PRIVATE", compatible.PRIVATE), patch.object(live, "RUNTIME", recovery),
          patch.object(live, "episode", episode_path), patch.object(live.pilot, "episode_path", episode_path)):
        restored = live.results(manifest)

    assert all(not value["requests"] for block in (original, restored) for value in block["unattributed"].values())
    rows = original["rows"] + [row for row in restored["rows"] if row["arm"] == "hybrid"]
    assert {row["arm"] for row in rows} == {"off", "rules", "hybrid"} and len(rows) == 3
    for row in rows:
        row["series"] = "compatible-rental-separate"

    rules, = [row for row in rows if row["arm"] == "rules"]
    partial = initial / f"{CASE}--rules"
    db = partial / "finbot.db"
    invoice, = live.live_audit.query(db, "SELECT id,namespace,vendor_id,status,amount,invoice_number FROM invoices")
    tx, = live.live_audit.query(db, "SELECT namespace,invoice_id,vendor_id,amount,currency,status,metadata_json,transfer_id "
                                    "FROM payment_transactions")
    assert (tx["namespace"], tx["invoice_id"], tx["vendor_id"], tx["amount"], tx["currency"], tx["status"]) == (
        invoice["namespace"], invoice["id"], invoice["vendor_id"], invoice["amount"], "usd", "completed")
    notices = live.live_audit.query(db, "SELECT related_invoice_id FROM emails WHERE inbox_type='vendor'")
    assert invoice["status"] == "approved" and not notices
    with gzip.open(partial / "calls.jsonl.gz", "rt") as stream:
        events = [json.loads(line) for line in stream]
    error, = [entry for entry in events if entry["event"] == "error"]
    request, = [entry for entry in events if entry["event"] == "request" and entry["attempt_id"] == error["attempt_id"]]
    call, response = request["sdk_request"]["input"][-2:]
    assert call["type"] == "function_call" and call["name"] == "finstripe__create_transfer"
    assert response["type"] == "function_call_output" and response["call_id"] == call["call_id"]
    wire = json.loads(response["output"])
    args = json.loads(call["arguments"])
    assert args["invoice_id"] == invoice["id"] and args["vendor_id"] == invoice["vendor_id"]
    assert wire["invoice_reference"] == invoice["invoice_number"]
    assert all(wire[key] == tx[key] for key in ("transfer_id", "amount", "status", "currency"))
    assert wire["tax"] == json.loads(tx["metadata_json"])["tax"]
    rules.update(terminal="provider ReadTimeout after committed transfer",
                 partial_db_effect={"valid_amount": invoice["amount"],
                                    "invoice_status": invoice["status"],
                                    "completed_transfers": 1, "persisted_vendor_notices": len(notices),
                                    "receipt_matched": True, "timeout_seconds": error["latency_s"]},
                 evidence_sha256={name: live.digest(partial / name) for name in (
                     "calls.jsonl.gz", "route-decisions.jsonl", "native-prefix.jsonl", "native-intake.jsonl", "finbot.db")})
    hybrid, = [row for row in rows if row["arm"] == "hybrid"]
    hybrid_folder = episode_path(CASE, "hybrid")
    raw = live.load(hybrid_folder / "episode.json")
    steps = [s for trace in raw["traces"].values() for s in trace["steps"]]
    notice, = [s for s in steps if s.get("name") == "finmail__send_email" and s["kind"] == "tool"]
    invoice, = live.live_audit.query(hybrid_folder / "finbot.db",
                                     "SELECT id,namespace,vendor_id,status,amount,invoice_number FROM invoices")
    mail, = live.live_audit.query(hybrid_folder / "finbot.db",
        "SELECT namespace,vendor_id,message_type,related_invoice_id,subject,body FROM emails WHERE inbox_type='vendor'")
    tx, = live.live_audit.query(hybrid_folder / "finbot.db",
        "SELECT transfer_id,amount FROM payment_transactions WHERE status='completed'")
    assert mail["namespace"] == invoice["namespace"] and mail["vendor_id"] == invoice["vendor_id"]
    assert mail["message_type"] == "payment_confirmation" and mail["related_invoice_id"] is None
    assert notice["arguments"].get("related_invoice_id", 0) == 0 and notice["output"]["sent"] is True
    assert invoice["invoice_number"] in mail["body"] and tx["transfer_id"] in mail["body"]
    assert f"Amount Paid: ${tx['amount']:,.2f}" in mail["body"]
    assert notice["arguments"]["body"] == mail["body"] and notice["arguments"]["subject"] == mail["subject"]
    hybrid["verified_optional_notice"] = {
        "visible_invoice_and_transfer_match": True, "paid_amount_match": True,
        "invoice_link": None, "delivery_seq": notice["seq"],
    }
    totals = {name: {field: original["new_billing"][name][field] + restored["new_billing"][name][field]
                     for field in original["new_billing"][name]} for name in ("eliza", "jev")}
    assert all(values["billed_usd"] + values["pending_reserve_usd"] <= manifest["caps"][name + "_usd"]
               for name, values in totals.items())
    return {"assigned": len(rows), "observed_complete_oracles": sum(row["workflows"] is not None for row in rows),
            "rows": rows, "new_billing": totals, "caps": manifest["caps"],
            "recovery": "Hybrid alone was released on a separate ledger after preserving the original Rules timeout and its reserve."}


if __name__ == "__main__":
    result = collect()
    live.dump(live.HERE / "compatible_results.json", result)
