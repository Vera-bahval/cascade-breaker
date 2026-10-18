#!/usr/bin/env python3
"""Resumable serial local inference after root method/input freeze; no API path."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def atomic(path,value):
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


def verify_frozen(manifest, expected_manifest_hash):
 if hashlib.sha256(manifest.read_bytes()).hexdigest()!=expected_manifest_hash:raise ValueError('Freeze manifest changed during inference')
 spec=json.loads(manifest.read_text())
 expected=spec.get('sha256',{})
 if not expected:raise ValueError('Freeze manifest has no pinned file checksums')
 for name,wanted in expected.items():
  path=Path(name)
  if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=wanted:raise ValueError(f'Frozen source/input drift: {name}')
 return len(expected)


def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--workspace',type=Path,default=Path.cwd())
 parser.add_argument('--inputs',type=Path,required=True)
 parser.add_argument('--output-directory',type=Path,required=True)
 parser.add_argument('--freeze-manifest',type=Path,required=True)
 parser.add_argument('--deadline',required=True)
 parser.add_argument('--resource-lease',action='store_true')
 args=parser.parse_args()
 if not args.resource_lease:raise PermissionError('Root resource lease required')
 if not args.freeze_manifest.is_file():raise ValueError('Method freeze manifest is required')
 root=args.workspace.resolve();base=root/'experiments/local_guards';output=args.output_directory.resolve();output.mkdir(parents=True,exist_ok=True)
 freeze_hash=hashlib.sha256(args.freeze_manifest.read_bytes()).hexdigest()
 deadline=dt.datetime.fromisoformat(args.deadline.replace('Z','+00:00')).timestamp()
 frozen_count=verify_frozen(args.freeze_manifest,freeze_hash)
 state={'verified_frozen_files':frozen_count,'status':'RUNNING','pid':os.getpid(),'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'freeze_manifest_sha256':freeze_hash,'deadline':args.deadline,'stages':[],'paid_inference':False}
 atomic(output/'runtime-run.json',state)
 awake=subprocess.Popen(['caffeinate','-i','-w',str(os.getpid())]) if sys.platform=='darwin' else None
 environment={**os.environ,'PYTHONPATH':str(base),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false'}
 try:
  for block,directory in (('N','nli'),('M','minicheck'),('G22','promptguard22'),('G86','promptguard86')):
   verify_frozen(args.freeze_manifest,freeze_hash)
   if time.time()>=deadline:state['status']='DEADLINE';break
   started=dt.datetime.now(dt.timezone.utc).isoformat()
   command=[str(root/'.venv-cheap/bin/python'),'-m','cascade_guard.v2_runtime','--block',block,'--inputs',str(args.inputs.resolve()),'--output',str(output/(block+'.jsonl')),'--model-dir',str(root/'.runtime/cheap-guards'/directory),'--deadline',args.deadline,'--resource-lease','--mps-probe','--lock-path',str(root/'.runtime/cheap-guards/heavy-model.lock')]
   with (output/(block+'.log')).open('a') as log:
    run=subprocess.run(command,cwd=root,env=environment,stdout=log,stderr=subprocess.STDOUT)
   stage={'block':block,'started_at':started,'finished_at':dt.datetime.now(dt.timezone.utc).isoformat(),'exit_code':run.returncode,'command':command}
   state['stages'].append(stage);atomic(output/'runtime-run.json',state)
   if run.returncode:state['status']='FAILED';break
  else:
   verify_frozen(args.freeze_manifest,freeze_hash)
   state['status']='COMPLETE'
 except Exception as exc:
  state['status']='FAILED';state['error']=f'{type(exc).__name__}: {exc}'
  raise
 finally:
  if awake is not None:awake.terminate();awake.wait()
  state['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();atomic(output/'runtime-run.json',state)
 if state['status']=='COMPLETE':
  sys.path.insert(0,str(base))
  from cascade_guard.v2_runtime import summarize_outputs
  summarize_outputs([output/(b+'.jsonl') for b in ('N','M','G22','G86')],output.parent/'runtime-summary.json')
 print(json.dumps(state,indent=2))
 return 0 if state['status']=='COMPLETE' else 1

if __name__=='__main__':raise SystemExit(main())
