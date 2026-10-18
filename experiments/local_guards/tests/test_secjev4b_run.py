import json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
from cascade_guard import secjev4b_run

class Fake:
 def __init__(self,*args):self.metadata={'model':'fake'};self.fingerprint='fake'
 def score(self,payload):return {'status':'OK','probabilities':{'q':{'false':.7,'true':.3}},'timing_ms':{'total':1.,'compute':.9},'model_metadata':self.metadata,'token_counts':{},'memory':{},'error':None}

def test_batch_normalized_and_resume():
 with tempfile.TemporaryDirectory() as directory:
  d=Path(directory);src=d/'inputs.jsonl';dst=d/'scores.jsonl'
  src.write_text(json.dumps({'prefix_id':'one','format':'plus_rationale','payload_hash':'hash','payload':{'state':{'a':1},'questions':{}}})+'\n')
  args=['x','--input',str(src),'--output',str(dst),'--device','mps','--mode','batch','--deadline-unix','9999999999']
  with patch.object(secjev4b_run,'SecJev4BScorer',Fake),patch.object(secjev4b_run,'SecJev4BMicrobatchScorer',Fake),patch.object(sys,'argv',args):secjev4b_run.main();secjev4b_run.main()
  records=[json.loads(x) for x in dst.read_text().splitlines()];assert len(records)==1;assert records[0]['probabilities']=={'q':.3};assert records[0]['format']=='plus_rationale';assert json.loads(dst.with_suffix('.manifest.json').read_text())['skipped']==1

def test_probe_three_repeats_six_payloads_and_parity():
 with tempfile.TemporaryDirectory() as directory:
  d=Path(directory);src=d/'inputs.jsonl';cpu=d/'cpu.json';mps=d/'mps.json'
  src.write_text(''.join(json.dumps({'prefix_id':str(i),'format':'plus_rationale','payload_hash':str(i),'payload':{'state':{'a':'a'*i},'questions':{}}})+'\n' for i in range(6)))
  def run(device,path,ref=None):
   args=['x','--input',str(src),'--output',str(path),'--device',device,'--mode','probe','--deadline-unix','9999999999']+(['--reference',str(ref)] if ref else [])
   with patch.object(secjev4b_run,'SecJev4BScorer',Fake),patch.object(secjev4b_run,'SecJev4BMicrobatchScorer',Fake),patch.object(sys,'argv',args):secjev4b_run.main()
  run('cpu',cpu);run('mps',mps,cpu);out=json.loads(mps.read_text());assert out['passed'];assert len(out['cases'])==6;assert all(len(r['results'])==3 for r in out['cases'])

def test_microbatch_aggregates_four_independent_questions_and_cleanup():
 from cascade_guard.secjev4b_microbatch import SecJev4BMicrobatchScorer
 from cascade_guard.secjev import SecJevScorer
 from types import SimpleNamespace
 obj=object.__new__(SecJev4BMicrobatchScorer);obj.device='mps';obj.metadata={'question_microbatch_size':1};cleanups=[]
 obj.torch=SimpleNamespace(mps=SimpleNamespace(empty_cache=lambda:cleanups.append(1),synchronize=lambda:None))
 seen=[]
 def result(self,payload):
  seen.append(payload);qid=next(iter(payload['questions']));return {'status':'OK','probabilities':{qid:{'false':.7,'true':.3}},'timing_ms':{'tokenize':1,'compute':2,'queue':0},'token_counts':{'state':9,'questions':{qid:{'state_plus_branch':12}},'model_rows_total':12},'memory':{'mps_driver_bytes':20+len(seen)},'error':None}
 payload={'state':{'x':1},'questions':{'q1':{},'q2':{},'q3':{},'q4':{}}}
 with patch.object(SecJevScorer,'score',result):out=obj.score(payload)
 assert out['status']=='OK';assert len(seen)==4;assert len(cleanups)==4;assert all(len(p['questions'])==1 for p in seen)
 assert out['timing_ms']['compute']==8;assert out['token_counts']['model_rows_total']==48;assert out['memory']['mps_driver_bytes']==24;assert all(abs(sum(p.values())-1)<1e-8 for p in out['probabilities'].values())

def test_microbatch_unknown_hides_partial_probabilities_and_cleans_up():
 from cascade_guard.secjev4b_microbatch import SecJev4BMicrobatchScorer
 from cascade_guard.secjev import SecJevScorer
 from types import SimpleNamespace
 obj=object.__new__(SecJev4BMicrobatchScorer);obj.device='mps';obj.metadata={};cleanups=[];obj.torch=SimpleNamespace(mps=SimpleNamespace(empty_cache=lambda:cleanups.append(1),synchronize=lambda:None))
 def bad(self,payload):return {'status':'UNKNOWN','probabilities':{},'timing_ms':{'total':1,'compute':0},'error':'overflow'}
 with patch.object(SecJevScorer,'score',bad):out=obj.score({'state':{},'questions':{'q1':{},'q2':{}}})
 assert out['status']=='UNKNOWN';assert out['probabilities']=={};assert len(cleanups)==1;assert 'q1: overflow'==out['error']
