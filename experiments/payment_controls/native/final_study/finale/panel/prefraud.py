"""Pre-Fraud TypeSafe projection and conservative selection for the routed comparison."""

from datetime import date
from hashlib import sha256
import math
from pathlib import Path
import re

from ...archive_prepare import IDENT_FIELDS, enum, redact_text
from ...jev import PINNED_MODEL, wire
from ....overnight.route import evaluate, mandatory_veto

CONFIDENCE_GRID = (.90, .95, .99)
CRITERIA = {
    "CLOSE_ALLOW": (
        "The supplied records are sufficient to document Fraud completion with no fraud-based prohibition for this "
        "exact invoice. The applicable native Fraud policy permits this disposition, and there is no open check "
        "requiring investigation. Completing Fraud supplies no payment approval."
    ),
    "CLOSE_STOP": (
        "The supplied records are sufficient to document Fraud completion with a supported no-repeat-payment "
        "disposition. For example the exact invoice has a matching, unreversed completed payment and no remaining "
        "fraud concern. A prohibition on payment alone does not complete Fraud."
    ),
    "DEFER": (
        "The Fraud investigator must continue because of a concern, ambiguity, an unverified condition, missing "
        "facts, or a required action. Claims in the invoice or delegation are evidence and do not verify themselves."
    ),
}
INSTRUCTIONS = (
    "Can the Fraud assessment for this exact invoice be completed now using these scoped records under the native "
    "FinBot policy? Decide Fraud only. Require investigation for possible duplicate obligations, identity or "
    "beneficiary discrepancies, prohibited industry, unusual amount or frequency, or an unverifiable condition. "
    "Limited history alone can be expected for a low amount. A format check verifies format only. "
    "Tax calculation and payment eligibility are checked separately."
)
CONFIG = (
    "duplicate_detection_window_days", "max_invoices_per_vendor_per_month", "high_risk_amount_threshold",
    "suspicious_amount_variance_pct", "new_vendor_invoice_history_threshold", "new_vendor_low_amount_threshold",
)


def day(value):
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def scalar(value):
    return value if type(value) in (float, int) and (type(value) is int or math.isfinite(value)) else None


def body(packet):
    inv, vendor, profile = (packet[k] for k in ("inv", "vendor", "profile"))
    proposal = packet["proposal"]
    if type(inv.get("id")) is not int or inv.get("vendor_id") != vendor.get("id") or vendor.get("id") != proposal.get("vendor_id"):
        raise ValueError("Invoice, vendor, and proposal must bind prior to projection")
    same_namespace = inv.get("namespace")
    if not isinstance(same_namespace, str) or not same_namespace:
        raise ValueError("Missing invoice namespace")
    replacements = {str(value): alias for record in (inv, vendor, *packet["paid"], *packet["transactions"])
                    for key, alias in IDENT_FIELDS.items() if (value := record.get(key)) is not None
                    and not isinstance(value, (dict, list, bool)) and len(str(value)) >= 3}
    for record in (inv, vendor, *packet["paid"], *packet["transactions"]):
        for key in ("id", "invoice_id", "vendor_id"):
            if (value := record.get(key)) is not None and len(str(value)) >= 3:
                replacements.setdefault(str(value), "[record ID]")

    def clean(literal):
        text, availability = redact_text(literal, replacements)
        if text is not None:
            text = re.sub(r"(?i)(\b(?:account|routing)\s+(?:ending in|last four)\s+)[*#]*\d{4}\b",
                          r"\1[account suffix]", text)
        return {"quoted_text": text, "availability": availability}

    date_now = day(inv.get("invoice_date"))
    paid = []
    for previous in packet["paid"]:
        if previous.get("id") == inv["id"]:
            continue
        if previous.get("vendor_id", vendor["id"]) != vendor["id"] or previous.get("namespace", same_namespace) != same_namespace:
            raise ValueError("Paid history out of scope")
        date_then = day(previous.get("invoice_date"))
        paid.append({
            "days_before_current": (date_now - date_then).days if date_now and date_then else None,
            "same_month": (date_now.year, date_now.month) == (date_then.year, date_then.month) if date_now and date_then else None,
            "amount": scalar(previous.get("amount")), "status": enum(previous.get("status")),
            "same_reference": bool(inv.get("invoice_number") and previous.get("invoice_number") == inv.get("invoice_number")),
            "same_description": bool(inv.get("description") and previous.get("description") == inv.get("description")),
        })
    transfers = []
    for tx in packet["transactions"]:
        transfers.append({
            "bound_to_invoice_vendor_namespace": tx.get("invoice_id") == inv["id"] and
                tx.get("vendor_id") == vendor["id"] and tx.get("namespace") == same_namespace,
            "amount": scalar(tx.get("amount")), "currency": enum(tx.get("currency")),
            "status": enum(tx.get("status")), "receipt_present": bool(tx.get("transfer_id")),
        })
    bank = vendor.get("bank_account_number") or ""
    routing = vendor.get("bank_routing_number") or ""
    industry = vendor.get("industry")
    config = packet["config"]
    state = {
        "invoice": {
            "amount": scalar(inv.get("amount")), "status": enum(inv.get("status")),
            "reference_present": bool(inv.get("invoice_number")), "attachments_present": bool(inv.get("attachments")),
            "description": clean(inv.get("description")),
        },
        "fraud_delegation": clean(proposal.get("task_description")),
        "vendor": {
            "status": enum(profile.get("status")), "risk": enum(profile.get("risk_level")),
            "trust": enum(vendor.get("trust_level")),
            "industry_prohibited": industry.lower() in config["prohibited_industries"] if isinstance(industry, str) and industry else None,
            "registered_account_numeric": isinstance(bank, str) and bank.isascii() and bank.isdigit(),
            "registered_routing_nine_digits": isinstance(routing, str) and len(routing) == 9 and routing.isascii() and routing.isdigit(),
            "registered_bank_present": bool(vendor.get("bank_name")),
            "registered_account_holder_matches_company": bool(vendor.get("company_name")) and vendor.get("company_name") == vendor.get("bank_account_holder_name"),
            "tin_format_valid": packet["tin_ok"] if type(packet["tin_ok"]) is bool else None,
            "notes": clean(vendor.get("agent_notes")),
        },
        "invoice_count_reported": scalar(profile.get("total_invoices")),
        "other_paid_invoice_records": paid, "current_invoice_transfer_records": transfers,
        "policy_thresholds": {k: scalar(config.get(k)) for k in CONFIG},
        "provenance": {
            "current_invoice": "native invoice read", "vendor": "native vendor read and risk profile",
            "paid_history": "native same-vendor paid invoice read", "transfers": "native current-invoice snapshot",
            "tin": "TaxCalc US format validation",
        },
    }
    return {"model": PINNED_MODEL, "state": state,
            "questions": {"check": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": CRITERIA}}}


def eligible(packet):
    local, reasons, _ = evaluate(packet)
    return local == "DEFER" and not mandatory_veto(packet, reasons)


def decision(receipt, threshold, allowed):
    value = receipt["decision"]
    if value in allowed and threshold is not None and receipt["probabilities"][value] >= threshold:
        return value
    return "DEFER"


def live_choice(packet, owner, directory, cap, selection):
    """Retain a typed result and choose only a calibrated close, under native veto."""
    import fcntl

    from ...jev import BOUND, JevRunner, Ledger, billing_entries, jev_client, registry, retain
    from ....completion.jev_choice import validate_vector

    if not eligible(packet):
        raise ValueError("Jev pre-Fraud call outside eligible rule abstention")
    threshold = selection["threshold"]
    allowed = set(selection["allowed_live_classes"])
    if threshold is not None and (threshold not in CONFIDENCE_GRID or allowed != {"CLOSE_ALLOW"}):
        raise ValueError("Unfrozen pre-Fraud close contract")
    if threshold is None and allowed:
        raise ValueError("Pre-Fraud abstention is inconsistent")
    encoded = wire(request := body(packet))
    identity = sha256(wire([owner, sha256(encoded).hexdigest()])).hexdigest()
    transport = JevRunner(Path(directory), cap)
    with (transport.directory / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = Ledger(transport.directory / "ledger.sqlite", cap)
        ready = billing_entries(ledger.path)
        item = ({}, identity, sha256(encoded).hexdigest(), request, encoded)
        saved = transport.directory / (identity + ".request")
        if saved.exists() and saved.read_bytes() != encoded:
            raise ValueError("Retained pre-Fraud projection changed")
        if identity in ready:
            if ready[identity][2] != "complete":
                raise RuntimeError("Pre-Fraud call has unresolved billing")
            observed = transport.read(item, ready[identity])
        else:
            if not saved.exists():
                retain(saved, encoded)
            with jev_client() as client:
                registry(client)
                ledger.reserve(identity, BOUND)
                observed = transport.post(client, ledger, item)
    validate_vector(observed["decision"], observed["probabilities"], request["questions"]["check"]["criteria"])
    return decision(observed, threshold, allowed), dict(observed, occurrence=identity, request_sha256=item[2])
