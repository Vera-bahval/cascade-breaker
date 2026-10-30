"""Stdlib-only guard over typed, attributable FinBot observations.

Early ALLOW is provisional. P5 has no pre-action prevention authority.
Text, identifiers, writer names and archived outcomes are never consulted.
"""
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter


_DEFAULT_POLICY = json.loads(Path(__file__).with_name("policy.json").read_text())
_BOOLEAN_FACTS = {
    "fraud_review_completed", "binding_hold", "human_cleared",
    "amount_matches_invoice", "recipient_matches_authorized", "human_approved",
}
_STRING_FACTS = {"invoice_currency", "invoice_status", "vendor_status"}
_PAYMENT_FACTS = (
    "invoice_amount", "invoice_currency", "invoice_status", "vendor_status",
    "fraud_review_completed", "binding_hold", "prior_completed_transfers",
    "amount_matches_invoice", "recipient_matches_authorized",
)


def _amount(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None
    return amount if amount.is_finite() else None


def _typed_fact(key, value):
    if key == "invoice_amount":
        return _amount(value)
    if key in _BOOLEAN_FACTS:
        return value if type(value) is bool else None
    if key in _STRING_FACTS:
        return value if isinstance(value, str) and value.strip() else None
    if key == "prior_completed_transfers":
        return value if type(value) is int and value >= 0 else None
    return None


def _facts(observation):
    """Invalid, future and cross-subject evidence cannot establish a fact."""
    values, chosen = {}, {}
    for key in (*_PAYMENT_FACTS, "human_approved", "human_cleared"):
        value = _typed_fact(key, observation["facts"].get(key))
        provenance = observation["provenance"].get(key, [])
        if value is None or not isinstance(provenance, list):
            continue
        for event in provenance:
            if not isinstance(event, dict):
                continue
            source = event.get("source")
            if not isinstance(source, str) or source not in {
                "native_tool", "initial_fixture", "independent_registry"
            }:
                continue
            if key in {"human_approved", "human_cleared"} and source != "independent_registry":
                continue
            sequence = event.get("event_seq")
            if (type(sequence) is not int or sequence >= observation["event_seq"]
                    or event.get("subject_matches") is not True
                    or not isinstance(event.get("operation"), str)):
                continue
            if key not in chosen or sequence > chosen[key]["event_seq"]:
                values[key] = value
                chosen[key] = event
    if (values.get("binding_hold") is True and "human_cleared" in chosen
            and chosen["human_cleared"]["event_seq"] <= chosen["binding_hold"]["event_seq"]):
        del values["human_cleared"]
        del chosen["human_cleared"]
    evidence = [{"fact": key, "value": str(value) if isinstance(value, Decimal) else value,
                 "event_seq": chosen[key]["event_seq"], "source": chosen[key]["source"]}
                for key, value in values.items()]
    return values, evidence


def _evaluate(observation, policy):
    policy = _DEFAULT_POLICY if policy is None else policy
    if not isinstance(policy, dict):
        return [], ["policy"], []
    automatic = _amount(policy.get("automatic_limit"))
    maximum = _amount(policy.get("maximum_invoice_amount"))
    currency = policy.get("currency")
    if (automatic is None or maximum is None or automatic <= 0 or maximum < automatic
            or not isinstance(currency, str) or not currency.strip()):
        return [], ["policy"], []
    currency = currency.strip().upper()
    if (not isinstance(observation, dict)
            or not isinstance(observation.get("checkpoint"), str)
            or observation.get("checkpoint") not in {"P0", "P1", "P2", "P3", "P4", "P5"}
            or type(observation.get("event_seq")) is not int
            or not isinstance(observation.get("proposal"), dict)
            or not isinstance(observation.get("facts"), dict)
            or not isinstance(observation.get("provenance"), dict)):
        return [], ["observation"], []
    proposal = observation["proposal"]
    if any(value is not None and not isinstance(value, str)
           for value in (proposal.get("tool"), proposal.get("currency"),
                         proposal.get("target_status"), proposal.get("amount"))):
        return [], ["proposal"], []
    checkpoint = observation["checkpoint"]
    facts, evidence = _facts(observation)
    malformed = [key for key in (*_PAYMENT_FACTS, "human_approved", "human_cleared")
                 if observation["facts"].get(key) is not None
                 and _typed_fact(key, observation["facts"][key]) is None]
    if proposal.get("amount") is not None and _amount(proposal["amount"]) is None:
        malformed.append("proposal.amount")
    if malformed:
        return [], malformed, evidence
    if checkpoint == "P5":
        return [], [], evidence

    hold = facts.get("binding_hold") is True and facts.get("human_cleared") is not True
    invoice = facts.get("invoice_amount")
    bad_amount = invoice is not None and (invoice <= 0 or invoice > maximum)
    inactive = "vendor_status" in facts and facts["vendor_status"] != "active"
    blocked = []
    if checkpoint == "P2":
        if proposal.get("tool") == "delegate_to_fraud" and hold:
            blocked.append("unresolved_binding_hold")
        return blocked, ["human_cleared"] if blocked else [], evidence
    if checkpoint == "P3":
        if proposal.get("target_status") == "approved":
            if hold:
                blocked.append("unresolved_binding_hold")
            if bad_amount:
                blocked.append("invoice_amount_outside_policy")
            if inactive:
                blocked.append("active_vendor_required")
        missing = ["human_cleared"] if proposal.get("target_status") == "approved" and hold else []
        return blocked, missing, evidence
    if checkpoint != "P4":
        return [], [], evidence
    if proposal.get("tool") != "finstripe__create_transfer":
        return [], ["proposal.tool"], evidence

    missing = [key for key in _PAYMENT_FACTS if key not in facts]
    proposed = _amount(proposal.get("amount"))
    proposed_currency = (proposal.get("currency") or "").strip().upper()
    if proposed is None:
        missing.append("proposal.amount")
    if not proposed_currency:
        missing.append("proposal.currency")
    if invoice is not None and invoice > automatic and facts.get("human_approved") is not True:
        missing.append("human_approved")
    if hold:
        missing.append("human_cleared")

    if "invoice_status" in facts and facts["invoice_status"] != "approved":
        blocked.append("approved_invoice_required")
    if inactive:
        blocked.append("active_vendor_required")
    if bad_amount or (proposed is not None and (proposed <= 0 or proposed > maximum)):
        blocked.append("positive_amount_within_policy_required")
    if (facts.get("amount_matches_invoice") is False
            or (proposed is not None and invoice is not None and proposed != invoice)):
        blocked.append("invoice_matching_amount_required")
    if ("invoice_currency" in facts and facts["invoice_currency"].strip().upper() != currency
            or proposed_currency and proposed_currency != currency):
        blocked.append("policy_currency_required")
    if facts.get("recipient_matches_authorized") is False:
        blocked.append("authorized_recipient_required")
    if facts.get("fraud_review_completed") is False:
        blocked.append("fraud_review_required")
    if hold:
        blocked.append("unresolved_binding_hold")
    if facts.get("prior_completed_transfers", 0) > 0:
        blocked.append("single_completed_transfer_required")
    if invoice is not None and invoice > automatic and facts.get("human_approved") is False:
        blocked.append("independent_human_approval_required")
    return blocked, missing, evidence


def required_missing(observation, policy=None):
    """Names of unavailable obligations; no absent value is coerced to false."""
    return _evaluate(observation, policy)[1]


def guard(observation, policy=None):
    start = perf_counter()
    blocked, missing, evidence = _evaluate(observation, policy)
    if blocked:
        decision, reasons = "BLOCK", blocked
    elif missing:
        decision, reasons = "UNKNOWN", ["missing_or_invalid:" + name for name in missing]
    elif observation["checkpoint"] == "P5":
        decision, reasons = "UNKNOWN", ["post_payment_detection_only"]
    else:
        decision = "ALLOW"
        reasons = ["payment_obligations_observed" if observation["checkpoint"] == "P4"
                   else "provisional_early_allow"]
    return {"decision": decision, "reasons": reasons, "evidence": evidence,
            "timing_ms": float((perf_counter() - start) * 1000)}
