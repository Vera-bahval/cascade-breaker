import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MODULE_PATH=Path(__file__).resolve().parents[1]/'scripts/run_guard_v2_models_v5.py'
spec=importlib.util.spec_from_file_location('guard_v5_runner',MODULE_PATH)
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class RunnerSafetyTests(unittest.TestCase):
 def test_frozen_source_drift_fails_closed(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);source=root/'source.py';source.write_text('original')
   manifest=root/'freeze.json';manifest.write_text(json.dumps({'sha256':{str(source):hashlib.sha256(source.read_bytes()).hexdigest()}}))
   manifest_hash=hashlib.sha256(manifest.read_bytes()).hexdigest()
   self.assertEqual(runner.verify_frozen(manifest,manifest_hash),1)
   source.write_text('changed')
   with self.assertRaisesRegex(ValueError,'drift'):runner.verify_frozen(manifest,manifest_hash)
 def test_deadline_cannot_extend_frozen_evaluation_reserve(self):
  frozen={'technical_runner_deadline_utc':'2026-10-15T23:00:00+00:00','inference_cutoff_utc':'2026-10-15T21:40:00+00:00'}
  runner.validate_deadlines(frozen,'2026-10-15T23:00:00+00:00','2026-10-15T21:40:00+00:00')
  with self.assertRaisesRegex(ValueError,'global deadline'):
   runner.validate_deadlines(frozen,'2026-10-16T00:00:00+00:00','2026-10-15T21:40:00+00:00')
  with self.assertRaisesRegex(ValueError,'cutoff differs'):
   runner.validate_deadlines(frozen,'2026-10-15T23:00:00+00:00','2026-10-15T22:00:00+00:00')
  with self.assertRaisesRegex(ValueError,'timezone'):
   runner.validate_deadlines(frozen,'2026-10-15T23:00:00','2026-10-15T21:40:00+00:00')

 def test_stop_terminates_only_owned_child_process_group(self):
  child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],start_new_session=True)
  try:
   runner.stop_owned_child(child)
   self.assertIsNotNone(child.poll())
   runner.stop_owned_child(child)
  finally:
   if child.poll() is None:child.kill();child.wait()

if __name__=='__main__':unittest.main()
