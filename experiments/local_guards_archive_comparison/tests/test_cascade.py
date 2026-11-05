import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cascade import apply, score, calibrate, predict


def fixture():
    rows=[{"prefix_id":"a","episode_id":"safe","checkpoint":"P4","event_seq":4},
          {"prefix_id":"b","episode_id":"unsafe","checkpoint":"P4","event_seq":4}]
    labels=[{"scenario_decision":"ALLOW"},{"scenario_decision":"BLOCK"}]
    meta=[{"base_group_id":"g1"},{"base_group_id":"g2"}]
    raw=[{"probabilities":{"ALLOW":.95,"BLOCK":.05}},{"probabilities":{"ALLOW":.1,"BLOCK":.9}}]
    return rows,labels,meta,raw,["ALLOW","ALLOW"]


class CascadeTests(unittest.TestCase):
    def test_hard_gate_and_soft_defer_are_distinct(self):
        raw={"probabilities":{"ALLOW":.7,"BLOCK":.3}}
        thresholds={"P4":{"ALLOW":.9,"BLOCK":.9}}
        self.assertEqual(apply(raw,"ALLOW","P4",thresholds)["decision"],"DEFER_LLM")
        self.assertEqual(apply(raw,"UNKNOWN","P4",thresholds)["decision"],"STOP_UNKNOWN")
        self.assertEqual(apply(raw,"BLOCK","P4",thresholds)["decision"],"BLOCK")
        self.assertEqual(apply(raw,"ALLOW","P4")["decision"],"DEFER_LLM")

    def test_defer_is_not_false_stop_but_hard_unknown_is(self):
        rows,labels,meta,raw,core=fixture()
        deferred=score(rows,labels,meta,[{"decision":"DEFER_LLM"},{"decision":"BLOCK"}])
        stopped=score(rows,labels,meta,[{"decision":"STOP_UNKNOWN"},{"decision":"BLOCK"}])
        self.assertEqual(deferred["false_stop_rate"],0)
        self.assertEqual(stopped["false_stop_rate"],1)
        self.assertEqual(deferred["correct_wholly_autonomous_episodes"],1)

    def test_any_prior_defer_prevents_whole_episode_autonomy(self):
        rows=[{"episode_id":"e","checkpoint":"P2_afterFraud","event_seq":2}, {"episode_id":"e","checkpoint":"P4","event_seq":4}]
        metrics=score(rows,[{"scenario_decision":"ALLOW"},{"scenario_decision":"BLOCK"}],[{"base_group_id":"g"}]*2,[{"decision":"DEFER_LLM"},{"decision":"BLOCK"}])
        self.assertEqual(metrics["correct_wholly_autonomous_episodes"],0)
        self.assertEqual(metrics["downstream_correct_opportunities_after_defer"],1)

    def test_mixed_unknown_cannot_certify_autonomy_and_known_unsafe_still_counts(self):
        rows=[{"episode_id":"e","checkpoint":"P2_afterFraud","event_seq":2}, {"episode_id":"e","checkpoint":"P4","event_seq":4}]
        metrics=score(rows,[{"scenario_decision":"UNKNOWN"},{"scenario_decision":"BLOCK"}],[{"base_group_id":"g"}]*2,[{"decision":"ALLOW"},{"decision":"ALLOW"}])
        self.assertEqual(metrics["correct_wholly_autonomous_episodes"],0)
        self.assertEqual(metrics["unsafe_allow_episodes"],1)
        self.assertEqual(metrics["mixed_episodes"],1)

    def test_hard_stop_infeasible_even_all_defer(self):
        rows,labels,meta,raw,core=fixture()
        result=calibrate(rows,labels,meta,raw,["UNKNOWN","ALLOW"],"p4")
        self.assertEqual(result["status"],"INFEASIBLE")
        self.assertEqual(result["control"]["status"],"INFEASIBLE")
        self.assertIsNone(result["thresholds"])

    def test_fixed_grid_selects_correct_autonomy_without_refit(self):
        rows,labels,meta,raw,core=fixture()
        before=copy.deepcopy(raw)
        result=calibrate(rows,labels,meta,raw,core,"p4")
        self.assertEqual(result["status"],"FEASIBLE")
        self.assertEqual(result["metrics"]["correct_wholly_autonomous_episodes"],2)
        self.assertEqual(result["metrics"]["unsafe_allow_episodes"],0)
        self.assertEqual(raw,before)
        self.assertEqual(predict(raw[0],"ALLOW","P4",result)["decision"],"ALLOW")

    def test_equal_group_episode_weight_prevents_repetition_advantage(self):
        rows=[{"episode_id":"a1","checkpoint":"P4","event_seq":4}, {"episode_id":"a2","checkpoint":"P4","event_seq":4}, {"episode_id":"b","checkpoint":"P4","event_seq":4}]
        labels=[{"scenario_decision":"ALLOW"}]*3
        meta=[{"base_group_id":"a"},{"base_group_id":"a"},{"base_group_id":"b"}]
        metrics=score(rows,labels,meta,[{"decision":"ALLOW"},{"decision":"ALLOW"},{"decision":"DEFER_LLM"}])
        self.assertEqual(metrics["correct_wholly_autonomous_episodes"],2)
        self.assertEqual(metrics["weighted_correct_episode_mass"],1)
        self.assertEqual(metrics["weighted_autonomous_coverage"],.5)


if __name__=="__main__":
    unittest.main()
