import copy
import unittest

from . import ml


def record(pid='p', group='g'):
    return dict(prefix_id=pid, episode_id=pid, group_id=group,
                native={'checkpoint': 'P4', 'event_seq': 10,
                        'observation': {'facts': {}, 'context': {}, 'proposal': {}}},
                observation={'checkpoint': 'P4', 'facts': {}, 'proposal': {}, 'tool_arguments': {}})


def with_history(amounts):
    row = record()
    native = row['native']['observation']
    native['context'].update(invoice_id=6, vendor_id=1)
    history = [dict(id=i, vendor_id=1, status='paid', amount=amount, event_seq=1) for i, amount in enumerate(amounts, 1)]
    history += [dict(id=6, vendor_id=1, status='paid', amount=9900, event_seq=1),
                dict(id=7, vendor_id=1, status='approved', amount=50000, event_seq=1)]
    native['facts']['vendor_invoice_history'] = history
    native['provenance'] = {'vendor_invoice_history': [dict(field='vendor_invoice_history', value=history,
        event_seq=1, source_ref='fixture', status='observed', kind='historical', subject={'vendor_id': 1})]}
    row['observation']['facts']['invoice_amount'] = '9900'
    return row


class MLTests(unittest.TestCase):
    def test_allowlisted_features_preserve_order_and_ignore_labels_and_ids(self):
        before = record()
        before['observation']['facts'].update(binding_hold=True, successful_review_after_hold=False)
        after = copy.deepcopy(before)
        after['observation']['facts'].update(binding_hold=False, successful_review_after_hold=True)
        self.assertNotEqual(ml.features(before), ml.features(after))
        renamed = copy.deepcopy(before)
        renamed.update(prefix_id='other', group_id='other', action_label='ALLOW', reasons=['anything'])
        renamed['observation'].update(context={'invoice_id': 'other'}, guard_decision='BLOCK')
        renamed['observation']['facts']['semantic_review_required'] = True
        self.assertEqual(ml.features(before), ml.features(renamed))

    def test_ties_abstain_and_sentinel_rejects_probability_one(self):
        self.assertEqual(ml.decide({'ALLOW': .5, 'BLOCK': .5}, {'ALLOW': 0, 'BLOCK': 0}), 'UNKNOWN')
        self.assertEqual(ml.decide({'ALLOW': 1., 'BLOCK': 0.}, {'ALLOW': ml.SENTINEL, 'BLOCK': 0}), 'UNKNOWN')
        self.assertIsNone(ml.decide(None, {'ALLOW': 0, 'BLOCK': 0}))

    def test_paid_history_distinguishes_C_G_and_excludes_current_unpaid(self):
        small = ml.features(with_history([1200, 850, 2300, 640, 1750]))
        large = ml.features(with_history([6800, 8900, 4600, 5700, 7400]))
        self.assertEqual(small['archive.prior_paid_count'], 5)
        self.assertEqual(small['archive.prior_paid_mean'], 1348)
        self.assertEqual(large['archive.prior_paid_mean'], 6680)
        self.assertEqual(small['archive.prior_paid_min'], 640)
        self.assertEqual(large['archive.prior_paid_max'], 8900)
        self.assertAlmostEqual(small['archive.current_to_prior_paid_mean'], 9900 / 1348)
        self.assertNotEqual(small, large)
        row = with_history([1200, 850, 2300, 640, 1750])
        row['native']['observation']['facts']['vendor_invoice_history'] += [
            dict(id=8, vendor_id=2, status='paid', amount=99999, event_seq=1),
            dict(id=9, vendor_id=1, status='paid', amount=99999, event_seq=11)]
        partial = ml.features(row)
        self.assertEqual(partial['archive.prior_paid_mean'], 1348)
        self.assertEqual(partial['archive.paid_history_state'], 'PARTIAL_INVALID')

    def test_insufficient_is_unscored_but_stays_in_denominator(self):
        score = ml.metrics(['ALLOW', 'BLOCK', 'INSUFFICIENT', 'BLOCK'], ['ALLOW', 'ALLOW', 'ALLOW', None])
        self.assertEqual((score['n'], score['resolved'], score['wrong_allow'], score['model_unavailable']), (4, 3, 1, 1))
        self.assertEqual(score['correct_coverage'], .25)
        self.assertEqual(score['insufficient_allow'], 1)
        self.assertEqual(score['unknown'], 0)

    def test_calibration_no_safe_and_infeasible_are_explicit(self):
        self.assertEqual(ml.calibrate(['BLOCK'], [{'ALLOW': .1, 'BLOCK': .9}])['status'], 'INFEASIBLE')
        probabilities = [{'ALLOW': .9, 'BLOCK': .1}, {'ALLOW': .9, 'BLOCK': .1}]
        self.assertEqual(ml.calibrate(['ALLOW', 'BLOCK'], probabilities)['status'], 'INFEASIBLE')
        good = ml.calibrate(['ALLOW', 'BLOCK', 'INSUFFICIENT'], [probabilities[0], {'ALLOW': .1, 'BLOCK': .9}, probabilities[0]])
        self.assertEqual(good['status'], 'FEASIBLE')
        self.assertEqual(good['metrics']['correct_coverage'], 2 / 3)

    def test_one_class_fit_is_unavailable_without_training(self):
        row = record()
        model = ml.fit('lr', [row], {'p': 'ALLOW'}, {'p': ml.features(row)}, seed=17)
        self.assertFalse(model['available'])
        self.assertEqual(ml.predict(model, [row], {}), [None])

    def test_nested_folds_keep_all_three_strata_group_disjoint(self):
        records = [record(f'p{i:03}', f'g{i//2:02}') for i in range(60)]
        labels = {r['prefix_id']: ml.LABELS[(i // 2) % 3] for i, r in enumerate(records)}
        folds = ml.partitions(records, labels)
        self.assertEqual(folds, ml.partitions(list(reversed(records)), labels))
        self.assertEqual(sorted(pid for f in folds for pid in f['test']), sorted(labels))
        for fold in folds:
            a, b, c = (set(fold['groups'][key]) for key in ('fit', 'cal', 'test'))
            self.assertFalse(a & b or a & c or b & c)


if __name__ == '__main__':
    unittest.main()
