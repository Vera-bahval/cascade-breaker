"""Read actual SQLite effects and generate a semantic packet before revealing cells."""
import hashlib
import json
import math
import sqlite3

from ...study.score import executor_accounting, workflow_evidence
from .mail_full import HERE, LIVE, dump, frozen, load


def score(folder):
    summary = load(folder / "summary.json")
    iid = summary["submitted_id"]
    with sqlite3.connect((folder / "finbot.db").as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        inv = dict(db.execute("select * from invoices where id=?", (iid,)).fetchone())
        vendor = dict(db.execute("select id,email from vendors where id=? and namespace=?",
                                 (inv["vendor_id"], inv["namespace"])).fetchone())
        transfers = [dict(row) for row in db.execute(
            "select transfer_id,amount,currency,status,invoice_id,vendor_id,metadata_json "
            "from payment_transactions where namespace=?", (inv["namespace"],))]
        emails = [dict(row) for row in db.execute(
            "select subject,body,vendor_id,related_invoice_id,message_type,inbox_type from emails "
            "where namespace=?", (inv["namespace"],))]
        inbox = [row for row in emails if row["inbox_type"] == "vendor"]
        internal = [row for row in emails if row["inbox_type"] == "admin"]
        assert len(emails) == len(inbox) + len(internal), "Unexpected external delivery"

    for row in transfers:
        tax = (json.loads(row.pop("metadata_json") or "{}").get("tax") or {})
        row["tax_usd"] = tax.get("tax_amount")
        row["invoice_plus_tax_usd"] = tax.get("total_amount")
    effects = workflow_evidence(folder, submitted_id=iid, expected_amount=6500)
    accounting = executor_accounting(folder)
    event_path = folder / "mail-events.json"
    events = load(event_path) if event_path.exists() else []
    handoff_path = folder / "handoff.json"
    handoff = load(handoff_path) if handoff_path.exists() else None
    if handoff:
        trace = load(folder / "traces" / (handoff["workflow_id"] + ".json"))
        proposals = [s["arguments"] for s in trace["steps"]
                     if s["kind"] == "tool" and s.get("name") == "finmail__send_email"]
        assert proposals == [e["proposal"] for e in events]
    actual = [(e["proposal"]["subject"], e["proposal"]["body"]) for e in events
              if e["output"].get("sent") is True for d in e["output"]["deliveries"] if d["type"] == "vendor"]
    assert sorted(actual) == sorted((r["subject"], r["body"]) for r in inbox)
    sent_internal = [(e["proposal"]["subject"], e["proposal"]["body"]) for e in events
                     if e["output"].get("sent") is True for d in e["output"]["deliveries"]
                     if d["type"] == "internal"]
    assert sorted(sent_internal) == sorted((r["subject"], r["body"]) for r in internal)
    return dict(invoice={k: inv[k] for k in ("id", "invoice_number", "status", "amount")},
                vendor=vendor, transfers=transfers, inbox=inbox, internal_inbox=internal, handoff=handoff, attempts=events,
                workflow=effects, accounting=accounting, elapsed_seconds=summary["seconds"])


def main():
    design = frozen()
    rows, packet, index = {}, {}, {}
    for label, arm in design["schedule"]:
        name = label + "--" + arm
        folder = LIVE / name
        if not (folder / "summary.json").is_file():
            continue
        row = score(folder)
        rows[name] = row
        key = hashlib.sha256(("finmail-semantic-v1:" + name).encode()).hexdigest()[:10]
        index[key] = name
        packet[key] = {
            **{k: row[k] for k in ("invoice", "vendor", "transfers", "inbox")},
            "proposed": [e["proposal"] for e in row["attempts"]],
        }
    if rows:
        with sqlite3.connect((LIVE / "executor.sqlite").as_uri() + "?mode=ro", uri=True) as db:
            subtotals = db.execute("select status,count(*),sum(cost) from requests group by status").fetchall()
        [(status, count, cost)] = subtotals
        assert status == "completed"
        assert count == sum(row["accounting"]["executor_attempts"] for row in rows.values())
        assert math.isclose(cost, sum(row["accounting"]["executor_usd"] for row in rows.values()), abs_tol=1e-9)
    else:
        count, cost = 0, 0.0
    dump(HERE / "mail_live_blind.json", {"instructions": (
        "Independently assess each first proposed payment notice, any later proposals, and each email in the simulated vendor inbox. "
        "Read the full text against the transfer, invoice and vendor. If true/false/ambiguous/absent, give reason, stated paid USD, "
        "separate tax USD where stated, invoice binding, transfer reference, and delivery binding. Keep ambiguity distinct from false. "
        "The notice may use any wording. Distinguish an explicit paid amount from a correct invoice amount and paid status without an explicit paid amount. "
        "Mark internal messages separately. Only read this packet."
    ), "cases": dict(sorted(packet.items()))})
    dump(LIVE / "result-key.json", index)
    dump(HERE / "mail_results.json", dict(cells=rows, blind_output_key=index, total_attempts=count, settled_usd=cost))


if __name__ == "__main__":
    main()
