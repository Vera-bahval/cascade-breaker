"""Independent synthetic provenance checks for new outer evaluation glue."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from cascade_guard.v2_feature_views import normalize_jev_file

SPEC = importlib.util.spec_from_file_location('v2_eval_outer_audit', Path(__file__).parents[1] / 'scripts/run_guard_v2_evaluation.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class AddonIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.scores = self.root / 'scores-v5'; self.scores.mkdir()
        self.jev_root = self.root / 'jev-v5'; self.jev_root.mkdir()
        self.inventory = {}
        inputs = self.root / 'inputs-v5'; inputs.mkdir()
        for name, count in [('archive-p4', 176), ('archive-partial', 176), ('raw64', 64), ('raw64-partial', 64), ('independent-p4', 240)]:
            items = [{'prefix_id': f'{name}-{i}', 'input_hash': f'h-{name}-{i}'} for i in range(count)]
            self.inventory[name] = items
            (inputs / (name + '-inputs.jsonl')).write_text(''.join(json.dumps(r) + '\n' for r in items))
        self.expected = {'method': 'method-hash', 'jev': 'jev-hash'}
        self.prior = {'status': 'COMPLETE', 'freeze_manifest_sha256': 'method-hash', 'models_unloaded': True,
                 'stages': [{'block': b, 'exit_code': 0} for b in runner.BLOCKS]}
        self.jev = {'status': 'COMPLETE', 'method_freeze_sha256': 'method-hash',
                    'jev_input_freeze_sha256': 'jev-hash', 'models_unloaded': True, 'exports': {}}
        for block in runner.BLOCKS:
            items = [dict(row, block=block) for rows in self.inventory.values() for row in rows]
            (self.scores / (block + '.jsonl')).write_text(''.join(json.dumps(r) + '\n' for r in items))
            (self.scores / (block + '.manifest.json')).write_text(json.dumps({'status': 'COMPLETE'}))
        for model in ('08', '4b'):
            folder = self.jev_root / model; folder.mkdir()
            entries = []
            all_items = []
            names = {'archive-all': 'archive-p4', 'archive-partial': 'archive-partial', 'raw64': 'raw64', 'raw64-partial': 'raw64-partial', 'independent-all': 'independent-p4'}
            for name, inventory_name in names.items():
                items = []
                for row in self.inventory[inventory_name]:
                    for block in (('J_cur', 'J_seq', 'J_agg', 'J_dynamic', 'J_prior') if model == '08' else ('J4_cur',)):
                        count = 1 if block in ('J_cur', 'J4_cur') else 3 if block == 'J_prior' else 4
                        items.append({'prefix_id': row['prefix_id'], 'block': block, 'provenance': {'checkpoint_inputs': [{'prefix_id': f"{row['prefix_id']}:stage-{i}", 'input_hash': 'fixture-hash'} for i in range(count)]}})
                all_items.extend(items)
                path = folder / ('features-' + name + '.jsonl'); path.write_text(''.join(json.dumps(r) + '\n' for r in items))
                entries.append({'collection': name, 'file': str(path), 'sha256': runner.sha(path)})
            combined = folder / 'features.jsonl'; combined.write_text(''.join(json.dumps(r) + '\n' for r in all_items))
            self.jev['exports'][model] = {'collections': entries, 'all_features': str(combined), 'sha256': runner.sha(combined)}
        self.save_prior()
        self.save_jev()

    def tearDown(self): self.temp.cleanup()

    def save_jev(self):
        (self.jev_root / 'runtime-run.json').write_text(json.dumps(self.jev))

    def save_prior(self):
        (self.scores / 'runtime-run.json').write_text(json.dumps(self.prior))

    def barrier(self): return runner.barrier(self.root, self.expected, scan=lambda: [])

    def test_completed_state_must_bind_same_freeze(self):
        self.assertTrue(self.barrier()[0])
        self.jev['jev_input_freeze_sha256'] = 'old'; self.save_jev()
        with self.assertRaisesRegex(ValueError, 'another method/input freeze'): self.barrier()

    def test_export_tamper_rejected_even_with_complete_state(self):
        path = Path(self.jev['exports']['08']['collections'][0]['file'])
        path.write_text('changed after completed export')
        with self.assertRaisesRegex(ValueError, 'export path/hash'): self.barrier()

    def test_score_filename_cannot_substitute_another_model(self):
        (self.scores / 'N.jsonl').write_text(json.dumps({'block': 'G22'}) + '\n')
        with self.assertRaisesRegex(ValueError, 'filename/model block'): self.barrier()

    def test_wrong_collection_prefix_and_duplicates_fail_before_view_write(self):
        source = self.root / 'features.jsonl'; dest = self.root / 'view.jsonl'
        record = {'prefix_id': 'archive-prefix', 'block': 'J_cur', 'status': 'OK',
                  'features': {'q': 0.2}, 'scalar_risk': 0.2, 'input_hash': 'original',
                  'provenance': {'checkpoint_inputs': [{'prefix_id': 'archive-prefix', 'input_hash': 'h'}]}}
        source.write_text(json.dumps(record) + '\n')
        with self.assertRaisesRegex(ValueError, 'prefix coverage'):
            normalize_jev_file(source, dest, model='08', collection='raw64', run_manifest='synthetic-run', expected_prefixes={'raw-prefix'})
        self.assertFalse(dest.exists())
        source.write_text((json.dumps(record) + '\n') * 2)
        with self.assertRaisesRegex(ValueError, 'Duplicate normalized'):
            normalize_jev_file(source, dest, model='08', collection='raw64', run_manifest='synthetic-run', expected_prefixes={'archive-prefix'})

    def test_actual_model_cutoff_enum_admits_only_complete_artifacts(self):
        self.prior['status'] = 'MODEL_CUTOFF'; self.save_prior()
        self.jev.update(status='DEADLINE', exports={}); self.save_jev()
        (self.scores / 'N.manifest.json').write_text(json.dumps({'status': 'PARTIAL'}))
        ready, proof = runner.barrier(self.root, self.expected, scan=lambda: [], now=2, cutoff=1)
        self.assertTrue(ready)
        self.assertNotIn('N', proof['available_models'])
        self.assertIn('G22', proof['available_models'])

    def test_cutoff_still_requires_both_models_unloaded(self):
        self.prior.update(status='INTERRUPTED', models_unloaded=False); self.save_prior()
        self.jev.update(status='DEADLINE', exports={}); self.save_jev()
        self.assertFalse(runner.barrier(self.root, self.expected, scan=lambda: [], now=2, cutoff=1)[0])

    def test_exit_zero_with_missing_score_is_excluded_before_open(self):
        self.prior['status'] = 'MODEL_CUTOFF'; self.save_prior()
        self.jev.update(status='DEADLINE', exports={}); self.save_jev()
        (self.scores / 'N.jsonl').unlink()
        (self.scores / 'N.manifest.json').write_text(json.dumps({'status': 'RUNNING'}))
        ready, proof = runner.barrier(self.root, self.expected, scan=lambda: [], now=2, cutoff=1)
        self.assertTrue(ready)
        self.assertNotIn('N', proof['available_models'])
        self.assertIn('G22', proof['available_models'])

    def test_zero_complete_models_still_builds_archive_only_pipeline(self):
        self.prior.update(status='MODEL_CUTOFF', stages=[]); self.save_prior()
        self.jev.update(status='DEADLINE', exports={}); self.save_jev()
        ready, proof = runner.barrier(self.root, self.expected, scan=lambda: [], now=2, cutoff=1)
        self.assertTrue(ready)
        self.assertEqual(proof['available_models'], [])
        plan = runner.commands(self.root, available_models=[], generation=5)
        self.assertFalse(any(name.startswith('blind-split') for name, _, _ in plan))
        trains = [command for name, command, _ in plan if name.startswith('train-')]
        self.assertEqual(len(trains), 2)
        self.assertTrue(all(command[-1].endswith('NO_COMPLETED_MODEL_BLOCKS.jsonl') for command in trains))


if __name__ == '__main__': unittest.main()
