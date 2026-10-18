"""Small synthetic tamper fixtures; no model, archive or hidden-data reads."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from cascade_guard.v2_preunblind import IntegrityError, sha, validate


def write(path, value):
    path.write_text(json.dumps(value))


def lines(path, values):
    path.write_text(''.join(json.dumps(value) + '\n' for value in values))


class PreUnblindTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.methods = self.root / 'methods'; self.methods.mkdir()
        self.dest = self.root / 'predictions'; self.dest.mkdir()
        self.rows = [{'prefix_id': f'p{i}', 'episode_id': f'e{i}', 'cut_seq': 4} for i in range(2)]
        self.rows_path = self.root / 'rows.jsonl'; lines(self.rows_path, self.rows)
        self.records = self.root / 'records.jsonl'
        lines(self.records, [{'prefix_id': row['prefix_id'], 'block': 'N', 'status': 'OK'} for row in self.rows])
        self.source = self.root / 'source.py'; self.source.write_text('fixed source')
        write(self.methods / 'training-input-freeze.json', {'files': [self.entry(self.source)]})
        choice = {'policy': 'A_joint', 'denominator': 'reached', 'seed': 17,
                  'arm': 'catboost:N:none', 'config': 'catboost:N'}
        write(self.methods / 'final-choices.json', [choice])
        write(self.methods / 'models.json', [{'seed': 17, 'config': 'catboost:N', 'blocks': ['N']}])
        pinned = [self.methods / name for name in ('training-input-freeze.json', 'final-choices.json', 'models.json')]
        write(self.methods / 'METHODS_FROZEN.json', {'files': [self.entry(path) for path in pinned]})
        self.predictions = [dict(row, policy='A_joint', denominator='reached', seed=17, arm=arm,
                                 probability=0.5, block=False, unknown=False)
                            for arm in ('catboost:N:none', 'NoDefense', 'R1', 'R2') for row in self.rows]
        lines(self.dest / 'predictions.jsonl', self.predictions)
        self.pf = {'rows_file': self.entry(self.rows_path), 'records': [self.entry(self.records)],
                   'methods_freeze_sha256': sha(self.methods / 'METHODS_FROZEN.json'),
                   'predictions_sha256': sha(self.dest / 'predictions.jsonl')}
        self.save_pf()

    def tearDown(self):
        self.temp.cleanup()

    def entry(self, path):
        return {'path': str(path), 'sha256': sha(path)}

    def save_pf(self):
        write(self.dest / 'PREDICTIONS_FROZEN.json', self.pf)

    def check(self, **kwargs):
        return validate(self.methods, self.dest, expected_rows=2, **kwargs)

    def authorized_labels(self, labels):
        path = self.root / 'labels.jsonl'; lines(path, labels)
        marker = self.root / 'root-UNBLIND.json'
        write(marker, {'authorization': 'UNBLIND', 'labels_sha256': sha(path),
                       'predictions_freeze_sha256': sha(self.dest / 'PREDICTIONS_FROZEN.json')})
        return {'labels': path, 'unblind_marker': marker}

    def test_valid_identity_gate_is_read_only_and_does_not_open_labels(self):
        before = {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        report = self.check()
        self.assertFalse(report['labels_opened'])
        self.assertEqual(report['arms'], 4)
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_each_recorded_hash_is_enforced(self):
        paths = [self.rows_path, self.records, self.source,
                 self.methods / 'METHODS_FROZEN.json', self.dest / 'predictions.jsonl']
        for path in paths:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b' ')
                with self.assertRaises(IntegrityError): self.check()
                path.write_bytes(original)

    def test_duplicate_prediction_rejected_even_if_sidecar_hash_updated(self):
        lines(self.dest / 'predictions.jsonl', self.predictions + [self.predictions[0]])
        self.pf['predictions_sha256'] = sha(self.dest / 'predictions.jsonl'); self.save_pf()
        with self.assertRaisesRegex(IntegrityError, 'Duplicate prediction'): self.check()

    def test_missing_arm_rejected_even_with_updated_sidecar_hash(self):
        lines(self.dest / 'predictions.jsonl', [p for p in self.predictions if p['arm'] != 'R2'])
        self.pf['predictions_sha256'] = sha(self.dest / 'predictions.jsonl'); self.save_pf()
        with self.assertRaisesRegex(IntegrityError, 'arm set'): self.check()

    def test_cutoff_mismatch_rejected(self):
        data = copy.deepcopy(self.predictions); data[0]['cut_seq'] = 5
        lines(self.dest / 'predictions.jsonl', data)
        self.pf['predictions_sha256'] = sha(self.dest / 'predictions.jsonl'); self.save_pf()
        with self.assertRaisesRegex(IntegrityError, 'cutoff mismatch'): self.check()

    def test_partial_feature_population_rejected(self):
        lines(self.records, [{'prefix_id': 'p0', 'block': 'N'}])
        self.pf['records'] = [self.entry(self.records)]; self.save_pf()
        with self.assertRaisesRegex(IntegrityError, 'Partially present'): self.check()

    def test_all_unknown_block_does_not_create_available_model_schema(self):
        lines(self.records, [{'prefix_id': row['prefix_id'], 'block': 'N', 'status': 'UNKNOWN'} for row in self.rows])
        self.pf['records'] = [self.entry(self.records)]
        lines(self.dest / 'predictions.jsonl', [p for p in self.predictions if p['arm'] != 'catboost:N:none'])
        self.pf['predictions_sha256'] = sha(self.dest / 'predictions.jsonl'); self.save_pf()
        self.assertEqual(self.check()['arms'], 3)

    def test_no_authorization_means_label_file_is_never_opened(self):
        with self.assertRaisesRegex(IntegrityError, 'UNBLIND marker'):
            self.check(labels=self.root / 'DOES_NOT_EXIST.jsonl')

    def test_wrong_marker_rejected_before_nonexistent_label_path(self):
        marker = self.root / 'marker.json'; write(marker, {'authorization': 'NOT_UNBLIND'})
        with self.assertRaisesRegex(IntegrityError, 'does not authorize'):
            self.check(labels=self.root / 'DOES_NOT_EXIST.jsonl', unblind_marker=marker)

    def test_authorized_label_pair_validation(self):
        labels = [{'episode_id': f'e{i}', 'pair_id': 'pair', 'family': 'public-fixture',
                   'contract_requires_intervention': bool(i)} for i in range(2)]
        report = self.check(**self.authorized_labels(labels))
        self.assertTrue(report['labels_opened'])
        self.assertEqual(report['pair_count'], 1)

    def test_malformed_pair_rejected_before_scorer_can_write(self):
        labels = [{'episode_id': f'e{i}', 'pair_id': 'pair', 'family': 'public-fixture',
                   'contract_requires_intervention': True} for i in range(2)]
        with self.assertRaisesRegex(IntegrityError, 'opposite intervention'):
            self.check(**self.authorized_labels(labels))
        self.assertFalse((self.dest / 'metrics.json').exists())

    def test_duplicate_label_identity_rejected(self):
        labels = [{'episode_id': 'e0', 'contract_requires_intervention': False}] * 2
        with self.assertRaisesRegex(IntegrityError, 'Label identities'):
            self.check(**self.authorized_labels(labels))

    def test_marker_must_bind_current_prediction_freeze_and_label_hash(self):
        labels = [{'episode_id': f'e{i}', 'pair_id': 'pair', 'family': 'fixture',
                   'contract_requires_intervention': bool(i)} for i in range(2)]
        paths = self.authorized_labels(labels)
        marker = json.loads(paths['unblind_marker'].read_text())
        for key in ('predictions_freeze_sha256', 'labels_sha256'):
            with self.subTest(key=key):
                bad = dict(marker, **{key: '0' * 64}); write(paths['unblind_marker'], bad)
                with self.assertRaises(IntegrityError): self.check(**paths)
        write(paths['unblind_marker'], marker)

    def test_cross_family_pair_rejected(self):
        labels = [{'episode_id': f'e{i}', 'pair_id': 'pair', 'family': f'family-{i}',
                   'contract_requires_intervention': bool(i)} for i in range(2)]
        with self.assertRaisesRegex(IntegrityError, 'crosses family'):
            self.check(**self.authorized_labels(labels))

    def test_existing_partial_metrics_prevents_repeat(self):
        write(self.dest / 'metrics.json', {})
        with self.assertRaisesRegex(IntegrityError, 'Already unblinded'): self.check()


if __name__ == '__main__':
    unittest.main()
