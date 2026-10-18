"""Public synthetic orchestration tests. No experiment inputs or labels opened."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).parents[1]/'scripts/finish_guard_v2_05.py'
spec=importlib.util.spec_from_file_location('completion05',SCRIPT);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class CompletionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.plan={'completion_deadline_utc':'2026-10-15T22:59:58.072112+00:00','root':str(self.root),'base':str(self.root),'labels':{'independent':{'path':'NEVER_READ_HIDDEN','sha256':m.HIDDEN_LABELS},'raw64':{'path':'NEVER_READ_RAW','sha256':'b'*64}},'diagnostics_protocol':'protocol','independent_control':{'control-dir':'control'}}
  for folder,name,_,_ in m.DESTINATIONS:
   p=self.root/folder/name;p.mkdir(parents=True);(p/'PREDICTIONS_FROZEN.json').write_text('{}')
 def invoke(self,validator=None,command=None,execute=True):
  with patch.object(m,'authorization',return_value=self.plan),patch.object(m,'readonly_gate',return_value=[{'pass':True}]*4):
   return m.complete('PLAN','a'*64,execute=execute,validator=validator or (lambda *a,**k:{}),run_command=command or (lambda c:None))
 def test_readonly_does_not_mark_or_run(self):
  result=self.invoke(execute=False,command=lambda c:self.fail('command before execute'))
  self.assertFalse(result['labels_read']);self.assertFalse((self.root/'completion-v5/STARTED.json').exists())
 def test_all_label_joins_before_any_score(self):
  labels=[];commands=[]
  def validate(*a,**kw):
   self.assertTrue(all((self.root/f/n/'ROOT_UNBLIND_05.json').exists() for f,n,_,_ in m.DESTINATIONS));labels.append(kw['labels']);return {}
  def command(c):self.assertEqual(len(labels),4);commands.append(c)
  self.invoke(validate,command)
  self.assertEqual(sum('cascade_guard.v2_preunblind' in c for c in commands),4)
  self.assertEqual(sum('cascade_guard.v2_external_diagnostics' in c for c in commands),4)
  self.assertEqual(commands[-1][2],'cascade_guard.v2_report')
 def test_expired_during_label_validation_never_scores(self):
  calls=[]
  def late(*a,**kw):
   calls.append(1);self.plan['completion_deadline_utc']='2020-01-01T00:00:00+00:00';return {}
  with self.assertRaises(ValueError):self.invoke(late,lambda c:self.fail('scored after expired join'))
  self.assertEqual(len(calls),1)
 def test_label_join_failure_no_score(self):
  with self.assertRaises(ValueError):self.invoke(lambda *a,**k:(_ for _ in ()).throw(ValueError('bad join')),lambda c:self.fail('score after bad join'))
  self.assertTrue((self.root/'completion-v5/FAILED_MANUAL_RECOVERY_REQUIRED.json').exists())
 def test_scorer_failure_stops_no_retry(self):
  calls=[]
  def fail(c):calls.append(c);raise RuntimeError('partial scorer')
  with self.assertRaises(RuntimeError):self.invoke(command=fail)
  self.assertEqual(len(calls),1);self.assertTrue((self.root/'completion-v5/STARTED.json').exists())
 def test_markers_exclusive(self):
  f,n,_,_=m.DESTINATIONS[0];p=self.root/f/n/'ROOT_UNBLIND_05.json';p.write_text('preserve')
  with self.assertRaises(FileExistsError):self.invoke()
  self.assertEqual(p.read_text(),'preserve')
 def test_existing_start_rejected_before_pipeline_read(self):
  p=self.root/'completion-v5/STARTED.json';p.parent.mkdir();p.write_text('{}')
  with patch.object(m,'pinned'):
   with self.assertRaisesRegex(ValueError,'already started'):m.readonly_gate(self.plan,lambda *a,**k:{})
 def test_existing_metrics_rejected_before_validator(self):
  state={'status':'PREDICTIONS_FROZEN_AWAITING_ROOT_UNBLIND','freeze_sha256':{'method':m.MF05,'addon':'x','jev':'x','split':'x'},'methods_freezes':{'evaluation-v5':'x','evaluation-partial-v5':'x'}}
  def read(p):return state if str(p).endswith('runtime-run.json') else {'sha256':{}}
  f,n,_,_=m.DESTINATIONS[0];(self.root/f/n/'metrics.json').write_text('{}')
  self.plan['source_sha256']={str(self.root/'NEW_ABLATION_PROTOCOL_05.json'):'x'}
  statefile=self.root/'evaluation-runner-v5/runtime-run.json';statefile.parent.mkdir();statefile.write_text('{}')
  with patch.object(m,'pinned'),patch.object(m,'read',side_effect=read),patch.object(m,'sha',return_value='x'):
   with self.assertRaisesRegex(ValueError,'partial completion'):m.readonly_gate(self.plan,lambda *a,**k:self.fail('validated existing metrics'))
 def test_wrong_auth_never_reads_labels(self):
  p=self.root/'plan.json';p.write_text(json.dumps({'authorization':'NO'}))
  with self.assertRaisesRegex(ValueError,'authorization absent'):m.authorization(p,m.sha(p))
 def test_labels_cannot_be_hashed_as_source_before_markers(self):
  label=self.root/'sealed.jsonl'
  plan=dict(self.plan,authorization='COMPLETE_GUARD_V2_05_AND_UNBLIND',generation=5,automatic_resume=False,method_freeze_sha256=m.MF05,source_sha256={str(label):'x'})
  plan['labels']=dict(plan['labels'],independent={'path':str(label),'sha256':m.HIDDEN_LABELS})
  p=self.root/'auth.json';p.write_text(json.dumps(plan))
  with self.assertRaisesRegex(ValueError,'pre-marker source pins'):m.authorization(p,m.sha(p))
  self.assertFalse(label.exists())
 def test_wrong_plan_hash_rejected(self):
  p=self.root/'plan.json';p.write_text('{}')
  with self.assertRaisesRegex(ValueError,'Pinned artifact changed'):m.authorization(p,'0'*64)
 def test_deadline_extension_rejected(self):
  with self.assertRaisesRegex(ValueError,'Cannot extend'):m.deadline({'completion_deadline_utc':'2027-01-01T00:00:00+00:00'})
 def test_unknown_pipeline_status_is_not_waitable(self):
  self.plan['source_sha256']={str(self.root/'NEW_ABLATION_PROTOCOL_05.json'):'x'}
  statefile=self.root/'evaluation-runner-v5/runtime-run.json';statefile.parent.mkdir();statefile.write_text('{}')
  def rd(p):return {'status':'MYSTERY_TERMINAL'} if str(p).endswith('runtime-run.json') else {'sha256':{}}
  with patch.object(m,'pinned'),patch.object(m,'read',side_effect=rd):
   with self.assertRaisesRegex(ValueError,'Unknown/malformed'):m.readonly_gate(self.plan,lambda *a,**k:{})
 def test_missing_mandatory_dependency_rejected(self):
  base=SCRIPT.parents[1];protocol=base/'results/guard-v2/external-diagnostics-protocol-v2.json'
  files=[SCRIPT,protocol]+[base/'cascade_guard'/name for name in ('v2_preunblind.py','v2_external_diagnostics.py','v2_report.py','v2_eval.py')]
  plan=dict(self.plan,authorization='COMPLETE_GUARD_V2_05_AND_UNBLIND',generation=5,automatic_resume=False,method_freeze_sha256=m.MF05,base=str(base.resolve()),source_sha256={str(p.resolve()):m.sha(p) for p in files},diagnostics_protocol=str(protocol.resolve()),independent_control={k:'unused' for k in ('control-dir','control-inputs','control-rows','control-method-freeze','control-source')})
  p=self.root/'root-auth.json';p.write_text(json.dumps(plan))
  with self.assertRaisesRegex(ValueError,'Missing mandatory dependency pin'):m.authorization(p,m.sha(p))
 def test_absent_pipeline_wait_is_readonly(self):
  self.plan['source_sha256']={str(self.root/'NEW_ABLATION_PROTOCOL_05.json'):'x'}
  with patch.object(m,'pinned'),patch.object(m,'read',return_value={'sha256':{}}):
   with self.assertRaises(m.NotReady):m.readonly_gate(self.plan,lambda *a,**k:self.fail('validator before pipeline'))
  self.assertFalse((self.root/'completion-v5/STARTED.json').exists())
class RawLabelsTests(unittest.TestCase):
 def test_author_field_is_exact_not_state_or_prediction(self):
  s=Path(__file__).parents[1]/'scripts/export_guard_v2_raw_labels.py';sp=importlib.util.spec_from_file_location('raw_export',s);e=importlib.util.module_from_spec(sp);sp.loader.exec_module(e)
  with tempfile.TemporaryDirectory() as d:
   source=Path(d)/'source.json';output=Path(d)/'labels.jsonl';source.write_text(json.dumps([{'id':'one','family':'family','expected_block':{'base':False,'strict_review':True},'label_reason':'author','state':{'danger':True},'prediction':True}]))
   e.export(source,output,False);row=json.loads(output.read_text());self.assertFalse(row['contract_requires_intervention']);self.assertNotIn('harm_if_continue',row);self.assertEqual(row['episode_id'],'raw:one')
if __name__=='__main__':unittest.main()
