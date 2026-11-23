"""Verify inbox, payment and parent completion in four controlled FinMail continuations."""
import json
import math
import re
import sqlite3
from decimal import Decimal

from experiments.payment_controls.study.score import executor_accounting, workflow_evidence
from .mail_live import LIVE, HERE


def score(side, arm):
    folder=LIVE/f"mail-{side}-{arm}"
    summary=json.loads((folder/"summary.json").read_text())
    events=json.loads((folder/"mail-events.json").read_text())
    iid=summary["submitted_id"]
    with sqlite3.connect((folder/"finbot.db").as_uri()+"?mode=ro",uri=True) as db:
        inv,=db.execute("select namespace,vendor_id,invoice_number,amount from invoices where id=?",(iid,)).fetchall()
        tx,=db.execute("select transfer_id,amount,currency from payment_transactions "
                       "where namespace=? and invoice_id=? and vendor_id=? and status='completed'",(inv[0],iid,inv[1])).fetchall()
        inbox=db.execute("select subject, body, vendor_id, related_invoice_id, message_type from emails "
                         "where namespace=? and inbox_type='vendor'",(inv[0],)).fetchall()
    effects=workflow_evidence(folder,submitted_id=iid,expected_amount=inv[3])
    receipts=executor_accounting(folder)
    assert receipts["executor_accounting_complete"] and tx[2]=="usd"
    messages=[]
    for subject,body,vendor,target,kind in inbox:
        # Independent scoring of these actual delivered drafts; never used in the guard.
        fields=re.findall(r"^(?:total paid|amount paid):\s*(?:USD\s*|\$)?([\d,]+\.\d{2})(?:\s*USD)?\s*$",body,re.I|re.M)
        paid=Decimal(fields[0].replace(",","")) if len(fields)==1 else None
        bound=vendor==inv[1] and target==iid and kind=="payment_confirmation" and tx[0] in body and inv[2] in body
        messages.append(dict(subject=subject,body=body,bound=bound,stated_paid_usd=str(paid),correct=bound and paid==Decimal(str(tx[1]))))
    return dict(side=side,arm=arm,subject_invoice=inv[2],attempts=events,delivered=messages,
                transfer_usd=tx[1],completed_transfers=effects["completed_transfers"],
                correct_transfer=effects["correct_transfer"],root_complete=effects["root_complete"],
                full_success=effects["full_complete"] and len(messages)==1 and messages[0]["correct"],
                elapsed_seconds=summary["seconds"],**receipts)


def main():
    rows=[score(side,arm) for side in ("matching","discrepant") for arm in ("off","guard")]
    with sqlite3.connect((LIVE/"executor.sqlite").as_uri()+"?mode=ro",uri=True) as db:
        counts=db.execute("select status,count(*),sum(cost) from requests group by status").fetchall()
    (status,requests,total),=counts
    assert status=="completed" and sum(r["executor_attempts"] for r in rows)==requests
    assert math.isclose(sum(r["executor_usd"] for r in rows),total,abs_tol=1e-10)
    (HERE/"mail_cells.json").write_text(json.dumps(dict(cells=rows,attempts=requests,total_usd=total),indent=2)+"\n")
    print([(r["arm"],r["side"],r["full_success"]) for r in rows],requests,total)


if __name__=="__main__":
    main()
