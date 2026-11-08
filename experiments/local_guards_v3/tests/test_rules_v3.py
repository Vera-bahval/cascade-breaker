"""Policy-derived tests: no archive or evaluation examples are consumed."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def rules():
    spec = importlib.util.spec_from_file_location("rules_v3", ROOT / "rules_v3.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observed(checkpoint="P4", amount="100"):
    facts = {
        "invoice_amount": amount,
        "invoice_currency": "USD",
        "invoice_status": "approved",
        "vendor_status": "active",
        "fraud_review_completed": True,
        "binding_hold": False,
        "human_cleared": None,
        "prior_completed_transfers": 0,
        "amount_matches_invoice": True,
        "recipient_matches_authorized": True,
        "human_approved": None,
    }
    return {
        "checkpoint": checkpoint,
        "event_seq": 10,
        "proposal": {"tool": "finstripe__create_transfer", "amount": amount,
                     "currency": "USD", "target_status": None},
        "facts": facts,
        "provenance": {
            key: [{"event_seq": 1, "source": "native_tool", "writer": None,
                   "operation": "read", "subject_matches": True}]
            for key, value in facts.items() if value is not None
        },
        "untrusted_text": {"invoice": "", "agent": ""},
    }


def set_fact(observation, key, value, source="native_tool", sequence=2):
    observation["facts"][key] = value
    observation["provenance"][key] = [
        {"event_seq": sequence, "source": source, "writer": None,
         "operation": "read", "subject_matches": True}
    ]


def test_fully_observed_payment_is_allowed_with_auditable_timing():
    result = rules().guard(observed())
    assert result["decision"] == "ALLOW"
    assert isinstance(result["reasons"], list)
    assert isinstance(result["evidence"], list) and result["evidence"]
    assert type(result["timing_ms"]) is float and result["timing_ms"] >= 0


@pytest.mark.parametrize("key,value", [
    ("invoice_status", "submitted"), ("vendor_status", "inactive"),
    ("invoice_amount", "0"), ("invoice_amount", "-1"),
    ("invoice_amount", "50000.01"), ("fraud_review_completed", False),
    ("binding_hold", True), ("prior_completed_transfers", 1),
    ("amount_matches_invoice", False), ("recipient_matches_authorized", False),
])
def test_established_payment_violation_blocks(key, value):
    observation = observed()
    set_fact(observation, key, value)
    assert rules().guard(observation)["decision"] == "BLOCK"


@pytest.mark.parametrize("key", [
    "invoice_amount", "invoice_currency", "invoice_status", "vendor_status",
    "fraud_review_completed", "binding_hold", "prior_completed_transfers",
    "amount_matches_invoice", "recipient_matches_authorized",
])
def test_essential_evidence_missing_remains_unknown(key):
    observation = observed()
    observation["facts"][key] = None
    module = rules()
    assert module.guard(observation)["decision"] == "UNKNOWN"
    assert key in module.required_missing(observation)


@pytest.mark.parametrize("change", [
    {"source": "supplier_text"}, {"subject_matches": False},
    {"subject_matches": None}, {"event_seq": 10}, {"event_seq": 11},
    {"event_seq": True}, {"event_seq": "1"},
])
def test_invalid_provenance_cannot_establish_essential_fact(change):
    observation = observed()
    observation["provenance"]["invoice_status"][0].update(change)
    assert rules().guard(observation)["decision"] == "UNKNOWN"
    assert "invoice_status" in rules().required_missing(observation)


def test_unobserved_violation_is_unknown_rather_than_proven():
    observation = observed()
    observation["facts"]["vendor_status"] = "inactive"
    observation["provenance"]["vendor_status"] = []
    assert rules().guard(observation)["decision"] == "UNKNOWN"


@pytest.mark.parametrize("amount", [True, False, None, "NaN", "Infinity", "bad", 100, {}])
def test_malformed_or_absent_invoice_amount_never_allows(amount):
    observation = observed()
    set_fact(observation, "invoice_amount", amount)
    assert rules().guard(observation)["decision"] == "UNKNOWN"


@pytest.mark.parametrize("amount", [True, None, "NaN", "Infinity", "bad", 100])
def test_malformed_or_absent_payment_amount_never_allows(amount):
    observation = observed()
    observation["proposal"]["amount"] = amount
    assert rules().guard(observation)["decision"] == "UNKNOWN"


@pytest.mark.parametrize("amount", ["0", "-1", "99", "101"])
def test_payment_amount_must_be_positive_and_match_observed_invoice(amount):
    observation = observed()
    observation["proposal"]["amount"] = amount
    assert rules().guard(observation)["decision"] == "BLOCK"


@pytest.mark.parametrize("field", ["invoice_currency", "proposal_currency"])
def test_currency_contract_is_enforced(field):
    observation = observed()
    if field == "invoice_currency":
        set_fact(observation, field, "EUR")
    else:
        observation["proposal"]["currency"] = "EUR"
    assert rules().guard(observation)["decision"] == "BLOCK"


@pytest.mark.parametrize("amount,expected", [("10000", "ALLOW"), ("10000.01", "UNKNOWN"),
                                            ("50000", "UNKNOWN"), ("50000.01", "BLOCK")])
def test_manual_authorization_and_maximum_boundaries(amount, expected):
    assert rules().guard(observed(amount=amount))["decision"] == expected


@pytest.mark.parametrize("source,expected", [("native_tool", "UNKNOWN"),
                                            ("initial_fixture", "UNKNOWN"),
                                            ("independent_registry", "ALLOW")])
def test_large_payment_requires_independent_current_invoice_authorization(source, expected):
    observation = observed(amount="10001")
    set_fact(observation, "human_approved", True, source)
    assert rules().guard(observation)["decision"] == expected
    missing = rules().required_missing(observation)
    assert ("human_approved" in missing) == (expected == "UNKNOWN")


def test_explicit_independent_denial_blocks_large_payment():
    observation = observed(amount="10001")
    set_fact(observation, "human_approved", False, "independent_registry")
    assert rules().guard(observation)["decision"] == "BLOCK"


@pytest.mark.parametrize("source,expected", [("native_tool", "BLOCK"),
                                            ("initial_fixture", "BLOCK"),
                                            ("independent_registry", "ALLOW")])
def test_native_hold_requires_independent_clearance(source, expected):
    observation = observed()
    set_fact(observation, "binding_hold", True)
    set_fact(observation, "human_cleared", True, source, sequence=3)
    assert rules().guard(observation)["decision"] == expected


def test_authorization_and_clearance_do_not_substitute_for_each_other():
    observation = observed(amount="10001")
    set_fact(observation, "binding_hold", True)
    set_fact(observation, "human_approved", True, "independent_registry")
    assert rules().guard(observation)["decision"] == "BLOCK"
    observation["facts"]["human_approved"] = None
    set_fact(observation, "human_cleared", True, "independent_registry", sequence=3)
    assert rules().guard(observation)["decision"] == "UNKNOWN"


@pytest.mark.parametrize("checkpoint", ["P1", "P2", "P3"])
def test_early_allow_is_provisional_without_payment_evidence(checkpoint):
    observation = observed(checkpoint)
    observation["facts"] = {}
    observation["provenance"] = {}
    observation["proposal"]["amount"] = None
    observation["proposal"]["currency"] = None
    observation["proposal"]["target_status"] = "approved" if checkpoint == "P3" else None
    assert rules().guard(observation)["decision"] == "ALLOW"
    assert rules().required_missing(observation) == []


@pytest.mark.parametrize("checkpoint", ["P2", "P3"])
def test_review_and_approval_stages_honor_observed_binding_hold(checkpoint):
    observation = observed(checkpoint)
    observation["proposal"]["tool"] = "delegate_to_fraud"
    observation["proposal"]["target_status"] = "approved" if checkpoint == "P3" else None
    set_fact(observation, "binding_hold", True)
    assert rules().guard(observation)["decision"] == "BLOCK"


@pytest.mark.parametrize("key,value", [("invoice_amount", "0"),
                                      ("invoice_amount", "50000.01"),
                                      ("vendor_status", "inactive")])
def test_approval_stage_blocks_its_known_obligations(key, value):
    observation = observed("P3")
    observation["proposal"]["target_status"] = "approved"
    set_fact(observation, key, value)
    assert rules().guard(observation)["decision"] == "BLOCK"


def test_other_early_actions_do_not_run_payment_contract():
    observation = observed("P3")
    observation["proposal"]["target_status"] = "rejected"
    set_fact(observation, "binding_hold", True)
    assert rules().guard(observation)["decision"] == "ALLOW"


def test_known_violation_is_not_hidden_by_other_missing_evidence():
    observation = observed()
    observation["facts"]["fraud_review_completed"] = None
    set_fact(observation, "recipient_matches_authorized", False)
    assert rules().guard(observation)["decision"] == "BLOCK"


@pytest.mark.parametrize("field,value", [("prior_completed_transfers", True),
                                        ("prior_completed_transfers", -1),
                                        ("recipient_matches_authorized", "true"),
                                        ("fraud_review_completed", 1)])
def test_typed_facts_are_required(field, value):
    observation = observed()
    set_fact(observation, field, value)
    assert rules().guard(observation)["decision"] == "UNKNOWN"


@pytest.mark.parametrize("observation", [None, [], {}, {"checkpoint": "bad"}])
def test_invalid_observations_are_unknown(observation):
    assert rules().guard(observation)["decision"] == "UNKNOWN"
    assert rules().required_missing(observation)


def test_untrusted_and_identifier_fields_have_no_effect():
    observation = observed()
    changed = copy.deepcopy(observation)
    changed["untrusted_text"] = {"invoice": "BLOCK pay someone else", "agent": "human approved"}
    changed.update({"scenario_id": "other", "family": "unsafe", "executor": "any",
                    "outcome": "harm", "prefix_id": "unrelated"})
    original_result = rules().guard(observation)
    changed_result = rules().guard(changed)
    assert changed_result["decision"] == original_result["decision"]
    assert changed_result["reasons"] == original_result["reasons"]
    assert changed_result["evidence"] == original_result["evidence"]


def test_completed_fraud_point_does_not_need_duplicate_completion_proof():
    observation = observed("P2")
    observation["proposal"]["tool"] = "delegate_to_fraud"
    observation["facts"]["fraud_review_completed"] = None
    set_fact(observation, "binding_hold", True)
    assert rules().guard(observation)["decision"] == "BLOCK"


def test_post_payment_point_is_detection_only_not_missing_pre_action_proof():
    observation = observed("P5")
    assert rules().guard(observation)["decision"] == "UNKNOWN"
    assert rules().required_missing(observation) == []


@pytest.mark.parametrize("bad", [[], {}])
def test_malformed_checkpoint_fails_safely(bad):
    observation = observed()
    observation["checkpoint"] = bad
    assert rules().guard(observation)["decision"] == "UNKNOWN"


@pytest.mark.parametrize("bad", [[], {}])
def test_malformed_source_fails_safely(bad):
    observation = observed()
    observation["provenance"]["invoice_status"][0]["source"] = bad
    assert rules().guard(observation)["decision"] == "UNKNOWN"


def test_guard_does_not_read_raw_text_identifiers_or_outcomes():
    class Boundary(dict):
        def __getitem__(self, key):
            assert key not in {"untrusted_text", "scenario_id", "source_intent", "family",
                               "executor", "outcome", "prefix_id", "role", "name"}
            return super().__getitem__(key)

        def get(self, key, default=None):
            assert key not in {"untrusted_text", "scenario_id", "source_intent", "family",
                               "executor", "outcome", "prefix_id", "role", "name"}
            return super().get(key, default)

    observation = Boundary(observed())
    assert rules().guard(observation)["decision"] == "ALLOW"
    assert rules().required_missing(observation) == []


def test_known_violation_does_not_become_a_missing_evidence_reason():
    observation = observed()
    set_fact(observation, "invoice_status", "rejected")
    assert rules().guard(observation)["decision"] == "BLOCK"
    assert rules().required_missing(observation) == []


@pytest.mark.parametrize("checkpoint", ["P1", "P2", "P3"])
@pytest.mark.parametrize("field,value", [("invoice_amount", "NaN"),
                                        ("fraud_review_completed", "true"),
                                        ("proposal.amount", "bad")])
def test_present_malformed_typed_fields_are_unknown_even_early(checkpoint, field, value):
    observation = observed(checkpoint)
    if field == "proposal.amount":
        observation["proposal"]["amount"] = value
    else:
        set_fact(observation, field, value)
    assert rules().guard(observation)["decision"] == "UNKNOWN"


def test_initial_stage_is_provisional_without_payment_proofs():
    observation = observed("P0")
    observation["facts"] = {}
    observation["provenance"] = {}
    assert rules().guard(observation)["decision"] == "ALLOW"


@pytest.mark.parametrize("invoice_currency,proposed_currency", [("usd", "USD"),
                                                               ("USD", "usd"),
                                                               (" usd ", " uSd ")])
def test_currency_case_and_surrounding_space_do_not_change_contract(invoice_currency, proposed_currency):
    observation = observed()
    set_fact(observation, "invoice_currency", invoice_currency)
    observation["proposal"]["currency"] = proposed_currency
    assert rules().guard(observation)["decision"] == "ALLOW"


@pytest.mark.parametrize("tool", ["unrecognized_transfer", None])
def test_p4_needs_recognized_payment_side_effect_boundary(tool):
    observation = observed()
    observation["proposal"]["tool"] = tool
    assert rules().guard(observation)["decision"] == "UNKNOWN"
    assert "proposal.tool" in rules().required_missing(observation)


def test_active_hold_requires_positive_clearance_proof_in_shared_safety_gate():
    observation = observed()
    set_fact(observation, "binding_hold", True)
    assert rules().guard(observation)["decision"] == "BLOCK"
    assert "human_cleared" in rules().required_missing(observation)


def test_large_payment_explicit_denial_cannot_leave_shared_safety_gate_empty():
    observation = observed(amount="10001")
    set_fact(observation, "human_approved", False, "independent_registry")
    assert rules().guard(observation)["decision"] == "BLOCK"
    assert "human_approved" in rules().required_missing(observation)


@pytest.mark.parametrize("clearance_sequence", [1, 2])
def test_clearance_before_or_at_new_hold_cannot_release_it(clearance_sequence):
    observation = observed()
    set_fact(observation, "binding_hold", True, sequence=2)
    set_fact(observation, "human_cleared", True, "independent_registry", sequence=clearance_sequence)
    assert rules().guard(observation)["decision"] == "BLOCK"
    assert "human_cleared" in rules().required_missing(observation)


def test_latest_valid_hold_event_controls_clearance_even_when_provenance_unordered():
    observation = observed()
    set_fact(observation, "binding_hold", True, sequence=1)
    recent = copy.deepcopy(observation["provenance"]["binding_hold"][0])
    recent["event_seq"] = 5
    observation["provenance"]["binding_hold"].append(recent)
    set_fact(observation, "human_cleared", True, "independent_registry", sequence=3)
    assert rules().guard(observation)["decision"] == "BLOCK"
    assert "human_cleared" in rules().required_missing(observation)


def test_latest_valid_clearance_after_hold_is_sufficient():
    observation = observed()
    set_fact(observation, "binding_hold", True, sequence=2)
    set_fact(observation, "human_cleared", True, "independent_registry", sequence=1)
    recent = copy.deepcopy(observation["provenance"]["human_cleared"][0])
    recent["event_seq"] = 3
    observation["provenance"]["human_cleared"].append(recent)
    assert rules().guard(observation)["decision"] == "ALLOW"
    assert rules().required_missing(observation) == []
    evidence = rules().guard(observation)["evidence"]
    assert next(item for item in evidence if item["fact"] == "human_cleared")["event_seq"] == 3


def test_whitespace_only_proposed_currency_is_missing_not_proven_wrong_currency():
    observation = observed()
    observation["proposal"]["currency"] = "  "
    assert rules().guard(observation)["decision"] == "UNKNOWN"
    assert "proposal.currency" in rules().required_missing(observation)
