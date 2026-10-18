"""Independent frozen-case evaluation. Never import this module into rule development."""
from __future__ import annotations
import argparse,copy,gzip,hashlib,importlib,json,statistics,time
from pathlib import Path
from .dataset import read_jsonl
from .rules import violations as old_violations


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def token_metadata(session):
    """Read only event token counters; no messages or credential material is retained."""
    counters=[]
    with Path(session).open() as f:
        for line in f:
            row=json.loads(line)
            if row.get('type')=='event_msg' and row.get('payload',{}).get('type')=='token_count':
                info=row['payload'].get('info') or {}
                if info.get('total_token_usage'):counters.append(info['total_token_usage'])
    if not counters:return {'available':False,'reason':'No cumulative session token counters.'}
    last=counters[-1]
    return {'available':True,'scope':'Dedicated agent session cumulative usage; input includes cached input, reasoning is subset of output.','input_tokens':last.get('input_tokens'), 'cached_input_tokens':last.get('cached_input_tokens'), 'output_tokens':last.get('output_tokens'), 'reasoning_output_tokens_subset':last.get('reasoning_output_tokens'), 'total_tokens':last.get('total_tokens'),'observed_counter_events':len(counters),'attribution':'Entire dedicated agent session from zero; session metadata uniquely identifies agent_path.'}

def rates(rows, expected_key='expected_block'):
    pos=[r for r in rows if r[expected_key]];neg=[r for r in rows if not r[expected_key]]
    tp=sum(r['block'] for r in pos);fp=sum(r['block'] for r in neg)
    return {'unsafe':len(pos),'safe':len(neg),'prevented':tp,'missed':len(pos)-tp,'false_stops':fp,'safe_completed':len(neg)-fp,'tpr':tp/len(pos) if pos else None,'fpr':fp/len(neg) if neg else None}


def evaluate(workspace:Path, frozen_source_sha256:str):
    root=workspace/'results/night-4b';private=root/'rules-private'
    freeze=json.loads((private/'freeze.json').read_text())
    assert digest(private/'cases.jsonl')==freeze['sha256'],'Hidden cases changed after freeze'
    source=workspace/'cascade_guard/rules_v2.py'
    assert digest(source)==frozen_source_sha256,'Rules source differs from declared frozen revision'
    marker=private/'evaluation-started.json'
    if marker.exists():raise RuntimeError('One-shot evaluation already started; no retuning/re-evaluation allowed')
    module=importlib.import_module('cascade_guard.rules_v2')
    marker.write_text(json.dumps({'source_sha256':frozen_source_sha256,'hidden_sha256':freeze['sha256'],'started_unix':time.time()},indent=2)+'\n')
    hidden=read_jsonl(private/'cases.jsonl');hidden_results={}
    for arm in ('original','rules_v2','rules_v2_strict_review'):
        result=[];durations=[]
        for case in hidden:
            st=copy.deepcopy(case['state']);call=old_violations if arm=='original' else lambda s:module.violations(s,strict_review=arm.endswith('strict_review'))
            issues=call(st)
            for _ in range(100):
                t=time.perf_counter_ns();call(st);durations.append((time.perf_counter_ns()-t)/1e6)
            result.append({'case_id':case['case_id'],'family':case['family'],'expected_block':case['expected_block'],'strict_review_expected_block':case['strict_review_expected_block'],'block':bool(issues),'violations':issues})
        hidden_results[arm]={'base_policy':rates(result),'strict_review_sensitivity':rates(result,'strict_review_expected_block'),'runtime_ms':{'p50':statistics.median(durations),'p95':sorted(durations)[int(.95*(len(durations)-1))]},'cases':result}
    prefixes=read_jsonl(workspace/'data/prefixes.jsonl');outcomes=[r for r in read_jsonl(workspace/'data/outcomes.jsonl') if not r['legacy_ambiguous']]
    with gzip.open(workspace/'data/archive/shadow-main.jsonl.gz','rt') as f:runs={r['run_id']:r for r in map(json.loads,f)}
    archive={}
    for arm in ('original','rules_v2','rules_v2_strict_review'):
        stopped=set();decisions=[];durations=[]
        for p in prefixes:
            if p['ambiguity'] or p['control_point']!='P4.finstripe__create_transfer':continue
            prior=[s for s in runs[p['episode_id']]['steps'] if s['seq']<p['cut_seq']]
            st=module.enrich_state(copy.deepcopy(p['state']),prior)
            t=time.perf_counter_ns()
            issues=old_violations(st) if arm=='original' else module.violations(st,strict_review=arm.endswith('strict_review'))
            durations.append((time.perf_counter_ns()-t)/1e6)
            if issues:stopped.add(p['episode_id'])
            decisions.append({'episode_id':p['episode_id'],'prefix_id':p['prefix_id'],'label':p['label'],'block':bool(issues),'violations':issues})
        harm=[r for r in outcomes if r['strict_harm']];safe=[r for r in outcomes if not r['strict_harm']];benign=[r for r in outcomes if r['source_benign']]
        archive[arm]={'episodes':len(outcomes),'p4_prefixes':len(decisions),'harmful_episodes':len(harm),'prevented_counterfactual':sum(r['episode_id'] in stopped for r in harm),'safe_continuation_episodes':len(safe),'safe_false_stops':sum(r['episode_id'] in stopped for r in safe),'source_benign_episodes':len(benign),'source_benign_stops':sum(r['episode_id'] in stopped for r in benign),'source_benign_compliant_payment':sum(r['baseline_paid'] and not r['strict_harm'] and r['episode_id'] not in stopped for r in benign),'runtime_ms':{'p50':statistics.median(durations),'p95':sorted(durations)[int(.95*(len(durations)-1))]},'decisions':decisions}
    output={'status':'COMPLETE','policy':'strict-hold-v1; successful review separately evaluated sensitivity','hidden_freeze':freeze,'rules_source_sha256':frozen_source_sha256,'hidden':hidden_results,'archive_retrospective':archive,'caveats':['Hidden synthetic cases are new crafted unit scenarios, not independent production episodes.','Archive results are counterfactual stops, not measured live prevention.','No development or tuning after hidden results were revealed.','Declared evidence flags derive from native/trusted provenance, not a model claim.']}
    (root/'rules-evaluation.json').write_text(json.dumps(output,indent=2)+'\n')
    return output


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workspace',type=Path,default=Path('.'));ap.add_argument('--frozen-source-sha256',required=True);args=ap.parse_args()
    out=evaluate(args.workspace,args.frozen_source_sha256)
    print(json.dumps({a:{k:v for k,v in r.items() if k!='decisions'} for a,r in out['archive_retrospective'].items()},indent=2))
if __name__=='__main__':main()
