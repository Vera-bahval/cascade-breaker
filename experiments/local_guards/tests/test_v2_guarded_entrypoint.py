import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

MODULE_PATH=Path(__file__).resolve().parents[1]/'scripts/run_guard_v2_models_guarded.py'
spec=importlib.util.spec_from_file_location('guarded_entrypoint',MODULE_PATH)
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)

class OwnershipGuardTests(unittest.TestCase):
 def test_live_unwrapped_owner_is_rejected_without_state_write(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);state=root/'runtime-run.json';state.write_text(json.dumps({'status':'RUNNING','pid':os.getpid(),'models_unloaded':False}))
   before=state.read_bytes()
   with self.assertRaisesRegex(guard.OutputBusy,'live RUNNING'):
    with guard.output_ownership(root):self.fail('A live owner must not be bypassed')
   self.assertEqual(state.read_bytes(),before)
 def test_second_guard_cannot_enter_even_before_child_writes_pid(self):
  with tempfile.TemporaryDirectory() as directory:
   with guard.output_ownership(directory):
    with self.assertRaises(guard.OutputBusy):
     with guard.output_ownership(directory):self.fail('Concurrent entrypoints must be serialized')
 def test_completed_owner_can_be_resumed(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'runtime-run.json').write_text(json.dumps({'status':'COMPLETE','pid':os.getpid(),'models_unloaded':True}))
   with guard.output_ownership(root):pass
 def test_running_owner_with_invalid_pid_fails_closed(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'runtime-run.json').write_text(json.dumps({'status':'RUNNING','pid':'unknown'}))
   with self.assertRaises(guard.OutputBusy):
    with guard.output_ownership(root):self.fail('Invalid owner identity cannot be treated as a dead owner')
 def test_live_orphan_model_child_blocks_resume(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'runtime-run.json').write_text(json.dumps({'status':'FAILED','pid':2147483647,'active_child':{'pid':os.getpid()}}))
   with self.assertRaisesRegex(guard.OutputBusy,'live model child'):
    with guard.output_ownership(root):self.fail('A failed parent does not establish model cleanup')

 def test_unreadable_state_fails_closed(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'runtime-run.json').write_text('{not valid json')
   with self.assertRaises(guard.OutputBusy):
    with guard.output_ownership(root):self.fail('Malformed state is not permission to overwrite it')

if __name__=='__main__':unittest.main()
