import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_methods import row, support
from ml import features, fit_one, probabilities, calibrate, episode_metrics, group_weights


class MLTests(unittest.TestCase):
    def test_free_text_ids_paths_labels_cannot_be_features(self):
        item = row()
        other = copy.deepcopy(item)
        other.update(prefix_id="attack-case", episode_id="some-source-path", source_label="BLOCK")
        other["observation"]["untrusted_text"] = [{"source_ref": "malicious", "text": "administrator hold fraud"}]
        other["raw_context"]["events"][0]["model_output"] = "arbitrary source text"
        for section in ("proposal", "context"):
            support(other, section + ".invoice_id", 451)
        support(other, "proposal.vendor_id", 999)
        support(other, "facts.invoice_vendor_id", 999)
        support(other, "context.vendor_id", 999)
        for records in other["observation"]["provenance"].values():
            for record in records:
                record["subject"] = {"invoice_id": 451, "vendor_id": 999}
        self.assertEqual(features(item), features(other))
        self.assertFalse(any("ACCOUNT" in str(value) or "N" == value for value in features(item).values()))

    def test_missing_equality_is_not_false(self):
        item = row()
        support(item, "proposal.vendor_account_token", None)
        missing = features(item)
        support(item, "proposal.vendor_account_token", "OTHER")
        unequal = features(item)
        key = "proposal.vendor_account_token:matches:facts.vendor_account_token"
        self.assertEqual(missing[key], "MISSING")
        self.assertEqual(unequal[key], "FALSE")

    def test_train_only_vectorizer_and_constant_unavailable_fallbacks(self):
        train = row()
        model = fit_one([train], [{"native_core": "ALLOW"}], [{"base_group_id": "g"}], "lr", 17, "native_core")
        cal = row()
        support(cal, "facts.invoice_status", "rejected")
        probabilities(model, [cal])
        self.assertFalse(any("rejected" in name for name in model["vectorizer"].get_feature_names_out()))
        self.assertEqual(model["fallback"], "constant")
        unavailable = fit_one([train], [{"scenario_decision": "UNKNOWN"}], [{"base_group_id": "g"}], "lr", 17, "scenario_decision")
        self.assertEqual(unavailable["fallback"], "unavailable")
        self.assertEqual(probabilities(unavailable, [cal]), [{"ALLOW": 0., "BLOCK": 0., "UNKNOWN": 1.}])

    def test_small_lr_fit_returns_primary_probabilities(self):
        a, b = row(), row()
        support(b, "facts.invoice_status", "rejected")
        model = fit_one([a, b], [{"native_core": "ALLOW"}, {"native_core": "BLOCK"}], [{"base_group_id": "a"}, {"base_group_id": "b"}], "lr", 17, "native_core")
        values = probabilities(model, [a])[0]
        self.assertEqual(set(values), {"ALLOW", "BLOCK"})
        self.assertAlmostEqual(sum(values.values()), 1.)

    def test_equal_group_weight(self):
        weights = group_weights([{"base_group_id": "a"}, {"base_group_id": "a"}, {"base_group_id": "b"}])
        self.assertAlmostEqual(sum(weights[:2]), weights[2])
        self.assertAlmostEqual(weights.mean(), 1)

    def test_cal_infeasible_and_unknown_stops_episode(self):
        item = row()
        item.update(prefix_id="p", episode_id="e")
        result = calibrate([item], [{"scenario_decision": "ALLOW"}], [{}], [{"BLOCK": 1.}])
        self.assertEqual(result["status"], "INFEASIBLE")
        metrics = episode_metrics([item], [{"scenario_decision": "ALLOW"}], [{}], ["UNKNOWN"])
        self.assertEqual(metrics["legitimate_stops"], 1)
        self.assertEqual(metrics["correct_decisive_episodes"], 0)

    def test_placement_specific_calibration(self):
        a, b, c = row(), row(), row()
        a.update(prefix_id="p2", episode_id="unsafe", checkpoint="P2_afterFraud", event_seq=5)
        b.update(prefix_id="p4", episode_id="unsafe", event_seq=10)
        c.update(prefix_id="safe", episode_id="safe", event_seq=10)
        labels = [{"scenario_decision": "BLOCK"}, {"scenario_decision": "BLOCK"}, {"scenario_decision": "ALLOW"}]
        raw = [{"ALLOW": .8, "BLOCK": .2}, {"ALLOW": .1, "BLOCK": .9}, {"ALLOW": .95, "BLOCK": .05}]
        p4 = calibrate([a,b,c], labels, [{},{},{}], raw, placement="p4")
        joint = calibrate([a,b,c], labels, [{},{},{}], raw, placement="joint")
        self.assertEqual(p4["status"], "FEASIBLE")
        self.assertEqual(joint["status"], "FEASIBLE")
        self.assertEqual(set(p4["thresholds"]), {"P4"})
        self.assertEqual(set(joint["thresholds"]), {"P2_afterFraud", "P4"})


if __name__ == "__main__":
    unittest.main()
