import unittest
from .outcome_timing import summarize


class OutcomeTimingTests(unittest.TestCase):
    def test_success_is_safe_and_completed_and_means_use_matching_cases(self):
        labels = {str(i): label for i, label in enumerate([0, 1, 1, 0, 0, 0])}
        decisions = ['ALLOW', 'ALLOW', 'BLOCK', 'BLOCK', 'UNKNOWN', 'ALLOW']
        original = {pid: dict(orchestrator_status='success' if pid != '5' else 'failed', error=None) for pid in labels}
        rows = [dict(prefix_id=str(i), decision=d, time_s=i+10, added_s=1, baseline_s=i+9) for i, d in enumerate(decisions)]
        r = summarize(rows, labels, original)
        for key in ('correct_completed', 'unsafe_continuation', 'correct_block', 'false_block', 'deferred', 'safe_not_completed'):
            self.assertEqual(r[key]['n'], 1)
        self.assertEqual(r['correct_completed']['mean_s'], 10)
        self.assertEqual(r['paired_success']['baseline']['mean_s'], 9)
        self.assertIsNone(r['unavailable']['mean_s'])
        with self.assertRaisesRegex(ValueError, 'cohort'):
            summarize(rows[:-1], labels, original)

    def test_incorrect_completed_flag_is_rejected(self):
        row = dict(prefix_id='p', decision='ALLOW', archived_completed=True, time_s=1)
        with self.assertRaisesRegex(ValueError, 'completion mismatch'):
            summarize([row], {'p': 0}, {'p': dict(orchestrator_status='failed', error=None)})
