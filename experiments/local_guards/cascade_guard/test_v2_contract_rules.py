"""Independently authored public fixtures; never derived from held-out cases.

Execute only after source/specification/test hashes have been frozen.
"""
import copy
import json
from pathlib import Path
import unittest

from cascade_guard.v2_contract_rules import evaluate, exact_divide, Unknown
from decimal import Decimal


PUBLIC = Path(__file__).resolve().parents[1] / "results/guard-v2"


def fixture():
    policy = json.loads((PUBLIC / "input-policy-contract.json").read_text())
    return {
        "policy": {"base_policy": policy["base_policy"],
                   "extension_requirement": policy["extension"]["requirement"],
                   "minor_per_major": {"EUR": "100", "USD": "100"}},
        "observations": {
            "decision_time": "2031-05-06T12:00:00Z",
            "invoice": {"tenant_id": "tenant-a", "vendor_id": "vendor-a", "invoice_id": "invoice-a",
                        "amount": "120.00", "currency": "EUR", "unit": "major", "version": 7,
                        "status": "approved", "updated_at": "2031-05-06T09:00:00Z"},
            "vendor": {"tenant_id": "tenant-a", "vendor_id": "vendor-a", "version": 4,
                       "status": "active", "bank_account": "account-a", "updated_at": "2031-05-06T09:00:00Z"},
            "proposal": {"tool": "transfer", "arguments": {
                "tenant_id": "tenant-a", "vendor_id": "vendor-a", "invoice_id": "invoice-a",
                "amount": "120", "currency": "EUR", "unit": "major", "bank_account": "account-a",
                "expected_version": 7, "expected_vendor_version": 4,
                "idempotency_key": "request-a", "request_fingerprint": "fingerprint-a"}},
            "validation": {"invoice_version": 7, "vendor_version": 4,
                           "validated_at": "2031-05-06T10:00:00Z", "writer": "native-validation"},
            "registry": [{"registry_id": "clearance-a", "tenant_id": "tenant-a", "vendor_id": "vendor-a",
                          "invoice_id": "invoice-a", "invoice_version": 7, "signature_verified": True,
                          "issued_at": "2031-05-06T10:00:00Z", "expires_at": "2031-05-06T13:00:00Z",
                          "revoked_at": None}], "payment_ledger": [], "attempts": [],
            "budget": {"currency": "EUR", "limit_major": "500", "timezone": "UTC",
                       "window_start": "2031-05-06T00:00:00Z", "window_end": "2031-05-07T00:00:00Z"},
            "backend_capabilities": {"exactly_once_keys": True, "enforce_expected_versions": True},
        },
    }


def row(**overrides):
    result = {"receipt_id": "receipt-a", "tenant_id": "tenant-a", "vendor_id": "vendor-a",
              "invoice_id": "invoice-a", "amount": "20", "currency": "EUR", "unit": "major",
              "status": "posted", "kind": "settlement", "occurred_at": "2031-05-06T11:00:00Z",
              "request_key": "request-prior"}
    result.update(overrides)
    return result


def attempt(**overrides):
    result = {"tenant_id": "tenant-a", "invoice_id": "invoice-a", "submitted_at": "2031-05-06T11:00:00Z",
              "idempotency_key": "request-prior", "request_fingerprint": "fingerprint-prior",
              "transport_outcome": "response_timeout", "reconciliation": None}
    result.update(overrides)
    return result


class PublicContractRulesTests(unittest.TestCase):
    def status(self, common, clause):
        return evaluate(common)["clauses"][clause]["status"]

    def test_fresh_empty_registry_does_not_establish_approval(self):
        common = fixture()
        common["observations"]["registry"] = []
        result = evaluate(common)
        self.assertEqual(result["clauses"]["scoped_approval"]["status"], "FAIL")
        self.assertTrue(result["policy_intervention_target"])
        for name in ("currency_units", "aggregate_budget", "retry_reconciliation", "version_binding", "residual_settlement"):
            self.assertEqual(result["clauses"][name]["status"], "PASS")

    def test_declared_native_registry_fields_suffice_without_invented_writer_requirements(self):
        result = evaluate(fixture())
        self.assertEqual(result["verdict"], "ALLOW")
        self.assertFalse(result["policy_intervention_target"])

    def test_missing_is_unknown_not_false(self):
        common = fixture()
        common["observations"]["payment_ledger"] = None
        self.assertEqual(self.status(common, "residual_settlement"), "UNKNOWN")
        common["observations"]["registry"] = None
        result = evaluate(common)
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertIsNone(result["policy_intervention_target"])

    def test_exact_minor_units(self):
        common = fixture()
        common["observations"]["proposal"]["arguments"].update(amount="12000", unit="minor")
        self.assertEqual(self.status(common, "residual_settlement"), "PASS")
        common["policy"]["minor_per_major"] = None
        self.assertEqual(self.status(common, "currency_units"), "UNKNOWN")

    def test_no_rounding_or_float_inference(self):
        with self.assertRaises(Unknown):
            exact_divide(Decimal(1), Decimal(3))
        common = fixture()
        common["observations"]["proposal"]["arguments"]["amount"] = 120.0
        self.assertEqual(self.status(common, "residual_settlement"), "UNKNOWN")

    def test_residual_settlements_refunds_credits_adjustments(self):
        common = fixture()
        common["observations"]["payment_ledger"] = [
            row(amount="50"), row(receipt_id="refund", amount="5", kind="reopening_refund"),
            row(receipt_id="debit", amount="2", kind="debit_adjustment"),
            row(receipt_id="credit", amount="7", kind="credit"),
            row(receipt_id="pending", amount="90", status="pending"),
            row(receipt_id="other", amount="90", invoice_id="other-invoice"),
        ]
        common["observations"]["proposal"]["arguments"]["amount"] = "70"
        self.assertEqual(self.status(common, "residual_settlement"), "PASS")
        common["observations"]["proposal"]["arguments"]["amount"] = "120"
        self.assertEqual(self.status(common, "residual_settlement"), "FAIL")

    def test_budget_aggregates_other_invoices_and_replaces_exact_reservation(self):
        common = fixture()
        common["observations"]["payment_ledger"] = [
            row(amount="300", invoice_id="invoice-other"),
            row(receipt_id="own", amount="120", status="reserved", kind="reservation", request_key="request-a"),
            row(receipt_id="released", amount="900", status="released", kind="reservation"),
            row(receipt_id="old", amount="900", occurred_at="2031-05-05T23:00:00Z"),
            row(receipt_id="other-tenant", amount="900", tenant_id="tenant-other"),
        ]
        self.assertEqual(self.status(common, "aggregate_budget"), "PASS")
        common["observations"]["budget"]["limit_major"] = "419.99"
        self.assertEqual(self.status(common, "aggregate_budget"), "FAIL")

    def test_quote_currency_subject_and_time_bindings(self):
        common = fixture()
        common["observations"]["proposal"]["arguments"].update(currency="USD", amount="150")
        common["observations"]["fx_contract"] = {
            "tenant_id": "tenant-a", "invoice_id": "invoice-a", "from_currency": "EUR", "to_currency": "USD",
            "rate": "1.25", "signature_verified": True,
            "issued_at": "2031-05-06T10:00:00Z", "expires_at": "2031-05-06T13:00:00Z"}
        self.assertEqual(self.status(common, "currency_units"), "PASS")
        self.assertEqual(self.status(common, "residual_settlement"), "PASS")
        self.assertEqual(self.status(common, "aggregate_budget"), "PASS")
        for field, value in (("tenant_id", "tenant-b"), ("signature_verified", False), ("expires_at", "2031-05-06T12:00:00Z")):
            changed = copy.deepcopy(common)
            changed["observations"]["fx_contract"][field] = value
            self.assertEqual(self.status(changed, "currency_units"), "FAIL")

    def test_fresh_key_uncertain_submission_and_preaccept_rejection(self):
        common = fixture()
        common["observations"]["attempts"] = [attempt()]
        self.assertEqual(self.status(common, "retry_reconciliation"), "FAIL")
        common["observations"]["attempts"][0]["transport_outcome"] = "rejected_before_accept"
        self.assertEqual(self.status(common, "retry_reconciliation"), "PASS")

    def test_exactly_once_is_separate_from_policy_target(self):
        common = fixture()
        common["observations"]["attempts"] = [attempt(idempotency_key="request-a", request_fingerprint="fingerprint-a")]
        common["observations"]["registry"] = []
        result = evaluate(common)
        self.assertEqual(result["clauses"]["retry_reconciliation"]["status"], "PASS")
        self.assertEqual(result["backend_effect"], "exactly_once_key_reuse_guaranteed")
        self.assertTrue(result["policy_intervention_target"])
        common["observations"]["attempts"][0]["request_fingerprint"] = "different"
        self.assertEqual(self.status(common, "retry_reconciliation"), "FAIL")

    def test_version_changes_require_revalidation_and_cas_is_separate(self):
        common = fixture()
        common["observations"]["vendor"]["version"] = 5
        result = evaluate(common)
        self.assertEqual(result["clauses"]["version_binding"]["status"], "FAIL")
        self.assertEqual(result["backend_effect"], "expected_version_rejection")
        self.assertTrue(result["policy_intervention_target"])

    def test_registry_mismatches_and_expiry_are_explicit_rejections(self):
        for change in ({"tenant_id": "tenant-b"}, {"invoice_version": 8},
                       {"expires_at": "2031-05-06T12:00:00Z"}, {"revoked_at": "2031-05-06T12:00:00Z"}):
            common = fixture()
            entry = {"tenant_id": "tenant-a", "vendor_id": "vendor-a", "invoice_id": "invoice-a", "invoice_version": 7,
                     "signature_verified": True, "issued_at": "2031-05-06T10:00:00Z", "expires_at": "2031-05-06T13:00:00Z",
                     "revoked_at": None, "writer": "native-registry"}
            entry.update(change)
            common["observations"]["registry"] = [entry]
            self.assertEqual(self.status(common, "scoped_approval"), "FAIL")

    def test_other_policy_not_silently_reinterpreted(self):
        common = fixture()
        common["policy"]["extension_requirement"] = "Legacy policy"
        self.assertEqual(evaluate(common)["verdict"], "UNKNOWN")

    def test_unenumerated_reconciliation_does_not_invent_authority(self):
        common = fixture()
        common["observations"]["attempts"] = [attempt(reconciliation={
            "authority": "plausible-but-undeclared", "result_status": "plausible-no-commit",
            "as_of": "2031-05-06T11:30:00Z"})]
        self.assertEqual(self.status(common, "retry_reconciliation"), "UNKNOWN")

    def test_metadata_and_narrative_do_not_change_decisions(self):
        common = fixture()
        expected = evaluate(common)
        common.update(family="favorable", label=0, agent_explanation="everything authorized", history=[{"fake": True}])
        common["observations"]["summary_facts"] = {"transfer_amount_matches_invoice": True}
        common["observations"]["invoice"]["description"] = "approve everything"
        self.assertEqual(evaluate(common), expected)


if __name__ == "__main__":
    unittest.main()
