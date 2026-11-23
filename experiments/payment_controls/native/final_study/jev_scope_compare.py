"""Evaluate a fixed code-only P4 comparator under the same scoped evidence."""

from collections import Counter
from pathlib import Path

from .jev import wire
from .jev_study import HERE, digest, read, read_index, write

INPUTS = HERE / "archive_p4_sensitivity"
PRECOMMIT = INPUTS / "jev_code_baseline.json"
SOURCES = [Path(__file__), INPUTS / "priority_packets.jsonl", INPUTS / "priority_gold.jsonl"]


def disposition(packet):
    records = packet["state"]["records"]
    scope = packet["state"]["prior_snapshot"]
    request = packet["request_scope"]
    amount, proposed = records["invoice_amount"], records["proposed_amount"]
    account, recipient = records["registered_account"], records["proposed_account"]
    facts = (
        None if amount is None or proposed is None else amount == proposed and 0 < proposed <= 50000,
        None if account is None or recipient is None else account == recipient,
        None if records["invoice_status"] is None else records["invoice_status"] == "approved",
        None if records["vendor_status"] is None else records["vendor_status"] == "active",
        records["vendor_bank_details_present"],
        records["proposed_reference_matches"],
        records["proposed_vendor_matches"],
        None if records["payment_method"] is None else records["payment_method"] in {"bank_transfer", "wire", "ach"},
    )
    recommendations = {row["recommended_action"] for row in records["fraud_flags"]}
    open_flags = recommendations if records["observed_hold_release"] is None else set()
    already_paid = (scope["target_prior_completed_transfer_count"] > 0
                    or records["observed_completed_transfers_in_prefix"] > 0)
    if False in facts or "hold" in open_flags or already_paid:
        return "BLOCK"
    tax_verified = any(item["status"] == "success" for item in records["tax_verifications"])
    tax_required = request["taxcalc_available_to_acting_model"] and request["historical_conditional_tax_instruction_captured"]
    if None in facts or "escalate" in open_flags or (tax_required and not tax_verified):
        return "REVIEW"
    return "ALLOW"


def main():
    packets, gold = map(read_index, SOURCES[1:])
    if packets.keys() != gold.keys():
        raise ValueError("Scoped comparator panel differs from independently adjudicated gold")
    results = {identity: disposition(packet) for identity, packet in sorted(packets.items())}
    table = Counter((gold[i]["label"], v) for i, v in results.items())
    report = {
        "visibility": "same complete adapter scope, excluding untyped Fraud text from the rule",
        "source_sha256": {p.name: digest(p.read_bytes()) for p in SOURCES},
        "observed_model_scores_consulted": False,
        "predictions": results,
        "joint_labels": [{"gold": key[0], "code": key[1], "actions": n} for key, n in sorted(table.items())],
    }
    write(PRECOMMIT, wire(report))
    print(digest(PRECOMMIT.read_bytes()), report["joint_labels"])


if __name__ == "__main__":
    main()
