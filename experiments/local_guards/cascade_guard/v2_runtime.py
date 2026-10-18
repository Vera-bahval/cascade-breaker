"""Corrected NLI local-evidence adapter; pinned weights and serial runtime reuse.

No experiment labels, outcome files or test-set fitting are imported here.
"""
from __future__ import annotations
import argparse
import json
import time
import math
from collections import OrderedDict
from pathlib import Path
from .cheap_nli import NLIAdapter, pair_windows, MODELS
from .cheap_runtime import run_serial
from .v2_inputs import FIXED_CLAIMS

VERSION='guard-nli-local-evidence-v2'
SANITY=(
 ('Fraud review has been completed.', 'Fraud review has been completed.', 'entailment'),
 ('Fraud review has not been completed.', 'Fraud review has been completed.', 'contradiction'),
 ('The invoice describes replacement chairs.', 'Fraud review has been completed.', 'neutral'),
 ('Policy permits automatic payments below 10000. The proposed payment amount is 2000.', 'The proposed payment is below the automatic payment limit.', 'entailment'),
)


def aggregate_v2(raw, block):
 labels=('entailment','contradiction','neutral') if block=='N' else ('supported','unsupported')
 support='entailment' if block=='N' else 'supported'
 features={};fixed_support=[]
 for variant in ('local','full'):
  for claim_id,_ in FIXED_CLAIMS:
   items=[r for r in raw if r['claim_id']==claim_id and r['source_id']==variant]
   values=[w['probabilities'] for r in items for w in r['windows'] if r['status']=='OK']
   features[f'{variant}.{claim_id}.missing']=int(not values)
   for label in labels:
    nums=[v[label] for v in values]
    features[f'{variant}.{claim_id}.{label}.max']=max(nums,default=-1.)
    features[f'{variant}.{claim_id}.{label}.mean']=sum(nums)/len(nums) if nums else -1.
   if variant=='local' and values:fixed_support.append(max(v[support] for v in values))
 for source in ('trusted_combined','untrusted_premise'):
  items=[r for r in raw if not r['fixed'] and r['source_id']==source]
  values=[w['probabilities'] for r in items for w in r['windows'] if r['status']=='OK']
  features[f'explanation.{source}.missing']=int(not values)
  for label in labels:
   nums=[v[label] for v in values]
   features[f'explanation.{source}.{label}.max']=max(nums,default=-1.)
   features[f'explanation.{source}.{label}.mean']=sum(nums)/len(nums) if nums else -1.
 return {'status':'UNKNOWN' if any(r['status']!='OK' for r in raw) else 'OK','features':features,'scalar_risk':None if len(fixed_support)!=4 else max(1-x for x in fixed_support),'window_count':sum(len(r['windows']) for r in raw),'raw':raw}


class CorrectedNLIAdapter(NLIAdapter):
 def __init__(self,*args,**kwargs):
  load_start=time.perf_counter()
  super().__init__(*args,**kwargs)
  load_ms=(time.perf_counter()-load_start)*1000
  sanity_start=time.perf_counter();sanity=self.semantic_sanity();sanity_ms=(time.perf_counter()-sanity_start)*1000
  self.model_metadata.update(adapter_version=VERSION,evidence_selection='fixed claim scope, same renderer and policy across all collections',support_aggregation='maximum window support; explicit contradiction retained independently',sanity=sanity,cold_weight_tokenizer_load_ms=load_ms,cpu_semantic_sanity_ms=sanity_ms,cold_load_field_semantics='run_serial cold_load includes adapter initialization and CPU semantic sanity')
  self.feature_template=aggregate_v2([],self.block)['features']
  self.batch_size=1;self.pair_cache=OrderedDict();self.last_compute_ms=0.

 def semantic_sanity(self):
  results=[]
  for premise,claim,expected in SANITY:
   plan=pair_windows(self.tokenizer,premise,claim,self.max_length)
   probabilities=self.infer_ids(plan['windows'][0]['input_ids'])[0]
   actual=max(probabilities,key=probabilities.get)
   target=expected if self.block=='N' else ('supported' if expected=='entailment' else 'unsupported')
   results.append({'premise':premise,'claim':claim,'expected':target,'actual':actual,'probabilities':probabilities,'passed':actual==target})
  return {'status':'PASS' if all(r['passed'] for r in results) else 'LIMITATION_DO_NOT_REMAP_LABELS','fixtures':results,'fixture_source':'frozen literal non-experiment examples; no hidden case accessed'}

 def infer_batch(self, sequences):
  import torch
  maximum=max(map(len,sequences));pad=self.tokenizer.pad_token_id
  if pad is None:raise ValueError('Batching requires explicit tokenizer padding token')
  ids=torch.full((len(sequences),maximum),pad,dtype=torch.long,device=self.device)
  mask=torch.zeros_like(ids)
  for index,sequence in enumerate(sequences):
   ids[index,:len(sequence)]=torch.tensor(sequence,dtype=torch.long,device=self.device);mask[index,:len(sequence)]=1
  with torch.inference_mode():
   values=self.model(input_ids=ids,attention_mask=mask).logits.softmax(dim=-1).float().cpu().tolist()
  if not all(math.isfinite(v) for row in values for v in row):raise ValueError('Nonfinite batched classifier output')
  return [{label:row[index] for index,label in self.labels.items()} for row in values]

 def score(self,record):
  payload=record['payload'];raw=[];pending=OrderedDict();requests=[]
  full=next(s['text'] for s in payload['trusted_sources'] if s['source_id']=='trusted_combined')
  for claim in payload['claims']:
   sources=(('local',payload['local_evidence'][claim['claim_id']]),('full',full)) if claim['fixed'] else (('trusted_combined',full),('untrusted_premise',payload['untrusted_premise']))
   for source_id,text in sources:
    plan=pair_windows(self.tokenizer,text,claim['text'],self.max_length)
    item={**claim,'source_id':source_id,'status':plan['status'],'premise_tokens':plan['premise_tokens'],'claim_tokens':plan['claim_tokens'],'windows':[]}
    if plan['status']!='OK':item['reason']=plan['reason']
    for window in plan['windows']:
     key=tuple(window['input_ids']);cached=key in self.pair_cache or key in pending
     target={'start_token':window['start_token'],'end_token':window['end_token'],'pair_tokens':len(key),'cache_hit':cached}
     item['windows'].append(target);requests.append((key,target))
     if key not in self.pair_cache:pending.setdefault(key,list(key))
    raw.append(item)
  compute_start=time.perf_counter();computed={};sequences=list(pending.items())
  for offset in range(0,len(sequences),self.batch_size):
   if getattr(self,'deadline_ts',float('inf'))<=time.time():raise TimeoutError('Runtime deadline')
   batch=sequences[offset:offset+self.batch_size]
   values=self.infer_batch([sequence for _,sequence in batch]) if self.batch_size>1 else [self.infer_ids(sequence)[0] for _,sequence in batch]
   computed.update((key,prob) for (key,_),prob in zip(batch,values))
  compute_ms=(time.perf_counter()-compute_start)*1000
  for key,target in requests:
   target['probabilities']=computed[key] if key in computed else self.pair_cache[key]
   if key in self.pair_cache:self.pair_cache.move_to_end(key)
  for key,value in computed.items():
   self.pair_cache[key]=value;self.pair_cache.move_to_end(key)
  while len(self.pair_cache)>4096:self.pair_cache.popitem(last=False)
  result=aggregate_v2(raw,self.block)
  result.update(timing_ms={'compute':compute_ms},pair_cache={'hits':sum(target['cache_hit'] for _,target in requests),'requested_windows':len(requests),'unique_forward_pairs':len(pending),'bound':4096,'scope':'exact token-pair probabilities; performance is observed cache-assisted'},batch_size=self.batch_size)
  return result


def probe_batched(adapter,examples):
 """Run uncached single-device gate, then real CPU batch1 vs MPS batch8."""
 import torch
 from .cheap_nli import probe_mps as original_probe
 result=original_probe(adapter,examples)
 if not result['passed']:return result
 sequences=[pair_windows(adapter.tokenizer,p,c,adapter.max_length)['windows'][0]['input_ids'] for p,c in examples]
 adapter.model.to('cpu');adapter.device='cpu'
 cpu=[[adapter.infer_ids(sequence)[0] for sequence in sequences] for _ in range(3)]
 adapter.model.to('mps');adapter.device='mps'
 probe={'cpu_batch_size':1,'candidate_batch_size':8,'repeats':3,'tolerance':1e-4,'max_delta':0.,'mps_aa_delta':0.,'argmax_changed':False,'passed':False,'cpu_repeats':cpu}
 try:
  mps=[adapter.infer_batch(sequences+sequences[:2]) for _ in range(3)]
  probe['mps_repeats']=mps
  for repeat in mps:
   for a,b in zip(cpu[0]+cpu[0][:2],repeat):
    probe['max_delta']=max(probe['max_delta'],max(abs(a[k]-b[k]) for k in a));probe['argmax_changed']|=max(a,key=a.get)!=max(b,key=b.get)
  for repeat in mps:
   for a,b in zip(mps[0],repeat):probe['mps_aa_delta']=max(probe['mps_aa_delta'],max(abs(a[k]-b[k]) for k in a))
  probe['passed']=probe['max_delta']<=1e-4 and probe['mps_aa_delta']<=1e-4 and not probe['argmax_changed']
 except Exception as exc:probe['reason']=f'{type(exc).__name__}: {exc}'
 adapter.batch_size=8 if probe['passed'] else 1
 adapter.model_metadata['batch_gate']=probe;adapter.model_metadata['selected_batch_size']=adapter.batch_size
 result['batch_gate']=probe
 return result


def create_adapter(model_id,revision,model_dir,device='cpu'):
 return CorrectedNLIAdapter(model_id,revision,Path(model_dir),device)


def main():
 parser=argparse.ArgumentParser()
 for key in ('inputs','output','model-dir','lock-path'):parser.add_argument('--'+key,type=Path,required=True)
 parser.add_argument('--block',choices=('N','M','G22','G86'),required=True)
 parser.add_argument('--deadline',required=True)
 parser.add_argument('--resource-lease',action='store_true')
 parser.add_argument('--mps-probe',action='store_true')
 parser.add_argument('--limit',type=int)
 args=parser.parse_args()
 if args.block in ('N','M'):
  model_id=next(k for k,v in MODELS.items() if v['block']==args.block);revision=MODELS[model_id]['revision'];factory='cascade_guard.v2_runtime:create_adapter'
 else:
  from .cheap_promptguard import MODEL_BLOCKS,OFFICIAL_CHECKPOINTS
  model_id=next(k for k,v in MODEL_BLOCKS.items() if v==args.block);revision=OFFICIAL_CHECKPOINTS[model_id]['revision'];factory='cascade_guard.cheap_promptguard:create_adapter'
 if args.block in ('N','M') and args.mps_probe:
  import cascade_guard.cheap_nli as legacy_nli
  original=legacy_nli.probe_mps
  def combined_probe(adapter,examples):
   legacy_nli.probe_mps=original
   try:return probe_batched(adapter,examples)
   finally:legacy_nli.probe_mps=combined_probe
  legacy_nli.probe_mps=combined_probe
 print(json.dumps(run_serial(args.inputs,args.output,factory,model_id,revision,args.model_dir,deadline=args.deadline,resource_lease=args.resource_lease,lock_path=args.lock_path,mps_probe=args.mps_probe,limit=args.limit)))

if __name__=='__main__':main()


def summarize_outputs(paths, output):
 """Report observed cache-assisted timings; never invent an uncached latency."""
 import statistics
 from collections import defaultdict,Counter
 groups=defaultdict(list)
 for path in paths:
  for line in Path(path).read_text().splitlines():
   if line.strip():
    row=json.loads(line);groups[(row['block'],row.get('provenance',{}).get('collection','unspecified'))].append(row)
 def quantile(values,p):
  values=sorted(values)
  if not values:return None
  position=(len(values)-1)*p;i=int(position);fraction=position-i
  return values[i]*(1-fraction)+values[min(i+1,len(values)-1)]*fraction
 stages=[]
 for (block,collection),rows in sorted(groups.items()):
  durations=[r['timing_ms']['total'] for r in rows]
  stages.append({'block':block,'collection':collection,'records':len(rows),'status_counts':dict(Counter(r['status'] for r in rows)),
   'p50_ms':quantile(durations,.5),'p95_ms':quantile(durations,.95),'cold_setup_ms':max(r['timing_ms'].get('cold_load',0) for r in rows),
   'max_rss_bytes':max(r.get('memory',{}).get('prefix_sampled_max',{}).get('rss_bytes',0) for r in rows),
   'max_mps_driver_bytes':max(r.get('memory',{}).get('prefix_sampled_max',{}).get('mps_driver_allocated_bytes',0) for r in rows),
   'model_revision':rows[0]['model_metadata']['revision'],'batch_size':rows[0].get('batch_size',1),
   'pair_cache_hits':sum(r.get('pair_cache',{}).get('hits',0) for r in rows),
   'unique_forward_pairs':sum(r.get('pair_cache',{}).get('unique_forward_pairs',0) for r in rows),
   'timing_semantics':'Observed serial cache-assisted path; cache lookup, tokenization, model computation and aggregation included. Not independent uncached per-case inference.'})
 result={'stages':stages}
 from .cheap_runtime import atomic_json
 atomic_json(output,result)
 return result
