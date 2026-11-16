"""Settle native receipts, executor and decision-provider spending, independently of labels."""
import csv
import json
import sqlite3
from .provider import HERE, PRIVATE
from .live_batch import ARMS, folder
from experiments.payment_controls.study.score import workflow_evidence, executor_accounting


def read_lines(path):
    return list(map(json.loads,path.open())) if path.is_file() else []


def collect(f, dest, arm, model_receipts):
    summary=json.loads((dest/"summary.json").read_text())
    tr=list(json.loads((dest/"direct-trace.json").read_text()).values())
    steps=[s for t in tr for s in t["steps"]]
    priorpath=dest/"prior.json"
    prior=json.loads(priorpath.read_text()) if priorpath.exists() else {}
    evidence=workflow_evidence(dest,submitted_id=summary["submitted_id"],expected_amount=f["invoice"]["amount"],
                               prior_transfer_ids={prior["transfer_id"]} if prior else ())
    acc=executor_accounting(dest)
    if not acc["executor_accounting_complete"]:raise ValueError("Executor accounting incomplete")
    decisions=read_lines(dest/"route-decisions.jsonl")
    models=[r for r in model_receipts if r["owner"].startswith(dest.name+":")]
    notify=[s for s in steps if s["kind"]=="tool" and s.get("name")=="finmail__send_email" and not s.get("error")
            and not (isinstance(s.get("output"),dict) and s["output"].get("error"))]
    iid=summary["submitted_id"]
    with sqlite3.connect((dest/"finbot.db").resolve().as_uri()+"?mode=ro",uri=True) as db:
        final_status,notes=db.execute("select status,agent_notes from invoices where id=?",(iid,)).fetchone()
        if prior:
            assert db.execute("select count(*) from payment_transactions where transfer_id=? and invoice_id=? and status='completed' and amount=?",
                              (prior["transfer_id"],iid,f["invoice"]["amount"])).fetchone()[0]==1
    native_turns=sum(s["kind"]=="llm" and s.get("agent")=="fraud_agent" for s in steps)
    jev_usd=sum(x["usd"] for x in models)
    return dict(case=f["id"],arm=arm,root_complete=evidence["root_complete"],paid_complete=evidence["full_complete"],
                correct_transfer=evidence["correct_transfer"],new_transfers=evidence["namespace_completed_transfers"],
                foreign_transfers=evidence["foreign_transfers"],unverified=evidence["unverified_transfer"],
                final_invoice_status=final_status,notifications=len(notify),recorded_flag="[Fraud Agent] FLAG:" in (notes or ""),
                native_fraud_llm_turns=native_turns,route_checks=len(decisions),
                routes="|".join(x["action"] for x in decisions),
                technical=bool(summary.get("technical_executor")) or any(any("error:" in r for r in x["reasons"]) for x in decisions),
                jev_calls=len(models),executor_calls=acc["executor_attempts"],executor_usd=acc["executor_usd"],
                jev_usd=jev_usd,full_usd=acc["executor_usd"]+jev_usd,seconds=summary["seconds"])


def main():
    cases={f["id"]:f for f in json.loads((HERE/"fixtures.json").read_text())}
    selected=json.loads((HERE/"live_selection.json").read_text())
    models=[json.loads(p.read_text()) for p in (PRIVATE/"jev").glob("*.json")]
    rows=[]
    for cid in selected:
        for arm in ARMS:
            dest=folder(cases[cid],arm)
            if (dest/"summary.json").is_file():rows.append(collect(cases[cid],dest,arm,models))
    with (HERE/"live_results.csv").open("w",newline="") as stream:
        w=csv.DictWriter(stream,fieldnames=rows[0],lineterminator="\n")
        w.writeheader();w.writerows(rows)


if __name__=="__main__":main()
