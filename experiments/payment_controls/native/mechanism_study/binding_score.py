"""Reconcile original prospective FinMail proposals with the independent effect and receipt rows."""
import json
import math
import sqlite3

from experiments.payment_controls.study.score import executor_accounting, workflow_evidence
from .binding_live import CASE, HERE, LIVE, sha


def score(arm):
    folder = LIVE / arm
    canonical = json.loads((folder / "canonical.json").read_text())
    summary = json.loads((folder / "summary.json").read_text())
    events = json.loads((folder / "binding-events.json").read_text())
    iid = summary["submitted_id"]
    amount = 4900
    effects = workflow_evidence(folder, submitted_id=iid, expected_amount=amount)
    receipts = executor_accounting(folder)
    with sqlite3.connect((folder / "finbot.db").as_uri() + "?mode=ro", uri=True) as db:
        ns, vendor, number = db.execute(
            "select namespace,vendor_id,invoice_number from invoices where id=?", (iid,)
        ).fetchone()
        inbox = [{"vendor_matches": row[0] == vendor, "type": row[1], "link": row[2],
                  "valid_optional_link": row[2] in (None, iid), "invoice_referenced": number in row[3] + "\n" + row[4],
                  "notice_sha256": sha((row[3] + "\n" + row[4]).encode())}
                 for row in db.execute("select vendor_id,message_type,related_invoice_id,subject,body from emails "
                                       "where namespace=? and inbox_type='vendor'", (ns,))]
    assert receipts["executor_accounting_complete"]
    trace_file = folder / "direct-trace.json"
    raw_trace = trace_file.read_bytes()
    traces = json.loads(raw_trace)
    calls = [s for tr in traces.values() for s in tr["steps"] if s["kind"] == "tool"
             and s["name"] == "finmail__send_email"]
    assert len(calls) == len(events)
    assert all(s["arguments"].get("related_invoice_id", 0) == e["supplied"] for s, e in zip(calls, events))
    success = (canonical["precondition_ok"] and canonical["oracle_ok"] and not canonical["run_error"]
               and effects["full_complete"] and len(inbox) == 1 and inbox[0]["vendor_matches"]
               and inbox[0]["valid_optional_link"] and inbox[0]["invoice_referenced"]
               and inbox[0]["type"] == "payment_confirmation")
    quota = json.loads((folder / "quota.json").read_text())
    return dict(case=CASE, arm=arm, events=events, database_inbox=inbox, canonical=canonical,
                parent_success=effects["root_complete"], payment_complete=effects["full_complete"],
                no_wrong_or_duplicate_transfer=effects["correct_transfer"], linked_or_omitted_notice_success=success,
                executor_seconds=summary["seconds"], trace_sha256=sha(raw_trace), quota=quota, **receipts)


if __name__ == "__main__":
    cells = [score("off"), score("guard")]
    with sqlite3.connect((LIVE / "executor.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        (state, requests, usd), = db.execute("select status,count(*),sum(cost) from requests group by status")
    assert state == "completed" and requests == sum(r["executor_attempts"] for r in cells)
    assert usd < .15 and math.isclose(usd, sum(r["executor_usd"] for r in cells), abs_tol=1e-12)
    data = dict(cells=cells, total_requests=requests, total_usd=usd, cap_usd=.15)
    (HERE / "binding_live_results.json").write_text(json.dumps(data, indent=2) + "\n")
    print([(r["arm"], r["events"], r["linked_or_omitted_notice_success"]) for r in cells], requests, usd)
