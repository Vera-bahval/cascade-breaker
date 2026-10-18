"""Deadline-bounded, restartable SecJev4B parity probe and three-format batch."""
from __future__ import annotations
import argparse,json,time,hashlib,os
from pathlib import Path
from .secjev4b import SecJev4BScorer
from .secjev4b_microbatch import SecJev4BMicrobatchScorer
from .secjev_batch import batch_row,inference_input_hash
from .mps_diagnostics import aa_summary
from .secjev_benchmark import compare

def main():
 p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,default=Path.cwd());p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--device',choices=['cpu','mps'],required=True);p.add_argument('--mode',choices=['probe','batch'],required=True);p.add_argument('--deadline-unix',type=float,required=True);p.add_argument('--reference',type=Path);p.add_argument('--formats',nargs='+',default=['plus_rationale','compact_policy_facts','relevant_history_obligations']);a=p.parse_args()
 if a.mode=='batch': a.deadline_unix-=120 # reserve final evaluation/report time inside the global budget
 if time.time()>=a.deadline_unix: raise TimeoutError('Deadline before model load')
 rows=[json.loads(x) for x in a.input.read_text().splitlines()];a.output.parent.mkdir(parents=True,exist_ok=True)
 scorer_type=SecJev4BMicrobatchScorer if a.device=='mps' else SecJev4BScorer
 scorer=scorer_type(a.workspace,a.device,1,'sdpa','solver_block' if a.device=='mps' else 'none')
 if a.mode=='probe':
  # Deterministic shortest/longest inputs, across the exact frozen formats.
  unique={r['payload_hash']:r for r in rows};ordered=sorted(unique.values(),key=lambda r:len(json.dumps(r['payload'],ensure_ascii=False)))
  selected=ordered[:3]+ordered[-3:]; report={'status':'RUNNING','selection':'3 shortest and 3 longest distinct frozen payloads by serialized characters','model_metadata':scorer.metadata,'input_sha256':hashlib.sha256(a.input.read_bytes()).hexdigest(),'cases':[]}
  ref={r['payload_hash']:r for r in json.loads(a.reference.read_text())['cases']} if a.reference else {}
  for row in selected:
   results=[]
   for repeat in range(3):
    if time.time()>=a.deadline_unix: raise TimeoutError('Deadline between probe calls')
    result=scorer.score(row['payload']);results.append(result)
    partial={'prefix_id':row['prefix_id'],'format':row['format'],'payload_hash':row['payload_hash'],'results':results,'aa':aa_summary(results)}
    a.output.write_text(json.dumps({**report,'current_case':partial},indent=2,allow_nan=False)+'\n')
    print(json.dumps({'mode':'probe','device':a.device,'prefix_id':row['prefix_id'],'format':row['format'],'repeat':repeat,'status':result['status'],'compute_ms':result['timing_ms']['compute'],'error':result.get('error')}),flush=True)
   item={'prefix_id':row['prefix_id'],'format':row['format'],'payload_hash':row['payload_hash'],'results':results,'aa':aa_summary(results)}
   if row['payload_hash'] in ref:item['cpu_parity']=[compare(ref[row['payload_hash']]['results'][0],x,tolerance=1e-4) for x in results]
   report['cases'].append(item);a.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
  report['status']='COMPLETE';report['passed']=all(c['aa'].get('max_abs_delta',0)==0 and all(r['status']=='OK' for r in c['results']) and all(x['passed'] for x in c.get('cpu_parity',[])) for c in report['cases']);a.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');return
 done={}
 if a.output.exists():
  for line in a.output.read_text().splitlines():
   r=json.loads(line)
   if not r['unknown']:done[(r['prefix_id'],r['format'],r['input_hash'])]=r
 manifest={'status':'RUNNING','model_metadata':scorer.metadata,'input_sha256':hashlib.sha256(a.input.read_bytes()).hexdigest(),'deadline_unix':a.deadline_unix,'pid':os.getpid(),'processed':0,'skipped':0,'unknown':0,'formats':a.formats}
 with a.output.open('a',buffering=1) as out:
  for fmt in a.formats:
   for row in rows:
    if row['format']!=fmt:continue
    ih=inference_input_hash(row['payload'],scorer.fingerprint);key=(row['prefix_id'],fmt,ih)
    if key in done:manifest['skipped']+=1;continue
    if time.time()>=a.deadline_unix:
     manifest['status']='DEADLINE';a.output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return
    result=scorer.score(row['payload']);r=batch_row(row,'plus_rationale',result,ih);r.update(format=fmt,payload_hash=row['payload_hash']);out.write(json.dumps(r,allow_nan=False)+'\n');manifest['processed']+=1;manifest['unknown']+=r['unknown']
    if not r['unknown']:done[key]=r
    a.output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'mode':'batch','format':fmt,'prefix_id':row['prefix_id'],'processed':manifest['processed'],'unknown':r['unknown'],'compute_ms':r['model_compute_ms']}),flush=True)
 manifest['status']='COMPLETE';a.output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__': main()
