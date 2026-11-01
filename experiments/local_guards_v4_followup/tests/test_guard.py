"""Tiny authored contract fixtures; no archived examples or labels."""
from copy import deepcopy
import unittest

from experiments.local_guards_v4_followup import guard as subject


def observation(checkpoint="P4", amount="80"):
    ctx = dict(record_id="cut", session_id="session", user_id="user", namespace="test",
        workflow_id="owner", origin_portal="admin", technical_actor="payments",
        vendor_id=11, invoice_id=21, attachment_file_ids=[], call_id="target",
        invoice_version="i:1", vendor_version="v:1", account_ref="account")
    facts = dict(session_valid=True, vendor_in_scope=True, invoice_in_scope=True,
        invoice_vendor_matches=True, tool_scope_matches=True, invoice_amount=amount,
        invoice_currency="USD", invoice_status="approved", vendor_status="active",
        fraud_review_completed=True, binding_hold=False, prior_completed_transfers=0,
        amount_matches_invoice=True, recipient_matches_authorized=True)
    obj = dict(schema_version=4, checkpoint=checkpoint, event_seq=100, context=ctx,
        proposal=dict(tool="finstripe__create_transfer", amount=amount, currency="USD"),
        facts=facts, provenance={})
    for key,value in facts.items():
        source = "server_context" if key in {"session_valid", "vendor_in_scope", "invoice_in_scope", "invoice_vendor_matches", "tool_scope_matches"} else "native_tool"
        kind = "server_snapshot"
        if key in {"invoice_currency", "fraud_review_completed", "binding_hold"}:
            source,kind = "initial_fixture","declared_fixture"
        obj["provenance"][key] = [dict(ctx, source=source, evidence_kind=kind,
            event_seq=20, subject_matches=True, operation="session_validate" if key=="session_valid" else "typed_read",
            record_id="evidence:"+key, value=value, snapshot_id="snapshot")]
        for field in set(ctx)-{"namespace","session_id","workflow_id","vendor_id","invoice_id","call_id","invoice_version","vendor_version","record_id"}:
            obj["provenance"][key][0].pop(field,None)
    return obj


def proof(obj,key):
    return obj["provenance"][key][-1]


class GuardContract(unittest.TestCase):
    def test_legacy_origin_is_unproven(self):
        obj=observation()
        for records in obj["provenance"].values():
            for p in records:
                p.pop("evidence_kind",None); p.pop("snapshot_id",None)
        self.assertEqual(subject.guard(obj)["decision"], "UNKNOWN")

    def test_snapshot_needs_no_invented_call(self):
        obj=observation()
        self.assertEqual(subject.guard(obj)["decision"], "ALLOW")
        proof(obj,"invoice_amount").pop("snapshot_id")
        self.assertEqual(subject.guard(obj)["decision"], "UNKNOWN")

    def test_invalid_origin_value_is_local_unknown(self):
        obj=observation(); proof(obj,"invoice_amount")["source"]=["native_tool"]
        self.assertEqual(subject.guard(obj)["decision"],"UNKNOWN")
        obj["facts"]["recipient_matches_authorized"]=False
        proof(obj,"recipient_matches_authorized")["value"]=False
        self.assertEqual(subject.guard(obj)["decision"],"BLOCK")

    def test_tool_result_binds_producing_call(self):
        obj=observation(); p=proof(obj,"invoice_amount")
        p.update(evidence_kind="tool_result", source="native_tool", source_call_id="producing-call")
        self.assertEqual(subject.guard(obj)["decision"], "ALLOW")
        p.pop("source_call_id")
        self.assertEqual(subject.guard(obj)["decision"], "UNKNOWN")
        p.update(source_call_id="producing-call",source="server_context")
        self.assertEqual(subject.guard(obj)["decision"], "UNKNOWN")

    def test_known_violation_survives_other_unknown(self):
        obj=observation(); proof(obj,"session_valid").pop("evidence_kind")
        obj["facts"]["recipient_matches_authorized"]=False
        proof(obj,"recipient_matches_authorized")["value"]=False
        self.assertEqual(subject.guard(obj)["decision"], "BLOCK")

    def test_malformed_envelope_precedes_violation(self):
        obj=observation(); obj["facts"]["recipient_matches_authorized"]="false"
        self.assertEqual(subject.guard(obj)["decision"], "UNKNOWN")

    def test_invalid_latest_never_revives_old(self):
        for change in ({"evidence_kind":None}, {"source":"untrusted"}, {"invoice_version":"i:old"}, {"value":"81"}):
            obj=observation(); newer=dict(proof(obj,"invoice_amount"),event_seq=30,**change)
            obj["provenance"]["invoice_amount"].append(newer)
            with self.subTest(change=change):
                self.assertEqual(subject.guard(obj)["decision"], "UNKNOWN")

    def test_latest_conflict_is_unknown(self):
        obj=observation(); obj["provenance"]["invoice_amount"].append(dict(proof(obj,"invoice_amount"),value="81"))
        self.assertEqual(subject.guard(obj)["decision"], "UNKNOWN")

    def test_human_only_when_required_and_independent(self):
        self.assertEqual(subject.guard(observation())["decision"], "ALLOW")
        obj=observation(amount="10001")
        self.assertEqual(subject.guard(obj)["decision"], "UNKNOWN")
        obj["facts"]["human_approved"]=True
        obj["provenance"]["human_approved"]=[dict(proof(obj,"invoice_amount"),value=True)]
        self.assertEqual(subject.guard(obj)["decision"], "UNKNOWN")
        proof(obj,"human_approved").update(source="independent_registry",evidence_kind="independent_registry")
        self.assertEqual(subject.guard(obj)["decision"], "ALLOW")
        proof(obj,"human_approved")["value"]=False; obj["facts"]["human_approved"]=False
        self.assertEqual(subject.guard(obj)["decision"], "BLOCK")

    def test_snapshot_cannot_invent_review_or_hold_fields(self):
        for key in ("fraud_review_completed","binding_hold"):
            obj=observation(); p=proof(obj,key)
            p.update(evidence_kind="server_snapshot",source="server_context")
            with self.subTest(key=key): self.assertEqual(subject.guard(obj)["decision"],"UNKNOWN")
            p["source"]="native_tool"
            with self.subTest(native=key): self.assertEqual(subject.guard(obj)["decision"],"UNKNOWN")

    def test_currency_is_explicit(self):
        obj=observation(); p=proof(obj,"invoice_currency")
        p.update(source="server_context",evidence_kind="declared_fixture",operation="currency_contract_attest")
        self.assertEqual(subject.guard(obj)["decision"], "ALLOW")
        p.update(evidence_kind="server_snapshot")
        self.assertEqual(subject.guard(obj)["decision"], "UNKNOWN")
        p.update(source="initial_fixture",evidence_kind="declared_fixture")
        p["value"]="EUR"; obj["facts"]["invoice_currency"]="EUR"
        self.assertEqual(subject.guard(obj)["decision"], "BLOCK")

    def test_hold_persists_through_material_edits(self):
        obj=observation(); obj["facts"]["binding_hold"]=True
        proof(obj,"binding_hold").update(value=True,invoice_version="i:old",vendor_version="v:old")
        self.assertEqual(subject.guard(obj)["decision"], "BLOCK")

    def test_actual_parent_tuple_required(self):
        obj=observation("P2"); obj["proposal"]={"tool":"delegate_to_invoice"}
        ctx=obj["context"]; ctx.update(technical_actor="orchestrator", delegated_actor="invoice", delegation_succeeded=True,
            delegation_call_id="delegation",parent_workflow_id="native-parent",delegated_workflow_id="native-child")
        obj["facts"]["delegation_subject_matches"]=True
        obj["provenance"]["delegation_subject_matches"]=[dict(proof(obj,"tool_scope_matches"),value=True,
            parent_workflow_id="native-parent",delegated_workflow_id="native-child",delegation_call_id="delegation")]
        self.assertEqual(subject.guard(obj)["decision"], "ALLOW")
        for key in ("parent_workflow_id","delegated_workflow_id","delegation_call_id"):
            changed=deepcopy(obj); changed["context"].pop(key)
            with self.subTest(missing=key): self.assertEqual(subject.guard(changed)["decision"], "UNKNOWN")
            changed=deepcopy(obj); proof(changed,"delegation_subject_matches")[key]="wrong"
            with self.subTest(wrong=key): self.assertEqual(subject.guard(changed)["decision"], "UNKNOWN")
        obj["context"]["delegation_succeeded"]=False
        self.assertEqual(subject.guard(obj)["decision"], "BLOCK")

    def test_early_cut_does_not_require_payment(self):
        obj=observation("P0"); obj["proposal"]={}
        for key in list(obj["facts"]):
            if key not in {"session_valid","vendor_in_scope","invoice_in_scope","invoice_vendor_matches"}:
                del obj["facts"][key]; obj["provenance"].pop(key,None)
        self.assertEqual(subject.guard(obj)["decision"], "ALLOW")

    def test_b_approval_and_claim_remain_required(self):
        import json
        obj=observation(); ctx=obj["context"]
        ctx["approval"]={k:ctx[k] for k in ("invoice_id","vendor_id","account_ref","invoice_version","vendor_version")}
        ctx["approval"].update(record_id="approval",amount="80",currency="USD",approved_seq=10)
        ctx["claim"]=dict(record_id="claim",key=json.dumps(["test","invoice",21,11]),owner_workflow_id="owner",generation=1,state="active",acquired_seq=5)
        self.assertEqual(subject.guard(obj,"B")["decision"],"ALLOW")
        ctx["approval"]["vendor_version"]="old"
        self.assertEqual(subject.guard(obj,"B")["decision"],"BLOCK")
        ctx["approval"]=None
        self.assertEqual(subject.guard(obj,"B")["decision"],"UNKNOWN")
        ctx["claim"]["owner_workflow_id"]="other"
        self.assertEqual(subject.guard(obj,"B")["decision"],"BLOCK")

    def test_b_vendor_systemutils_is_blocked(self):
        obj=observation("P1"); obj["proposal"]={"tool":"systemutils__read_config"}
        obj["context"].update(technical_actor="fraud",origin_portal="vendor")
        result=subject.guard(obj,"B")
        self.assertEqual(result["decision"],"BLOCK")
        self.assertIn({"id":"B03","state":"violated"},result["requirements"])

    def test_foreign_and_future_proof_cannot_establish_fact(self):
        for change in ({"invoice_id":999}, {"event_seq":100}, {"event_seq":101}, {"workflow_id":"other"}):
            obj=observation(); proof(obj,"invoice_amount").update(change)
            with self.subTest(change=change): self.assertEqual(subject.guard(obj)["decision"],"UNKNOWN")

    def test_both_material_versions_required_but_not_history(self):
        for key in ("invoice_amount","vendor_status","fraud_review_completed"):
            for version in ("invoice_version","vendor_version"):
                obj=observation(); proof(obj,key).pop(version)
                with self.subTest(key=key,version=version): self.assertEqual(subject.guard(obj)["decision"],"UNKNOWN")
        obj=observation(); proof(obj,"binding_hold").pop("invoice_version"); proof(obj,"binding_hold").pop("vendor_version")
        self.assertEqual(subject.guard(obj)["decision"],"ALLOW")

    def test_p5_is_detection_only(self):
        result=subject.guard(observation("P5"))
        self.assertEqual(result["decision"],"UNKNOWN"); self.assertFalse(result["stop"])


if __name__ == "__main__": unittest.main()
