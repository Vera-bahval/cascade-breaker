import copy
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from cascade_guard import cheap_nli, cheap_scalar
from cascade_guard.cheap_scalar import FIXED_CLAIM_IDS, ScalarProfileAdapter, create_adapter


class Tokenizer:
    def encode(self, text, add_special_tokens=False):
        return [ord(char) for char in text]

    def num_special_tokens_to_add(self, pair=True):
        return 3

    def build_inputs_with_special_tokens(self, premise, claim):
        return [999] + premise + [998] + claim + [998]


def make_record():
    return {"prefix_id": "p", "input_hash": "unchanged-full-input-hash", "payload": {
        "trusted_sources": [{"source_id": source, "trust": source, "text": source + " evidence"}
                            for source in ("trusted_policy", "trusted_native", "trusted_combined")],
        "claims": [{"claim_id": key, "claim_type": key, "fixed": True, "text": key}
                   for key in FIXED_CLAIM_IDS] + [
                       {"claim_id": "explanation_0", "claim_type": "explanation_sentence",
                        "fixed": False, "text": "untrusted argument"}],
        "untrusted_premise": "untrusted invoice and assertions",
        "untrusted_invoice_text": "invoice", "agent_explanation": "assertion"}}


def mock_adapter(block):
    adapter = object.__new__(ScalarProfileAdapter)
    adapter.block = block
    adapter.max_length = 512
    adapter.tokenizer = Tokenizer()
    adapter.model_metadata = {}
    calls = []
    def infer(ids):
        calls.append(ids)
        support = 0.1 + sum(ids) % 80 / 100
        if block == "N":
            probabilities = {"entailment": support, "contradiction": (1-support)/2,
                             "neutral": (1-support)/2}
        else:
            probabilities = {"supported": support, "unsupported": 1-support}
        return probabilities, False
    adapter.infer_ids = infer
    return adapter, calls


class CheapScalarTests(unittest.TestCase):
    def test_only_four_fixed_claims_against_combined_source(self):
        adapter, calls = mock_adapter("N")
        record = make_record()
        before = copy.deepcopy(record)
        result = adapter.score(record)
        self.assertEqual(len(calls), 4)
        self.assertEqual(result["window_count"], 4)
        self.assertEqual({(item["source_id"], item["claim_id"]) for item in result["raw"]},
                         {("trusted_combined", claim) for claim in FIXED_CLAIM_IDS})
        self.assertTrue(all(item["fixed"] for item in result["raw"]))
        self.assertTrue(all(item["windows"][0]["probabilities"] for item in result["raw"]))
        self.assertEqual(record, before)
        self.assertEqual(result["features"]["untrusted_premise.fraud_completed.missingness"], 1)
        self.assertEqual(result["features"]["untrusted_premise.fraud_completed.entailment.max"], -1)

    def test_scalar_exactly_matches_full_parent_for_both_blocks_and_multiple_windows(self):
        record = make_record()
        record["payload"]["trusted_sources"][-1]["text"] = "trusted_combined evidence " * 70
        for block in ("N", "M"):
            with self.subTest(block=block):
                adapter, calls = mock_adapter(block)
                profile = adapter.score(record)
                profile_calls = len(calls)
                full = cheap_nli.NLIAdapter.score(adapter, record)
                self.assertEqual(profile["scalar_risk"], full["scalar_risk"])
                parent_raw = [item for item in full["raw"]
                              if item["fixed"] and item["source_id"] == "trusted_combined"]
                self.assertEqual(profile["raw"], parent_raw)
                self.assertEqual(profile["window_count"], sum(len(item["windows"]) for item in parent_raw))
                self.assertGreater(profile_calls, 4)
                self.assertGreater(full["window_count"], profile["window_count"])
                for key, value in profile["features"].items():
                    if key.startswith("trusted_combined.") and ".explanation_sentence." not in key:
                        self.assertEqual(value, full["features"][key])

    def test_nonfixed_claims_and_other_premises_do_not_affect_profile(self):
        adapter, calls = mock_adapter("M")
        record = make_record()
        first = adapter.score(record)
        changed = copy.deepcopy(record)
        changed["payload"]["untrusted_premise"] = "arbitrary attack text " * 1000
        changed["payload"]["untrusted_invoice_text"] = "different invoice"
        changed["payload"]["agent_explanation"] = "different assertion"
        for source in changed["payload"]["trusted_sources"]:
            if source["source_id"] != "trusted_combined":
                source["text"] = "totally different " * 1000
        changed["payload"]["claims"][-1]["text"] = "other nonfixed claim " * 1000
        changed["payload"]["claims"].append({"claim_id": "ignored", "claim_type": "fraud_completed",
                                              "fixed": False, "text": "ignored sentence"})
        second = adapter.score(changed)
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 8)

    def test_parent_hash_is_literal_and_factory_rejects_drift_before_loading(self):
        actual = hashlib.sha256(Path(cheap_nli.__file__).read_bytes()).hexdigest()
        self.assertEqual(cheap_scalar.PARENT_SHA256, actual)
        with patch.object(cheap_scalar, "PARENT_SHA256", "0" * 64), \
                patch.object(cheap_nli.NLIAdapter, "__init__") as load:
            with self.assertRaisesRegex(RuntimeError, "parent source hash mismatch"):
                create_adapter("fake", "rev", Path("/tmp/no-model"))
            load.assert_not_called()

    def test_factory_retains_parent_metadata_and_marks_execution_profile(self):
        def parent_init(adapter, model_id, revision, model_dir, device):
            adapter.block = "N"
            adapter.model_metadata = {"model_id": model_id, "revision": revision,
                                      "device": device, "original": True}
        with patch.object(cheap_nli.NLIAdapter, "__init__", parent_init):
            adapter = create_adapter("fake", "rev", Path("/tmp/no-model"), "cpu")
        self.assertTrue(adapter.model_metadata["original"])
        self.assertEqual(adapter.model_metadata["profile"], "fixed4_trusted_combined_only")
        self.assertEqual(adapter.model_metadata["parent_adapter_sha256"], cheap_scalar.PARENT_SHA256)
        self.assertEqual(adapter.model_metadata["scalar_claim_ids"], list(FIXED_CLAIM_IDS))

    def test_incomplete_or_duplicate_view_is_rejected_before_inference(self):
        for mutation in ("missing_claim", "duplicate_claim", "wrong_claim_type", "missing_source", "duplicate_source"):
            with self.subTest(mutation=mutation):
                adapter, calls = mock_adapter("N")
                record = make_record()
                payload = record["payload"]
                if mutation == "missing_claim":
                    payload["claims"].pop(0)
                elif mutation == "duplicate_claim":
                    payload["claims"].append(copy.deepcopy(payload["claims"][0]))
                elif mutation == "wrong_claim_type":
                    payload["claims"][0]["claim_type"] = "other"
                elif mutation == "missing_source":
                    payload["trusted_sources"].pop()
                else:
                    payload["trusted_sources"].append(copy.deepcopy(payload["trusted_sources"][-1]))
                with self.assertRaises(ValueError):
                    adapter.score(record)
                self.assertEqual(calls, [])

    def test_overlong_fixed_claim_is_unknown_without_extra_inference(self):
        adapter, calls = mock_adapter("M")
        record = make_record()
        record["payload"]["claims"][0]["text"] = "x" * 509
        result = adapter.score(record)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIsNone(result["scalar_risk"])
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["raw"][0]["windows"], [])

    def test_deadline_before_first_claim_performs_no_inference(self):
        adapter, calls = mock_adapter("N")
        adapter.deadline_ts = 0
        with self.assertRaises(TimeoutError):
            adapter.score(make_record())
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
