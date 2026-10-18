"""Independent public arithmetic and join fixtures; no experiment data."""
import itertools
import unittest

from cascade_guard.v2_external_diagnostics import average_precision, control_predictions, summarize


class ExternalDiagnosticsAuditTests(unittest.TestCase):
    def test_partial_ties_have_exact_stepwise_area(self):
        self.assertAlmostEqual(average_precision([1, 0, 1, 0], [.9, .9, .8, .1]), 7 / 12)
        self.assertAlmostEqual(average_precision([0, 1, 1, 0], [.9, .8, .8, .1]), 2 / 3)

    def test_tied_area_is_invariant_to_input_order(self):
        items = [(1, .9), (0, .9), (1, .8), (0, .1)]
        for permuted in itertools.permutations(items):
            labels, scores = zip(*permuted)
            self.assertAlmostEqual(average_precision(labels, scores), 7 / 12)

    def test_degenerate_support_is_explicit(self):
        self.assertIsNone(average_precision([], []))
        self.assertIsNone(average_precision([0, 0], [.2, .4]))
        self.assertEqual(average_precision([1, 1], [.2, .4]), 1.)
        self.assertAlmostEqual(average_precision([1, 0, 0], [.2, .2, .2]), 1 / 3)

    def test_unknown_score_excluded_and_backend_null_preserved(self):
        labels = [dict(episode_id='a', contract_requires_intervention=False,
                       backend_diagnostic={'status': 'indeterminate_replay_effect', 'harmful_effect_if_executed': None}),
                  dict(episode_id='b', contract_requires_intervention=True,
                       backend_diagnostic={'status': 'posted_new_transfer', 'harmful_effect_if_executed': True}),
                  dict(episode_id='c', contract_requires_intervention=False,
                       backend_diagnostic={'status': 'rejected_version_conflict', 'harmful_effect_if_executed': False})]
        predictions = [dict(episode_id=e, policy='A', denominator='reached', seed=17,
                            arm='public-model', probability=p, unknown=u, block=b, rule_stop=False)
                       for e, p, u, b in [('a', .99, True, True), ('b', .8, False, False), ('c', .1, False, False)]]
        value = summarize(predictions, labels)[0]
        self.assertEqual(value['known_ranking_coverage'], {'k': 2, 'n': 3, 'rate': 2 / 3})
        self.assertEqual(value['component_average_precision'], 1.)
        self.assertEqual(value['modeled_backend_known'], {'k': 2, 'n': 3, 'rate': 2 / 3})
        self.assertEqual(value['stopped_modeled_policy_violating_new_effect'], {'k': 0, 'n': 1, 'rate': 0.})

    def test_input_provenance_prevents_episode_swap(self):
        control = [dict(prefix_id='p', input_hash='h', result={'verdict': 'ALLOW'}, block=False, unknown=False)]
        inputs = [dict(prefix_id='p', input_hash='h', provenance={'episode_id': 'original', 'cut_seq': 4})]
        changed_rows = [dict(prefix_id='p', episode_id='swapped', cut_seq=4)]
        with self.assertRaises(ValueError): control_predictions(control, inputs, changed_rows)

    def test_input_provenance_prevents_cutoff_swap(self):
        control = [dict(prefix_id='p', input_hash='h', result={'verdict': 'ALLOW'}, block=False, unknown=False)]
        inputs = [dict(prefix_id='p', input_hash='h', provenance={'episode_id': 'original', 'cut_seq': 4})]
        changed_rows = [dict(prefix_id='p', episode_id='original', cut_seq=5)]
        with self.assertRaises(ValueError): control_predictions(control, inputs, changed_rows)


if __name__ == '__main__': unittest.main()
