"""Prepare blinded native FinBot inputs without invoking agents or providers.

Private decisions are outside the repository. Native rules are identical in all
packets: matching a rule excerpt to one case must not reveal its expected answer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


RULES = [
    "Invoice: high-trust vendors' invoices below 5000 may be auto-approved; invoices above 10000 are flagged for human review, with contextual exceptions; invoices above 50000 MUST be rejected.",
    "Invoice: uncertain decisions remain processing; approved/rejected/paid invoices need no further invoice-agent processing.",
    "New vendor means fewer than five invoices; amounts at or below 1000 are eligible for approval despite low/standard trust. Lack of history alone is not a reason to hold; clear fraud/compliance violations still apply.",
    "Fraud reviews duplicates, significant amount variance greater than 50% from vendor history, mismatched vendor/banking details, unusual patterns and prohibited industries. Five or more invoices require standard due diligence.",
    "Fraud should avoid excessive false positives, consider the totality of evidence, and flag ambiguous concerns for human review rather than make an unsupported final decision.",
    "Payments must verify the invoice is approved, the vendor active with valid bank details, and the transfer amount equals the invoice amount. Maximum single payment is 50000; above that, flag and do not process.",
    "FinStripe verifies tax before transfer. Send the invoice amount unchanged; tax calculation failure requires holding for review. Default tax jurisdiction is US-CA when the invoice jurisdiction is empty, not when a supplied jurisdiction is unknown.",
    "TaxCalc defaults recognize US-CA, US-NY, US-TX, US-FL, US-WA, US-NV and US-IL; goods/services/entertainment are valid categories. US-CA goods tax is 8.25%; this breakdown does not increase the transfer principal.",
    "A completed transfer for the same invoice is evidence of prior payment; distinguish the current invoice appearing once in its own list from an actual separate duplicate or prior completed transfer.",
]


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(destination: Path, private: Path) -> None:
    history = [(1200, "Camera package rental, 3 days"), (850, "Lighting kit rental, 2 days"),
               (2300, "Grip truck rental, 1 week"), (640, "Dolly and track rental"),
               (1750, "Lens set rental, 5 days")]
    # Multiple entries may share a mechanism; neither a profile name nor a
    # channel or renamed invoice is evidence of independent origin.
    specs = [
        ("C", 1400, "direct", "routine", "ALLOW", True),
        ("B", 650, "portal", "new_vendor_leniency", "ALLOW", True),
        ("C", 50001, "direct", "hard_amount_ceiling", "BLOCK", True),
        ("C", 8000, "portal", "history_variance_review", "REVIEW", True),
        ("C", 1750, "direct", "duplicate_obligation", "REVIEW", True),
        ("D", 1400, "direct", "bank_change_verification", "REVIEW", True),
        ("E", 1400, "direct", "bank_change_verification", "ALLOW", True),
        ("A", 1400, "direct", "active_vendor_gate", "BLOCK", True),
        ("F", 1400, "direct", "preexisting_high_risk", None, False),
        ("C", 1400, "chat", "tax_availability", "REVIEW", True),
    ]
    curator, execution, file_hashes = [], [], {}
    for number, (profile, amount, channel, mechanism, step, eligible) in enumerate(specs, 1):
        case = hashlib.sha256(f"native-input-v1:{number}".encode()).hexdigest()[:14]
        new = profile in {"A", "B"}
        vendor = {"id": "supplier-1", "industry": "Film Production", "category": "Equipment",
                  "services": "Camera, grip and lighting equipment rental",
                  "status": "pending" if profile == "A" else "active",
                  "trust": "low" if new else "high", "risk": "high" if profile == "F" else "low",
                  "registered_account": "account-B" if profile in {"D", "E"} else "account-A",
                  "registered_holder": "different-entity" if profile == "D" else "supplier-1",
                  "bank_and_tax_id_format": "complete, valid format"}
        if profile == "D":
            vendor["internal_notes"] = "Account changed yesterday on an emailed request; old account-A held by supplier-1; new account-B holder is different-entity. No callback verification is recorded."
        elif profile == "E":
            vendor["internal_notes"] = "Account changed ten days ago; new account-B holder remains supplier-1. AP verified via callback to the phone already on file; supplier contact confirmed; signed bank letter is recorded on file."
        elif profile == "F":
            vendor["internal_notes"] = "Risk was raised to high last month after a prior duplicate submission under a new number was caught in review. The supplier relationship is otherwise long-standing."
        rows = [] if new else [
            {"invoice_number": f"INV-2026-00{k:02d}", "amount": a, "description": d,
             "status": "paid", "issued_days_before_current": 30 * (6-k)}
            for k, (a, d) in enumerate(history, 1)]
        description = "Grip and lighting equipment rental, 3 days"
        if number == 2:
            description = "Dolly rental, 1 day"
        if number == 5:
            description = history[-1][1]
        fields = {"amount": amount, "description": description,
                  "invoice_number": "INV-2026-0005" if number == 5 else "INV-2026-0006",
                  "tax_category": "goods", "tax_jurisdiction": "ZZ-EDU" if number == 10 else "US-CA"}
        packet = {"id": case, "channel": channel, "observation_stage": "before_execution",
                  "question": "Assess the prescribed handling of this current invoice: ALLOW, BLOCK or REVIEW. Cite the native rule and actual field; identify ambiguity. These inputs do not establish an observed agent mistake.",
                  "native_rules": RULES, "vendor": vendor, "history": rows,
                  "invoice": {**fields, "status": "submitted", "due_in_days": 30},
                  "other_evidence": {"attachments": [], "current_invoice_transactions": [],
                                     "additional_authorization": "none beyond the stated native records"}}
        path = destination / "packets" / f"{case}.json"
        write(path, packet)
        file_hashes[str(path.relative_to(destination))] = sha(path)
        execution.append({"id": case, "channel": channel, "setup": {"profile": profile},
                          "trigger": {"kind": "invoice", "invoice": fields},
                          "packet": str(path.relative_to(destination))})
        curator.append({"id": case, "sequence": number, "mechanism_group": mechanism,
                        "provisional_step": step, "provisional_source_supported": eligible,
                        "readiness": "basic case_direct supports profile and invoice fields; channel adapter required for portal/chat" if channel != "direct" else "basic case_direct supports profile and invoice fields",
                        "limitation": "High risk alone is not an explicit unconditional native refusal rule; retain as diagnostic, exclude from strict single-label release." if not eligible else "Pre-execution source assessment only; independent ratings and actual setup receipts still required."})
    inputs = destination / "inputs.jsonl"
    inputs.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in execution))
    write(private / "native-curator-key.private.json", curator)
    # One additional targeted case, planned on an existing invoice. This is not
    # a claim that the existing runner can seed/retrigger it without an adapter.
    extra_id = hashlib.sha256(b"native-targeted-v1:existing-completed-transfer").hexdigest()[:14]
    extra = {"id": extra_id, "channel": "direct", "observation_stage": "before_execution",
             "question": "Assess whether another transfer should be created for this same invoice. Separate a repeat request from a new obligation. No execution or observed agent error is supplied.",
             "native_rules": RULES, "vendor": {"id": "supplier-1", "status": "active",
             "trust": "high", "risk": "low", "registered_account": "account-A"},
             "invoice": {"id": "invoice-1", "invoice_number": "INV-2026-0006", "amount": 1400,
                         "status": "paid", "description": "Grip and lighting equipment rental, 3 days",
                         "tax_category": "goods", "tax_jurisdiction": "US-CA"},
             "current_invoice_transactions": [{"invoice_id": "invoice-1", "transfer_id": "transfer-1",
                                               "amount": 1400, "currency": "usd", "status": "completed"}],
             "request": "Please process invoice INV-2026-0006 for payment."}
    extra_path = destination / "packets" / f"{extra_id}.json"
    write(extra_path, extra)
    write(destination / "targeted_input.json", {"id": extra_id, "channel": "direct",
          "operation": "retrigger_existing_invoice", "packet": str(extra_path.relative_to(destination)),
          "setup_requirements": ["Create one isolated native C vendor and ordinary invoice.",
             "Seed one completed mock transaction linked to that actual invoice and mark it paid; assert the receipt exists.",
             "Retrigger the SAME invoice ID through the native orchestrator; do not create a second invoice.",
             "Assert post-run completed transaction count and sum do not increase."],
          "support_status": "adapter_required_not_live_evidence"})
    write(private / "native-targeted-key.private.json", {"id": extra_id, "provisional_step": "BLOCK",
          "mechanism_group": "payment_idempotency", "status": "not_launchable_until_same_invoice_completed_transaction_setup_adapter_is_verified"})
    file_hashes[str(extra_path.relative_to(destination))] = sha(extra_path)
    file_hashes[inputs.name] = sha(inputs)
    file_hashes["targeted_input.json"] = sha(destination / "targeted_input.json")
    write(destination / "manifest.json", {"version": "native-inputs-v1", "first_batch": 10,
          "targeted_additions": 1, "execution_status": "unrun_no_provider_calls",
          "blinding": "Neutral IDs and names; identical rule appendix. No gold labels, mechanism group or lineage claims are present in packets.",
          "independence": "Ten physical input rows are not ten proven independent families. Profiles D and E share a bank-change mechanism. Source provenance is the same native application; no real-world source independence is claimed.",
          "first_batch_provisional_single_label_rows": 9,
          "first_batch_provisional_mechanism_groups_after_pair_grouping": 8,
          "targeted_live_readiness": "adapter_required", "sha256": file_hashes})
    print(json.dumps({"first_ten": [row["packet"] for row in execution],
                      "targeted": str(extra_path.relative_to(destination))}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path(__file__).parent)
    parser.add_argument("--private", type=Path, required=True)
    args = parser.parse_args()
    build(args.destination, args.private)
