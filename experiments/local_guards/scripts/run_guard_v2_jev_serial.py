#!/usr/bin/env python3
"""Wait for prior frozen runtimes, then run the two Jev models serially.

This outer runner does not alter frozen model/input code, consume labels, or
hold the global heavy lock while starting a child that acquires that same lock.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

COLLECTIONS=('archive-all','archive-partial','raw64','raw64-partial','independent-all')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, value):
 path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
 tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');tmp.replace(path)


def verify(manifest, expected):
 if sha(manifest)!=expected: raise ValueError('Frozen manifest changed: '+str(manifest))
 spec=json.loads(Path(manifest).read_text())
 for name,wanted in spec['sha256'].items():
  if not Path(name).is_file() or sha(name)!=wanted:raise ValueError('Frozen file drift: '+name)
 return len(spec['sha256'])


def frozen_identity(method, jev):
 spec=json.loads(Path(jev).read_text())
 if spec['method_freeze_sha256']!=sha(method): raise ValueError('Jev input freeze belongs to another method freeze')


def heavy_children():
 result=subprocess.run(['ps','-axo','pid=,ppid=,command='],capture_output=True,text=True,check=True)
 found=[]
 for line in result.stdout.splitlines():
  parts=line.strip().split(None,2)
  if len(parts)!=3:continue
  pid,ppid,command=parts
  if '-m cascade_guard.v2_runtime ' in command or '-m cascade_guard.v2_jev ' in command:
   found.append({'pid':int(pid),'ppid':int(ppid),'command':command})
 return found


def ready(prior, expected_ids):
 path=Path(prior)/'runtime-run.json'
 if not path.is_file():return False,{'reason':'prior runtime state not created'}
 state=json.loads(path.read_text())
 if state.get('status')!='COMPLETE':return False,{'reason':'prior runtime not COMPLETE','prior_status':state.get('status')}
 stages=state.get('stages',[])
 if {s.get('block') for s in stages if s.get('exit_code')==0}!={'N','M','G22','G86'}:
  return False,{'reason':'missing successful prior runtime stages'}
 for block in ('N','M','G22','G86'):
  score=Path(prior)/(block+'.jsonl')
  if not score.is_file():return False,{'reason':'missing prior score file','block':block}
  rows=[json.loads(line) for line in score.read_text().splitlines()]
  ids=[row['prefix_id'] for row in rows]
  if len(rows)!=720 or len(set(ids))!=720 or set(ids)!=expected_ids:
   return False,{'reason':'prior score coverage mismatch','block':block,'rows':len(rows),'unique':len(set(ids))}
 children=heavy_children()
 if children:return False,{'reason':'prior heavy child still running','children':children}
 return True,{'prior_runtime_sha256':sha(path),'score_rows_per_block':720,'heavy_children':[]}


def lease_idle(lock_path):
 with Path(lock_path).open('a') as handle:
  try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return False
  finally:
   # Closing also unlocks; this intentionally does not bypass the child lock.
   pass
 return True


def run_stage(command, name, root, environment, destination, state, deadline):
 remaining=deadline-time.time()
 if remaining<=0:raise TimeoutError('Technical deadline reached before '+name)
 state['current_stage']=name;state['status']='RUNNING';atomic(destination/'runtime-run.json',state)
 stage={'name':name,'command':command,'started_at':dt.datetime.now(dt.timezone.utc).isoformat()}
 with (destination/(name+'.log')).open('a') as log:
  child=subprocess.Popen(command,cwd=root,env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  stage['pid']=child.pid;state['current_child']=stage;atomic(destination/'runtime-run.json',state)
  try:code=child.wait(timeout=remaining)
  except (subprocess.TimeoutExpired,KeyboardInterrupt):
   os.killpg(child.pid,signal.SIGTERM)
   try:child.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
   stage['exit_code']=child.returncode;stage['status']='DEADLINE_OR_INTERRUPTED'
   stage['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();state['stages'].append(stage)
   state.pop('current_child',None);atomic(destination/'runtime-run.json',state)
   raise TimeoutError('Technical deadline or interruption during '+name)
 stage['exit_code']=code;stage['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat()
 state['stages'].append(stage);state.pop('current_child',None);atomic(destination/'runtime-run.json',state)
 if code:raise RuntimeError(name+' failed with exit code '+str(code))


def complete_scores(path, expected):
 if not Path(path).is_file():return False
 rows=[json.loads(x) for x in Path(path).read_text().splitlines()]
 latest={r['prefix_id']:r for r in rows}
 return set(latest)==set(expected) and all(not r.get('unknown') for r in latest.values())


def export_collections(root, destination, model):
 sys.path.insert(0,str(root/'experiments/local_guards'))
 from cascade_guard.v2_jev import feature_records
 folder=destination/model;scores=[json.loads(x) for x in (folder/'scores.jsonl').read_text().splitlines()]
 exported=[];all_features=[]
 for name in COLLECTIONS:
  path=folder/(name+'-inputs.jsonl');inputs=[json.loads(x) for x in path.read_text().splitlines()]
  ids={r['prefix_id'] for r in inputs};selected=[r for r in scores if r['prefix_id'] in ids]
  subset=folder/(name+'-scores.jsonl')
  subset.write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in selected))
  features=feature_records(inputs,selected,'0.8B' if model=='08' else '4B')
  target=folder/('features-'+name+'.jsonl')
  target.write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in features));all_features.extend(features)
  exported.append({'collection':name,'inputs':len(inputs),'feature_rows':len(features),'file':str(target),'sha256':sha(target),
                   'unknown_feature_rows':sum(r['status']=='UNKNOWN' for r in features)})
 target=folder/'features.jsonl';target.write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in all_features))
 return {'collections':exported,'all_features':str(target),'sha256':sha(target),'rows':len(all_features)}


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--workspace',type=Path,default=Path.cwd())
 parser.add_argument('--method-freeze',type=Path,required=True);parser.add_argument('--jev-freeze',type=Path,required=True)
 parser.add_argument('--prior',type=Path,required=True);parser.add_argument('--destination',type=Path,required=True)
 parser.add_argument('--deadline',required=True);parser.add_argument('--future-resource-lease',action='store_true')
 args=parser.parse_args()
 if not args.future_resource_lease:raise PermissionError('Explicit root future resource lease required')
 root=args.workspace.resolve();dest=args.destination.resolve();dest.mkdir(parents=True,exist_ok=True)
 method=args.method_freeze.resolve();jev=args.jev_freeze.resolve();method_hash=sha(method);jev_hash=sha(jev)
 frozen_identity(method,jev)
 count=verify(method,method_hash);verify(jev,jev_hash)
 deadline=dt.datetime.fromisoformat(args.deadline.replace('Z','+00:00')).timestamp()
 runtime=root/'.runtime/mps-diagnostics/.venv/bin/python'
 lock=root/'.runtime/cheap-guards/heavy-model.lock';lock.parent.mkdir(parents=True,exist_ok=True)
 expected_ids={json.loads(x)['prefix_id'] for x in (dest/'4b/inputs.jsonl').read_text().splitlines()}
 if len(expected_ids)!=720:raise ValueError('Expected exactly 720 final P4 inputs')
 state={'status':'WAITING_PRIOR','pid':os.getpid(),'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'deadline':args.deadline,'verified_frozen_files':count,'method_freeze_sha256':method_hash,
        'jev_input_freeze_sha256':jev_hash,'script_sha256':sha(__file__),'stages':[],
        'paid_inference':False,'labels_read':False,'model_order':['08','4b']}
 awake=None
 with (dest/'watcher.lock').open('a') as watcher:
  fcntl.flock(watcher,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if (dest/'runtime-run.json').exists():
   previous=json.loads((dest/'runtime-run.json').read_text())
   state['stages']=previous.get('stages',[]);state['previous_pid']=previous.get('pid')
  atomic(dest/'runtime-run.json',state)
  if sys.platform=='darwin':awake=subprocess.Popen(['caffeinate','-i','-w',str(os.getpid())])
  environment={**os.environ,'PYTHONPATH':str(root/'experiments/local_guards'),
               'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false',
               'PYTORCH_MPS_FAST_MATH':'0','PYTORCH_ENABLE_MPS_FALLBACK':'0'}
  try:
   while True:
    if time.time()>=deadline:raise TimeoutError('Deadline while waiting for prior runtime')
    ok,why=ready(args.prior,expected_ids)
    if ok and lease_idle(lock):break
    state['wait_reason']=why;state['last_checked_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    atomic(dest/'runtime-run.json',state);time.sleep(min(30,max(0,deadline-time.time())))
   state['prior_barrier']=why;state['heavy_start_at']=dt.datetime.now(dt.timezone.utc).isoformat()
   verify(method,method_hash);verify(jev,jev_hash)
   run_stage([str(runtime),'-c','import json,torch; assert torch.backends.mps.is_available(), "MPS unavailable in this process"; print(json.dumps({"mps_available":True,"torch":torch.__version__}))'],
             'metal-preflight',root,environment,dest,state,deadline)
   for model in ('08','4b'):
    verify(method,method_hash);verify(jev,jev_hash)
    folder=dest/model;input_path=folder/'inputs.jsonl'
    common=[str(runtime),'-m','cascade_guard.v2_jev','--workspace',str(root),'--model','0.8B' if model=='08' else '4B','--input',str(input_path)]
    cpu=folder/'cpu-gate.json';mps=folder/'mps-gate.json';scores=folder/'scores.jsonl'
    for device,output in [('cpu',cpu),('mps',mps)]:
     if output.exists():
      gate=json.loads(output.read_text())
      if gate.get('status')=='COMPLETE' and not gate.get('passed'):raise RuntimeError('Existing numerical gate failed; requires diagnosis: '+str(output))
      done=gate.get('status')=='COMPLETE' and gate.get('passed')
     else:done=False
     if not done:
      verify(method,method_hash);verify(jev,jev_hash)
      command=common+['--mode','probe','--device',device,'--output',str(output)]
      if device=='mps':command+=['--reference',str(cpu)]
      run_stage(command,model+'-'+device+'-probe',root,environment,dest,state,deadline)
     if not json.loads(output.read_text()).get('passed'):raise RuntimeError('Numerical gate failed: '+str(output))
    verify(method,method_hash);verify(jev,jev_hash)
    ids=[json.loads(x)['prefix_id'] for x in input_path.read_text().splitlines()]
    if not complete_scores(scores,ids):
     run_stage(common+['--mode','batch','--device','mps','--output',str(scores),'--gate',str(mps)],
               model+'-mps-batch',root,environment,dest,state,deadline)
    # Inference process has exited: no model remains loaded during feature export.
    state.setdefault('exports',{})[model]=export_collections(root,dest,model)
    atomic(dest/'runtime-run.json',state)
   verify(method,method_hash);verify(jev,jev_hash)
   if heavy_children():raise RuntimeError('Unexpected heavy child at completion')
   state['status']='COMPLETE';state['models_unloaded']=True
  except TimeoutError as exc:state['status']='DEADLINE';state['error']=str(exc)
  except Exception as exc:state['status']='FAILED';state['error']=f'{type(exc).__name__}: {exc}'
  finally:
   if awake is not None:awake.terminate();awake.wait()
   state.pop('current_child',None);state['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat()
   atomic(dest/'runtime-run.json',state)
 return 0 if state['status']=='COMPLETE' else 1


if __name__=='__main__':raise SystemExit(main())
