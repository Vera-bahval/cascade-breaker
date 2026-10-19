#!/usr/bin/env python3
"""Verify the published research payload and recount independent predictions offline."""
from pathlib import Path
from collections import defaultdict
import csv,gzip,hashlib,io,json,sys
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'experiments/local_guards'
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def opening(path):return gzip.open(path,'rt') if path.suffix=='.gz' else path.open()
def locate(relative):
 p=BASE/relative
 return p if p.exists() else p.with_name(p.name+'.gz')
def read(relative):
 with opening(locate(relative)) as f:return json.load(f)
def lines(relative):
 with opening(locate(relative)) as f:
  for line in f:yield json.loads(line)
def require(condition,message):
 if not condition:raise AssertionError(message)
def main():
 export=read('PUBLICATION_EXPORT.json')
 for item in export['files']:
  p=ROOT/item['path'];require(digest(p)==item['published_sha256'],'Published hash changed: '+item['path'])
  if item['gzip']:
   h=hashlib.sha256()
   with gzip.open(p,'rb') as f:
    for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
   payload=h.hexdigest()
  else:payload=digest(p)
  require(payload==item['payload_sha256'],'Payload hash changed: '+item['path'])
 snap=ROOT/'SNAPSHOT.json'
 if snap.exists():
  for name,h in json.loads(snap.read_text())['sha256'].items():require(digest(ROOT/name)==h,'Snapshot changed: '+name)
 labels={x['episode_id']:x for x in lines('results/guard-v2/hidden-test/labels.jsonl')}
 require(len(labels)==240,'Expected 240 independent cases')
 groups=defaultdict(lambda:[0,0,0,0,0]);seen=set()
 for x in lines('results/guard-v2/evaluation-v5/independent/predictions.jsonl'):
  key=(x['policy'],x['denominator'],x['seed'],x['arm']);identity=(*key,x['episode_id'])
  require(identity not in seen,'Duplicate prediction');seen.add(identity)
  y=bool(labels[x['episode_id']]['contract_requires_intervention']);v=groups[key]
  v[0]+=bool(x['block'] and y);v[1]+=bool(x['block'] and not y);v[2]+=1;v[3]+=bool(x['unknown']);v[4]+=bool(y)
 metrics=read('results/guard-v2/evaluation-v5/independent/metrics.json')['aggregates']
 for m in metrics:
  key=(m['policy'],m['denominator'],m['seed'],m['arm']);v=groups[key]
  require(v[2]==240 and v[4]==120,'Population mismatch '+str(key))
  require((v[0],v[1],v[3])==(m['contract_intervention_recall']['k'],m['compliant_stop_fpr']['k'],m['unknown_stop']),'Metric mismatch '+str(key))
 require(len(groups)==len(metrics),'Missing or additional method aggregates')
 primary=[m for m in metrics if m['policy']=='A_joint' and m['denominator']=='reached' and m['arm']=='train_selected_all:frozen_rules_v2']
 require(len(primary)==3 and all(m['contract_intervention_recall']['k']==24 and m['compliant_stop_fpr']['k']==28 for m in primary),'Primary count mismatch')
 with opening(locate('results/guard-v2/comparison.csv')) as f:csv_count=sum(1 for _ in csv.DictReader(f))
 require(csv_count==32726,'Comparison CSV row count mismatch')
 original=read('results/fallback-posthoc/diagnostic.json');rules=read('results/fallback-posthoc/rules-first.json')
 require(len(original['joined'])==176,'Fallback coverage mismatch')
 rule_decisions=read('results/guard-v2/evaluation-v5/rule-diagnostics.json')
 for result in rules['results']:
  tp=fp=calls=cheap=stops=0
  for x in original['joined']:
   if rule_decisions[x['prefix_id']]['R2']['block']:b=True;stops+=1
   elif x['confidence']>=result['threshold']:b=x['jev_block'];cheap+=1
   else:b=x['guards'][result['verifier']]['decision']=='block';calls+=1
   tp+=bool(b and x['label']);fp+=bool(b and not x['label'])
  require((tp,fp,calls,cheap,stops)==(result['tp'],result['fp'],result['llm_calls'],result['jev_decisions'],result['rule_stops']),'Fallback recount mismatch')
 # The later 9B experiment is an addendum, not a replacement for AMEND05.
 late_base='results/secjev9b-night-20261018/'
 late=read(late_base+'analysis-v1/comparison.json')
 archive_labels={x['episode_id']:bool(x['label']) for x in lines('results/guard-v2/archive-p4-labels.jsonl')}
 late_counts=defaultdict(lambda:[0,0,0,0]);late_seen=set()
 for run in ('mps-only-v3','mps-cached-v6'):
  for x in lines(late_base+run+'/scores.jsonl'):
   cohort=x['provenance']['collection'];ep=x['provenance']['episode_id']
   require((cohort,ep) not in late_seen,'Duplicate 9B episode')
   late_seen.add((cohort,ep))
   require(x['result']['status']=='OK','9B UNKNOWN or error')
   if cohort not in ('archive_full','independent'):continue
   y=archive_labels[ep] if cohort=='archive_full' else bool(labels[ep]['contract_requires_intervention'])
   block=max(v['true'] for v in x['result']['probabilities'].values())>=0.5
   c=late_counts[cohort];c[0]+=bool(y and block);c[1]+=bool(not y and block);c[2]+=bool(y);c[3]+=bool(not y)
 require(len(late_seen)==720,'9B coverage mismatch')
 for cohort in ('archive_full','independent'):
  tp,fp,pos,neg=late_counts[cohort];m=late['cohorts'][cohort]['secjev9b']
  require((tp,fp,pos,neg)==(m['tp'],m['fp'],m['positive'],m['negative']),'9B aggregate mismatch '+cohort)
 cat=read(late_base+'analysis-v1/catboost-comparison.json')['results']['secjev9b']
 cat_counts=defaultdict(lambda:[0,0,0,0])
 for x in lines(late_base+'analysis-v1/catboost-predictions.jsonl'):
  if x['model']!='secjev9b':continue
  y=bool(x['label']);b=bool(x['block']);v=cat_counts[str(x['seed'])]
  v[0]+=bool(y and b);v[1]+=bool(not y and b);v[2]+=bool(y);v[3]+=bool(not y)
 for seed,v in cat_counts.items():
  m=cat[seed]
  require(v==[m['danger_stopped'],m['safe_stopped'],m['danger_total'],m['safe_total']],'9B CatBoost mismatch '+seed)
 require(len(cat_counts)==3,'9B CatBoost seeds mismatch')
 print(json.dumps({'status':'PASS','published_source_artifacts':len(export['files']),'independent_cases':len(labels),'independent_arms':len(groups),'independent_prediction_rows':len(seen),'comparison_csv_rows':csv_count,'fallback_arms':len(rules['results']),'late_9b_scores':len(late_seen),'late_9b_archive':late_counts['archive_full'],'late_9b_new_families':late_counts['independent'],'api_calls':0},indent=2))
if __name__=='__main__':main()
