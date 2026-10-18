"""Exact independent question inputs, serial FP32 forwards, bounded Metal cache."""
from __future__ import annotations
import hashlib,time
from pathlib import Path
from .secjev4b import SecJev4BScorer
from .secjev import SecJevScorer,canonical_hash

class SecJev4BMicrobatchScorer(SecJev4BScorer):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs)
  self.metadata.update(base_scorer_sha256=self.metadata['scorer_sha256'],scorer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),question_microbatch_size=1,cache_policy='empty_cache_between_questions_and_after_request',numerical_reference_question_batch_size=4)
  self.fingerprint=canonical_hash({k:v for k,v in self.metadata.items() if k!='model_load_ms'})
 def score(self,payload):
  started=time.perf_counter();distributions={};counts={'questions':{},'model_rows_total':0};memory={};tokenize=compute=queue=cleanup=0.;error=None
  for qid,question in payload['questions'].items():
   result=SecJevScorer.score(self,{'state':payload['state'],'questions':{qid:question}})
   for key,value in result.get('memory',{}).items():memory[key]=max(memory.get(key,0),value)
   timing=result['timing_ms'];tokenize+=timing.get('tokenize',0);compute+=timing.get('compute',0);queue+=timing.get('queue',0)
   tc=result.get('token_counts',{});counts['state']=tc.get('state',counts.get('state',0));counts['questions'].update(tc.get('questions',{}));counts['model_rows_total']+=tc.get('model_rows_total',0)
   began=time.perf_counter()
   if self.device=='mps':self.torch.mps.empty_cache();self.torch.mps.synchronize()
   cleanup+=(time.perf_counter()-began)*1000
   if result['status']!='OK':error=f'{qid}: {result.get("error")}';break
   distributions.update(result['probabilities'])
  return {'status':'UNKNOWN' if error else 'OK','probabilities':{} if error else distributions,'timing_ms':{'tokenize':tokenize,'compute':compute,'total':(time.perf_counter()-started)*1000,'queue':queue,'cleanup':cleanup},'model_metadata':self.metadata,'token_counts':counts,'memory':memory,'error':error}
