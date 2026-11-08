import gzip
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from . import policy_sources as sources


class PolicySourceTests(unittest.TestCase):
    def test_only_first_input_system_text_is_used(self):
        first = 'You are an autonomous payment processing assistant.\nDate: original'
        later = first.replace('original', 'later')
        rows = [dict(input=[dict(role='user', content=first)], output=[dict(role='system', content=first)]),
                dict(input={'messages': [dict(role='system', content=first)]}),
                dict(input=[None, dict(role='system', content={'text': first}), dict(role='system', content=first)],
                     usage={'ignored': True}, billing={'ignored': True}, auth={'ignored': True}),
                dict(input=[dict(role='system', content=later)])]
        found = sources.first_instructions('\n'.join(json.dumps(r) for r in rows).encode())
        self.assertEqual(set(found), {'payments'})
        self.assertEqual(found['payments'], dict(text=first, sha256=sources.sha_bytes(first.encode()), source_line=3))
        with self.assertRaisesRegex(ValueError, 'malformed calls JSON at line 1'):
            sources.first_instructions(b'not JSON')

    def test_verified_fixture_and_deterministic_publication(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / 'episode.tar.gz'
            name = 'run/C/sample.calls.jsonl'
            prompt = "You are FinBot's autonomous invoice processing assistant."
            data = (json.dumps({'input': [{'role': 'system', 'content': prompt}]}) + '\n').encode()
            with tarfile.open(archive, 'w:gz') as tar:
                member = tarfile.TarInfo(name)
                member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
            archive_hash = sources.sha_bytes(archive.read_bytes())
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'cases': [{'prefix_id': 'p'}]}))
            metadata = root / 'metadata.jsonl'
            row = dict(prefix_id='p', source='episode.tar.gz', source_sha256=archive_hash, member='run/C/sample.hooks.jsonl')
            metadata.write_text(json.dumps(row) + '\n')
            index, audit = sources.extract(manifest, metadata, root)
            self.assertEqual(audit['captured_cases'], 1)
            self.assertEqual(audit['verified_archive_sha256'], {str(archive.resolve()): archive_hash})
            self.assertEqual(index['cases']['p']['invoice']['member_sha256'], sources.sha_bytes(data))
            output = root / 'index.json.gz'
            sources.publish(output, index)
            original = output.read_bytes()
            sources.publish(output, index)
            self.assertEqual(original, output.read_bytes())
            self.assertEqual(json.loads(gzip.decompress(original)), index)
            with self.assertRaises(FileExistsError):
                sources.publish(output, dict(index, scope='changed'))
            row['source_sha256'] = '0' * 64
            metadata.write_text(json.dumps(row) + '\n')
            with self.assertRaisesRegex(ValueError, 'archive SHA-256 mismatch'):
                sources.extract(manifest, metadata, root)


if __name__ == '__main__':
    unittest.main()
