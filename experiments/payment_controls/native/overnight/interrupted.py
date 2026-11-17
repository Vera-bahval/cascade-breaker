"""Read an interrupted episode without replaying a model or payment."""
import gzip
import json
import sqlite3

from .provider import HERE,PRIVATE
from .live_batch import RUNTIME,folder,ARMS


def read_attempt(f,d):
    with gzip.open(d/"calls.jsonl.gz","rt") as stream:
        journal=list(map(json.loads,stream))
    requests=[x for x in journal if x["event"]=="request"]
    if journal[-1]["event"]!="error" or "Timeout" not in journal[-1]["error"]:
        raise ValueError("Unsupported interruption")
    messages=requests[-1]["request"]["messages"]
    proposed={c["id"]:c["function"] for m in messages for c in m.get("tool_calls",[])}
    outputs={proposed[m["tool_call_id"]]["name"]:json.loads(m["content"]) for m in messages
             if m["role"]=="tool" and m["tool_call_id"] in proposed}
    receipt=outputs["finstripe__create_transfer"]
    paid=outputs["process_payment"]
    with sqlite3.connect((d/"finbot.db").resolve().as_uri()+"?mode=ro",uri=True) as db:
        iid,status=db.execute("select id,status from invoices where invoice_number=? and amount=?",
                              (f["invoice"]["invoice_number"],f["invoice"]["amount"])).fetchone()
        tx,=db.execute("select transfer_id,invoice_id,status,amount,currency from payment_transactions").fetchall()
        notices,=db.execute("select count(*) from emails").fetchone()
        flagged,=db.execute("select instr(coalesce(agent_notes,''),'[Fraud Agent] FLAG:') from invoices where id=?",(iid,)).fetchone()
        bank,=db.execute("select v.bank_account_number from vendors v join invoices i on i.vendor_id=v.id and i.namespace=v.namespace where i.id=?",(iid,)).fetchone()
    assert tx==(receipt["transfer_id"],iid,"completed",f["invoice"]["amount"],"usd") and receipt["vendor_account"]==bank
    assert paid["invoice_id"]==iid and paid["payment_reference"]==tx[0] and paid["processed"] and status=="paid"
    with sqlite3.connect((RUNTIME/"executor.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as db:
        charges=[db.execute("select status,cost,reserve from requests where id=?",(r["attempt_id"],)).fetchone() for r in requests]
    assert all(a[0]=="completed" for a in charges[:-1]) and charges[-1][0]=="unknown"
    with sqlite3.connect((PRIVATE/"jev/ledger.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as db:
        reservations=db.execute("select reserve from requests where status='pending'").fetchall()
    assert len(reservations)==1
    r,=list(map(json.loads,(d/"route-decisions.jsonl").read_text().splitlines()))
    assert r["action"]=="DEFER" and "route_error:ConnectError" in r["reasons"]
    usd=sum(x[1] for x in charges[:-1])
    return dict(case=f["id"],arm=ARMS[-1],root_complete=False,paid_complete=False,correct_transfer=True,new_transfers=1,
                foreign_transfers=0,unverified=False,final_invoice_status=status,notifications=notices,recorded_flag=bool(flagged),
                native_fraud_llm_turns=sum(any(t["function"]["name"]=="get_vendor_risk_profile" for t in x["request"]["tools"]) for x in requests),
                route_checks=1,route_latency_ms="[]",routes=r["action"],technical=True,jev_calls=1,
                executor_calls=len(requests),executor_usd=usd,jev_usd=0.,full_usd=usd,
                seconds=(d/"calls.jsonl.gz").stat().st_mtime-d.stat().st_birthtime,
                cost_unsettled_reserve=charges[-1][2]+reservations[0][0])


def main():
    f,=[f for f in json.loads((HERE/"fixtures.json").read_text()) if f["id"]=="856421eec4fe76"]
    result=read_attempt(f,folder(f,ARMS[-1]))
    (HERE/"interrupted_outcome.json").write_text(json.dumps(result,indent=2)+"\n")

if __name__=="__main__":main()
