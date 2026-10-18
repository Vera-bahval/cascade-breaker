"""Public archive-only snapshot tests. No hidden or real model scores."""
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import types
import subprocess
import unittest
from unittest.mock import patch
SCRIPT=Path(__file__).parents[1]/'scripts/run_guard_v2_archive08_supplement.py'
spec=importlib.util.spec_from_file_location('archive08supp',SCRIPT);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ArchiveSupplementTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.d=Path(self.tmp.name)
  self.inputs=[{'prefix_id':str(i),'provenance':{'episode_id':str(i//4),'stage_index':i%4}} for i in range(704)]
  self.scores=[{'prefix_id':str(i),'status':'OK','unknown':False} for i in range(704)]
 def files(self,scores=None,inputs=None):
  a=self.d/'inputs.jsonl';b=self.d/'scores.jsonl';m.jsonl(a,self.inputs if inputs is None else inputs);m.jsonl(b,self.scores if scores is None else scores);return a,b,self.d/'archive-copy.jsonl'
 def test_selects_only_exact_archive_identity(self):
  a,b,o=self.files(self.scores+[{'prefix_id':'hidden-not-read-for-selection','status':'UNKNOWN','unknown':True}]);_,out,meta=m.archive_snapshot(a,b,o)
  self.assertEqual(len(out),704);self.assertEqual(meta['episodes'],176);self.assertEqual({x['prefix_id'] for x in out},{str(i) for i in range(704)})
 def test_unselected_quality_never_fully_deserialized(self):
  a,b,o=self.files(self.scores+[{'prefix_id':'external','probabilities':{'UNREAD':'UNREAD'},'status':'UNREAD'}])
  original=m.json.loads
  def guard(text,*args,**kwargs):
   if 'UNREAD' in text:raise AssertionError('External quality deserialized')
   return original(text,*args,**kwargs)
  with patch.object(m.json,'loads',side_effect=guard):_,selected,_=m.archive_snapshot(a,b,o)
  self.assertEqual(len(selected),704)
 def test_missing_checkpoint_rejected_without_output(self):
  a,b,o=self.files(self.scores[:-1])
  with self.assertRaisesRegex(ValueError,'Missing archive checkpoint'):m.archive_snapshot(a,b,o)
  self.assertFalse(o.exists())
 def test_unknown_not_complete_case_filtered(self):
  scores=self.scores.copy();scores[0]=dict(scores[0],status='UNKNOWN',unknown=True);a,b,o=self.files(scores)
  with self.assertRaisesRegex(ValueError,'Incomplete'):m.archive_snapshot(a,b,o)
  self.assertFalse(o.exists())
 def test_duplicate_rejected(self):
  a,b,o=self.files(self.scores+[self.scores[0]])
  with self.assertRaisesRegex(ValueError,'Duplicate'):m.archive_snapshot(a,b,o)
 def test_incomplete_input_timeline_rejected(self):
  a,b,o=self.files(inputs=self.inputs[:-1])
  with self.assertRaisesRegex(ValueError,'exact complete'):m.archive_snapshot(a,b,o)
 def test_snapshot_does_not_overwrite(self):
  a,b,o=self.files();o.write_text('preserve')
  with self.assertRaises(FileExistsError):m.archive_snapshot(a,b,o)
  self.assertEqual(o.read_text(),'preserve')
 def test_main_incomplete_blocks_before_data_access(self):
  with self.assertRaisesRegex(ValueError,'Main completion'):m.check_main(self.d)
 def mock_export(self,reserve):
  root=self.d/'root';base=self.d/'base';out=root/'supplemental';(root/'jev-v5/08').mkdir(parents=True);(root/'inputs-v5').mkdir()
  m.jsonl(root/'jev-v5/08/archive-all-inputs.jsonl',self.inputs);m.jsonl(root/'jev-v5/08/scores.jsonl',self.scores)
  m.jsonl(root/'inputs-v5/archive-p4-inputs.jsonl',[{'prefix_id':str(i*4+3)} for i in range(176)])
  protocol={'root':str(root),'base':str(base),'output':str(out),'heavy_lock':str(self.d/'heavy.lock'),'minimum_cv_remaining_seconds':1200}
  jev=types.ModuleType('cascade_guard.v2_jev');jev.feature_records=lambda *a:[{'prefix_id':str(i*4+3),'block':b,'status':'OK'} for i in range(176) for b in m.BLOCKS]
  views=types.ModuleType('cascade_guard.v2_feature_views');views.normalize_jev_file=lambda a,b,**k:(b.write_text('PUBLIC FEATURES') or {'path':str(b)})
  return protocol,{'cascade_guard.v2_jev':jev,'cascade_guard.v2_feature_views':views},out
 def test_export_preserved_when_cv_budget_insufficient(self):
  protocol,modules,out=self.mock_export(10)
  with patch.object(m,'check_protocol',return_value=protocol),patch.object(m,'check_main',return_value='public'),patch.object(m,'remaining',return_value=10),patch.dict(sys.modules,modules),patch.object(m.subprocess,'Popen') as child:
   result=m.execute('public','public',run_cv=True)
  self.assertEqual(result,'EXPORT_COMPLETE_CV_DEFERRED');self.assertTrue((out/'EXPORT_COMPLETE.json').exists());self.assertTrue((out/'Jev-08.jsonl').exists());child.assert_not_called()
 def test_expired_during_export_never_seals_complete(self):
  protocol,modules,out=self.mock_export(1)
  with patch.object(m,'check_protocol',return_value=protocol),patch.object(m,'check_main',return_value='public'),patch.object(m,'remaining',side_effect=[1,-1]),patch.dict(sys.modules,modules):
   with self.assertRaises(TimeoutError):m.execute('public','public')
  self.assertTrue((out/'archive-scores.jsonl').exists());self.assertTrue((out/'EXPORT_INCOMPLETE.json').exists());self.assertFalse((out/'EXPORT_COMPLETE.json').exists())
 def test_integrity_check_consumes_cv_reserve_no_launch(self):
  protocol,modules,out=self.mock_export(1300);clock={'remaining':1300,'calls':0}
  def protocol_check(*a):
   clock['calls']+=1
   if clock['calls']==3:clock['remaining']=-1
   return protocol
  with patch.object(m,'check_protocol',side_effect=protocol_check),patch.object(m,'check_main',return_value='public'),patch.object(m,'remaining',side_effect=lambda:clock['remaining']),patch.dict(sys.modules,modules),patch.object(m.subprocess,'Popen') as child:
   result=m.execute('public','public',run_cv=True)
  self.assertEqual(result,'EXPORT_COMPLETE_CV_DEFERRED');child.assert_not_called();self.assertTrue((out/'EXPORT_COMPLETE.json').exists())
 def test_cv_launch_failure_marks_incomplete(self):
  protocol,modules,out=self.mock_export(1300)
  with patch.object(m,'check_protocol',return_value=protocol),patch.object(m,'check_main',return_value='public'),patch.object(m,'remaining',return_value=1300),patch.dict(sys.modules,modules),patch.object(m.subprocess,'Popen',side_effect=OSError('public launch failure')):
   with self.assertRaises(OSError):m.execute('public','public',run_cv=True)
  self.assertTrue((out/'EXPORT_COMPLETE.json').exists());self.assertEqual(m.read(out/'CV_INCOMPLETE.json')['status'],'INCOMPLETE')
 def test_cv_timeout_preserves_export_and_marks_incomplete(self):
  protocol,modules,out=self.mock_export(1300)
  child=unittest.mock.Mock(pid=999);child.wait.side_effect=[subprocess.TimeoutExpired('public',1),0]
  with patch.object(m,'check_protocol',return_value=protocol),patch.object(m,'check_main',return_value='public'),patch.object(m,'remaining',return_value=1300),patch.dict(sys.modules,modules),patch.object(m.subprocess,'Popen',return_value=child),patch.object(m.os,'killpg') as kill:
   with self.assertRaises(subprocess.TimeoutExpired):m.execute('public','public',run_cv=True)
  self.assertTrue((out/'EXPORT_COMPLETE.json').exists());self.assertEqual(m.read(out/'CV_INCOMPLETE.json')['status'],'INCOMPLETE');kill.assert_called_once()
 def test_protocol_wrong_sha_rejected(self):
  p=self.d/'protocol.json';p.write_text('{}')
  with self.assertRaisesRegex(ValueError,'protocol changed'):m.check_protocol(p,'0'*64)
 def test_only_fixed_nineteen_configs_prospective(self):
  p=self.d/'protocol.json';m.save(p,{'deadline_utc':m.DEADLINE,'blocks':list(m.BLOCKS),'expected_config_count':20})
  with self.assertRaisesRegex(ValueError,'Different prospective arms'):m.check_protocol(p,m.sha(p))
if __name__=='__main__':unittest.main()
