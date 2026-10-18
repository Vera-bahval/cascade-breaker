#!/usr/bin/env python3
"""Serial supervised 4B numerical checks then deadline-limited resumable scoring."""
import argparse,json,os,subprocess,time,hashlib
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,default=Path(__file__).resolve().parents[3]);p.add_argument('--deadline-unix',type=float,required=True);a=p.parse_args();root=a.workspace.resolve();target=root/'experiments/local_guards/results/night-4b';target.mkdir(parents=True,exist_ok=True);runtime=target/'runtime';runtime.mkdir(exist_ok=True)
 env={**os.environ,'PYTHONPATH':str(root/'experiments/local_guards'),'PYTORCH_MPS_FAST_MATH':'0','PYTORCH_ENABLE_MPS_FALLBACK':'0','HF_HUB_OFFLINE':'1'}
 python=root/'.runtime/mps-diagnostics/.venv/bin/python';inputs=target/'formats/inputs.jsonl';status={'started_unix':time.time(),'deadline_unix':a.deadline_unix,'status':'RUNNING','stages':[]}
 def run(name,arguments):
  if name in ('cpu-probe','mps-probe') and (runtime/f'{name}.json').exists():
   old=json.loads((runtime/f'{name}.json').read_text())
   metadata=old.get('model_metadata',{})
   model_source=root/'experiments/local_guards/cascade_guard/secjev4b.py'
   source_matches=metadata.get('scorer_sha256')==hashlib.sha256(model_source.read_bytes()).hexdigest()
   if name=='mps-probe':
    micro_source=root/'experiments/local_guards/cascade_guard/secjev4b_microbatch.py'
    source_matches=(metadata.get('question_microbatch_size')==1 and metadata.get('cache_policy')=='empty_cache_between_questions_and_after_request' and metadata.get('base_scorer_sha256')==hashlib.sha256(model_source.read_bytes()).hexdigest() and metadata.get('scorer_sha256')==hashlib.sha256(micro_source.read_bytes()).hexdigest())
   if old.get('status')=='COMPLETE' and old.get('passed') and source_matches and old.get('input_sha256')==hashlib.sha256(inputs.read_bytes()).hexdigest():
    status['stages'].append({'stage':name,'resumed_completed':True});return
  remaining=a.deadline_unix-time.time()-10 # leave termination grace inside the hard wall-clock budget
  if remaining<=0:raise TimeoutError('Deadline')
  cmd=[str(python),'-m','cascade_guard.secjev4b_run','--workspace',str(root),'--input',str(inputs),'--deadline-unix',str(a.deadline_unix),*arguments];started=time.time()
  with (runtime/f'{name}.log').open('a',buffering=1) as log:
   child=subprocess.Popen(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   try:code=child.wait(timeout=remaining)
   except subprocess.TimeoutExpired:
    child.terminate()
    try:child.wait(timeout=10)
    except subprocess.TimeoutExpired:child.kill();child.wait()
    raise TimeoutError('Experiment deadline stopped model process')
  status['stages'].append({'stage':name,'started_unix':started,'finished_unix':time.time(),'exit_code':code,'log':str(runtime/f'{name}.log')});(runtime/'pipeline.json').write_text(json.dumps(status,indent=2)+'\n')
  if code:raise RuntimeError(f'{name} exited {code}')
 try:
  run('cpu-probe',['--device','cpu','--mode','probe','--output',str(runtime/'cpu-probe.json')])
  if not json.loads((runtime/'cpu-probe.json').read_text()).get('passed'):raise RuntimeError('CPU repeat validity failed')
  run('mps-probe',['--device','mps','--mode','probe','--reference',str(runtime/'cpu-probe.json'),'--output',str(runtime/'mps-probe.json')])
  if not json.loads((runtime/'mps-probe.json').read_text()).get('passed'):raise RuntimeError('MPS numerical parity failed; explicit fallback decision required')
  run('batch',['--device','mps','--mode','batch','--output',str(target/'scores.jsonl')])
  status['status']=json.loads((target/'scores.manifest.json').read_text())['status']
 except Exception as exc:status['status']='STOPPED';status['error']=str(exc)
 status['finished_unix']=time.time();(runtime/'pipeline.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
if __name__=='__main__':main()
