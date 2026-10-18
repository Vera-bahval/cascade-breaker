#!/usr/bin/env python3
"""Root-authorized one-shot completion. No fits, inference, or automatic resume."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time

MF05='905199e01d99950fe905cb741d27bee56df5be745819d62d64820fb119747d44'
HIDDEN_LABELS='89135d1002f0589e8818bc5673a6b1ba9c239cc0c4de5d94d9ac8077b9519dfa'
DESTINATIONS=(('evaluation-v5','independent',240,'independent'),('evaluation-v5','raw64',64,'raw64'),('evaluation-partial-v5','raw64-partial',64,'raw64'),('evaluation-v5','raw64-partial-shift',64,'raw64'))

class NotReady(RuntimeError):pass

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def require(ok,msg):
 if not ok:raise ValueError(msg)
def exclusive(p,obj):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as h:json.dump(obj,h,indent=2,allow_nan=False);h.write('\n');h.flush();os.fsync(h.fileno())
def pinned(p,wanted):require(Path(p).is_file() and sha(p)==wanted,'Pinned artifact changed: '+str(p))
def deadline(plan):
 value=dt.datetime.fromisoformat(plan['completion_deadline_utc'].replace('Z','+00:00'))
 require(value.tzinfo is not None,'Completion deadline must include timezone')
 require(value.isoformat()=='2026-10-15T22:59:58.072112+00:00','Cannot extend frozen completion deadline')
 require(dt.datetime.now(dt.timezone.utc)<value,'Explicit root completion deadline expired')

def authorization(plan_path,expected_sha):
 pinned(plan_path,expected_sha);plan=read(plan_path)
 require(plan.get('authorization')=='COMPLETE_GUARD_V2_05_AND_UNBLIND','Root authorization absent')
 require(plan.get('generation')==5 and plan.get('automatic_resume') is False,'Wrong generation or resume policy')
 require(plan.get('method_freeze_sha256')==MF05,'Wrong method generation')
 require(plan['labels']['independent']['sha256']==HIDDEN_LABELS,'Hidden label commitment differs')
 label_paths={str(Path(v['path']).resolve()) for v in plan['labels'].values()}
 require(not label_paths & {str(Path(p).resolve()) for p in plan['source_sha256']},'Labels cannot be pre-marker source pins')
 for p,s in plan['source_sha256'].items():pinned(p,s)
 require(str(Path(__file__).resolve()) in plan['source_sha256'],'Root did not pin this runner')
 base=Path(plan['base'])
 for name in ('v2_preunblind.py','v2_external_diagnostics.py','v2_report.py','v2_eval.py'):
  require(str(base/'cascade_guard'/name) in plan['source_sha256'],'Missing completion dependency pin: '+name)
 require(plan['diagnostics_protocol'] in plan['source_sha256'],'Diagnostic protocol pin missing')
 root=Path(plan['root'])
 mandatory=[Path(__file__).resolve(),base/'tests/test_v2_completion_runner.py',base/'tests/test_v2_completion_audit.py',base/'GUARD-V2-COMPLETION-05.md',base/'tests/test_v2_preunblind.py',base/'tests/test_v2_external_diagnostics.py']
 mandatory += [root/name for name in ('NEW_ABLATION_PROTOCOL_05.json','SPLIT_PROTOCOL_FREEZE_05.json','JEV_INPUT_FREEZE_05.json','JEV_CLOCK_GUARD_05.json')]
 control=plan['independent_control']
 require(set(control)=={'control-dir','control-inputs','control-rows','control-method-freeze','control-source'},'Incomplete independent control contract')
 mandatory += [Path(control[k]) for k in ('control-inputs','control-rows','control-method-freeze','control-source')]
 for path in mandatory:require(str(path.resolve()) in plan['source_sha256'],'Missing mandatory dependency pin: '+str(path))
 require(plan['source_sha256'][str(Path(__file__).resolve())]==sha(__file__),'Runner pin differs')
 deadline(plan);return plan

def readonly_gate(plan,validator):
 root=Path(plan['root']);method=root/'METHOD_FREEZE_05.json';pinned(method,MF05)
 require(not (root/'completion-v5/STARTED.json').exists(),'Completion was already started; root manual recovery required')
 for p,s in read(method)['sha256'].items():pinned(p,s)
 # Root pins the addon and every late protocol/source, not dynamically blessed hashes.
 require(str(root/'NEW_ABLATION_PROTOCOL_05.json') in plan['source_sha256'],'Addon pin missing')
 addon=read(root/'NEW_ABLATION_PROTOCOL_05.json')
 for p,s in addon['sha256'].items():pinned(p,s)
 statepath=root/'evaluation-runner-v5/runtime-run.json'
 if not statepath.exists():raise NotReady('Prediction pipeline state absent')
 state=read(statepath)
 if state.get('status') in ('FAILED','DEADLINE'):raise ValueError('Prediction pipeline failed; root manual action required')
 if state.get('status') in ('WAITING_INFERENCE_BARRIER','RUNNING'):raise NotReady('Prediction pipeline not complete')
 require(state.get('status')=='PREDICTIONS_FROZEN_AWAITING_ROOT_UNBLIND','Unknown/malformed prediction pipeline status')
 require(not state.get('child_pid'),'Prediction child still recorded')
 require(state.get('freeze_sha256',{}).get('method')==MF05,'Pipeline method mismatch')
 for key,name in [('addon','NEW_ABLATION_PROTOCOL_05.json'),('jev','JEV_INPUT_FREEZE_05.json'),('split','SPLIT_PROTOCOL_FREEZE_05.json')]:
  require(state.get('freeze_sha256',{}).get(key)==sha(root/name),'Pipeline protocol mismatch')
 for folder in ('evaluation-v5','evaluation-partial-v5'):
  require(state['methods_freezes'][folder]==sha(root/folder/'METHODS_FROZEN.json'),'Final model seal changed')
 checks=[]
 for folder,name,count,label_key in DESTINATIONS:
  dest=root/folder/name
  for output in ('metrics.json','UNBLINDED.json','pair-metrics.json','external-diagnostics.json','ROOT_UNBLIND_05.json'):
   require(not (dest/output).exists(),'Existing/partial completion artifact; root manual recovery required: '+str(dest/output))
  checks.append(validator(root/folder,dest,expected_rows=count))
 return checks

def complete(plan_path,expected_sha,*,execute=False,validator=None,run_command=None):
 plan=authorization(plan_path,expected_sha)
 if validator is None:
  sys.path.insert(0,str(Path(plan['base']).resolve()))
  from cascade_guard.v2_preunblind import validate
  validator=validate
 checks=readonly_gate(plan,validator)
 deadline(plan)
 if not execute:return {'status':'READY_READ_ONLY','labels_read':False,'destinations':len(checks)}
 root=Path(plan['root']);work=Path(plan['base']);statepath=root/'completion-v5/STARTED.json'
 exclusive(statepath,{'authorization_plan_sha256':expected_sha,'status':'ONE_SHOT_STARTED','readonly_checks':checks})
 # Any failure after this seal requires explicit manual root recovery. No retries.
 try:
  authorization(plan_path,expected_sha) # STARTED already owns this one-shot transaction
  for folder,name,count,key in DESTINATIONS:
   deadline(plan)
   dest=root/folder/name;exclusive(dest/'ROOT_UNBLIND_05.json',{'authorization':'UNBLIND','authorization_plan_sha256':expected_sha,'predictions_freeze_sha256':sha(dest/'PREDICTIONS_FROZEN.json'),'labels_sha256':plan['labels'][key]['sha256']})
  # Validate every authorized label join before executing the first scorer.
  for folder,name,count,key in DESTINATIONS:
   deadline(plan)
   validator(root/folder,root/folder/name,expected_rows=count,labels=Path(plan['labels'][key]['path']),unblind_marker=root/folder/name/'ROOT_UNBLIND_05.json')
   deadline(plan)
  def default_runner(command):
   deadline(plan)
   remaining=dt.datetime.fromisoformat(plan['completion_deadline_utc']).timestamp()-time.time()
   child=subprocess.Popen(command,cwd=work,start_new_session=True)
   try:code=child.wait(timeout=remaining)
   except BaseException:
    os.killpg(child.pid,signal.SIGKILL);child.wait();raise
   if code:raise subprocess.CalledProcessError(code,command)
  runner=run_command or default_runner
  for folder,name,count,key in DESTINATIONS:
   authorization(plan_path,expected_sha);dest=root/folder/name;marker=dest/'ROOT_UNBLIND_05.json';labels=plan['labels'][key]['path']
   runner([sys.executable,'-m','cascade_guard.v2_preunblind','--methods',str(root/folder),'--destination',str(dest),'--expected-rows',str(count),'--labels',labels,'--unblind-marker',str(marker),'--score'])
   command=[sys.executable,'-m','cascade_guard.v2_external_diagnostics','run','--destination',str(dest),'--labels',labels,'--marker',str(marker),'--plan',plan['diagnostics_protocol'],'--output',str(dest/'external-diagnostics.json'),'--method-freeze',str(root/folder/'METHODS_FROZEN.json')]
   if key=='independent':
    for flag,path in plan['independent_control'].items():command.extend(['--'+flag,path])
   runner(command)
  runner([sys.executable,'-m','cascade_guard.v2_report','--base',str(work)])
  deadline(plan)
  exclusive(root/'completion-v5/COMPLETE.json',{'status':'COMPLETE','authorization_plan_sha256':expected_sha,'destinations':4})
  return {'status':'COMPLETE','destinations':4}
 except BaseException as exc:
  exclusive(root/'completion-v5/FAILED_MANUAL_RECOVERY_REQUIRED.json',{'status':'FAILED_MANUAL_RECOVERY_REQUIRED','error':type(exc).__name__+': '+str(exc)})
  raise

def main():
 p=argparse.ArgumentParser();p.add_argument('--authorization-plan',type=Path,required=True);p.add_argument('--authorization-sha256',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--wait',action='store_true');a=p.parse_args()
 while True:
  try:result=complete(a.authorization_plan,a.authorization_sha256,execute=a.execute);break
  except NotReady:
   if not a.wait or (Path(read(a.authorization_plan)['root'])/'completion-v5/STARTED.json').exists():raise
   authorization(a.authorization_plan,a.authorization_sha256);time.sleep(20)
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
