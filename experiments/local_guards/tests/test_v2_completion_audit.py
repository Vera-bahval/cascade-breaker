"""Independent public counterexamples for completion; no experiment files read."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / 'scripts/finish_guard_v2_05.py'
spec = importlib.util.spec_from_file_location('completion_audit', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class CompletionAudit(unittest.TestCase):
    def test_fourth_label_failure_never_starts_any_scorer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = {'root': str(root), 'base': str(root),
                    'labels': {key: {'path': 'DO_NOT_READ', 'sha256': key * 8}
                               for key in ('independent', 'raw64')}}
            for folder, name, _, _ in m.DESTINATIONS:
                dest = root / folder / name
                dest.mkdir(parents=True)
                (dest / 'PREDICTIONS_FROZEN.json').write_text(json.dumps({'destination': name}))
            calls = []

            def validator(methods, dest, **kwargs):
                self.assertIsNotNone(kwargs.get('unblind_marker'))
                for folder, name, _, key in m.DESTINATIONS:
                    destination = root / folder / name
                    marker = json.loads((destination / 'ROOT_UNBLIND_05.json').read_text())
                    self.assertEqual(marker['predictions_freeze_sha256'],
                                     m.sha(destination / 'PREDICTIONS_FROZEN.json'))
                    self.assertEqual(marker['labels_sha256'], plan['labels'][key]['sha256'])
                calls.append(str(dest))
                if len(calls) == 4:
                    raise ValueError('fourth cohort label mismatch')
                return {}

            with patch.object(m, 'authorization', return_value=plan), \
                    patch.object(m, 'readonly_gate', return_value=[{}] * 4), \
                    patch.object(m, 'deadline'):
                with self.assertRaisesRegex(ValueError, 'fourth cohort'):
                    m.complete('UNREAD_PLAN', 'hash', execute=True, validator=validator,
                               run_command=lambda command: self.fail('scoring before all joins'))
            self.assertEqual(len(calls), 4)
            self.assertTrue((root / 'completion-v5/STARTED.json').exists())
            self.assertTrue((root / 'completion-v5/FAILED_MANUAL_RECOVERY_REQUIRED.json').exists())
            self.assertFalse((root / 'completion-v5/COMPLETE.json').exists())

    def test_exclusive_transaction_preserves_existing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'STARTED.json'
            target.write_bytes(b'original transaction evidence')
            with self.assertRaises(FileExistsError):
                m.exclusive(target, {'new': 'transaction'})
            self.assertEqual(target.read_bytes(), b'original transaction evidence')


if __name__ == '__main__':
    unittest.main()
