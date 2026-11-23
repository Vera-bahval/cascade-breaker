"""Collect trace coordinates and isolated DB effects from B-048."""
from collections import Counter
import gzip
import hashlib
import json
import sqlite3

from .other_notice import EXPECTED, HERE, LIVE, ROOT


def write(name, record):
    (HERE / name).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(directory):
    path, = (directory / "traces").glob("*.json")
    trace = json.loads(path.read_bytes())
    steps = trace["steps"]
    summary = json.loads((directory / "summary.json").read_bytes())
    dbfile = directory / "finbot.db"
    with sqlite3.connect(dbfile.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        inv = db.execute("select id, namespace, vendor_id, status from invoices where invoice_number='B-048'").fetchone()
        payments = [dict(row) for row in db.execute(
            "select status, amount from payment_transactions where namespace=? and invoice_id=?",
            (inv["namespace"], inv["id"]),
        )]
        notices = [dict(row) for row in db.execute(
            "select id,message_type,related_invoice_id from emails "
            "where namespace=? and vendor_id=? and inbox_type='vendor' and direction='outbound'",
            (inv["namespace"], inv["vendor_id"]),
        )]

    def select(kind, name):
        return [s for s in steps if s["kind"] == kind and s.get("name") == name]

    models = [dict(seq=s["seq"], type=call["arguments"]["notification_type"])
              for s in steps if s["kind"] == "llm" and isinstance(s.get("output"), dict)
              for call in s["output"].get("tool_calls", [])
              if call.get("name") == "delegate_to_communication"
              and "notification_type" in call.get("arguments", {})]
    proposal = []
    for s in select("tool", "delegate_to_communication"):
        a = s["arguments"]
        proposal.append(dict(seq=s["seq"], type=a.get("notification_type"),
                             vendor_match=a.get("vendor_id") == inv["vendor_id"]))
    deliveries = []
    for s in select("tool", "finmail__send_email"):
        if not isinstance(s.get("output"), dict):
            continue
        out = s["output"]
        vendor = [d for d in out.get("deliveries", []) if d.get("type") == "vendor"
                  and d.get("vendor_id") == inv["vendor_id"]]
        deliveries.append(dict(seq=s["seq"], type=s["arguments"].get("message_type"),
                               vendor_deliveries=len(vendor)))
    flags = [dict(seq=s["seq"], action=s["output"]["recommended_action"])
             for s in select("tool", "flag_invoice_for_review") if isinstance(s.get("output"), dict)
             and s["output"].get("flagged") and s["output"].get("invoice_id") == inv["id"]]
    done = [dict(seq=s["seq"], status=s["output"]["task_status"]) for s in select("tool", "complete_task")
            if s.get("agent") == "orchestrator_agent" and isinstance(s.get("output"), dict)]
    with gzip.open(directory / "calls.jsonl.gz", "rt") as stream:
        accounts = [x for x in map(json.loads, stream) if x["event"] == "accounting"]
    assert len(accounts) == summary["executor_calls"]
    assert abs(sum(r["eliza_cost_usd"] for r in accounts) - summary["executor_usd"]) < 1e-10
    events = directory / "notice-inputs.json"
    return dict(source=str(path.relative_to(ROOT)), trace_sha256=digest(path), db_sha256=digest(dbfile),
                invoice_id=inv["id"], status=inv["status"], flags=flags, payments=payments,
                proposal=models, tool_return=proposal, deliveries=deliveries, vendor_mail=notices, done=done,
                executor_calls=len(accounts), eliza_usd=summary["executor_usd"],
                seconds=summary["seconds"], intervention=json.loads(events.read_bytes()) if events.exists() else [],
                metered_calls_sha256=digest(directory / "calls.jsonl.gz"))


def main():
    old = ROOT / ".runtime/payment-controls-chp3/mechanism-live-v1"
    archive = {directory.name.split("-")[2] if not any(x in directory.name for x in ("after-fraud", "before-transfer"))
               else ("after-fraud" if "after-fraud" in directory.name else "before-transfer"): read(directory)
               for directory in sorted(old.glob("portal-*-d8c2993de5cc2f"))}
    assert len(archive) == 5 and all(len(v["vendor_mail"]) == 1 for v in archive.values())
    assert Counter(v["vendor_mail"][0]["message_type"] for v in archive.values()) == {
        "action_required": 4, EXPECTED: 1,
    }
    live = {name: read(LIVE / name) for name in ("off", "guard", "off-v2", "guard-v2", "off-v3", "guard-v3", "off-v3b", "guard-v3b", "off-v3c", "guard-v3c") if (LIVE / name / "summary.json").exists()}
    account = None
    ledger = LIVE / "executor.sqlite"
    if ledger.exists():
        with sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True) as db:
            account = [list(r) for r in db.execute("select status,count(*),sum(cost) from requests group by status")]
    errors = {}
    for name in ("off-v3", "off-v3b", "guard-v3b"):
        directory = LIVE / name
        if directory.is_dir():
            errors[name] = {"stage": "startup import" if name == "off-v3" else "delegation wrapper",
                            "accounted_requests": live.get(name, {}).get("executor_calls", 0),
                            "dollars": live.get(name, {}).get("eliza_usd", 0)}
    if account and all(row[0] == "completed" for row in account):
        assert sum(v["executor_calls"] for v in live.values()) == sum(row[1] for row in account)
        assert abs(sum(v["eliza_usd"] for v in live.values()) - sum(row[2] for row in account)) < 1e-10
    write("other_notice_results.json", dict(archive=archive, live=live, harness_errors=errors, ledger=account))


if __name__ == "__main__":
    main()
