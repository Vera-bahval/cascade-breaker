"""Open diagnostic of native structured checks. No executor, LLM, payment, or external API."""
import asyncio
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
import sqlite3
from statistics import mean
import sys
from unittest.mock import patch

from .extract import HERE, LIVE, NATIVE, PRIVATE, ROOT


def historical_rows(folder, snap):
    """Select only rows listed in the intake, whose last write predates this invoice."""
    current = snap["invoice"]
    conn = sqlite3.connect((folder/"finbot.db").resolve().as_uri()+"?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = []
        for original in snap["other_invoices"]:
            row = conn.execute("SELECT * FROM invoices WHERE namespace=? AND vendor_id=? AND id=?",
                               (current["namespace"], current["vendor_id"], original["id"])).fetchone()
            if not row or any(row[k] != v for k,v in original.items()):
                raise ValueError("Historical record differs from pre-call intake")
            if datetime.fromisoformat(row["updated_at"]) > datetime.fromisoformat(current["created_at"]):
                raise ValueError("Historical record changed after intake")
            rows.append(dict(row))
        return rows
    finally:
        conn.close()


def assess(inv, vendor, profile, paid, transactions, tin_ok, config):
    """Close only under the visible, structured-risk interpretation of the native task."""
    hist = [x for x in paid if x["id"] != inv["id"]]
    amount = inv["amount"]
    source_date = datetime.fromisoformat(inv["invoice_date"]).date()
    ages = [(source_date - datetime.fromisoformat(x["invoice_date"]).date()).days for x in hist]
    typical = mean(x["amount"] for x in hist) if hist else None
    delta = abs(amount-typical)/typical if typical and typical>0 else None
    local_bank = (bool(vendor["bank_name"]) and vendor["bank_account_number"].isascii()
                  and vendor["bank_account_number"].isdigit() and len(vendor["bank_routing_number"])==9
                  and vendor["bank_routing_number"].isascii() and vendor["bank_routing_number"].isdigit()
                  and bool(vendor["company_name"]) and vendor["company_name"] == vendor["bank_account_holder_name"])
    facts = dict(principal=amount, history=len(hist), historical_mean=typical, relative_deviation=delta,
                 tin_format=tin_ok, registered_bank_fields_consistent=local_bank,
                 prior_status=inv["status"])
    reasons = []
    if not tin_ok or not local_bank or vendor["agent_notes"]:
        reasons.append("verify_identity_or_bank_record")
    if not vendor["industry"] or vendor["industry"].lower() in config["prohibited_industries"]:
        reasons.append("industry")
    if profile["status"]!="active" or profile["risk_level"]!="low":
        reasons.append("vendor_status_or_risk")
    if (profile["total_invoices"]!=len(hist)+1 or any(age<0 for age in ages)
            or any(not math.isfinite(x["amount"]) or x["amount"]<=0 for x in hist)):
        reasons.append("incomplete_or_unusable_history")
    if any(x["invoice_number"]==inv["invoice_number"] or
           (age<=config["duplicate_detection_window_days"] and
            (x["amount"]==amount or x["description"]==inv["description"])) for x,age in zip(hist,ages)):
        reasons.append("possible_same_obligation")
    same_month = sum(datetime.fromisoformat(x["invoice_date"]).date().replace(day=1)==source_date.replace(day=1)
                     for x in hist)
    if 1+same_month>config["max_invoices_per_vendor_per_month"]:
        reasons.append("frequency")
    if not math.isfinite(amount) or amount<=0 or amount>=config["high_risk_amount_threshold"]:
        reasons.append("amount")
    if delta is not None and 100*delta>config["suspicious_amount_variance_pct"]:
        reasons.append("amount_variance")
    if len(hist)<config["new_vendor_invoice_history_threshold"] and amount>config["new_vendor_low_amount_threshold"]:
        reasons.append("insufficient_comparable_history")
    if not inv["invoice_number"] or not inv["description"] or inv["status"] not in ("approved","paid") or inv["attachments"]:
        reasons.append("status_or_document_review")
    exact = [t for t in transactions if t["invoice_id"]==inv["id"] and t["vendor_id"]==vendor["id"]
             and t["namespace"]==inv["namespace"] and t["status"]=="completed" and t["amount"]==amount
             and t["currency"]=="usd" and t["transfer_id"]]
    stop = inv["status"]=="paid" and len(exact)==len(transactions)==1
    if (transactions or inv["status"]=="paid") and not stop:
        reasons.append("unreconciled_settlement")
    route = "DEFER" if reasons else ("CLOSE_STOP" if stop else "CLOSE_ALLOW")
    return route, reasons, {**facts, "matched_settlements":len(exact)}


async def run():
    sys.path[:0] = [str(ROOT/"finbot"), str(ROOT/"scenarios")]
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from finbot.core.data import database
    from finbot.core.data.models import Invoice, Vendor
    from finbot.tools.data.fraud import get_vendor_risk_profile, get_vendor_invoices, update_fraud_agent_notes
    from finbot.tools.data.invoice import get_invoice_details
    from finbot.tools.data.vendor import get_vendor_details
    from finbot.mcp.servers.taxcalc.server import create_taxcalc_server
    from runner.direct_mode import session_for

    index = json.loads((HERE/"index.json").read_text())
    packet_bytes = (PRIVATE/"packets.json").read_bytes()
    binding = json.loads((HERE/"binding_audit.json").read_text())
    if hashlib.sha256(packet_bytes).hexdigest() != binding["packet_sha256"]:
        raise ValueError("Pre-call packets differ from the audited extraction")
    packets = json.loads(packet_bytes)
    config = json.loads((NATIVE/"build_freeze.json").read_text())["static_defaults"]["agents"]["FraudComplianceAgent"]["default_config"]
    results = {}
    for key, record in index.items():
        folder = LIVE/record["source"]
        raw = (folder/"native-intake.jsonl").read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record["intake_sha"]:
            raise ValueError("Intake changed")
        snap, = map(json.loads, raw.splitlines())

        current = {**snap["invoice"], "status":packets[key]["invoice"]["status"]}
        vendor = snap["vendor"]
        history = historical_rows(folder,snap)
        engine = create_engine("sqlite://")
        factory = sessionmaker(bind=engine)
        try:
            for model in (Vendor, Invoice):
                model.__table__.create(engine)
            with factory.begin() as db:
                for cls, data in [(Vendor,vendor), *((Invoice,x) for x in [*history,current])]:
                    fields = dict(data)
                    for field in ("created_at","updated_at","invoice_date","due_date"):
                        if field in fields:
                            fields[field] = datetime.fromisoformat(fields[field])
                    if isinstance(fields.get("attachments"),list):
                        fields["attachments"] = json.dumps(fields["attachments"])
                    db.add(cls(**fields))
                    db.flush()
            session = session_for(current["namespace"], vendor["id"])
            with patch.object(database, "SessionLocal", factory):
                inv = await get_invoice_details(current["id"],session)
                ven = await get_vendor_details(vendor["id"],session)
                profile = await get_vendor_risk_profile(ven["id"],session)
                paid = await get_vendor_invoices(ven["id"],session,status="paid")
                tax = await create_taxcalc_server(session).call_tool("validate_tax_id",{"tax_id":ven["tin"],"country":"US"})
                route, reasons, facts = assess(inv,ven,profile,paid,snap["transactions"],tax.structured_content["format_valid"],config)
                proposal = packets[key]["proposal"]
                if (set(proposal) != {"vendor_id","task_description"} or proposal["vendor_id"] != ven["id"]
                        or not isinstance(proposal["task_description"],str) or not proposal["task_description"].strip()):
                    route, reasons = "FIX_DELEGATION", ["invalid_proposal",*reasons]
                note = json.dumps(dict(invoice_id=inv["id"],scope="Fraud only",decision=route,reasons=reasons,facts=facts),sort_keys=True)
                if route.startswith("CLOSE"):
                    await update_fraud_agent_notes(ven["id"], note, session)
                    if not (await get_vendor_details(ven["id"],session))["agent_notes"].rstrip().endswith(note):
                        raise ValueError("Assessment not persisted")
                results[key] = dict(route=route,reasons=reasons,facts=facts,native_note_verified=route.startswith("CLOSE"))
        finally:
            engine.dispose()
    gold=json.loads((HERE/"gold.json").read_text())
    for key,row in results.items():
        row.update(family=index[key]["family"],gold=gold[key]["action"])
    (HERE/"native_reads_results.json").write_text(json.dumps(results,indent=2,sort_keys=True)+"\n")
    print(Counter((v["route"],v["gold"]) for v in results.values()))


if __name__=="__main__":
    asyncio.run(run())
