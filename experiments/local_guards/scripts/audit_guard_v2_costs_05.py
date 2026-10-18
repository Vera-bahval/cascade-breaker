#!/usr/bin/env python3
"""Presentation-only cost provenance. Never deserialize scores/features/labels.

The projection parser skips every unrequested JSON value lexically. No model,
training, label, quality, inference-provider or process-launch code is imported.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

DECODER=json.JSONDecoder()
ROW_FIELDS={'prefix_id':True,'block':True,'input_hash':True,'run_hash':True,
 'provenance':{'collection':True,'episode_id':True,'cut_seq':True},
 'timing_ms':{'total':True,'compute':True,'queue':True,'cold_load':True},
 'memory':{'prefix_sampled_max':{'rss_bytes':True,'mps_driver_allocated_bytes':True}},
 'model_metadata':{'model_id':True,'revision':True,'device':True,'cold_weight_tokenizer_load_ms':True,'cpu_semantic_sanity_ms':True}}
GATE_FIELDS={k:True for k in ('passed','selected_device','repeats','elapsed_s','elapsed_ms','duration_ms','duration_s')}


def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def require(ok,reason):
 if not ok:raise ValueError(reason)
def space(s,i):
 while i<len(s) and s[i].isspace():i+=1
 return i
def skip(s,i):
 """Skip one raw JSON value without decoding unrequested scalar/container."""
 i=space(s,i);require(i<len(s),'Missing JSON value')
 if s[i]=='"':
  i+=1
  while i<len(s):
   if s[i]=='\\':i+=2
   elif s[i]=='"':return i+1
   else:i+=1
  raise ValueError('Unterminated JSON string')
 if s[i] in '[{':
  closing='}' if s[i]=='{' else ']';i+=1
  while True:
   i=space(s,i);require(i<len(s),'Unterminated JSON container')
   if s[i]==closing:return i+1
   if s[i] in ',:':i+=1;continue
   i=skip(s,i)
 start=i
 while i<len(s) and s[i] not in ',}] \t\r\n':i+=1
 require(i>start,'Invalid JSON scalar');return i
def project(s,fields,i=0):
 i=space(s,i)
 if fields is True:
  require(s[i] not in '[{','Metadata scalar cannot contain a JSON container')
  return DECODER.raw_decode(s,i)
 if isinstance(fields,list):
  require(len(fields)==1 and s[i]=='[','Expected projected object array');i+=1;items=[]
  while True:
   i=space(s,i)
   if s[i]==']':return items,i+1
   item,i=project(s,fields[0],i);items.append(item);i=space(s,i)
   if s[i]==']':return items,i+1
   require(s[i]==',','Missing array separator');i+=1
 require(s[i]=='{','Expected JSON object');i+=1;result={}
 while True:
  i=space(s,i)
  if s[i]=='}':return result,i+1
  key,end=DECODER.raw_decode(s,i);require(isinstance(key,str),'Object key must be string')
  i=space(s,end);require(s[i]==':','Missing object colon');i=space(s,i+1)
  if key in fields:result[key],i=project(s,fields[key],i)
  else:i=skip(s,i)
  i=space(s,i)
  if s[i]=='}':return result,i+1
  require(s[i]==',','Missing object separator');i+=1

def metadata(path,fields):return project(Path(path).read_text(),fields)[0]
def quantile(values,q):
 if not values:return None
 v=sorted(values);p=(len(v)-1)*q;i=int(p);return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(p-i)
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def interval(stage):
 try:return (dt.datetime.fromisoformat(stage['finished_at'].replace('Z','+00:00'))-dt.datetime.fromisoformat(stage['started_at'].replace('Z','+00:00'))).total_seconds()*1000
 except (KeyError,TypeError,ValueError):return None

def summarize_rows(paths):
 groups=defaultdict(list);identities=set();pins={}
 for path in map(Path,paths):
  pins[str(path.resolve())]=sha(path)
  with path.open() as f:
   for line in f:
    if not line.strip():continue
    r=project(line,ROW_FIELDS)[0];key=r['block'],r['prefix_id']
    require(key not in identities,'Duplicate scored row identity');identities.add(key)
    groups[r['block'],r.get('provenance',{}).get('collection','unspecified')].append(r)
 stages=[]
 for (block,collection),rows in sorted(groups.items()):
  durations=[r['timing_ms']['total'] for r in rows if finite(r.get('timing_ms',{}).get('total'))]
  cold=[r for r in rows if finite(r.get('timing_ms',{}).get('cold_load')) and r['timing_ms']['cold_load']>0]
  def peak(key):
   vv=[r.get('memory',{}).get('prefix_sampled_max',{}).get(key) for r in rows]
   vv=[v for v in vv if finite(v)];return max(vv) if vv else None
  stages.append(dict(block=block,collection=collection,records=len(rows),timed_records=len(durations),row_sum_ms=sum(durations) if durations else None,p50_ms=quantile(durations,.5),p95_ms=quantile(durations,.95),
   cold_setup_events=[dict(prefix_id=r['prefix_id'],cold_setup_ms=r['timing_ms']['cold_load'],weight_tokenizer_load_ms=r.get('model_metadata',{}).get('cold_weight_tokenizer_load_ms'),cpu_semantic_sanity_ms=r.get('model_metadata',{}).get('cpu_semantic_sanity_ms')) for r in cold],
   cold_setup_ms=sum(r['timing_ms']['cold_load'] for r in cold) if cold else None,
   cold_setup_status='OBSERVED_AT_RUN_START' if cold else 'NOT_MEASURED_IN_THIS_COLLECTION',
   max_rss_bytes=peak('rss_bytes'),max_mps_driver_bytes=peak('mps_driver_allocated_bytes'),
   inference_cost_source='Actual persisted row timings; mutable resume manifest wall/written ignored',timing_semantics='Observed serial cache-assisted row path; source preprocessing included, cold setup separate'))
 return stages,pins

def audit(root,output,score_paths=None):
 root=Path(root).resolve();require((root/'completion-v5/COMPLETE.json').is_file(),'Completion marker required; no metadata read before completion')
 completion=metadata(root/'completion-v5/COMPLETE.json',{'status':True,'destinations':True});require(completion.get('status')=='COMPLETE' and completion.get('destinations')==4,'Malformed completion marker')
 paths=score_paths or [root/'scores-v5'/f'{b}.jsonl' for b in ('G22','G86','N','M')]
 paths=[p for p in map(Path,paths) if p.exists()];stages,pins=summarize_rows(paths)
 metadata_pins={str((root/'completion-v5/COMPLETE.json').resolve()):sha(root/'completion-v5/COMPLETE.json'),str((root/'scores-v5/runtime-run.json').resolve()):sha(root/'scores-v5/runtime-run.json')}
 runtime=metadata(root/'scores-v5/runtime-run.json',{'pid':True,'stages':[{'block':True,'started_at':True,'finished_at':True,'exit_code':True}]})
 # Stages contain operational metadata only, not model outputs or task labels.
 actual=[]
 for stage in (runtime.get('stages',[]) if runtime.get('pid')==66054 else []):
  actual.append({k:stage.get(k) for k in ('block','started_at','finished_at','exit_code')}|dict(wall_ms=interval(stage),owner_pid=runtime.get('pid'),source='scores-v5/runtime-run.json; actual owner stage envelope',
   interpretation='Includes startup, weight load, gates, extraction and I/O; do not add it to contained row/gate/cold costs'))
 duplicate_path=root/'duplicate-orchestrator-67514.json';duplicate=None
 if duplicate_path.exists():
  metadata_pins[str(duplicate_path.resolve())]=sha(duplicate_path)
  d=metadata(duplicate_path,{'real_owner':{'pid':True},'duplicate_owner':{'pid':True,'started_at':True,'finished_at':True},'new_heavy_inference_from_duplicate':True})
  duplicate=dict(**d,orchestration_overhead_ms=interval(d.get('duplicate_owner',{})),inference_ms=0 if d.get('new_heavy_inference_from_duplicate') is False else None,
   interpretation='Duplicate cached resume / lease rejection overhead, not G22 inference; never use its mutable stage manifest as original model cost')
 gates=[]
 for path in sorted((root/'scores-v5').glob('*.mps-probe.json')):
  g=metadata(path,GATE_FIELDS);elapsed=next((g[k]*(1000 if k.endswith('_s') else 1) for k in ('elapsed_ms','duration_ms','elapsed_s','duration_s') if finite(g.get(k))),None)
  gates.append(dict(path=str(path),sha256=sha(path),block=path.name.split('.')[0],metadata=g,elapsed_ms=elapsed,elapsed_status='RECORDED' if elapsed is not None else 'NOT_RECORDED; exact gate elapsed cannot be recovered from probability validation arrays'))
 aborted=[];aborted_path=root/'scores-amend04-aborted-summary/N.jsonl'
 if aborted_path.exists():
  aborted,aborted_pins=summarize_rows([aborted_path]);pins.update(aborted_pins)
  for row in aborted:row['scope']='ABORTED_AMEND04_WASTED_COMPUTE_NOT_QUALITY'
 result=dict(schema='guard-v2-cost-provenance-v2',metadata_only=True,excluded='features, probability distributions, task outcomes, labels and quality metrics never deserialized',
  stages=stages,actual_owner_pid_expected=66054,actual_owner_stage_status='VERIFIED_OWNER_66054' if runtime.get('pid')==66054 else 'UNKNOWN_WRONG_OR_MISSING_OWNER; stage wall not used',actual_owner_stages=actual,duplicate_orchestration=duplicate,gates=gates,aborted04_waste=aborted,source_sha256=sha(__file__),score_file_sha256=pins,metadata_source_sha256=metadata_pins,
  limits=['Stage wall, row sum, cold setup and gates overlap: never sum all as total cost.','Aborted04 waste here covers persisted NLI row times and observed cold events only; missing interrupted startup/gate/I/O cost is not zero.','This addon covers PG/NLI/MiniCheck runtime files; Jev checkpoint/head latency remains in its separate frozen runtime/profile evidence.','Missing gate elapsed is UNKNOWN, not stage-wall minus row sum: residual includes startup/serialization/queue/I/O.','Cold setup can include CPU semantic sanity; weights/sanity separate only when explicitly measured.','Later collection without a cold event is NOT_MEASURED_IN_THIS_COLLECTION, not zero model cold cost.','RSS/Metal are process/device observed envelope; no per-model physical allocation or monetary cost inferred.'])
 output=Path(output);require(not output.exists(),'Refusing overwrite cost artifact');output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.root,a.output)
if __name__=='__main__':main()
