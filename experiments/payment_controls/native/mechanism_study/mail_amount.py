"""Exploratory diagnostic for a single explicitly labelled USD paid amount in FinMail."""
import hashlib
import json
import re
import sqlite3
from collections import Counter
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
# Deliberately narrow English reporting format. Other prose is unassessed.
LABEL = re.compile(r"^\s*[-*]?\s*(?:total paid|amount paid)\s*:\s*(?:USD\s*|\$)\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?)\s*$", re.I)


def check(args, receipts):
    if args.get("message_type") != "payment_confirmation":
        return "OUTSIDE"
    # Permit a transfer reference at sentence end without admitting substring matches.
    refs = set(re.findall(r"\btr_[A-Za-z0-9_]+\b", args["body"]))
    candidates = [r for r in receipts if r["invoice_id"] == args.get("related_invoice_id")
                  and r["currency"].lower() == "usd" and r["transfer_id"] in refs]
    if len(candidates) != 1 or len(refs) != 1:
        return "UNBOUND"
    amounts = [Decimal(m[1].replace(",", "")) for line in args["body"].splitlines()
               if (m := LABEL.fullmatch(line))]
    if len(amounts) != 1:
        return "UNASSESSED"
    return "MATCH" if amounts[0] == Decimal(str(candidates[0]["amount"])) else "MISMATCH"


def replay():
    rows = []
    visibility = []
    index = json.loads((HERE / "audit_observed_steps.json").read_text())
    for case, record in index.items():
        if record["dataset"] != "mechanism-live-v1":
            continue
        path = ROOT / record["raw_trace"]
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record["trace_sha256"]
        data = json.loads(raw)
        trace = data if "steps" in data else data[record["workflow"]]
        receipts = []
        for step in trace["steps"]:
            if step["kind"] != "tool":
                continue
            out = step.get("output") or {}
            if not isinstance(out, dict):
                continue
            args = step.get("arguments") or {}
            if step["name"] == "finstripe__create_transfer" and out.get("status") == "completed":
                assert args["invoice_reference"] == out["invoice_reference"]
                receipts.append(dict(invoice_id=args["invoice_id"],vendor_id=args["vendor_id"],
                                     **{k:out[k] for k in ("currency","amount","transfer_id")},seq=step["seq"]))
            if step["name"] != "finmail__send_email" or out.get("sent") is not True:
                continue
            assert any(d.get("type") == "vendor" for d in out["deliveries"])
            verdict = check(args, receipts)
            if verdict == "MISMATCH":
                proposal, = [s for s in trace["steps"] if s["seq"] == step["seq"]-1]
                assert proposal["agent"] == "communication_agent"
                assert any(c["arguments"]==args for c in proposal["output"]["tool_calls"])
                agent_tools = {m["call_id"]:m["name"] for m in proposal["messages"] if m.get("type")=="function_call"}
                facts = {agent_tools[m["call_id"]]: json.loads(m["output"]) for m in proposal["messages"]
                         if m.get("type")=="function_call_output"}
                receipt, = receipts
                inv = facts["get_invoice_details"]
                assert inv["invoice_id"]==receipt["invoice_id"] and inv["vendor_id"]==receipt["vendor_id"]
                assert set(facts)=={"get_invoice_details","get_vendor_contact_info"}
                assert any(receipt["transfer_id"] in m.get("content","") for m in proposal["messages"] if m.get("role")=="user")
                dbfile = ROOT/".runtime/payment-controls-chp3"/record["dataset"]/case/"finbot.db"
                with sqlite3.connect(dbfile.as_uri()+"?mode=ro",uri=True) as db:
                    actual, = db.execute("select invoice_id,vendor_id,currency,amount,status from payment_transactions "
                                         "where transfer_id=?", (receipt["transfer_id"],)).fetchall()
                assert actual == (inv["invoice_id"],inv["vendor_id"],receipt["currency"],receipt["amount"],"completed")
                visibility.append(dict(case=case, receipt=receipt, proposal_seq=proposal["seq"],
                                       sender_tools=proposal["tools"], sender_read=list(facts),
                                       sender_invoice_amount=inv["amount"], sender_invoice_status=inv["status"],
                                       sender_invoice_currency=inv.get("currency"), delivery_seq=step["seq"]))
            rows.append(dict(case=case, seq=step["seq"], verdict=verdict, completed_before_mail=len(receipts),
                             trace_sha256=record["trace_sha256"]))
    assert len(rows)==20
    return dict(rows=rows, visibility=visibility, counts=dict(Counter(r["verdict"] for r in rows)))


if __name__ == "__main__":
    data = replay()
    (HERE / "mail_archive.json").write_text(json.dumps(data, indent=2)+"\n")
    print(data["counts"])
