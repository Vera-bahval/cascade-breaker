"""Shared-input timing contract; never a quality evaluation."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from experiments.local_guards_archive_comparison import benchmark


class BenchmarkTests(unittest.TestCase):
    def test_selection_ignores_non_p4_and_row_order(self):
        self.assertTrue(callable(getattr(benchmark, 'select_inputs', None)), 'shared TRAIN selection is missing')
        with tempfile.TemporaryDirectory() as td:
            rows = [{'checkpoint':'P4','prefix_id':'a'}, {'checkpoint':'P2_afterFraud','prefix_id':'b'},
                    {'checkpoint':'P4','prefix_id':'c'}]
            paths = [Path(td)/'a.gz', Path(td)/'b.gz']
            for path, values in zip(paths,(rows,list(reversed(rows)))):
                with gzip.open(path,'wt') as out:
                    for row in values: out.write(json.dumps(row)+'\n')
            first = benchmark.select_inputs(paths[0], 2)
            second = benchmark.select_inputs(paths[1], 2)
            self.assertEqual([r['row_sha256'] for r in first], [r['row_sha256'] for r in second])
            self.assertEqual({r['row']['prefix_id'] for r in first}, {'a','c'})

    def test_unavailable_old_adapter_has_no_fabricated_zero_decision_timing(self):
        row = {'checkpoint':'P4','event_seq':0,'observation':{'facts':{},'proposal':{},'context':{},'provenance':{}},'raw_context':{}}
        candidate = benchmark.Candidate('v1')
        result = candidate(row)
        self.assertFalse(result['adapter_applicable'])
        self.assertIsNone(result['guard_ms'])
        self.assertGreater(result['full_ms'], 0)
        self.assertTrue(result['unavailable_fields'])

    def test_native_hook_enforces_selected_callback_before_effect(self):
        self.assertTrue(callable(getattr(benchmark, 'native_hook_trial', None)), 'native hook callback extension is missing')
        good = benchmark.native_hook_trial('native_core', 'safe', False)
        bad = benchmark.native_hook_trial('native_core', 'amount_mismatch', False)
        calibrated = benchmark.native_hook_trial('lr17_calibrated', 'safe', True)
        self.assertEqual((good['p4_verdicts'],good['payments']),(['ALLOW'],1))
        self.assertEqual((bad['p4_verdicts'],bad['payments']),(['BLOCK'],0))
        self.assertEqual((calibrated['p4_verdicts'],calibrated['payments']),(['UNKNOWN'],0))
        self.assertTrue(calibrated['later_model_blocked'])
        self.assertTrue(calibrated['later_native_effect_blocked'])

    def test_frozen_ml_probability_and_combined_calls_match(self):
        row = benchmark.select_inputs(benchmark.TRAIN, 1)[0]['row']
        candidate = benchmark.Candidate('scenario_decision-lr-17')
        result = candidate(row)
        self.assertTrue(result['probability_parity'])
        self.assertGreater(result['probability_ms'],0)
        self.assertGreater(result['calibration_and_gate_combined_ms'],0)
        self.assertEqual(result['operating_point_status'],'INFEASIBLE')


if __name__=='__main__': unittest.main()
