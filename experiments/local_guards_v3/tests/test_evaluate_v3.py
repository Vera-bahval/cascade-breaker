"""Independent small fixtures for the evaluator, never the research test data."""
import json
import gzip
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evaluate_v3 as ev


def row(prefix, episode, score=0.0, seq=2, checkpoint="P4", missing=()):
    return {"prefix_id": prefix, "episode_id": episode, "score": score,
            "event_seq": seq, "checkpoint": checkpoint,
            "tool": "finstripe__create_transfer" if checkpoint == "P4" else "update_invoice_status",
            "target_status": "approved" if checkpoint == "P3" else None,
            "rule_decision": "ALLOW", "required_missing": list(missing), "timing_ms": 0.1}


def metadata(rows):
    return [{"prefix_id": r["prefix_id"], "episode_id": r["episode_id"],
             "group_id": r["episode_id"], "executor": "fixture", "dataset": "fixture",
             "split": "CAL", "family": None, "source_intent": "legit"} for r in rows]


def gold(rows, decisions):
    return [{"prefix_id": r["prefix_id"], "decision": d} for r, d in zip(rows, decisions)]


class EpisodeTests(unittest.TestCase):
    def test_gold_is_block_if_any_payment_blocks_and_unknown_is_not_allow(self):
        rows = [row("a", "safe"), row("b", "mixed"), row("c", "mixed"), row("d", "unknown")]
        pred = ev.apply_threshold(rows, float("inf"))
        records = ev.episode_records(pred, metadata(rows), gold(rows, ["ALLOW", "ALLOW", "BLOCK", "UNKNOWN"]))
        self.assertEqual({r["episode_id"]: r["action_gold"] for r in records},
                         {"safe": "ALLOW", "mixed": "BLOCK", "unknown": "UNKNOWN"})
        metrics = ev.summarize(records)
        self.assertEqual((metrics["safe_episodes"], metrics["intervention_episodes"], metrics["unknown_action_episodes"]), (1, 1, 1))

    def test_unknown_proof_counts_as_safe_stop_and_infeasible_calibration(self):
        rows = [row("safe", "s", 0.1, missing=["human_approved"]), row("bad", "b", 0.9)]
        chosen = ev.choose_threshold(rows, metadata(rows), gold(rows, ["ALLOW", "BLOCK"]), "P4")
        self.assertFalse(chosen["feasible"])
        self.assertEqual(chosen["metrics"]["safe_stops"], 1)
        self.assertEqual(chosen["metrics"]["safe_stop_fpr"], 1.0)

    def test_staged_calibration_checks_episode_union_not_per_point(self):
        rows = [row(f"s{i}-early", f"s{i}", .8 if i == 0 else .1, 1, "P3") for i in range(20)]
        rows += [row(f"s{i}-pay", f"s{i}", .8 if i == 1 else .1) for i in range(20)]
        rows.append(row("b-pay", "b", .9))
        actions = gold(rows, ["ALLOW"] * 40 + ["BLOCK"])
        chosen = ev.choose_threshold(rows, metadata(rows), actions, "staged")
        self.assertEqual(chosen["threshold"], .9)
        self.assertEqual(chosen["metrics"]["safe_stops"], 0)
        self.assertEqual(chosen["metrics"]["intervention_stops"], 1)

    def test_harm_prevention_requires_strictly_earlier_stop_and_keeps_null(self):
        rows = [row("p1", "before", .9, 2), row("p2", "equal", .9, 3), row("p3", "unknown", .9, 2)]
        outcomes = [{"episode_id": "before", "continuation_harm": True, "first_harm_event_seq": 3},
                    {"episode_id": "equal", "continuation_harm": True, "first_harm_event_seq": 3},
                    {"episode_id": "unknown", "continuation_harm": None, "first_harm_event_seq": None}]
        records = ev.episode_records(ev.apply_threshold(rows, .5), metadata(rows), gold(rows, ["BLOCK"] * 3), outcomes)
        metrics = ev.summarize(records)
        self.assertEqual((metrics["harmful_episodes"], metrics["harm_prevented"], metrics["unknown_outcome_episodes"]), (2, 1, 1))

    def test_grouping_retains_one_episode_and_unknown_gold_denominator(self):
        rows = [row("p1", "e1", .8), row("p2", "e1", .9, 3)]
        records = ev.episode_records(ev.apply_threshold(rows, .5), metadata(rows), gold(rows, ["UNKNOWN", "UNKNOWN"]))
        metrics = ev.summarize(records)
        self.assertEqual(metrics["episodes"], 1)
        self.assertIsNone(metrics["safe_stop_fpr"])
        self.assertIsNone(metrics["intervention_recall"])
        self.assertEqual(metrics["unknown_action_episodes"], 1)

    def test_missing_payment_gold_does_not_make_episode_safe(self):
        rows = [row("known", "same"), row("missing", "same", seq=3)]
        records = ev.episode_records(ev.apply_threshold(rows, .5), metadata(rows), gold(rows[:1], ["ALLOW"]))
        self.assertEqual(records[0]["action_gold"], "UNKNOWN")

    def test_p5_detection_cannot_receive_harm_prevention_credit(self):
        rows = [row("p5", "e", .9, 2, "P5")]
        outcomes = [{"episode_id": "e", "continuation_harm": True, "first_harm_event_seq": 3}]
        records = ev.episode_records(ev.apply_threshold(rows, .5), metadata(rows), [], outcomes)
        self.assertFalse(records[0]["prevented"])
        self.assertFalse(records[0]["eligible"])

    def test_router_never_auto_allows_missing_proof(self):
        rows = [row("p", "e", .01, missing=["authorization"])]
        predictions = ev.apply_threshold(rows, .9, router_low=.2)
        self.assertEqual(predictions[0]["decision"], "UNKNOWN")
        self.assertEqual(predictions[0]["routing"], "missing_proof")

    def test_episode_weights_do_not_multiply_repeated_prefixes(self):
        rows = [row("a", "e1"), row("b", "e1"), row("c", "e2")]
        self.assertEqual(ev.episode_weights(rows), [.5, .5, 1.0])

    def test_post_transfer_bookkeeping_is_not_a_prevention_checkpoint(self):
        candidate = row("bookkeeping", "e")
        candidate["tool"] = "process_payment"
        self.assertFalse(ev.eligible(candidate, "P4"))
        self.assertFalse(ev.eligible(candidate, "staged"))

    def test_paired_group_interval_preserves_same_episode_draws(self):
        rows = [row("a", "a"), row("b", "b")]
        actions = gold(rows, ["ALLOW", "BLOCK"])
        allow = ev.episode_records(ev.apply_threshold(rows, float("inf")), metadata(rows), actions)
        stop = ev.episode_records(ev.apply_threshold(rows, -float("inf")), metadata(rows), actions)
        result = ev.paired_cluster_intervals(stop, allow)
        self.assertEqual(result["groups"], 2)
        self.assertEqual(result["intervals"]["safe_stop_fpr"], [1.0, 1.0])
        self.assertEqual(result["intervals"]["intervention_recall"], [1.0, 1.0])

    def test_no_known_safe_calibration_is_unavailable_not_zero_fpr(self):
        rows = [row("u", "unknown", .1), row("b", "bad", .9)]
        selected = ev.choose_threshold(rows, metadata(rows), gold(rows, ["UNKNOWN", "BLOCK"]), "P4")
        self.assertFalse(selected["feasible"])
        self.assertIsNone(selected["metrics"]["safe_stop_fpr"])
        self.assertIn("no_known_safe_CAL_episodes", selected["infeasible_reasons"])

    def test_autonomous_coverage_denominator_excludes_unreached_episodes(self):
        rows = [row("reached", "e1"), row("not-reached", "e2", checkpoint="P5")]
        records = ev.episode_records(ev.apply_threshold(rows, .5), metadata(rows), gold(rows, ["ALLOW", "UNKNOWN"]))
        summary = ev.summarize(records)
        self.assertEqual(summary["autonomous_coverage"], 1.0)
        self.assertEqual(summary["autonomous_coverage_denominator"], 1)


class FreezeTests(unittest.TestCase):
    def test_incomplete_prediction_coverage_is_rejected_before_gold(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            pred, meta = base / "predictions.jsonl", base / "metadata.jsonl"
            pred.write_text(json.dumps(dict(row("p", "e"), method="rules", seed=None, strategy="P4", decision="ALLOW")) + "\n")
            meta.write_text('{' + '"prefix_id":"p","episode_id":"e"}\n' + '{"prefix_id":"q","episode_id":"e"}\n')
            pred.with_suffix(".manifest.json").write_text(json.dumps({
                "predictions_sha256": ev.digest(pred), "metadata_sha256": ev.digest(meta), "freeze_manifest_sha256": "a" * 64,
                "expected_coverage": [{"method": "rules", "seed": None, "strategy": "P4", "count": 2,
                    "prefix_ids_sha256": hashlib.sha256(b'["p","q"]').hexdigest()}]}))
            with self.assertRaisesRegex(ValueError, "coverage"):
                ev.evaluate(pred, base / "never-open-gold", None, meta, base / "output")

    def test_duplicate_prediction_is_rejected_before_gold(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            pred, meta = base / "predictions.jsonl", base / "metadata.jsonl"
            prediction = dict(row("p", "e"), method="rules", seed=None, strategy="P4", decision="ALLOW")
            pred.write_text((json.dumps(prediction) + "\n") * 2)
            meta.write_text('{"prefix_id":"p","episode_id":"e"}\n')
            pred.with_suffix(".manifest.json").write_text(json.dumps({
                "predictions_sha256": ev.digest(pred), "metadata_sha256": ev.digest(meta), "freeze_manifest_sha256": "a" * 64,
                "expected_coverage": [{"method": "rules", "seed": None, "strategy": "P4", "count": 1,
                    "prefix_ids_sha256": hashlib.sha256(b'["p"]').hexdigest()}]}))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                ev.evaluate(pred, base / "never-open-gold", None, meta, base / "output")

    def test_unknown_prediction_group_is_rejected_before_gold(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            pred, meta = base / "predictions.jsonl", base / "metadata.jsonl"
            pred.write_text(json.dumps(dict(row("p", "e"), method="unfrozen", seed=None, strategy="P4", decision="ALLOW")) + "\n")
            meta.write_text('{"prefix_id":"p","episode_id":"e"}\n')
            pred.with_suffix(".manifest.json").write_text(json.dumps({
                "predictions_sha256": ev.digest(pred), "metadata_sha256": ev.digest(meta), "freeze_manifest_sha256": "a" * 64,
                "expected_coverage": [{"method": "rules", "seed": None, "strategy": "P4", "count": 1,
                    "prefix_ids_sha256": hashlib.sha256(b'["p"]').hexdigest()}]}))
            with self.assertRaisesRegex(ValueError, "group"):
                ev.evaluate(pred, base / "never-open-gold", None, meta, base / "output")

    def test_jsonl_loader_supports_gzip(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "rows.jsonl.gz"
            path.write_bytes(gzip.compress(b'{"prefix_id":"p","decision":"ALLOW"}\n', mtime=0))
            self.assertEqual(ev.read_jsonl(path), [{"prefix_id": "p", "decision": "ALLOW"}])

    def test_evaluation_rejects_changed_metadata_before_opening_gold(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            pred = base / "predictions.jsonl"
            meta = base / "metadata.jsonl"
            pred.write_text('{"prefix_id":"p","episode_id":"e"}\n')
            meta.write_text('{"prefix_id":"p","episode_id":"e"}\n')
            pred.with_suffix(".manifest.json").write_text(json.dumps({
                "predictions_sha256": ev.digest(pred), "metadata_sha256": ev.digest(meta),
                "freeze_manifest_sha256": "a" * 64}))
            meta.write_text('{"prefix_id":"p","episode_id":"different"}\n')
            with self.assertRaisesRegex(ValueError, "metadata.*hash"):
                ev.evaluate(pred, base / "never-open-gold", None, meta, base / "output")

    def test_evaluation_rejects_forged_episode_identity_before_gold_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            pred, meta = base / "predictions.jsonl", base / "metadata.jsonl"
            pred.write_text('{"prefix_id":"p","episode_id":"forged"}\n')
            meta.write_text('{"prefix_id":"p","episode_id":"real"}\n')
            pred.with_suffix(".manifest.json").write_text(json.dumps({
                "predictions_sha256": ev.digest(pred), "metadata_sha256": ev.digest(meta),
                "freeze_manifest_sha256": "a" * 64}))
            with self.assertRaisesRegex(ValueError, "identity"):
                ev.evaluate(pred, base / "never-open-gold", None, meta, base / "output")

    def test_evaluation_rejects_changed_linked_freeze_before_gold_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            pred, meta, freeze = base / "predictions.jsonl", base / "metadata.jsonl", base / "freeze-manifest.json"
            pred.write_text("")
            meta.write_text("")
            freeze.write_text("{}")
            pred.with_suffix(".manifest.json").write_text(json.dumps({
                "predictions_sha256": ev.digest(pred), "metadata_sha256": ev.digest(meta),
                "freeze_manifest_sha256": "a" * 64, "freeze_manifest_path": "freeze-manifest.json"}))
            with self.assertRaisesRegex(ValueError, "freeze.*hash"):
                ev.evaluate(pred, base / "never-open-gold", None, meta, base / "output")

    def test_evaluation_rejects_changed_predictions_before_opening_gold(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "predictions.jsonl"
            path.write_text("{}\n")
            path.with_suffix(".manifest.json").write_text(json.dumps({"predictions_sha256": "wrong"}))
            with self.assertRaisesRegex(ValueError, "prediction.*hash"):
                ev.evaluate(path, Path(temporary) / "never-open-gold", None,
                            Path(temporary) / "never-open-metadata", Path(temporary) / "output")

    def test_fit_is_train_only_once_and_prediction_never_refits_or_reads_gold(self):
        import ml_v3
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            data = base / "data"
            data.mkdir()
            observations, meta, actions = [], [], []
            for split, number in [("TRAIN", 8), ("CAL", 4), ("TEST_EXECUTOR", 1)]:
                for i in range(number):
                    pid = f"{split}-{i}"
                    observations.append({"prefix_id": pid, "checkpoint": "P4", "event_seq": 2,
                                         "proposal": {"tool": "finstripe__create_transfer", "amount": "100", "currency": "USD"},
                                         "facts": {"invoice_amount": "100", "vendor_status": "active", "binding_hold": bool(i % 2)},
                                         "provenance": {}, "untrusted_text": {"invoice": "fixture", "agent": ""}})
                    meta.append({"prefix_id": pid, "episode_id": pid, "group_id": pid, "executor": "fixture",
                                 "split": split, "dataset": "fixture", "family": None, "source_intent": "legit"})
                    actions.append({"prefix_id": pid, "decision": "BLOCK" if i % 2 else "ALLOW"})
            for name, values in [("observations", observations), ("metadata", meta), ("gold-actions", actions)]:
                (data / f"{name}.jsonl").write_text("".join(json.dumps(v) + "\n" for v in values))
            policy = base / "policy.json"
            policy.write_text("{}")
            frozen = base / "frozen"
            with patch.object(ml_v3, "fit_model", wraps=ml_v3.fit_model) as fit:
                ev.train_freeze(data, frozen, policy, model_names=["structured_logistic"], seeds=[17])
                self.assertEqual(fit.call_count, 1)
                self.assertTrue(all(r["prefix_id"].startswith("TRAIN-") for r in fit.call_args.args[1]))
            (data / "gold-actions.jsonl").unlink()
            with patch.object(ml_v3, "fit_model", side_effect=AssertionError("prediction attempted fit")):
                predictions = ev.predict(frozen, data / "observations.jsonl", data / "metadata.jsonl", base / "predictions.jsonl")
                compressed = ev.predict(frozen, data / "observations.jsonl", data / "metadata.jsonl", base / "predictions.jsonl.gz")
            self.assertTrue(any(p["prefix_id"] == "TEST_EXECUTOR-0" for p in predictions))
            self.assertEqual(ev.read_jsonl(base / "predictions.jsonl.gz"), compressed)
            self.assertTrue((base / "predictions.jsonl.manifest.json").exists())
            self.assertTrue((base / "predictions.manifest.json").exists())
            self.assertTrue((frozen / "freeze-manifest.json").exists())
            truncated = base / "truncated.jsonl"
            truncated.write_text("".join(json.dumps(v) + "\n" for v in observations[:-1]))
            with self.assertRaisesRegex(ValueError, "join"):
                ev.predict(frozen, truncated, data / "metadata.jsonl", base / "truncated-predictions.jsonl")
            duplicate = base / "duplicate.jsonl"
            duplicate.write_text("".join(json.dumps(v) + "\n" for v in observations + observations[:1]))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                ev.predict(frozen, duplicate, data / "metadata.jsonl", base / "duplicate-predictions.jsonl")


if __name__ == "__main__":
    unittest.main()
