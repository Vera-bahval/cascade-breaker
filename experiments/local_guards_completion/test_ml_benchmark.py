import itertools
import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

from . import ml
from . import ml_benchmark as benchmark


class MLBenchmarkTests(unittest.TestCase):
    def test_actual_singleton_path_sums_components_and_excludes_diagnostics(self):
        row = {'adapters': {'native': {'payload': {'checkpoint': 'P4'}}}}
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.execute('CREATE TABLE packets (id TEXT PRIMARY KEY, packet TEXT)')
        db.execute('INSERT INTO packets VALUES (?,?)', (benchmark.canonical(('p4', 'p')), json.dumps(row)))
        vectorizer, scaler, estimator = Mock(), Mock(), Mock()
        vectorizer.transform.return_value = [[2]]
        scaler.transform.return_value = [[3]]
        estimator.predict_proba.return_value = [[.8, .2]]
        estimator.classes_ = ['ALLOW', 'BLOCK']
        bundle = dict(model=dict(available=True, vectorizer=vectorizer, scaler=scaler, estimator=estimator),
                      operating_point=dict(status='FEASIBLE', thresholds=dict(ALLOW=.5, BLOCK=.5)))
        values = {'precut': 1}
        with patch.object(benchmark, 'perf_counter_ns', side_effect=itertools.count(0, 1000000)), \
             patch.object(benchmark, 'prepare', return_value={'checkpoint': 'P4'}) as prepare, \
             patch.object(benchmark, 'guard', return_value={'process_decision': 'ALLOW'}), \
             patch.object(ml, 'features', return_value=values):
            result, record, actual, process = benchmark.measure(db, 'p', bundle)
        self.assertEqual(result['working_ms'], 5)
        self.assertEqual(result['argmax_working_ms'], 5)
        self.assertEqual(result['process_working_ms'], 3)
        self.assertEqual((result['decision'], result['argmax_decision']), ('ALLOW', 'ALLOW'))
        self.assertEqual(result['probabilities'], {'ALLOW': .8, 'BLOCK': .2})
        estimator.predict_proba.assert_called_once_with([[3]])
        prepare.assert_called_once_with(row, method='current', tax_mode='default')
        expected = dict(result, feature_sha256=ml.feature_hash(values))
        benchmark.validate(result, values, expected)
        with self.assertRaisesRegex(ValueError, 'features differ'):
            benchmark.validate(result, {'future': 2}, expected)
        changed = dict(expected, probabilities={'ALLOW': .7, 'BLOCK': .3})
        with self.assertRaisesRegex(ValueError, 'probabilities differ'):
            benchmark.validate(result, values, changed)
        with self.assertRaisesRegex(ValueError, 'probabilities differ'):
            benchmark.validate(dict(result, probabilities={'ALLOW': float('nan'), 'BLOCK': .2}), values, expected)

    def test_unavailable_model_measures_process_path_without_inventing_ML_time(self):
        db = Mock()
        db.execute.return_value.fetchone.return_value = [json.dumps({'adapters': {'native': {'payload': {}}}})]
        bundle = dict(model=dict(available=False), operating_point=dict(status='MODEL_UNAVAILABLE'))
        with patch.object(benchmark, 'prepare', return_value={'checkpoint': 'P4'}), \
             patch.object(benchmark, 'guard', return_value={'process_decision': 'BLOCK'}), \
             patch.object(ml, 'features') as features:
            result, _, values, _ = benchmark.measure(db, 'p', bundle)
        features.assert_not_called()
        self.assertIsNone(values)
        self.assertIsNone(result['probabilities'])
        self.assertIsNone(result['decision'])
        self.assertTrue(all(result[field] is None for field in benchmark.TIMERS))
        self.assertEqual(result['process_decision'], 'BLOCK')
        self.assertGreaterEqual(result['process_working_ms'], 0)


if __name__ == '__main__':
    unittest.main()
