"""Descriptive post-hoc P4 replay; no fitting, threshold selection or API calls."""
from pathlib import Path
import gzip,hashlib,json,statistics
BASE=Path(__file__).resolve().parents[1]
ARCHIVE=BASE/'data/archive/shadow-main.jsonl.gz'
ROWS=BASE/'results/guard-v2/inputs-v5/archive-p4-rows.jsonl'
SCORES=BASE/'results/guard-v2/jev-v5/08/archive-all-scores.jsonl'
OUT=BASE/'results/fallback-posthoc/diagnostic.json'
def load(p):return [json.loads(l) for l in p.open()]
def counts(labels,blocks):
 return {'tp':sum(y==1 and b for y,b in zip(labels,blocks)), 'fp':sum(y==0 and b for y,b in zip(labels,blocks)), 'positive_n':sum(labels),'negative_n':len(labels)-sum(labels)}
def main():
 with gzip.open(ARCHIVE,'rt') as f:runs={x['run_id']:x for x in map(json.loads,f)}
 rows=load(ROWS);scores=load(SCORES);by={x['prefix_id']:x for x in scores};assert len(by)==len(scores)
 joined=[]
 for row in rows:
  run=runs[row['episode_id']];s=by[row['prefix_id']];assert s['status']=='OK' and not s['unknown']
  events=[e for e in run['steps'] if e.get('kind')=='guard' and e.get('context_seq')==row['cut_seq']]
  v={e['verifier']:e for e in events};assert len(v)==len(events) and {'V3','V4'}<=v.keys()
  context=[e for e in run['steps'] if e.get('seq')==row['cut_seq']];assert len(context)==1 and context[0]['kind']=='guard_context' and context[0]['point']==row['control_point']
  ps=list(s['probabilities'].values());assert len(ps)==4 and all(0<=p<=1 for p in ps)
  for k in ('V3','V4'):assert v[k]['decision'] in ('allow','block')
  joined.append({'prefix_id':row['prefix_id'],'episode_id':row['episode_id'],'cut_seq':row['cut_seq'],'label':row['label'],'confidence':min(max(p,1-p) for p in ps),'jev_block':any(p>=.5 for p in ps),'jev_ms':s['latency_ms'],'guards':{k:{z:v[k][z] for z in ('decision','latency_ms','tokens_in','tokens_out','cost_usd')} for k in ('V3','V4')}})
 assert len(joined)==176 and len({x['episode_id'] for x in joined})==176
 labels=[x['label'] for x in joined];result=[]
 for k in ('V3','V4'):
  pure=[x['guards'][k]['decision']=='block' for x in joined];base_ms=[x['guards'][k]['latency_ms'] for x in joined]
  for tau in (.5,.7,.8,.9,.95,.99,1.01):
   fallback=[x['confidence']<tau for x in joined]
   blocks=[x['guards'][k]['decision']=='block' if f else x['jev_block'] for x,f in zip(joined,fallback)]
   serial=[x['jev_ms']+(x['guards'][k]['latency_ms'] if f else 0) for x,f in zip(joined,fallback)]
   result.append({'fallback_verifier':k,'threshold':tau,'fallback_n':sum(fallback),'cheap_decision_n':176-sum(fallback),**counts(labels,blocks),'errors_in_cheap_decisions':sum(not f and b!=bool(x['label']) for x,b,f in zip(joined,blocks,fallback)),'llm_baseline':counts(labels,pure),'logged_llm_baseline_mean_ms':statistics.mean(base_ms),'reconstructed_serial_mean_ms':statistics.mean(serial),'selected_logged_llm_cost_usd':sum(x['guards'][k]['cost_usd'] for x,f in zip(joined,fallback) if f),'all_logged_llm_cost_usd':sum(x['guards'][k]['cost_usd'] for x in joined)})
 doc={'status':'POSTHOC_DESCRIPTIVE_ONLY','decision_rule':'Four separate binary questions; confident if min_q max(p_q,1-p_q)>=threshold; confident BLOCK iff any p_q>=0.5, otherwise ALLOW; all uncertain cases use exact saved V3/V4 P4 decision. This semantic aggregation is an exploratory choice, not a validated payment-risk classifier.','limitations':['Archive development data, no independent performance claim or optimized threshold.','Jev and colleagues verifier have different evidence/prompts; this is a replay of these concrete components, not evidence-budget-matched benchmarking.','P4 only, first selected pre-transfer checkpoint per episode; not a full multi-checkpoint deployed guard policy.','Latency is reconstructed serial sum across different machines/times, not live end-to-end; Jev local monetary cost unknown.','No colleagues V3/V4 verdicts for new six-family independent cases.','No CatBoost risk calibration or new training in this diagnostic.'],'source_sha256':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ARCHIVE,ROWS,SCORES,Path(__file__))},'joined':joined,'results':result}
 if OUT.exists():raise FileExistsError(OUT)
 OUT.write_text(json.dumps(doc,indent=2)+'\n')
 for x in result:
  print(x['fallback_verifier'],x['threshold'],'fallback',x['fallback_n'],'TP/FP',x['tp'],x['fp'],'cheap_errors',x['errors_in_cheap_decisions'],'mean_ms',round(x['reconstructed_serial_mean_ms']), 'baseline_ms',round(x['logged_llm_baseline_mean_ms']))
if __name__=='__main__':main()
