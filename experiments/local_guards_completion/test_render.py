import gzip
import json
from pathlib import Path
import tempfile
import unittest

from . import render


class RenderTests(unittest.TestCase):
    def test_published_gzip_policy_index_does_not_need_ignored_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'captured-policies.json.gz'
            with gzip.open(path, 'wt') as stream:
                json.dump({'cases': {'one': {}}}, stream)
            self.assertEqual(len(render.read(path)['cases']), 1)
            self.assertFalse(path.with_suffix('').exists())

    def test_quality_uses_supplied_denominator_and_separates_unavailable(self):
        row = dict.fromkeys(render.CELLS, 0)
        row.update(correct_allow=1, insufficient_block=1, unavailable=1,
                   model_unavailable=1, adapter_unavailable=0, correct=1)
        text = render.quality_table([('example', row)], 3)
        self.assertIn('1 / 3 (33,33%)', text)
        self.assertIn('| 0 | 1 / 0 | 0 / 1 |', text)
        with self.assertRaisesRegex(ValueError, 'partition'):
            render.quality_table([('example', row)], 4)

    def test_no_measurement_is_not_zero(self):
        self.assertEqual(render.fmt(None), 'нет данных')
        self.assertEqual(render.fmt(0), '0,00')
        self.assertEqual(render.pct(0, 0), 'нет данных')

    def test_compact_table_cannot_hide_unavailable_answers(self):
        row = dict.fromkeys(render.CELLS, 0)
        row.update(unavailable=1, model_unavailable=1, adapter_unavailable=0, correct=0)
        with self.assertRaisesRegex(ValueError, 'cannot hide'):
            render.quality_table([('example', row)], 1, compact=True)

    def test_main_keeps_controls_and_answers_while_appendix_keeps_zero_rows(self):
        s = render.read(render.HERE / 'results-summary.json')
        cost = render.read(render.HERE / 'cost-audit.json')
        report = render.build_report(s, cost, 382)
        self.assertIn('## Ответы на вопросы исследования', report)
        self.assertIn('373 / 542', report)
        self.assertNotIn('| Прежний ML v3, LR |', report)
        self.assertIn('UNKNOWN на всех 542', report)
        appendix = render.build_tables(s, render.read(s['ml']['curves']), render.read(s['ml']['feature_audit']))
        self.assertIn('saved/v3_ml/', appendix)

    def test_fixed_grid_points_are_preserved_without_selecting_a_threshold(self):
        curves = {'methods': {'lr': [
            {'metrics': dict(n=4, safe_n=2, correct=2, wrong_allow=1, safe_stop=1)},
            {'metrics': dict(n=4, safe_n=0, correct=0, wrong_allow=0, safe_stop=0)}]}}
        self.assertEqual(render.curve_points(curves), {'lr': [(50., 1, 50.), (0., 0, None)]})
        curves['methods']['lr'][0]['metrics']['correct'] = 5
        with self.assertRaisesRegex(ValueError, 'denominator'):
            render.curve_points(curves)

    def test_main_excludes_argmax_diagnostics_but_preserves_their_vectors(self):
        s = {'p4': {'primary_methods': ['oof/lr/calibrated', 'oof/lr/argmax_diagnostic'],
            'methods': {'oof/lr/calibrated': {'diagnostic': False},
                        'oof/lr/argmax_diagnostic': {'diagnostic': True}}}}
        self.assertEqual(render.primary(s), ['oof/lr/calibrated'])
        self.assertEqual(len(s['p4']['methods']), 2)

    def test_old_entry_point_is_only_a_forwarder(self):
        from experiments.local_guards_archive_profile.update_report import run
        self.assertIs(run, render.run)

    def test_real_saved_curves_supply_every_plotted_point(self):
        summary = render.HERE / 'results-summary.json'
        if not summary.exists():
            self.skipTest('sealed completion summary not ready')
        s = json.loads(summary.read_text())
        curves = render.read(s['ml']['curves'])
        points = render.curve_points(curves)
        for method, records in curves['methods'].items():
            self.assertEqual(len(points[method]), len(records))
            self.assertTrue(all(row['metrics']['n'] == s['p4']['n'] for row in records))
            for point, row in zip(points[method], records):
                self.assertEqual(point[0], 100 * row['metrics']['correct'] / s['p4']['n'])
                self.assertEqual(point[1], row['metrics']['wrong_allow'])


if __name__ == '__main__':
    unittest.main()
