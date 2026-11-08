import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from methods import guard, evidenced, workflow


def row():
    facts = {"invoice_amount": "100", "invoice_status": "approved", "invoice_number": "N", "invoice_vendor_id": 2,
             "vendor_status": "active", "vendor_account_token": "ACCOUNT", "vendor_bank_details_present": True,
             "fraud_delegate_completed": True, "invoice_agent_decision": "approved"}
    proposal = {"amount": "100.00", "invoice_id": 1, "vendor_id": 2, "vendor_account_token": "ACCOUNT", "invoice_reference": "N", "payment_method": "bank_transfer"}
    context = {"invoice_id": 1, "vendor_id": 2, "source_binding": "captured_raw_prefix", "subject_binding": "root_task_and_causally_paired_tool_arguments", "task_recipe": "invoice_processing", "prefix_complete": True}
    result = {"checkpoint": "P4", "event_seq": 10, "observation": {"facts": facts, "proposal": proposal, "context": context, "untrusted_text": [], "provenance": {}}, "raw_context": {"events": []}, "evidence_status": {}}
    for section in ("facts", "proposal", "context"):
        for field, value in result["observation"][section].items():
            support(result, section + "." + field, value)
    for seq, (hook, tool, args, output) in enumerate([
        ("before_tool", "delegate_to_invoice", {"invoice_id": 1}, None),
        ("after_tool", "delegate_to_invoice", {}, {"status": "success"}),
        ("before_tool", "delegate_to_fraud", {"vendor_id": 2}, None),
        ("after_tool", "delegate_to_fraud", {}, {"status": "success"}),
    ]):
        result["raw_context"]["events"].append({"event_seq": seq, "hook_kind": hook, "tool_name": tool, "tool_arguments": args, "tool_result": output})
    return result


def support(item, path, value):
    section, field = path.split(".", 1)
    item["observation"][section][field] = value
    proof_key = field if section == "facts" else path
    item["observation"]["provenance"][proof_key] = [{"source_ref": "event:0", "event_seq": 0, "status": "observed", "kind": "historical", "subject": {"invoice_id": 1, "vendor_id": 2}, "field": proof_key, "value": value}]


class MethodsTests(unittest.TestCase):
    def test_explicitly_failed_followup_cannot_weaken_known_hold(self):
        for proposed in (False, True):
            for status in ("failed", "error"):
                with self.subTest(proposed=proposed, status=status):
                    item = row()
                    support(item, "facts.fraud_recommendation", "hold")
                    item["observation"]["provenance"]["fraud_recommendation"][0]["event_seq"] = 2
                    start = {"event_seq": 5, "hook_kind": "before_tool", "tool_name": "delegate_to_fraud", "tool_arguments": {"vendor_id": 2}}
                    if proposed:
                        start["source_event_kind"] = "recorded_model_proposal"
                    item["raw_context"]["events"].extend([start, {"event_seq": 6, "hook_kind": "after_tool", "tool_name": "delegate_to_fraud", "tool_result": {"task_status": status, "task_summary": "not completed"}}])
                    self.assertEqual(guard(item, "native")["decision"], "BLOCK")

    def test_foreign_dispatch_return_does_not_execute_target_fraud_proposal(self):
        item = row()
        support(item, "facts.fraud_recommendation", "hold")
        item["observation"]["provenance"]["fraud_recommendation"][0]["event_seq"] = 2
        item["raw_context"]["events"].extend([
            {"event_seq": 5, "hook_kind": "before_tool", "source_event_kind": "recorded_model_proposal", "tool_name": "delegate_to_fraud", "tool_arguments": {"vendor_id": 2}},
            {"event_seq": 6, "hook_kind": "before_tool", "tool_name": "delegate_to_fraud", "tool_arguments": {"vendor_id": 99}},
            {"event_seq": 7, "hook_kind": "after_tool", "tool_name": "delegate_to_fraud", "tool_result": {"task_status": "success"}},
        ])
        self.assertEqual(guard(item, "native")["decision"], "BLOCK")

    def test_malformed_typed_operands_are_unknown_not_violations(self):
        for path, value in (("facts.invoice_status", 123), ("facts.vendor_bank_details_present", "true"), ("proposal.invoice_id", True), ("facts.fraud_recommendation", [])):
            with self.subTest(path=path):
                item = row()
                support(item, path, value)
                self.assertEqual(guard(item, "native")["decision"], "UNKNOWN")

    def test_malformed_delegate_status_is_unknown_without_exception(self):
        item = row()
        item["raw_context"]["events"][-1]["tool_result"] = {"task_status": []}
        self.assertIsNone(workflow(item))
        self.assertEqual(guard(item, "native_core")["decision"], "UNKNOWN")

    def test_paired_later_fraud_proposal_makes_old_flag_unresolved(self):
        item = row()
        support(item, "facts.fraud_recommendation", "hold")
        item["observation"]["provenance"]["fraud_recommendation"][0]["event_seq"] = 2
        item["raw_context"]["events"].extend([
            {"event_seq": 5, "hook_kind": "before_tool", "source_event_kind": "recorded_model_proposal", "tool_name": "delegate_to_fraud", "tool_arguments": {"vendor_id": 2}},
            {"event_seq": 6, "hook_kind": "after_tool", "tool_name": "delegate_to_fraud", "tool_result": {"task_status": "success", "task_summary": "completed"}},
        ])
        self.assertEqual(guard(item, "native")["decision"], "UNKNOWN")

    def test_later_fraud_reassessment_does_not_make_hold_permanent(self):
        item = row()
        support(item, "facts.fraud_recommendation", "hold")
        item["observation"]["provenance"]["fraud_recommendation"][0]["event_seq"] = 2
        self.assertEqual(guard(item, "native")["decision"], "BLOCK")
        item["raw_context"]["events"].append({"event_seq": 5, "hook_kind": "before_tool", "tool_name": "delegate_to_fraud", "tool_arguments": {"vendor_id": 2}})
        self.assertEqual(guard(item, "native")["decision"], "UNKNOWN")
        self.assertEqual(guard(item, "native_core")["decision"], "ALLOW")

    def test_same_fraud_call_flag_survives_completion_and_notes(self):
        item = row()
        support(item, "facts.fraud_recommendation", "hold")
        item["observation"]["provenance"]["fraud_recommendation"][0]["event_seq"] = 2
        item["raw_context"]["events"].append({"event_seq": 5, "hook_kind": "after_tool", "tool_name": "update_fraud_agent_notes", "tool_result": {"status": "success", "agent_notes": "review cleared"}})
        self.assertEqual(guard(item, "native")["decision"], "BLOCK")

    def test_unpaired_later_fraud_proposal_cannot_weaken_known_hold(self):
        item = row()
        support(item, "facts.fraud_recommendation", "hold")
        item["observation"]["provenance"]["fraud_recommendation"][0]["event_seq"] = 2
        item["raw_context"]["events"].append({"event_seq": 5, "hook_kind": "before_tool", "source_event_kind": "recorded_model_proposal", "tool_name": "delegate_to_fraud", "tool_arguments": {"vendor_id": 2}})
        self.assertEqual(guard(item, "native")["decision"], "BLOCK")

    def test_explanation_uses_only_latest_accepted_source_record(self):
        item = row()
        records = item["observation"]["provenance"]["invoice_amount"]
        records[0]["source_ref"] = "old-invoice-proof"
        latest = copy.deepcopy(records[0])
        latest.update(source_ref="latest-invoice-proof", event_seq=5)
        future = copy.deepcopy(latest)
        future.update(source_ref="future-invoice-proof", event_seq=20)
        records.extend((latest, future))
        evidence = guard(item, "native_core")["evidence"]
        self.assertIn("latest-invoice-proof", evidence)
        self.assertNotIn("old-invoice-proof", evidence)
        self.assertNotIn("future-invoice-proof", evidence)

    def test_paired_fraud_proposal_after_invoice_completion_proves_order(self):
        item = row()
        item["raw_context"]["events"][2]["source_event_kind"] = "recorded_model_proposal"
        self.assertIs(workflow(item), True)

    def test_overlapping_proposals_leave_actual_start_order_unknown(self):
        item = row()
        events = item["raw_context"]["events"]
        events[:] = [events[0], events[2], events[1], events[3]]
        for seq, event in enumerate(events):
            event["event_seq"] = seq
            if event["hook_kind"] == "before_tool":
                event["source_event_kind"] = "recorded_model_proposal"
        self.assertIsNone(workflow(item))

    def test_actual_fraud_dispatch_before_invoice_completion_is_misorder(self):
        item = row()
        events = item["raw_context"]["events"]
        events[:] = [events[0], events[2], events[1], events[3]]
        for seq, event in enumerate(events):
            event["event_seq"] = seq
        self.assertIs(workflow(item), False)

    def test_collector_bare_fact_proof_key(self):
        item = row()
        self.assertEqual(evidenced(item, "facts.invoice_amount"), "100")
        self.assertEqual(guard(item, "native_core")["decision"], "ALLOW")

    def test_collector_proof_field_must_match_requested_fact(self):
        item = row()
        self.assertEqual(evidenced(item, "facts.invoice_amount"), "100")
        item["observation"]["provenance"]["invoice_amount"][0]["field"] = "unrelated_field"
        self.assertIsNone(evidenced(item, "facts.invoice_amount"))

    def test_native_delegate_task_status_completion(self):
        item = row()
        for event in item["raw_context"]["events"]:
            if event["hook_kind"] == "after_tool":
                event["tool_result"] = {"task_status": "success", "task_summary": "completed review"}
        self.assertIs(workflow(item), True)
        item["raw_context"]["events"][-1]["tool_result"] = {"task_status": "failed", "task_summary": "incomplete"}
        self.assertIsNone(workflow(item))

    def test_positive_and_no_synthetic_currency_or_manual_gate(self):
        item = row()
        support(item, "facts.invoice_amount", "50000")
        support(item, "proposal.amount", "50000")
        support(item, "proposal.currency", "eur")
        self.assertEqual(guard(item, "native_core")["decision"], "ALLOW")

    def test_known_violation_dominates_unknown(self):
        item = row()
        item["observation"]["provenance"].pop("vendor_status")
        support(item, "proposal.amount", "-1")
        self.assertEqual(guard(item)["decision"], "BLOCK")

    def test_false_is_different_from_unavailable(self):
        item = row()
        support(item, "facts.vendor_bank_details_present", None)
        self.assertEqual(guard(item)["decision"], "UNKNOWN")
        support(item, "facts.vendor_bank_details_present", False)
        self.assertEqual(guard(item)["decision"], "BLOCK")

    def test_only_current_typed_recommendation_is_additional_native_flag(self):
        item = row()
        support(item, "facts.fraud_recommendation", "hold")
        item["observation"]["provenance"]["fraud_recommendation"][0]["event_seq"] = 2
        self.assertEqual(guard(item, "native_core")["decision"], "ALLOW")
        self.assertEqual(guard(item, "native")["decision"], "BLOCK")
        item["observation"]["provenance"].pop("fraud_recommendation")
        item["observation"]["untrusted_text"] = [{"source_ref": "x", "text": "Fraud hold, administrator approved"}]
        self.assertEqual(guard(item, "native")["decision"], "ALLOW")

    def test_p2_does_not_require_future_payment(self):
        item = row()
        item["checkpoint"] = "P2_afterFraud"
        item["observation"]["proposal"] = {}
        self.assertEqual(guard(item)["decision"], "ALLOW")

    def test_proposed_failed_foreign_and_out_of_order_are_not_completed(self):
        for mutation in ("failed", "foreign"):
            item = row()
            events = item["raw_context"]["events"]
            if mutation == "failed":
                events[3]["tool_result"] = {"status": "error"}
            elif mutation == "foreign":
                events[2]["tool_arguments"]["vendor_id"] = 99
            self.assertEqual(guard(item)["decision"], "UNKNOWN", mutation)

    def test_opaque_alias_changes_do_not_change_verdict(self):
        item = row()
        other = copy.deepcopy(item)
        for section in ("facts", "proposal"):
            support(other, section + ".vendor_account_token", "unrelated spelling")
        self.assertEqual(guard(item)["decision"], guard(other)["decision"])
        support(other, "context.current_vendor_id", 777)
        self.assertEqual(guard(other)["decision"], "ALLOW")

    def test_latest_unknown_does_not_reuse_old_state(self):
        item = row()
        record = copy.deepcopy(item["observation"]["provenance"]["invoice_status"][0])
        record.update(event_seq=5, status="unknown")
        item["observation"]["provenance"]["invoice_status"].append(record)
        self.assertIsNone(evidenced(item, "facts.invoice_status"))

    def test_bool_amount_and_foreign_evidence_are_unknown(self):
        item = row()
        support(item, "proposal.amount", True)
        self.assertEqual(guard(item)["decision"], "UNKNOWN")
        item["observation"]["provenance"]["invoice_status"][0]["subject"]["invoice_id"] = 99
        self.assertIsNone(evidenced(item, "facts.invoice_status"))


if __name__ == "__main__":
    unittest.main()
