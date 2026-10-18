"""Cached raw64 posthoc comparison. No inference/fitting; raw labels score only."""
from __future__ import annotations
import argparse
import copy
import json
import math
import time
from collections import defaultdict
from pathlib import Path
import numpy as np
from .cheap_eval import (SEEDS, WRAPPERS, configs, config_name, primary_config,
    digest, dump, jsonl, finite, select_threshold, raw_metrics, probability_metrics, selection_rank)
from .dataset import read_jsonl


def decode_threshold(value):
    return math.inf if value is None or value == 'infinity' else float(value)


def redecide(records, threshold, wrapper, controls, policy):
    output=[]
    for row in records:
        result=copy.deepcopy(row)
        control=controls[(row['seed'],wrapper,row['prefix_id'])]
        if row.get('cut_seq') != control.get('cut_seq'):
            raise ValueError('Control cutoff mismatch')
        p=row['probability'] if row['learned_component'] else row['scalar_risk']
        unknown=p is None or not math.isfinite(p)
        rule=bool(control['block'])
        result.update(arm=row['arm'].rsplit(':',1)[0]+':'+wrapper,
                      policy=policy,threshold=finite(threshold),unknown=unknown,
                      rule_stop=rule,block=bool(unknown or rule or p>=threshold))
        result['rule_wrapper_ms']=control.get('rule_wrapper_ms')
        parts=[result.get(k) for k in ('inference_cost_ms','decision_model_ms','rule_wrapper_ms')]
        result['reconstructed_total_guard_ms']=sum(parts) if all(isinstance(v,(float,int)) for v in parts) else None
        output.append(result)
    return output


def source_paths(base):
    root=base/'results/cheap-guards'
    return [Path(__file__),base/'cascade_guard/cheap_policy_comparison.py',
        base/'cascade_guard/cheap_eval.py',base/'cascade_guard/night_ml.py',
        base/'data/prefixes.jsonl',base/'data/outcomes.jsonl',
        root/'evaluation/input-freeze.json',root/'evaluation/predictions.jsonl',
        root/'evaluation/raw64/predictions.jsonl',root/'evaluation/raw64/calibration.json',
        root/'evaluation/raw64/metrics.json',root/'evaluation/raw64/unsupported.json',
        root/'raw64/labels.jsonl']


def freeze(base, output):
    output.mkdir(parents=True,exist_ok=True)
    plan={'created_unix':time.time(),'role':'POSTHOC known authored raw64 stress, not independent validation',
        'policies':['A_joint','B_independent','C_lowest'],
        'threshold_grid':'Exact unique finite archive OOF score values plus infinity; >= comparator',
        'threshold_selection':'Full-archive 3-fold grouped OOF probabilities only; source raw labels never used',
        'selection':'Archive OOF final-system feasibility, harm recall, FP, median inference latency, lexical config. Full winner and raw-supported winner separately.',
        'no_new_inference':True,'no_new_fits':True,
        'legacy_reproduction':'Recompute legacy A calibration and all prior raw prediction decisions before new scoring',
        'unsupported':'J checkpoints and tabular schemas absent; 4B raw scores absent. No imputation.',
        'source_files':{str(p):digest(p) for p in source_paths(base)}}
    target=output/'input-freeze.json'
    if target.exists():
        saved=json.loads(target.read_text())
        if saved['source_files']!=plan['source_files']:raise ValueError('Frozen source/input changed')
        return saved
    dump(target,plan)
    return plan


def run(base, output):
    from .cheap_policy_comparison import POLICIES, choose_from_curves, exact_curve, policy_rank
    plan=json.loads((output/'input-freeze.json').read_text())
    for path,expected in plan['source_files'].items():
        if digest(path)!=expected:raise ValueError('Frozen source/input changed: '+path)
    root=base/'results/cheap-guards'
    archive=read_jsonl(root/'evaluation/predictions.jsonl')
    oldraw=read_jsonl(root/'evaluation/raw64/predictions.jsonl')
    oldcal=json.loads((root/'evaluation/raw64/calibration.json').read_text())
    lookup_oldcal={(r['seed'],r['arm']):r for r in oldcal}
    ids={p['prefix_id'] for p in archive}
    rows=[r for r in read_jsonl(base/'data/prefixes.jsonl') if r['prefix_id'] in ids]
    outcomes=[o for o in read_jsonl(base/'data/outcomes.jsonl') if not o.get('legacy_ambiguous')]
    assert len(rows)==176 and len(outcomes)==214
    available=json.loads((root/'evaluation/input-freeze.json').read_text())['available_complete_blocks']
    cfgs=configs(available)
    archives=defaultdict(list); raws=defaultdict(list)
    for row in archive:archives[(row['seed'],row['arm'])].append(row)
    for row in oldraw:raws[(row['seed'],row['arm'])].append(row)
    wrappers={'none':'NoDefense','original_rules':'R1','frozen_rules_v2':'R2'}
    archiveflags={(seed,w):{r['prefix_id']:r['block'] for r in archives[(seed,control)]}
                  for seed in SEEDS for w,control in wrappers.items()}
    rawcontrols={(r['seed'],w,r['prefix_id']):r for w,control in wrappers.items() for r in oldraw if r['arm']==control}
    predictions=[];calibrations=[];unsupported=[];repro=[]
    for seed in SEEDS:
        legacy_candidates=defaultdict(list)
        candidates=defaultdict(list)
        supported_candidates=defaultdict(list)
        for cfg in cfgs:
            name=config_name(cfg)
            archived=archives[(seed,name+':none')]
            index={r['prefix_id']:r for r in archived}
            if len(index)!=176 or any(r['fit_failed'] for r in archived):raise ValueError('Incomplete cached OOF '+name)
            probs=[index[r['prefix_id']]['probability' if cfg[0]!='scalar' else 'scalar_risk'] for r in rows]
            cached=raws.get((seed,name+':none'),[])
            supported=len(cached)==64 and not any(r['fit_failed'] for r in cached)
            reason=lookup_oldcal[(seed,name+':none')].get('unsupported_reason')
            latency=float(np.median([r['inference_cost_ms'] for r in archived]))
            standalone_curve=exact_curve(rows,probs,outcomes,{})
            for wrapper in WRAPPERS:
                arm=name+':'+wrapper
                threshold,cal,_=select_threshold(rows,probs,outcomes,archiveflags[(seed,wrapper)])
                expected=lookup_oldcal[(seed,arm)]
                if threshold!=decode_threshold(expected['threshold']) or cal['metrics']!=expected['calibration']['metrics']:
                    raise AssertionError('Legacy threshold/calibration mismatch '+arm)
                if supported:
                    recomputed=redecide(cached,threshold,wrapper,rawcontrols,'legacy_A')
                    old={r['prefix_id']:r for r in raws[(seed,arm)]}
                    if len(old)!=64 or any(any(r[k]!=old[r['prefix_id']][k] for k in ('block','unknown','rule_stop')) for r in recomputed):
                        raise AssertionError('Legacy raw decisions mismatch '+arm)
                repro.append({'seed':seed,'arm':arm,'calibration_exact':True,'decisions_exact':supported,'raw_supported':supported})
                if primary_config(cfg):
                    legacy_candidates[wrapper].append((selection_rank(cfg,cal,latency),name,supported))
                joint_curve=standalone_curve if wrapper=='none' else exact_curve(rows,probs,outcomes,archiveflags[(seed,wrapper)])
                for policy in POLICIES:
                    t,c=choose_from_curves(joint_curve,standalone_curve,policy)
                    rr=redecide(cached,t,wrapper,rawcontrols,policy) if supported else []
                    record={'seed':seed,'arm':arm,'policy':policy,'threshold':finite(t),'calibration':c,
                            'raw_supported':supported,'unsupported_reason':reason,'calibration_source':'full archive grouped OOF only'}
                    calibrations.append(record)
                    predictions.extend(rr)
                    if not supported:unsupported.append({'seed':seed,'arm':arm,'policy':policy,'reason':reason})
                    if primary_config(cfg):
                        rank=policy_rank(name,c,latency)
                        candidate=(rank,name,record,rr,supported,reason)
                        candidates[(policy,wrapper)].append(candidate)
                        if supported:supported_candidates[(policy,wrapper)].append(candidate)
        for kind in ('train_selected_combo','train_selected_raw_supported_combo'):
            for wrapper,values in legacy_candidates.items():
                values=[v for v in values if v[2]] if kind.endswith('raw_supported_combo') else values
                _,name,supported=min(values,key=lambda x:x[0])
                expected=lookup_oldcal[(seed,kind+':'+wrapper)]
                if expected['selected_config']!=name:raise AssertionError('Legacy archive candidate selection mismatch')
                if supported:
                    selected=raws[(seed,kind+':'+wrapper)]
                    original={r['prefix_id']:r for r in raws[(seed,name+':'+wrapper)]}
                    if len(selected)!=64 or any(r['block']!=original[r['prefix_id']]['block'] for r in selected):raise AssertionError('Legacy selected raw decisions mismatch')
                repro.append({'seed':seed,'arm':kind+':'+wrapper,'calibration_exact':True,'decisions_exact':supported,'raw_supported':supported})
        for kind,collection in [('train_selected_combo',candidates),('train_selected_raw_supported_combo',supported_candidates)]:
            for (policy,wrapper),values in collection.items():
                _,name,cal,rr,supported,reason=min(values,key=lambda x:x[0])
                arm=kind+('_B2' if policy=='B_independent' else '')+':'+wrapper
                calibrations.append(dict(cal,arm=arm,selected_config=name))
                if supported:predictions.extend([dict(r,arm=arm,selected_config=name) for r in rr])
                else:unsupported.append({'seed':seed,'arm':arm,'policy':policy,'selected_config':name,'reason':reason})
        for kind,collection in [('train_selected_Blegacy_combo',candidates),('train_selected_Blegacy_raw_supported_combo',supported_candidates)]:
            standalone=collection.get(('B_independent','none'),[])
            if standalone:
                winner=min(standalone,key=lambda x:x[0])[1]
                for wrapper in WRAPPERS:
                    chosen=next(c for c in collection[('B_independent',wrapper)] if c[1]==winner)
                    _,name,cal,rr,supported,reason=chosen
                    arm=kind+':'+wrapper
                    calibrations.append(dict(cal,arm=arm,selected_config=name,selection_scope='standalone component winner reused before final OR'))
                    if supported:predictions.extend([dict(r,arm=arm,selected_config=name) for r in rr])
                    else:unsupported.append({'seed':seed,'arm':arm,'policy':'B_independent','selected_config':name,'reason':reason})
        for policy in POLICIES:
            for control in wrappers.values():
                predictions.extend([dict(r,policy=policy) for r in raws[(seed,control)]])
    # First access to raw labels: every threshold/config/decision above is frozen.
    labels=read_jsonl(root/'raw64/labels.jsonl')
    grouped=defaultdict(list)
    for row in predictions:grouped[(row['policy'],row['seed'],row['arm'])].append(row)
    metrics=[]
    labelmap={r['prefix_id']:r['label'] for r in labels}
    for (policy,seed,arm),pp in grouped.items():
        if len(pp)!=64 or len({r['prefix_id'] for r in pp})!=64:raise ValueError('Raw population incomplete')
        metric=raw_metrics(pp,labels)
        metric.update(policy=policy,seed=seed,arm=arm,complete=True,label_use='descriptive only after all archive selection')
        if pp[0]['learned_component']:
            metric.update(probability_metrics([dict(r,label=labelmap[r['prefix_id']]) for r in pp],pp))
        metrics.append(metric)
    unsupported.append({'family':'matched_4B','reason':'No existing raw64 4B final-model scores; no new inference/fits requested for saved-score comparison'})
    jsonl(output/'predictions.jsonl',predictions)
    dump(output/'calibration.json',calibrations)
    dump(output/'metrics.json',{'scope':plan['role'],'aggregates':metrics})
    dump(output/'unsupported.json',unsupported)
    dump(output/'legacy-reproduction.json',{'all_exact':True,'calibrations':len(repro),'supported_decision_sets':sum(r['raw_supported'] for r in repro),'checks':repro})
    dump(output/'manifest.json',{'status':'COMPLETE_SUPPORTED_CACHED_METHODS','input_freeze_sha256':digest(output/'input-freeze.json'),
        'no_new_fits':True,'no_new_inference':True,'no_raw_label_selection':True,
        'predictions':len(predictions),'aggregates':len(metrics),'output_hashes':{p.name:digest(p) for p in output.glob('*') if p.is_file() and p.name!='manifest.json'}})
    print(json.dumps({'predictions':len(predictions),'aggregates':len(metrics),'legacy_exact':True}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=Path('experiments/local_guards'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--freeze-only',action='store_true')
    args=parser.parse_args();output=args.output or args.base/'results/policy-comparison/raw64'
    if args.freeze_only:freeze(args.base,output)
    else:run(args.base,output)

if __name__=='__main__':main()
