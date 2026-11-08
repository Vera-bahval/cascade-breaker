import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import run
from .records import rows, sha
from .test_rules import row


class RunTests(unittest.TestCase):
    def test_predictions_keep_identity_and_change_hash_with_pre_cut_input(self):
        source = row()
        source.update(prefix_id='opaque', episode_id='episode', mode='common', query_id='saved-query')
        first = run.predict('p4', source, run.VARIANTS[0], 'source-hash')
        self.assertEqual((first['prefix_id'], first['query_id'], first['event_seq']), ('opaque', 'saved-query', 100))
        self.assertEqual(first['source_input_sha256'], 'source-hash')
        source['adapters']['native']['payload']['raw_context']['proposed_action']['tool_arguments']['invoice_reference'] = 'wrong'
        second = run.predict('p4', source, run.VARIANTS[0], 'source-hash')
        self.assertNotEqual(first['input_sha256'], second['input_sha256'])
        self.assertEqual(second['result']['decision'], 'BLOCK')
        source['completion_evidence']['tax_available'] = dict(value=True, event_seq=100, source_ref='future')
        with self.assertRaises(ValueError):
            run.predict('p4', source, run.VARIANTS[0], 'source-hash')

    def test_freeze_rejects_changed_code_and_changed_label_freeze(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run, 'HERE', Path(directory)):
            root = Path(directory)
            for name in run.REQUIRED_CODE:
                (root / name).write_text('frozen code')
            (root / 'labels-freeze.json').write_text('{"opaque_receipt":true}')
            freeze = dict(status='FROZEN', code_sha256={name: sha(root / name) for name in run.REQUIRED_CODE},
                          labels_freeze_sha256=sha(root / 'labels-freeze.json'))
            (root / 'code-freeze.json').write_text(json.dumps(freeze))
            self.assertEqual(run.admitted()['labels_freeze_sha256'], freeze['labels_freeze_sha256'])
            dependency = root/'dependency.py'
            dependency.write_text('pinned helper')
            freeze['project_dependency_sha256'] = {'dependency.py':sha(dependency)}
            (root/'code-freeze.json').write_text(json.dumps(freeze))
            with patch.object(run,'EXP',root/'experiments'):
                run.admitted()
                dependency.write_text('changed helper')
                with self.assertRaises(ValueError):
                    run.admitted()
            freeze.pop('project_dependency_sha256')
            (root/'code-freeze.json').write_text(json.dumps(freeze))
            (root / 'rules.py').write_text('changed')
            with self.assertRaises(ValueError):
                run.admitted()
            (root / 'rules.py').write_text('frozen code')
            (root / 'labels-freeze.json').write_text('changed receipt')
            with self.assertRaises(ValueError):
                run.admitted()

    def test_exclusive_outputs_do_not_overwrite_prior_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'predictions.jsonl.gz'
            with run.writer(path) as emit:
                emit({'answer': 'sealed'})
            prior = path.read_bytes()
            with self.assertRaises(FileExistsError), run.writer(path):
                pass
            self.assertEqual(path.read_bytes(), prior)
            self.assertEqual(list(rows(path)), [{'answer': 'sealed'}])
            with patch.object(run, 'admitted', return_value={}), patch.object(run, 'guard') as guard:
                with self.assertRaises(FileExistsError):
                    run.run(Path(directory))
                guard.assert_not_called()


if __name__ == '__main__':
    unittest.main()
