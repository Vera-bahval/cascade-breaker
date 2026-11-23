"""Minimal blinded factual supplement for independently recorded structured reviews."""
from hashlib import sha256
import json

from ... import live_review


def receipts(dest):
    source, outcomes = dest / "pre-fraud-packets.jsonl", dest / "pre-fraud-route.jsonl"
    if not source.is_file() or not outcomes.is_file():
        return
    inputs = {row["owner"]: row["packet"] for row in map(json.loads, source.read_text().splitlines())}
    for row in map(json.loads, outcomes.read_text().splitlines()):
        packet = inputs.get(row["owner"])
        digest = sha256(json.dumps(packet, sort_keys=True, default=str).encode()).hexdigest()
        if packet is not None and row.get("packet_sha256") == digest:
            yield packet, row


def project(dest, episode):
    aliases = {name: f"W{index}" for index, name in enumerate(sorted(episode["traces"]), 1)}
    replacements = live_review.replace_entities(episode, episode["after"]["transactions"])
    for packet, row in receipts(dest):
        if row["action"] not in {"CLOSE_ALLOW", "CLOSE_STOP"}:
            continue
        trace = episode["traces"].get(row["workflow_id"], {})
        anchor = next((step["seq"] for step in trace.get("steps", []) if
                       step.get("kind") == "pre_fraud_route"
                       and step.get("packet_sha256") == row["packet_sha256"]), None)
        invoice, vendor, profile = packet["inv"], packet["vendor"], packet["profile"]
        yield {
            "workflow": aliases.get(row["workflow_id"]), "recorded_at_seq": anchor,
            "invoice_id": invoice["id"], "principal": invoice["amount"], "invoice_status": invoice["status"],
            "invoice_date": invoice["invoice_date"], "registered_vendor_matches": invoice["vendor_id"] == vendor["id"],
            "vendor_status": profile["status"], "vendor_risk": profile["risk_level"],
            "invoice_description": live_review.excerpt(invoice.get("description"), replacements),
            "invoice_has_documents": bool(invoice.get("attachments")),
            "vendor_notes_present": bool(vendor.get("agent_notes")),
            "vendor_industry": live_review.excerpt(vendor.get("industry"), replacements),
            "vendor_services": live_review.excerpt(vendor.get("services"), replacements),
            "prior_paid_invoice_amounts_dates_and_scopes": [
                {"amount": item["amount"], "invoice_date": item["invoice_date"],
                 "description": live_review.excerpt(item.get("description"), replacements)}
                for item in packet["paid"] if item["id"] != invoice["id"]
            ],
            "registered_vendor_invoice_count": profile["total_invoices"],
            "recorded_structured_findings": row["facts"],
            "material_findings_requiring_more_investigation": row["mandatory_veto"],
            "exact_prior_payment_receipt_bound": row["action"] == "CLOSE_STOP" and bool(row.get("settlement")),
            "source": "independent structured prepayment record checks",
        }
