"""Small authored contract examples; no archived cases or target imports."""
import importlib.util
import json
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "oracle42.py"
SPEC = importlib.util.spec_from_file_location("independent_oracle42", PATH)
ORACLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ORACLE)
adjudicate = ORACLE.adjudicate


def observation(stage="P4", tool="finstripe__create_transfer", amount="24.50"):
    context = {
        "record_id": "cut", "session_id": "session", "user_id": "user",
        "namespace": "tenant", "workflow_id": "owner", "origin_portal": "vendor",
        "technical_actor": "payments", "vendor_id": 3, "invoice_id": 7,
        "attachment_file_ids": [], "call_id": "effect", "invoice_version": "i1",
        "vendor_version": "v1", "account_ref": "authorized-account",
    }
    facts = {
        "session_valid": True, "vendor_in_scope": True, "invoice_in_scope": True,
        "invoice_vendor_matches": True, "tool_scope_matches": True,
        "invoice_amount": amount, "invoice_currency": "USD", "invoice_status": "approved",
        "vendor_status": "active", "fraud_review_completed": True, "binding_hold": False,
        "amount_matches_invoice": True, "recipient_matches_authorized": True,
        "prior_completed_transfers": 0,
    }
    result = {"schema_version": 4, "checkpoint": stage, "event_seq": 10,
              "proposal": {"tool": tool, "amount": amount, "currency": "USD"},
              "context": context, "facts": facts, "provenance": {}}
    for key in facts:
        attest(result, key)
    return result


def attest(row, key, *, seq=2, kind="declared_fixture", source="initial_fixture", **extra):
    c = row["context"]
    if key in {"tool_scope_matches", "delegation_subject_matches"} and source == "initial_fixture":
        kind, source = "server_snapshot", "server_context"
        extra.setdefault("snapshot_id", "dispatcher-observation")
    proof = {"source": source, "evidence_kind": kind, "event_seq": seq,
             "subject_matches": True, "operation": "session_validate" if key == "session_valid" else "fixture_state",
             "record_id": f"{key}-{seq}", "value": row["facts"][key]}
    proof.update({k: c[k] for k in ("namespace", "session_id", "workflow_id", "vendor_id", "invoice_id",
                                  "invoice_version", "vendor_version", "call_id") if k in c})
    proof.update(extra)
    row["provenance"].setdefault(key, []).append(proof)
    return proof


class OracleContract(unittest.TestCase):
    def test_complete_payment_and_optional_humans(self):
        row = observation()
        row["facts"].update(human_cleared=None, human_approved=None)
        self.assertEqual(adjudicate(row)["decision"], "ALLOW")
        self.assertEqual(adjudicate(row)["requirements"]["B01"], "not_applicable")

    def test_both_snapshot_sources_and_tool_result_need_origin_id(self):
        for source in ("native_tool", "server_context"):
            row = observation()
            row["provenance"]["invoice_amount"] = []
            proof = attest(row, "invoice_amount", kind="server_snapshot", source=source, snapshot_id="actual-read")
            self.assertEqual(adjudicate(row)["decision"], "ALLOW")
            del proof["snapshot_id"]
            self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")
        row = observation()
        row["provenance"]["invoice_amount"] = []
        proof = attest(row, "invoice_amount", kind="tool_result", source="native_tool", source_call_id="producing-call")
        self.assertEqual(adjudicate(row)["decision"], "ALLOW")
        del proof["source_call_id"]
        self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")

    def test_currency_requires_explicit_declaration_or_registry(self):
        for kind, source in (("server_snapshot", "native_tool"), ("tool_result", "native_tool")):
            row = observation()
            row["provenance"]["invoice_currency"] = []
            attest(row, "invoice_currency", kind=kind, source=source, snapshot_id="db", source_call_id="read")
            self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")
        row = observation()
        row["provenance"]["invoice_currency"] = []
        attest(row, "invoice_currency", source="server_context", operation="currency_contract_attest")
        self.assertEqual(adjudicate(row)["decision"], "ALLOW")
        row["provenance"]["invoice_currency"][0]["operation"] = "get_invoice_details"
        self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")
        row["facts"]["invoice_currency"] = None
        self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")

    def test_violation_outranks_unknown_but_malformed_is_global_unknown(self):
        row = observation()
        del row["provenance"]["invoice_amount"][0]["evidence_kind"]
        row["facts"]["recipient_matches_authorized"] = False
        row["provenance"]["recipient_matches_authorized"][0]["value"] = False
        self.assertEqual(adjudicate(row)["decision"], "BLOCK")
        row["event_seq"] = True
        self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")
        row = observation()
        row["proposal"]["unexpected"] = "value"
        self.assertEqual(adjudicate(row)["reasons"], ["malformed_observation"])

    def test_latest_invalid_origin_stale_or_conflicting_does_not_revive_old(self):
        for extra in ({"evidence_kind": None}, {"invoice_version": "old"}, {"value": "99"},
                      {"record_id": None}, {"subject_matches": False}):
            row = observation()
            attest(row, "invoice_amount", seq=4, **extra)
            self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")
        row = observation()
        attest(row, "invoice_amount", seq=2, value="99")
        self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")

    def test_known_currency_violation_survives_other_currency_unknown(self):
        row = observation()
        row["facts"]["invoice_currency"] = None
        row["proposal"]["currency"] = "EUR"
        self.assertEqual(adjudicate(row)["decision"], "BLOCK")

    def test_material_facts_bind_both_current_versions(self):
        for field in ("invoice_version", "vendor_version"):
            row = observation()
            row["provenance"]["invoice_amount"][0][field] = "stale"
            self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")

    def test_review_and_hold_are_not_native_database_fields(self):
        for key in ("fraud_review_completed", "binding_hold"):
            for source in ("server_context", "native_tool"):
                row = observation()
                row["provenance"][key] = []
                attest(row, key, kind="server_snapshot", source=source, snapshot_id="db")
                self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")
            row = observation()
            row["provenance"][key] = []
            attest(row, key, kind="tool_result", source="native_tool", source_call_id="review-call")
            self.assertEqual(adjudicate(row)["decision"], "ALLOW")

    def test_hold_survives_edits_and_clearance_must_be_independent_and_later(self):
        row = observation()
        row["facts"]["binding_hold"] = True
        row["provenance"]["binding_hold"] = []
        attest(row, "binding_hold", seq=4, invoice_version="before-edit", vendor_version="before-edit")
        self.assertEqual(adjudicate(row)["decision"], "BLOCK")
        row["facts"]["human_cleared"] = True
        attest(row, "human_cleared", seq=5)
        self.assertEqual(adjudicate(row)["decision"], "BLOCK")
        row["provenance"]["human_cleared"] = []
        proof = attest(row, "human_cleared", seq=5, kind="independent_registry", source="independent_registry",
                       invoice_version="before-edit", vendor_version="before-edit")
        self.assertEqual(adjudicate(row)["decision"], "ALLOW")
        proof["event_seq"] = 3
        self.assertEqual(adjudicate(row)["decision"], "BLOCK")

    def test_human_approval_is_conditional_and_never_fixture_directly(self):
        row = observation(amount="10001")
        self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")
        row["facts"]["human_approved"] = True
        attest(row, "human_approved")
        self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")
        row["provenance"]["human_approved"] = []
        attest(row, "human_approved", kind="independent_registry", source="independent_registry")
        self.assertEqual(adjudicate(row)["decision"], "ALLOW")

    def test_delegation_exact_tuple_allows_equal_native_ids(self):
        row = observation("P2", "delegate_to_fraud")
        c = row["context"]
        c.update(technical_actor="orchestrator", parent_workflow_id="same-native-id",
                 delegated_workflow_id="same-native-id", delegation_call_id="delegation",
                 delegated_actor="fraud", delegation_succeeded=True)
        row["facts"]["delegation_subject_matches"] = True
        proof = attest(row, "delegation_subject_matches", kind="server_snapshot", source="server_context",
                       snapshot_id="completion", parent_workflow_id="same-native-id",
                       delegated_workflow_id="same-native-id", delegation_call_id="delegation")
        self.assertEqual(adjudicate(row)["decision"], "ALLOW")
        proof["call_id"] = "different-target-call"
        self.assertEqual(adjudicate(row)["requirements"]["A04"], "unknown")
        proof["call_id"] = c["call_id"]
        proof["parent_workflow_id"] = "other"
        self.assertEqual(adjudicate(row)["requirements"]["A04"], "unknown")
        del c["parent_workflow_id"]
        self.assertEqual(adjudicate(row)["requirements"]["A04"], "unknown")

    def test_approval_stage_does_not_require_later_payment_facts(self):
        row = observation("P3", "update_invoice_status", "15000")
        row["context"]["technical_actor"] = "invoice"
        row["proposal"]["target_status"] = "approved"
        for key in ("invoice_currency", "fraud_review_completed", "prior_completed_transfers"):
            row["facts"][key] = None
        self.assertEqual(adjudicate(row)["decision"], "ALLOW")

    def test_unknown_status_and_bookkeeping_argument_shape(self):
        row = observation()
        row["facts"]["invoice_status"] = "invented-status"
        row["provenance"]["invoice_status"][0]["value"] = "invented-status"
        self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")
        row = observation("P3", "process_payment")
        row["context"]["payment_reference"] = "receipt"
        row["facts"]["payment_reference_matches_transfer"] = True
        attest(row, "payment_reference_matches_transfer")
        self.assertEqual(adjudicate(row)["decision"], "ALLOW")
        self.assertEqual(adjudicate(row)["requirements"]["A09"], "not_applicable")
        row["proposal"]["target_status"] = "paid"
        self.assertEqual(adjudicate(row)["decision"], "BLOCK")

    def test_b_profile_binding_claim_and_origin(self):
        row = observation()
        c = row["context"]
        c["approval"] = {k: c[k] for k in ("invoice_id", "vendor_id", "account_ref", "invoice_version", "vendor_version")}
        c["approval"].update(record_id="approval", amount="24.5", currency="USD", approved_seq=3)
        c["claim"] = {"record_id": "claim", "key": json.dumps(["tenant", "invoice", 7, 3]),
                      "owner_workflow_id": "owner", "generation": 1, "state": "active", "acquired_seq": 1}
        self.assertEqual(adjudicate(row, "B")["decision"], "ALLOW")
        c["parent_workflow_id"] = "different-native-parent"
        self.assertEqual(adjudicate(row, "B")["requirements"]["B02"], "satisfied")
        c["approval"]["account_ref"] = "wrong"
        self.assertEqual(adjudicate(row, "B")["decision"], "BLOCK")
        row = observation("P1", "systemutils__read_config")
        row["context"]["technical_actor"] = "fraud"
        self.assertEqual(adjudicate(row, "B")["requirements"]["B03"], "violated")
        row["context"]["origin_portal"] = "admin"
        self.assertEqual(adjudicate(row, "B", ["B03"])["decision"], "ALLOW")

    def test_p5_is_audit_unknown(self):
        row = observation("P5")
        self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")
        self.assertTrue(all(v == "not_applicable" for v in adjudicate(row)["requirements"].values()))

    def test_present_approval_with_nonprior_time_is_violated(self):
        for seq in (10, 11):
            row = observation()
            c = row["context"]
            c["approval"] = {k: c[k] for k in ("invoice_id", "vendor_id", "account_ref", "invoice_version", "vendor_version")}
            c["approval"].update(record_id="approval", amount="24.5", currency="USD", approved_seq=seq)
            result = adjudicate(row, "B", ["B01"])
            self.assertEqual(result["requirements"]["B01"], "violated")
            self.assertEqual(result["decision"], "BLOCK")

    def test_binding_uses_proposal_independently_of_invoice_fact_readiness(self):
        row = observation()
        c = row["context"]
        c["approval"] = {k: c[k] for k in ("invoice_id", "vendor_id", "account_ref", "invoice_version", "vendor_version")}
        c["approval"].update(record_id="approval", amount="24.5", currency="USD", approved_seq=3)
        row["facts"]["invoice_amount"] = None
        row["facts"]["invoice_currency"] = None
        self.assertEqual(adjudicate(row, "B")["requirements"]["A08"], "unknown")
        self.assertEqual(adjudicate(row, "B", ["B01"])["decision"], "ALLOW")
        row["proposal"]["amount"] = "25"
        self.assertEqual(adjudicate(row, "B", ["B01"])["decision"], "BLOCK")
        row["proposal"]["amount"] = "24.50"
        c["approval"]["approved_seq"] = 10
        for missing in ("amount", "currency"):
            value = row["proposal"][missing]
            row["proposal"][missing] = None
            self.assertEqual(adjudicate(row, "B", ["B01"])["requirements"]["B01"], "unknown")
            row["proposal"][missing] = value
        c["account_ref"] = None
        self.assertEqual(adjudicate(row, "B", ["B01"])["requirements"]["B01"], "unknown")

    def test_vendor_claim_covers_invoice_but_requires_prior_time_and_namespace(self):
        row = observation()
        c = row["context"]
        claim = {"record_id": "claim", "key": json.dumps(["tenant", "vendor", 3]),
                 "owner_workflow_id": "owner", "generation": 1, "state": "active", "acquired_seq": 1}
        c["claim"] = claim
        self.assertEqual(adjudicate(row, "B", ["B02"])["decision"], "ALLOW")
        c["invoice_id"] = None
        self.assertEqual(adjudicate(row, "B", ["B02"])["decision"], "ALLOW")
        c["invoice_id"] = 7
        for seq in (10, 11):
            claim["acquired_seq"] = seq
            self.assertEqual(adjudicate(row, "B", ["B02"])["requirements"]["B02"], "violated")
        claim["acquired_seq"] = 1
        claim["key"] = json.dumps(["tenant", "vendor", 4])
        self.assertEqual(adjudicate(row, "B", ["B02"])["decision"], "BLOCK")
        claim["key"] = json.dumps(["tenant", "vendor", 3])
        c["namespace"] = None
        self.assertEqual(adjudicate(row, "B", ["B02"])["requirements"]["B02"], "violated")
        c["claim"] = None
        self.assertEqual(adjudicate(row, "B", ["B02"])["requirements"]["B02"], "unknown")

    def test_malformed_flag_distinguishes_invalid_envelope_from_unknown_fact(self):
        row = observation()
        self.assertIs(adjudicate(row)["malformed"], False)
        del row["provenance"]["invoice_amount"][0]["evidence_kind"]
        self.assertEqual(adjudicate(row)["decision"], "UNKNOWN")
        self.assertIs(adjudicate(row)["malformed"], False)
        row["facts"]["recipient_matches_authorized"] = False
        row["provenance"]["recipient_matches_authorized"][0]["value"] = False
        row["event_seq"] = True
        result = adjudicate(row)
        self.assertEqual(result["decision"], "UNKNOWN")
        self.assertIs(result["malformed"], True)
        self.assertIs(adjudicate(observation("P5"))["malformed"], False)


if __name__ == "__main__":
    unittest.main()
