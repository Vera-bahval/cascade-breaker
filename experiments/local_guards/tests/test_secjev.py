import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from cascade_guard.secjev import SecJevScorer, canonical_hash
from cascade_guard.secjev_batch import batch_row, run_batch, inference_input_hash
from cascade_guard.secjev_benchmark import compare


class FakeRequestType:
    @staticmethod
    def model_validate(payload):
        if "state" not in payload or not payload.get("questions"):
            raise ValueError("Invalid request")
        return payload


class OverflowModel:
    def encode(self, tokenizer, record, **options):
        assert options["strict"] is True
        assert options["max_state"] == 8192
        raise ValueError("state exceeds 8192 tokens")


class SecJevUnitTests(unittest.TestCase):
    def test_overflow_returns_unknown_without_probabilities(self):
        scorer = object.__new__(SecJevScorer)
        scorer.lock = threading.Lock()
        scorer.metadata = {"model": "fake"}
        scorer.model = OverflowModel()
        scorer.tokenizer = None
        scorer.request_type = FakeRequestType
        scorer.to_record = lambda payload: (payload, [])
        result = scorer.score({"state": "long", "questions": {"q": {}}})
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["probabilities"], {})
        self.assertIn("8192", result["error"])

    def test_batch_uses_full_precision_true_probability(self):
        p = 0.9234567890123
        result = {"status": "OK", "probabilities": {"q": {"false": 1-p, "true": p}},
                  "timing_ms": {"total": 1.0}, "error": None}
        row = batch_row({"prefix_id": "p"}, "facts_action", result, "hash")
        self.assertEqual(row["probabilities"]["q"], p)
        self.assertEqual(row["distributions"]["q"]["false"], 1-p)
        self.assertFalse(row["unknown"])

    def test_resume_and_changed_inputs(self):
        calls = []
        def score(payload):
            calls.append(copy.deepcopy(payload))
            return {"status": "OK", "probabilities": {"q": {"false": 0.2, "true": 0.8}},
                    "timing_ms": {"total": 1}, "error": None}
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory)/"input.jsonl", Path(directory)/"scores.jsonl"
            prefix = {"prefix_id": "p1", "state": {"explanation": "rationale"},
                      "state_facts_action": {"explanation": ""}, "questions": {"q": {"type": "noul"}}}
            source.write_text(json.dumps(prefix)+"\n")
            first = run_batch(source, destination, score, "model-v1")
            second = run_batch(source, destination, score, "model-v1")
            self.assertEqual((first["processed"], second["skipped"]), (2, 2))
            self.assertEqual(len(calls), 2)
            prefix["state"]["explanation"] = "different rationale"
            source.write_text(json.dumps(prefix)+"\n")
            changed = run_batch(source, destination, score, "model-v1")
            self.assertEqual((changed["processed"], changed["skipped"]), (1, 1))
            version = run_batch(source, destination, score, "model-v2")
            self.assertEqual(version["processed"], 2)

    def test_missing_ablation_does_not_silently_score_subset(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory)/"input.jsonl", Path(directory)/"scores.jsonl"
            source.write_text(json.dumps({"prefix_id": "p", "state": {}, "questions": {}})+"\n")
            with self.assertRaisesRegex(ValueError, "state_facts_action"):
                run_batch(source, destination, lambda _: None, "v1")

    def test_exact_input_cache_preserves_all_prefix_rows_and_model_timing(self):
        calls = []
        def score(payload):
            calls.append(payload)
            return {"status": "OK", "probabilities": {"q": {"false": 0.2, "true": 0.8}},
                    "timing_ms": {"total": 10, "compute": 9}, "error": None}
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory)/"input.jsonl", Path(directory)/"scores.jsonl"
            rows = [{"prefix_id": f"p{i}", "state": {}, "state_facts_action": {},
                     "questions": {"q": {"type": "noul"}}} for i in range(2)]
            source.write_text("\n".join(json.dumps(row) for row in rows)+"\n")
            result = run_batch(source, destination, score, "v1")
            outputs = [json.loads(line) for line in destination.read_text().splitlines()]
            self.assertEqual(result["processed"], 4)
            self.assertEqual(result["model_calls"], 1)
            self.assertEqual(result["cache_hits"], 3)
            self.assertEqual(len(outputs), 4)
            self.assertEqual(outputs[0]["model_compute_ms"], 9)
            self.assertIsNone(outputs[1]["model_compute_ms"])
            self.assertEqual(outputs[1]["reused_reference_compute_ms"], 9)
            self.assertEqual(outputs[0]["probabilities"], outputs[-1]["probabilities"])

    def test_hash_preserves_input_and_ignores_key_order(self):
        self.assertEqual(canonical_hash({"x": 1, "y": 2}), canonical_hash({"y": 2, "x": 1}))
        self.assertNotEqual(canonical_hash({"x": 1}), canonical_hash({"x": 2}))

    def test_inference_cache_preserves_rendering_order(self):
        a = {"state": {"first": "one", "second": "two"}, "questions": {}}
        b = {"state": {"second": "two", "first": "one"}, "questions": {}}
        self.assertNotEqual(inference_input_hash(a, "v1"), inference_input_hash(b, "v1"))

    def test_parity_requires_same_decisions_even_below_numeric_tolerance(self):
        a = {"status": "OK", "probabilities": {"q": {"false": 0.4996, "true": 0.5004}}}
        b = {"status": "OK", "probabilities": {"q": {"false": 0.5004, "true": 0.4996}}}
        result = compare(a, b)
        self.assertLess(result["max_abs_delta"], 1e-3)
        self.assertFalse(result["passed"])
        self.assertEqual(result["categorical_flips"], ["q"])


if __name__ == "__main__":
    unittest.main()
