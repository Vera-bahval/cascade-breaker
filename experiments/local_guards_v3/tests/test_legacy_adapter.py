import importlib.util
from pathlib import Path


def test_legacy_adapter_preserves_missingness_instead_of_defaulting_safe():
    path = Path(__file__).resolve().parents[1] / "legacy_adapter.py"
    assert path.exists(), "legacy input compatibility adapter is not implemented"
    spec = importlib.util.spec_from_file_location("legacy_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    row = {"checkpoint": "P4", "event_seq": 5,
           "proposal": {"tool": "finstripe__create_transfer", "amount": "20", "currency": "USD"},
           "facts": {}, "provenance": {}, "untrusted_text": {"invoice": "", "agent": ""}}
    for name in ("legacy_v1", "legacy_v2"):
        assert module.guard(row, name)["decision"] == "UNKNOWN"


def test_foreign_subject_clearance_does_not_clear_legacy_hold():
    path = Path(__file__).resolve().parents[1] / "legacy_adapter.py"
    spec = importlib.util.spec_from_file_location("legacy_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    facts = {"invoice_amount": "20", "invoice_currency": "USD", "invoice_status": "approved",
             "vendor_status": "active", "fraud_review_completed": True, "binding_hold": True,
             "human_cleared": True, "human_approved": None, "prior_completed_transfers": 0,
             "amount_matches_invoice": True, "recipient_matches_authorized": True}
    proof = {key: [{"event_seq": 1, "source": "native_tool", "operation": "snapshot",
                    "subject_matches": True}] for key, value in facts.items() if value is not None}
    proof["human_cleared"] = [{"event_seq": 1, "source": "independent_registry", "operation": "clearance",
                               "subject_matches": False}]
    row = {"checkpoint": "P4", "event_seq": 5,
           "proposal": {"tool": "finstripe__create_transfer", "amount": "20", "currency": "USD"},
           "facts": facts, "provenance": proof, "untrusted_text": {"invoice": "", "agent": ""}}
    assert module.guard(row, "legacy_v2")["decision"] == "BLOCK"
