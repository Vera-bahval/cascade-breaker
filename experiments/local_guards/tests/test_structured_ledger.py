import copy
import gzip
import json
import unittest
from pathlib import Path

from cascade_guard.structured_ledger import build_ledger, build_views, ordered_hash

BASE = Path(__file__).resolve().parent.parent


def example(prefix_id):
    rows = {r["prefix_id"]: r for r in map(json.loads, (BASE / "data/prefixes.jsonl").read_text().splitlines())}
    row = rows[prefix_id]
    run = next(r for r in map(json.loads, gzip.decompress((BASE / "data/archive/shadow-main.jsonl.gz").read_bytes()).decode().splitlines())
               if r["run_id"] == row["episode_id"])
    context = next(s for s in run["steps"] if s["seq"] == row["cut_seq"])
    return row, run, context


class StructuredLedgerTests(unittest.TestCase):
    def test_future_guard_and_allocation_metadata_cannot_change_ledger(self):
        row, run, context = example("115dc554d7e53b650b6c8343")
        original, _ = build_views(run["db_initial"], context, run["steps"], row["state"], row["questions"])
        changed = copy.deepcopy(run)
        for step in changed["steps"]:
            if step["seq"] >= context["seq"] or step["kind"] in ("guard", "llm", "injection", "guard_context"):
                step.update({"source_case": "OUTCOME_SECRET", "guard_verdict": "BLOCK_SECRET", "output": "FUTURE_SECRET"})
        changed.update({"db_final": "FINAL_SECRET", "case_id": "ATTACK_SECRET", "label": "LABEL_SECRET"})
        result, metadata = build_views(changed["db_initial"], context, changed["steps"], row["state"], row["questions"])
        self.assertEqual(original, result)
        for meta in metadata.values():
            self.assertLess(meta["max_observed_seq"], context["seq"])
        text = json.dumps(result)
        for forbidden in ("SECRET", run["run_id"], run["namespace"], run["case_id"], "db_final", "guard_verdict"):
            self.assertNotIn(forbidden, text)

    def test_native_write_success_is_separate_from_failed_task(self):
        row, run, context = example("0f7d422abce6d7ca36ce9e36")
        ledger, _ = build_ledger(run["db_initial"], context, run["steps"])
        risk_update = next(e for e in ledger["chronological_actions"] if e.get("tool") == "update_vendor_risk")
        self.assertTrue(risk_update["call_success"])
        self.assertTrue(risk_update["effect"]["committed"])
        self.assertEqual(ledger["latest_agent_task_status"]["fraud_agent"]["task_status"], "failed")
        self.assertTrue(any(o["requirement"] == "successful Fraud task completion" for o in ledger["unresolved_obligations"]))

    def test_committed_approval_is_not_independent_authorization(self):
        row, run, context = example("ed96cde3a858bf046ca3dd73")
        ledger, _ = build_ledger(run["db_initial"], context, run["steps"])
        origin = ledger["current_field_provenance"]["invoice_status"]
        self.assertEqual(origin["value"], "approved")
        self.assertEqual(origin["writer"], "invoice_agent")
        self.assertFalse(origin["independent_authorization"])
        self.assertEqual(ledger["latest_agent_task_status"]["fraud_agent"]["task_status"], "success")

    def test_proposal_keeps_concrete_mismatch_without_future_result(self):
        row, run, context = example("bc50aabae33e7e9a39d5bd9f")
        ledger, _ = build_ledger(run["db_initial"], context, run["steps"], compact=True)
        action = ledger["current_proposed_action"]
        self.assertFalse(action["executed"])
        self.assertEqual(action["arguments"]["amount"], 3680)
        self.assertEqual(ledger["original_facts"]["invoice_amount"], 3200)
        self.assertNotEqual(action["arguments"]["vendor_account"], ledger["original_facts"]["authorized_vendor_account"])

    def test_current_state_and_question_order_exactly_preserved(self):
        row, run, context = example("baea55b592c4314234ad2bb3")
        views, _ = build_views(run["db_initial"], context, run["steps"], row["state"], row["questions"])
        payload = {"state": row["state"], "questions": row["questions"]}
        self.assertEqual(ordered_hash(payload), ordered_hash(views["current_state"]))
        for view in views.values():
            self.assertEqual(json.dumps(view["questions"]), json.dumps(row["questions"]))
        compact = views["compact_evidence_ledger"]["state"]["compact_evidence_ledger"]
        self.assertNotIn("deduplicated_agent_and_supplier_texts", compact)
        self.assertNotIn("agent_notes", json.dumps(compact["committed_and_task_actions"]))

    def test_supplier_description_and_generated_payment_description_keep_origins(self):
        row, run, context = example("baea55b592c4314234ad2bb3")
        ledger, _ = build_ledger(run["db_initial"], context, run["steps"])
        catalog = ledger["deduplicated_agent_and_supplier_texts"]
        argument_ref = ledger["current_proposed_action"]["arguments"]["description_text_ref"]
        self.assertEqual(catalog[argument_ref]["trust"], "agent-generated tool argument; not independent permission evidence")
        invoice_read = next(e for e in ledger["chronological_actions"] if e.get("tool") == "get_invoice_details")
        supplier_ref = invoice_read["result"]["description_text_ref"]
        self.assertEqual(catalog[supplier_ref]["trust"], "untrusted supplier input")


if __name__ == "__main__":
    unittest.main()
