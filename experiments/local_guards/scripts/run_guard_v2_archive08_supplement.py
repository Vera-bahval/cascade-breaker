#!/usr/bin/env python3
"""Archive-only supplemental export/CV AFTER main completion; no pretrained feature-model inference."""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

DEADLINE='2026-10-15T22:59:58.072112+00:00'
BLOCKS=('J_cur','J_seq','J_agg','J_dynamic','J_prior')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def require(ok,msg):
 if not ok:raise ValueError(msg)
def rows(p):
 with Path(p).open() as handle:
  for line in handle:
   if line.strip():yield json.loads(line)
def save(p,value):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as h:json.dump(value,h,indent=2,allow_nan=False);h.write('\n')
def jsonl(p,values):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as h:
  for v in values:h.write(json.dumps(v,sort_keys=True,allow_nan=False)+'\n')
def remaining():return dt.datetime.fromisoformat(DEADLINE).timestamp()-time.time()
def check_protocol(path,wanted):
 require(sha(path)==wanted,'Supplemental protocol changed');protocol=read(path)
 require(protocol['deadline_utc']==DEADLINE,'No deadline extension')
 require(protocol['blocks']==list(BLOCKS) and protocol['expected_config_count']==19,'Different prospective arms')
 for file,expected in protocol['source_sha256'].items():require(sha(file)==expected,'Supplemental source drift: '+file)
 require(protocol['source_sha256'].get(str(Path(__file__).resolve()))==sha(__file__),'Runner is not pinned')
 root=Path(protocol['root'])
 require(protocol['minimum_cv_remaining_seconds']==1200,'Prospective CV reserve changed')
 for required in (Path(__file__).resolve(),Path(protocol['base'])/'tests/test_v2_archive08_supplement.py',Path(protocol['base'])/'tests/test_v2_archive08_supplement_audit.py',Path(protocol['base'])/'GUARD-V2-ARCHIVE08-SUPPLEMENT.md',Path(__file__).with_name('audit_guard_v2_costs_05.py').resolve(),root/'ROOT_AUTHORIZATION_PLAN_05.json'):
  require(str(required) in protocol['source_sha256'],'Missing supplemental dependency pin')
 for manifest_name in ('METHOD_FREEZE_05.json','NEW_ABLATION_PROTOCOL_05.json'):
  p=root/manifest_name;require(str(p) in protocol['source_sha256'],'Missing base freeze pin')
  for file,wanted_sha in read(p)['sha256'].items():require(sha(file)==wanted_sha,'Frozen base drift: '+file)
 return protocol

def prefix_only(line):
 """Use independently reviewed lexical projection, not full score decoding."""
 spec=importlib.util.spec_from_file_location('supplement_cost_projection',Path(__file__).with_name('audit_guard_v2_costs_05.py'))
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 metadata,end=module.project(line,{'prefix_id':True})
 require(not line[end:].strip(),'Trailing data after score object')
 require(isinstance(metadata.get('prefix_id'),str),'Missing scalar prefix identity')
 return metadata['prefix_id']

def archive_snapshot(inputs_path,scores_path,output):
 inputs=list(rows(inputs_path));ids={r['prefix_id'] for r in inputs}
 require(len(inputs)==704 and len(ids)==704,'Need exact complete archive704')
 require(len({r['provenance']['episode_id'] for r in inputs})==176,'Need176 archive timelines')
 chosen=[];seen=set();before=sha(scores_path)
 with Path(scores_path).open() as handle:
  for line in handle:
   if not line.strip():continue
   prefix=prefix_only(line)
   if prefix not in ids:continue
   row=json.loads(line) # Only archive identities reach full deserialization.
   require(row['prefix_id']==prefix and prefix not in seen,'Duplicate/mismatched archive score')
   require(row['status']=='OK' and row.get('unknown') is False,'Incomplete archive score')
   seen.add(prefix);chosen.append(row)
 require(seen==ids,'Missing archive checkpoint; no selective complete-case filtering')
 require(sha(scores_path)==before,'Source score file changed during snapshot')
 jsonl(output,chosen)
 return inputs,chosen,{'source_scores_sha256':before,'archive_scores_sha256':sha(output),'checkpoint_count':704,'episodes':176,'selected_by':'frozen archive prefix IDs only'}

def check_main(root):
 complete=root/'completion-v5/COMPLETE.json';require(complete.exists() and read(complete).get('status')=='COMPLETE','Main completion is not COMPLETE')
 authorization=root/'ROOT_AUTHORIZATION_PLAN_05.json'
 require(read(complete)['authorization_plan_sha256']==sha(authorization),'Main completion belongs to different authorization')
 for folder in ('scores-v5','jev-v5'):
  runtime=read(root/folder/'runtime-run.json');require(runtime.get('models_unloaded') is True and runtime.get('status')!='RUNNING','Inference not unloaded')
 pipeline=read(root/'evaluation-runner-v5/runtime-run.json');require(pipeline['status']=='PREDICTIONS_FROZEN_AWAITING_ROOT_UNBLIND','Main prediction pipeline not complete')
 for folder in ('evaluation-v5','evaluation-partial-v5'):
  require(sha(root/folder/'METHODS_FROZEN.json')==pipeline['methods_freezes'][folder],'Main model seal drift')
 for folder,name in (('evaluation-v5','independent'),('evaluation-v5','raw64'),('evaluation-partial-v5','raw64-partial'),('evaluation-v5','raw64-partial-shift')):
  dest=root/folder/name;pf=read(dest/'PREDICTIONS_FROZEN.json')
  require(sha(dest/'predictions.jsonl')==pf['predictions_sha256'],'Main predictions changed')
  require((dest/'UNBLINDED.json').exists() and (dest/'external-diagnostics.json').exists(),'Main release not complete')
 return sha(complete)

def export_deadline(out):
 if remaining()<=0:
  save(Path(out)/'EXPORT_INCOMPLETE.json',{'status':'INCOMPLETE','reason':'global deadline during export','preserved_partial_artifacts':True})
  raise TimeoutError('Global deadline during archive export')

def execute(protocol_path,protocol_sha,*,run_cv=False):
 p=check_protocol(protocol_path,protocol_sha);root=Path(p['root']);base=Path(p['base']);out=Path(p['output'])
 require(remaining()>0,'Deadline expired');main_sha=check_main(root)
 require(not out.exists(),'Supplemental output exists; no automatic resume')
 # A complete main run has unloaded inference; lock still guards any other owner.
 lock=Path(p['heavy_lock']);lock.parent.mkdir(parents=True,exist_ok=True)
 with lock.open('a') as lease:
  fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
  check_protocol(protocol_path,protocol_sha);check_main(root)
  out.mkdir(parents=True);save(out/'STARTED.json',{'scope':'POSTHOC_ARCHIVE_ONLY; no independent claim','main_complete_sha256':main_sha,'protocol_sha256':protocol_sha,'no_new_feature_model_inference':True,'hidden_labels_read':False})
  inputs,scores,provenance=archive_snapshot(root/'jev-v5/08/archive-all-inputs.jsonl',root/'jev-v5/08/scores.jsonl',out/'archive-scores.jsonl')
  export_deadline(out)
  sys.path.insert(0,str(base))
  from cascade_guard.v2_jev import feature_records
  from cascade_guard.v2_feature_views import normalize_jev_file
  features=feature_records(inputs,scores,'0.8B')
  export_deadline(out)
  require(len(features)==880 and all(r['status']=='OK' for r in features),'Need all880 actual features')
  require({r['block'] for r in features}==set(BLOCKS),'Unexpected J representation')
  raw=out/'archive-features-raw.jsonl';jsonl(raw,features)
  expected={r['prefix_id'] for r in rows(root/'inputs-v5/archive-p4-inputs.jsonl')}
  normalized=normalize_jev_file(raw,out/'Jev-08.jsonl',model='08',collection='archive',run_manifest=root/'jev-v5/runtime-run.json',expected_prefixes=expected)
  export_deadline(out)
  save(out/'EXPORT_COMPLETE.json',{'status':'EXPORT_COMPLETE','provenance':provenance,'normalized':normalized,'protocol_sha256':protocol_sha,'scope':'complete archive only; independent data absent'})
  if not run_cv or remaining()<p['minimum_cv_remaining_seconds']:
   save(out/'CV_DEFERRED.json',{'status':'DEFERRED','export_preserved':True,'reason':'export-only request or insufficient prospective minimum CV reserve','remaining_seconds':remaining()});return 'EXPORT_COMPLETE_CV_DEFERRED'
  require(remaining()>0,'Deadline before CV');check_protocol(protocol_path,protocol_sha)
  if remaining()<p['minimum_cv_remaining_seconds']:
   save(out/'CV_DEFERRED.json',{'status':'DEFERRED','export_preserved':True,'reason':'reserve exhausted by final integrity checks','remaining_seconds':remaining()});return 'EXPORT_COMPLETE_CV_DEFERRED'
  save(out/'evaluation/SUPPLEMENTAL_SCOPE.json',{'scope':'POSTHOC_ARCHIVE_ONLY','main_unblinded_before_this_series':True,'external_metrics_not_claimed':True,'same_original_archive_176_and_group_allocations':True,'new_feature_inference':False,'main_availablepool_unchanged':True})
  command=[str(base/'.venv-finbot/bin/python'),'-m','cascade_guard.v2_eval','train','--output',str(out/'evaluation'),'--rows',str(root/'inputs-v5/archive-p4-rows.jsonl'),'--outcomes',str(root/'evaluation/outcomes214.jsonl'),'--allocations',str(base/'results/cheap-guards/evaluation/fold-allocations.json'),'--records',str(out/'Jev-08.jsonl')]
  save(out/'CV_STARTED.json',{'status':'RUNNING','command':command,'deadline_utc':DEADLINE})
  with (out/'cv.log').open('x') as log:
   if remaining()<=0:
    save(out/'CV_INCOMPLETE.json',{'status':'INCOMPLETE','export_preserved':True,'reason':'deadline before child launch'});return 'CV_INCOMPLETE'
   try:child=subprocess.Popen(command,cwd=base,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   except OSError as exc:
    save(out/'CV_INCOMPLETE.json',{'status':'INCOMPLETE','export_preserved':True,'reason':'CV launch failed: '+type(exc).__name__});raise
   try:code=child.wait(timeout=max(.01,remaining()))
   except BaseException:
    try:os.killpg(child.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    child.wait();save(out/'CV_INCOMPLETE.json',{'status':'INCOMPLETE','export_preserved':True,'reason':'deadline/interruption; no automatic rerun'});raise
  if code or remaining()<=0:
   save(out/'CV_INCOMPLETE.json',{'status':'INCOMPLETE','exit_code':code,'export_preserved':True});return 'CV_INCOMPLETE'
  choices=read(out/'evaluation/training-input-freeze.json')
  require(len(choices['configs'])==19,'Unexpected fitted configuration inventory')
  method_sha=sha(out/'evaluation/METHODS_FROZEN.json')
  if remaining()<=0:
   save(out/'CV_INCOMPLETE.json',{'status':'INCOMPLETE','export_preserved':True,'reason':'deadline before completion seal'});return 'CV_INCOMPLETE'
  save(out/'CV_COMPLETE.json',{'status':'COMPLETE','configs':19,'scope':'posthoc archive nested CV only, never independent performance','methods_freeze_sha256':method_sha,'export_preserved':True});return 'CV_COMPLETE'

def main():
 p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,required=True);p.add_argument('--protocol-sha256',required=True);p.add_argument('--run-cv',action='store_true');a=p.parse_args();print(execute(a.protocol,a.protocol_sha256,run_cv=a.run_cv))
if __name__=='__main__':main()
