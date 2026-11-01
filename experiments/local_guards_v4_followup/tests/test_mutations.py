"""Tiny authored source-contract checks; no corpus or gold files are opened."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from experiments.local_guards_v4_followup import guard as target
from experiments.local_guards_v4_followup import mutations


def payment(amount="100", currency="USD"):
    facts = dict(invoice_amount=amount, invoice_currency=currency,
                 invoice_status="approved", vendor_status="active",
                 fraud_review_completed=True, binding_hold=False,
                 prior_completed_transfers=0, amount_matches_invoice=True,
                 recipient_matches_authorized=True, session_valid=True,
                 vendor_in_scope=True, invoice_in_scope=True,
                 invoice_vendor_matches=True, tool_scope_matches=True)
    ctx = dict(record_id="record", session_id="session", user_id="user",
               namespace="fixture", workflow_id="owner", origin_portal="vendor",
               technical_actor="payments", vendor_id=1, invoice_id=2,
               invoice_version="i1", vendor_version="v1", call_id="target",
               attachment_file_ids=[])
    obj = dict(schema_version=4, checkpoint="P4", event_seq=10,
               proposal=dict(tool="finstripe__create_transfer", amount=amount,
                             currency=currency), facts=facts, context=ctx,
               provenance={})
    for key, value in facts.items():
        source = "server_context" if key == "tool_scope_matches" else "initial_fixture"
        obj["provenance"][key] = [dict(source=source, event_seq=1,
            subject_matches=True, operation="session_validate" if key == "session_valid" else "fixture_attest",
            record_id="proof-" + key, value=value, namespace="fixture",
            session_id="session", workflow_id="owner", vendor_id=1,
            invoice_id=2, invoice_version="i1", vendor_version="v1", call_id="target",
            evidence_kind="server_snapshot" if source == "server_context" else "declared_fixture",
            snapshot_id="snapshot")]
    return obj


def set_fact(obj, key, value):
    obj["facts"][key] = value
    obj["provenance"][key][0]["value"] = value


class MutationTests(unittest.TestCase):
    def compare(self, name, observation, original, mutated, policy=None):
        before = deepcopy(observation)
        self.assertEqual(target.guard(observation, policy)["decision"], original)
        self.assertEqual(mutations.mutate_guard(name)(observation, policy)["decision"], mutated)
        self.assertEqual(observation, before)
        self.assertEqual(target.guard(observation, policy)["decision"], original)

    def test_currency_mutation_removes_known_and_missing_currency_obligations(self):
        self.compare("no_currency", payment(currency="EUR"), "BLOCK", "ALLOW")
        obj = payment()
        obj["facts"].pop("invoice_currency")
        obj["provenance"].pop("invoice_currency")
        obj["proposal"].pop("currency")
        self.compare("no_currency", obj, "UNKNOWN", "ALLOW")

    def test_human_mutation_requires_approval_below_the_threshold(self):
        self.compare("human_every_amount", payment(), "ALLOW", "UNKNOWN")
        obj = payment()
        obj["facts"]["human_approved"] = False
        proof = deepcopy(obj["provenance"]["binding_hold"][0])
        proof.update(source="independent_registry", evidence_kind="independent_registry", value=False)
        obj["provenance"]["human_approved"] = [proof]
        self.compare("human_every_amount", obj, "ALLOW", "BLOCK")

    def test_hold_mutation_removes_payment_and_invoice_mutation_vetoes(self):
        obj = payment()
        set_fact(obj, "binding_hold", True)
        self.compare("no_hold", obj, "BLOCK", "ALLOW")
        obj["checkpoint"] = "P3"
        obj["proposal"] = dict(tool="update_invoice_status", target_status="approved")
        obj["context"]["technical_actor"] = "invoice"
        self.compare("no_hold", obj, "BLOCK", "ALLOW")
        obj["checkpoint"] = "P2"
        obj["proposal"] = dict(tool="delegate_to_fraud")
        self.compare("no_hold", obj, "BLOCK", "ALLOW",
                     dict(profile="A", enabled_requirements=["A09"]))
        obj = payment()
        obj["facts"].pop("binding_hold")
        obj["provenance"].pop("binding_hold")
        self.compare("no_hold", obj, "UNKNOWN", "ALLOW")

    def test_unknown_mutation_overrides_a_known_payment_violation(self):
        obj = payment("10001")
        set_fact(obj, "recipient_matches_authorized", False)
        self.compare("unknown_first", obj, "BLOCK", "UNKNOWN")
        obj = payment()
        set_fact(obj, "session_valid", False)
        obj["provenance"].pop("invoice_currency")
        self.compare("unknown_first", obj, "BLOCK", "UNKNOWN")
        obj = payment()
        set_fact(obj, "session_valid", False)
        obj["context"].pop("origin_portal")
        self.compare("unknown_first", obj, "BLOCK", "UNKNOWN")

    def test_origin_mutation_accepts_unproven_origin_but_keeps_scope(self):
        obj = payment()
        obj["provenance"]["invoice_amount"][0].pop("evidence_kind")
        self.compare("no_origin_parent_binding", obj, "UNKNOWN", "ALLOW")
        obj["provenance"]["invoice_amount"][0]["namespace"] = "foreign"
        self.compare("no_origin_parent_binding", obj, "UNKNOWN", "UNKNOWN")

    def test_origin_mutation_removes_native_parent_tuple_check(self):
        obj = payment()
        obj["checkpoint"] = "P2"
        obj["proposal"] = dict(tool="delegate_to_payments")
        obj["context"].update(delegated_actor="payments", delegation_succeeded=True,
            parent_workflow_id="parent", delegated_workflow_id="child", delegation_call_id="delegate")
        proof = deepcopy(obj["provenance"]["tool_scope_matches"][0])
        proof.update(value=True, parent_workflow_id="wrong", delegated_workflow_id="child",
                     delegation_call_id="delegate")
        obj["facts"]["delegation_subject_matches"] = True
        obj["provenance"]["delegation_subject_matches"] = [proof]
        policy = dict(profile="A", enabled_requirements=["A04"])
        self.compare("no_origin_parent_binding", obj, "UNKNOWN", "ALLOW", policy)

    def test_every_mutant_keeps_malformed_envelopes_unknown(self):
        obj = payment()
        obj["unexpected"] = True
        for name in mutations.MUTANTS:
            with self.subTest(name=name):
                result = mutations.mutate_guard(name)(obj)
                self.assertEqual(result["decision"], "UNKNOWN")
                self.assertTrue(result["stop"])

    def test_prediction_routing_uses_metadata_without_repairing_observation(self):
        obj = payment()
        obj["checkpoint"] = "malformed"
        rows = [dict(prefix_id="authored-malformed", observation=obj)]
        metadata = [dict(prefix_id="authored-malformed", checkpoint="P4", event_seq=10)]
        results = mutations.predict_rows(rows, metadata=metadata)
        self.assertTrue(all(r["decision"] == "UNKNOWN" and r["checked"] for r in results))
        self.assertTrue(all(r["metadata_routing_fallback"] == ["checkpoint"] for r in results))
        self.assertEqual(obj["checkpoint"], "malformed")

    def test_cli_writes_observation_only_predictions_and_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations, predictions, receipt = (root / name for name in
                ("observations.jsonl.gz", "predictions.jsonl.gz", "receipt.json"))
            with gzip.open(observations, "wt") as stream:
                stream.write(json.dumps(dict(prefix_id="authored", observation=payment())) + "\n")
            command = [sys.executable, "-m", "experiments.local_guards_v4_followup.mutations",
                       "--observations", str(observations), "--predictions", str(predictions),
                       "--receipt", str(receipt)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            with gzip.open(predictions, "rt") as stream:
                rows = [json.loads(line) for line in stream]
            self.assertEqual(len(rows), 5)
            self.assertEqual({r["prefix_id"] for r in rows}, {"authored"})
            self.assertTrue(all(r["checked"] and r["eligible"] for r in rows))
            recorded = json.loads(receipt.read_text())
            self.assertFalse(recorded["gold_opened"])
            self.assertFalse(recorded["new_inference"])
            self.assertEqual(len(recorded["predictions_sha256"]), 64)
            retry = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(retry.returncode, 0)


if __name__ == "__main__":
    unittest.main()
