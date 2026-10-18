"""Independent public no-peeking/identity counterexamples; no real scores."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'supplement_audit', Path(__file__).parents[1] / 'scripts/run_guard_v2_archive08_supplement.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SupplementalScopeAudit(unittest.TestCase):
    def test_external_quality_payload_is_never_json_decoded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = [{'prefix_id': str(i), 'provenance': {'episode_id': str(i // 4)}}
                      for i in range(704)]
            scores = [{'prefix_id': str(i), 'status': 'OK', 'unknown': False}
                      for i in range(704)]
            runner.jsonl(root / 'inputs', inputs)
            runner.jsonl(root / 'scores', scores)
            with (root / 'scores').open('a') as handle:
                handle.write('{"probabilities":[NEVER_DECODE],"labels":{"secret":NEVER_DECODE},'
                             '"prefix_id":"outside-fixed-archive"}\n')
            _, chosen, _ = runner.archive_snapshot(root / 'inputs', root / 'scores', root / 'out')
            self.assertEqual(len(chosen), 704)
            self.assertFalse(any(r['prefix_id'] == 'outside-fixed-archive' for r in chosen))

    def test_archive_payload_error_is_not_silently_complete_case_filtered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = [{'prefix_id': str(i), 'provenance': {'episode_id': str(i // 4)}}
                      for i in range(704)]
            runner.jsonl(root / 'inputs', inputs)
            (root / 'scores').write_text('{"prefix_id":"0","probabilities":[BAD_ARCHIVE]}\n')
            with self.assertRaises(json.JSONDecodeError):
                runner.archive_snapshot(root / 'inputs', root / 'scores', root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_container_cannot_smuggle_quality_through_prefix_identity(self):
        with self.assertRaises(ValueError) as raised:
            runner.prefix_only('{"prefix_id":{"probability":NEVER_DECODE}}')
        self.assertNotEqual(type(raised.exception).__name__, 'JSONDecodeError')


if __name__ == '__main__':
    unittest.main()
