import datetime as dt
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

from cascade_guard.cheap_inputs import digest
from cascade_guard.cheap_nli import aggregate, pair_windows
from cascade_guard.cheap_runtime import heavy_lease, run_serial


class Tokenizer:
    def encode(self, text, add_special_tokens=False):
        return list(range(len(text.split())))

    def num_special_tokens_to_add(self, pair=True):
        return 3

    def build_inputs_with_special_tokens(self, premise, claim):
        return [999] + premise + [998] + claim + [998]


class CheapNLITests(unittest.TestCase):
    def test_complete_overlapping_premise_and_full_claim(self):
        plan = pair_windows(Tokenizer(), "p " * 1300, "c " * 20)
        covered = set()
        for w in plan["windows"]:
            covered.update(range(w["start_token"], w["end_token"]))
            self.assertLessEqual(len(w["input_ids"]), 512)
            self.assertEqual(w["input_ids"][-21:-1], list(range(20)))
        self.assertEqual(covered, set(range(1300)))
        for first, second in zip(plan["windows"], plan["windows"][1:]):
            self.assertEqual(first["end_token"] - second["start_token"], 64)

    def test_overlong_claim_unknown_without_truncation(self):
        plan = pair_windows(Tokenizer(), "p " * 700, "c " * 509)
        self.assertEqual(plan["status"], "UNKNOWN")
        self.assertEqual(plan["claim_tokens"], 509)
        self.assertEqual(plan["windows"], [])

    def test_minicheck_unsupported_never_contradiction_and_fixed_only_risk(self):
        raw = [{"claim_id": f"c{i}", "claim_type": c, "fixed": True, "source_id": "trusted_combined", "status": "OK", "windows": [{"probabilities": {"supported": prob, "unsupported": 1-prob}}]} for i, (c, prob) in enumerate(zip(("fraud_completed", "hold_clear", "invariants_compliant", "policy_authorized"), (.9, .8, .7, .6)))]
        a = aggregate(raw, "M")
        self.assertAlmostEqual(a["scalar_risk"], .4)
        self.assertFalse(any("contradiction" in k for k in a["features"]))
        raw.append({"claim_id": "explanation_0", "claim_type": "explanation_sentence", "fixed": False, "source_id": "trusted_combined", "status": "OK", "windows": [{"probabilities": {"supported": .01, "unsupported": .99}}]})
        b = aggregate(raw, "M")
        self.assertEqual(a["scalar_risk"], b["scalar_risk"])
        self.assertEqual(set(a["features"]), set(b["features"]))
        raw[0]["status"] = "UNKNOWN"; raw[0]["windows"] = []
        self.assertIsNone(aggregate(raw, "M")["scalar_risk"])

    def test_nli_entailment_and_contradiction_independently_retained(self):
        raw = [{"claim_id": "fraud_completed", "claim_type": "fraud_completed", "fixed": True, "source_id": "trusted_combined", "status": "OK", "windows": [{"probabilities": {"entailment": .8, "contradiction": .1, "neutral": .1}}, {"probabilities": {"entailment": .1, "contradiction": .85, "neutral": .05}}]}]
        features = aggregate(raw, "N")["features"]
        self.assertEqual(features["trusted_combined.fraud_completed.entailment.max"], .8)
        self.assertEqual(features["trusted_combined.fraud_completed.contradiction.max"], .85)

    def test_serial_resume_refuses_input_drift_and_lease_is_exclusive(self):
        module = types.ModuleType("cheap_test_fake")
        module.__file__ = __file__
        class Adapter:
            block = "TEST"
            model_metadata = {"test": True}
            def score(self, record):
                return {"status": "OK", "features": {"x": 1.}, "scalar_risk": .5, "window_count": 1, "raw": []}
        module.create = lambda **kw: Adapter()
        sys.modules[module.__name__] = module
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); inputs = root / "inputs.jsonl"; out = root / "scores.jsonl"
            records = [{"prefix_id": str(i), "payload": {"n": i}, "input_hash": digest({"n": i})} for i in range(2)]
            inputs.write_text("".join(json.dumps(r)+"\n" for r in records))
            args = dict(deadline=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(), resource_lease=True)
            result = run_serial(inputs, out, "cheap_test_fake:create", "fake", "rev", root, limit=1, **args)
            self.assertEqual(result["completed"], 1)
            result = run_serial(inputs, out, "cheap_test_fake:create", "fake", "rev", root, **args)
            self.assertEqual(result["completed"], 2)
            self.assertTrue(all(json.loads(x)["inference_cost_ms"] >= 0 for x in out.read_text().splitlines()))
            inputs.write_text(inputs.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "Resume rejected"):
                run_serial(inputs, out, "cheap_test_fake:create", "fake", "rev", root, **args)
            with heavy_lease(root / "lock", True):
                with self.assertRaises(RuntimeError):
                    with heavy_lease(root / "lock", True):
                        pass


if __name__ == "__main__":
    unittest.main()
