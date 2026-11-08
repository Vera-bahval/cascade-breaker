"""Compatibility-only legacy baselines; missing facts are not invented.

The source modules are byte-for-byte copies from publication ec93a1b. The
adapter supplies the same attributable facts to both versions. Its UNKNOWN
coverage restriction is explicit and is not an original legacy capability.
"""
import json
from pathlib import Path
import sys
from time import perf_counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from legacy.rules import violations as v1
from legacy.rules_v2 import violations as v2
from rules_v3 import required_missing, _facts


NAMES = ("legacy_v1", "legacy_v2")


def guard(observation, name, policy=None):
    started = perf_counter()
    if name not in NAMES:
        raise ValueError("unknown legacy baseline")
    policy = policy or json.loads((HERE / "policy.json").read_text())
    if observation.get("checkpoint") != "P4" or observation.get("proposal", {}).get("tool") != "finstripe__create_transfer":
        return {"decision": "UNKNOWN", "reasons": ["legacy_payment_only"], "evidence": [], "timing_ms": 0.0}
    # Legacy versions already handle absent positive authorization by blocking.
    # Their normalized input needs base facts, not v3's autonomous-ALLOW gate.
    missing = [name for name in required_missing(observation, policy)
               if name not in {"human_cleared", "human_approved"}]
    if missing:
        return {"decision": "UNKNOWN", "reasons": ["legacy_input_unavailable:" + x for x in missing],
                "evidence": [], "timing_ms": (perf_counter() - started) * 1000}
    # The legacy caller contract is normalized trusted state. Do not promote a
    # forged/unscoped slot to that contract merely because its type is valid.
    facts, _ = _facts(observation)
    from decimal import Decimal
    amount = Decimal(facts["invoice_amount"])
    state = {
        "authoritative_snapshot": {"vendor_status": facts["vendor_status"], "invoice_status": facts["invoice_status"],
            "fraud_action": "HOLD" if facts["binding_hold"] else None,
            "hold_cleared": facts.get("human_cleared") is True},
        "facts_computed_by_code": {"positive_invoice_amount": amount > 0,
            "amount_above_experimental_automatic_limit": amount > Decimal(policy["automatic_limit"]),
            "fraud_review_completed": facts["fraud_review_completed"],
            "transfer_amount_matches_invoice": facts["amount_matches_invoice"],
            "recipient_matches_authorized_account": facts["recipient_matches_authorized"],
            "completed_transfer_exists": facts["prior_completed_transfers"] > 0},
        "proposed_action": "finstripe__create_transfer",
        "agent_explanation_not_independent_evidence": observation.get("untrusted_text", {}).get("agent", ""),
        "authorization_evidence": {"required": amount > Decimal(policy["automatic_limit"]),
            "registry_verified": facts.get("human_approved")},
        "clearance_evidence": {"registry_verified": facts.get("human_cleared")},
    }
    issues = (v1 if name == "legacy_v1" else v2)(state)
    return {"decision": "BLOCK" if issues else "ALLOW", "reasons": issues,
            "evidence": [], "timing_ms": (perf_counter() - started) * 1000}
