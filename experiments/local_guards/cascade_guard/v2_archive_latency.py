"""Archive-only warm single-row latency profiling of already frozen ML heads.
No fitting, inference-provider calls, threshold selection, or prediction saving.
"""
from __future__ import annotations
import argparse
import datetime as dt
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import time

VERSION='archive-latency-v2'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def require(ok,message):
 if not ok:raise ValueError(message)
def write(path,value):
 path=Path(path);require(not path.exists(),'Refusing to overwrite latency artifact')
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def sample_ids(ids,seed,n=16):
 require(len(ids)==len(set(ids)),'Duplicate sample identity')
 return sorted(ids,key=lambda pid:hashlib.sha256(f'{VERSION}|{seed}|{pid}'.encode()).hexdigest())[:n]
def quantile(values,q):
 if not values:return None
 ss=sorted(values);p=(len(ss)-1)*q;lo=int(p);return ss[lo]+(ss[min(lo+1,len(ss)-1)]-ss[lo])*(p-lo)
def stats(values):return dict(n=len(values),p50_ms=quantile(values,.5),p95_ms=quantile(values,.95))
def freeze(path,source_freeze):
 tests=Path(__file__).resolve().parents[1]/'tests/test_v2_archive_latency.py'
 write(path,dict(version=VERSION,source_sha256=sha(__file__),tests_sha256=sha(tests),source_freeze_sha256=sha(source_freeze),
  sample='Known-feature archive rows only, first 16 prefix IDs ordered by sha256(archive-latency-v2|seed|prefix_id), same sample across heads when eligible inventories match; no outcome-based selection',
  execution='One untimed warmup per model; single-row predict wall time includes its own feature matrix preparation; separate x/render/tabular/rules microprofiles',
  deadline='Cooperative soft budget at most 300 seconds after integrity validation, capped by frozen global deadline; cannot interrupt an individual joblib/predict call. Partial explicit; no pretrained feature-model inference or fitting',
  cost='Cached feature extraction source times retained; sum is reconstructed eager serial path, not live end-to-end; no per-model memory inference'))

def validate_completion(methods,source_freeze,completion,authorization_plan,authorization_sha):
 require(completion is not None and Path(completion).is_file(),'Completion marker required before profiling')
 require(authorization_plan is not None and authorization_sha is not None,'Pinned root authorization required')
 require(sha(authorization_plan)==authorization_sha,'Root authorization hash differs')
 authorization=read(authorization_plan);root=Path(authorization['root']).resolve()
 require(authorization.get('authorization')=='COMPLETE_GUARD_V2_05_AND_UNBLIND' and authorization.get('generation')==5,'Wrong root authorization')
 require(Path(completion).resolve()==root/'completion-v5/COMPLETE.json','Completion marker is outside authorized root')
 completed=read(completion)
 require(completed.get('status')=='COMPLETE' and completed.get('destinations')==4 and completed.get('authorization_plan_sha256')==authorization_sha,'Malformed or unbound completion marker')
 require(Path(source_freeze).resolve()==root/'METHOD_FREEZE_05.json' and authorization.get('method_freeze_sha256')==sha(source_freeze),'Source generation differs from authorization')
 methods=Path(methods).resolve();require(methods in (root/'evaluation-v5',root/'evaluation-partial-v5'),'Methods outside authorized generation')
 state=read(root/'evaluation-runner-v5/runtime-run.json')
 require(state.get('status')=='PREDICTIONS_FROZEN_AWAITING_ROOT_UNBLIND' and not state.get('child_pid'),'Pipeline not successfully sealed')
 require(state.get('freeze_sha256',{}).get('method')==sha(source_freeze),'Pipeline source generation mismatch')
 for key,name in (('addon','NEW_ABLATION_PROTOCOL_05.json'),('jev','JEV_INPUT_FREEZE_05.json'),('split','SPLIT_PROTOCOL_FREEZE_05.json')):
  require(state.get('freeze_sha256',{}).get(key)==sha(root/name),'Pipeline protocol identity mismatch')
 require(state['methods_freezes'].get(methods.name)==sha(methods/'METHODS_FROZEN.json'),'Fitted methods not anchored to completed pipeline')
 for p,wanted in authorization['source_sha256'].items():
  if Path(p).suffix=='.py':require(sha(p)==wanted,'Root authorized source differs')
 deadline=dt.datetime.fromisoformat(authorization['completion_deadline_utc'].replace('Z','+00:00'))
 require(deadline.tzinfo is not None,'Global deadline timezone missing')
 frozen_limit=dt.datetime.fromisoformat(read(source_freeze)['technical_runner_deadline_utc'].replace('Z','+00:00'))
 require(frozen_limit.tzinfo is not None and deadline<=frozen_limit,'Root profiling deadline extends frozen global deadline')
 return deadline.timestamp()


def run(methods,rows_path,record_paths,source_freeze,plan,output,max_seconds=300,completion=None,authorization_plan=None,authorization_sha=None):
 global_deadline=validate_completion(methods,source_freeze,completion,authorization_plan,authorization_sha)
 require(time.time()<global_deadline,'Frozen global deadline has expired')
 require(0<max_seconds<=300,'Cooperative profiling budget must be 0..300 seconds')
 methods=Path(methods);spec=read(plan)
 require(spec['source_sha256']==sha(__file__),'Profiler source differs from protocol')
 tests=Path(__file__).resolve().parents[1]/'tests/test_v2_archive_latency.py'
 require(spec['tests_sha256']==sha(tests),'Profiler tests differ from protocol')
 require(spec['source_freeze_sha256']==sha(source_freeze),'Source freeze differs from protocol')
 sf=read(source_freeze)
 for path,digest in sf['sha256'].items():
  if Path(path).suffix=='.py':require(sha(path)==digest,'Frozen scientific source differs')
 mf=read(methods/'METHODS_FROZEN.json');ts=read(methods/'training-input-freeze.json')
 for entry in mf['files']:require(sha(entry['path'])==entry['sha256'],'Fitted methods hash differs')
 pins={entry['path']:entry['sha256'] for entry in ts['files']}
 for path in [Path(rows_path),*map(Path,record_paths)]:require(str(path.resolve()) in pins and sha(path)==pins[str(path.resolve())],'Archive input not pinned in training freeze')
 require(Path(rows_path).name in ('archive-p4-rows.jsonl','partial-archive-p4-rows.jsonl','archive-partial-p4-rows.jsonl','archive-p4-partial-rows.jsonl'),'Only explicit archive rows allowed')
 import joblib
 from .dataset import read_jsonl
 from . import cheap_eval as old
 from .v2_inputs import render
 from .v2_features import tabular_features
 from .v2_legacy_rules import evaluate
 rows=list(read_jsonl(rows_path));require(len(rows)==176 and all('label' in r for r in rows),'Expected known 176-row archive population')
 records,schemas=old.load_records(record_paths);lookup={r['prefix_id']:r for r in rows}
 deadline=time.monotonic()+min(max_seconds,max(0,global_deadline-time.time()));profiles=[];micro=[];selections={s:sample_ids(list(lookup),s) for s in (17,29,43)}
 entries=read(methods/'models.json');processed=set()
 for entry in entries:
  key=(entry['seed'],entry['config']);processed.add(key)
  eligible=[pid for pid in lookup if all((r:=records.get((pid,b))) is not None and r['status']=='OK' and sorted(r['features'])==ts['feature_schemas'][b] for b in entry['blocks'])]
  ids=sample_ids(eligible,entry['seed']);vals=[];prep=[];sources=[];failures=[]
  fitted=None
  if time.monotonic()<deadline and ids:
   modelpath=methods/'models'/entry['filename'];require(sha(modelpath)==entry['sha256'],'Serialized model hash differs from models metadata')
   fitted=joblib.load(modelpath);fitted.predict([lookup[ids[0]]],records)
  for pid in ids:
   if time.monotonic()>=deadline or fitted is None:break
   row=lookup[pid]
   try:
    start=time.perf_counter();fitted.x([row],records);prep.append((time.perf_counter()-start)*1000)
    start=time.perf_counter();prediction=fitted.predict([row],records);elapsed=(time.perf_counter()-start)*1000
    if len(prediction)!=1 or prediction[0] is None or not math.isfinite(prediction[0]):raise ValueError('UNKNOWN prediction in known-only timing sample')
    vals.append(elapsed)
    costs=[old.latency(records.get((pid,b))) for b in entry['blocks']]
    sources.append(None if any(v is None or not math.isfinite(v) for v in costs) else sum(costs))
   except Exception as exc:failures.append(type(exc).__name__)
  reconstructed=[v+c for v,c in zip(vals,sources) if c is not None]
  profiles.append(dict(seed=entry['seed'],config=entry['config'],kind=entry['kind'],status='OK' if ids and len(vals)==len(ids) else 'INCOMPLETE',requested_n=len(ids),eligible_archive_n=len(eligible),sample_prefix_ids=ids,
   warm_single_row_prediction=stats(vals),pure_feature_matrix_preparation=stats(prep),cached_source_extraction=stats([v for v in sources if v is not None]),
   reconstructed_eager_path_excluding_rules=stats(reconstructed),failures=failures,memory='Not measured per model; do not infer from process-envelope peaks'))
 for seed,ids in selections.items():
  for op in ('render','tabular','R1','R2'):
   vals=[];failures=[]
   for pid in ids:
    if time.monotonic()>=deadline:break
    common=lookup[pid]['canonical'];start=time.perf_counter()
    try:
     if op=='render':render(common)
     elif op=='tabular':tabular_features(common)
     else:evaluate(common,method=op)
     vals.append((time.perf_counter()-start)*1000)
    except Exception as exc:failures.append(type(exc).__name__)
   micro.append(dict(seed=seed,operation=op,status='OK' if ids and len(vals)==len(ids) else 'INCOMPLETE',requested_n=len(ids),timing=stats(vals),failures=failures))
 result=dict(version=VERSION,scope='Measured archive-only warm singleton ML prediction; no hidden observations or labels accessed',
  protocol_sha256=sha(plan),methods_freeze_sha256=sha(methods/'METHODS_FROZEN.json'),source_freeze_sha256=sha(source_freeze),
  profiles=profiles,microprofiles=micro,complete=all(r['status']=='OK' for r in profiles+micro),
  budget_note='Cooperative soft budget; individual model load/predict may overrun the last check; caller must enforce hard process timeout if required. No deadline extension.',note='Cached source feature times plus singleton decision times reconstruct an eager serial path; not live FinBot. Source views may share inference; no zero cost for missing source timings. No per-model memory measurement.')
 write(output,result);return result

def main():
 p=argparse.ArgumentParser();p.add_argument('phase',choices=('freeze','run'));p.add_argument('--plan',type=Path,required=True);p.add_argument('--source-freeze',type=Path,required=True)
 p.add_argument('--authorization-plan',type=Path);p.add_argument('--authorization-sha');p.add_argument('--completion',type=Path);p.add_argument('--methods',type=Path);p.add_argument('--rows',type=Path);p.add_argument('--records',type=Path,nargs='+');p.add_argument('--output',type=Path);p.add_argument('--max-seconds',type=float,default=300)
 a=p.parse_args()
 if a.phase=='freeze':freeze(a.plan,a.source_freeze)
 else:run(a.methods,a.rows,a.records,a.source_freeze,a.plan,a.output,a.max_seconds,completion=a.completion,authorization_plan=a.authorization_plan,authorization_sha=a.authorization_sha)
if __name__=='__main__':main()
