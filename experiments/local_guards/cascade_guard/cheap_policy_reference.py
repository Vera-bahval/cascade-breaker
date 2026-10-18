"""Post-hoc policy comparison of cached SecJev 4B outputs; no inference APIs.

Fit reconstruction is needed because the historical reference did not save its
inner OOF scores. The reconstructed scores are saved before policy evaluation.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
import time
from collections import defaultdict
from pathlib import Path

from . import cheap_eval as e
from . import cheap_reference as ref

WRAPPERS = e.WRAPPERS


def inputs(base):
    primary = base/'results/cheap-guards/evaluation'
    outcomes = [o for o in e.read_jsonl(base/'data/outcomes.jsonl') if not o['legacy_ambiguous']]
    ids = {o['episode_id'] for o in outcomes}
    rows = [r for r in e.read_jsonl(base/'data/prefixes.jsonl') if r['episode_id'] in ids
            and r['control_point']=='P4.finstripe__create_transfer' and not r['already_harmful']]
    records, schemas = ref.load_cached(base/'results/night-4b/scores.jsonl',
        base/'results/night-4b/formats/inputs.jsonl', {r['prefix_id'] for r in rows})
    alloc = json.loads((primary/'fold-allocations.json').read_text())
    if alloc != e.allocation(outcomes, base/'results/night-4b/evaluation/folds.json'):
        raise ValueError('Fold allocations changed')
    assert len(rows)==176 and len(outcomes)==214
    return rows, outcomes, records, schemas, alloc


def collect(base, output):
    output.mkdir(parents=True, exist_ok=True)
    if (output/'cached-fits.jsonl').exists():
        raise ValueError('Cached fit generation already exists; do not overwrite')
    rows, outcomes, records, schemas, alloc = inputs(base)
    paths = [Path(__file__), Path(e.__file__), Path(ref.__file__),
        base/'cascade_guard/ml.py', base/'cascade_guard/night_ml.py',
        base/'cascade_guard/offline.py', base/'cascade_guard/rules.py', base/'cascade_guard/rules_v2.py',
        base/'data/prefixes.jsonl', base/'data/outcomes.jsonl', base/'data/archive/shadow-main.jsonl.gz',
        base/'results/night-4b/scores.jsonl', base/'results/night-4b/formats/inputs.jsonl',
        base/'results/cheap-guards/evaluation/fold-allocations.json',
        base/'results/cheap-guards/matched-reference/predictions.jsonl']
    freeze = {'phase':'FROZEN_BEFORE_RECONSTRUCTED_FITS', 'created_at':time.time(),
        'source_files':[{'path':str(p), 'sha256':e.digest(p)} for p in paths], 'record_files':[],
        'post_hoc':True, 'transformer_inference_calls':0, 'paid_api_calls':0,
        'heads':list(ref.HEADS), 'formats':list(ref.FORMATS), 'wrappers':list(WRAPPERS),
        'policies':{'A':'joint max inner TP, min FP, highest threshold',
                    'B':'component max TP/min FP/highest threshold; OR rules; select format on actual final inner system',
                    'C':'lowest finite joint feasible score threshold, infinity if needed'},
        'candidate_grid':'exact unique finite scores with >=; infinity means off; legacy A separately reconstructed',
        'target_episode_fpr':.05, 'catboost':e.CB_PARAMS,
        'allocation_sha256':e.stable_hash(alloc), 'schema_sha256':e.stable_hash(schemas),
        'motivation':'Historical cached 4B evaluation lacks inner curves; only tiny downstream CB fits repeated; no transformer inference.'}
    e.dump(output/'fit-input-freeze.json',freeze)
    e.dump(output/'fold-allocations.json',alloc)
    e.dump(output/'feature-schema.json',schemas)
    subset=lambda ids:[r for r in rows if r['episode_id'] in set(ids)]
    by_id={o['episode_id']:o for o in outcomes}
    fits=[];timings=[]
    for allocation in alloc:
        seed=allocation['seed'];fold=allocation['outer_fold']
        for head in ref.HEADS:
            for fmt in ref.FORMATS:
                cfg=ref.config(head,fmt);inner=[];stats=[]
                for j, split in enumerate(allocation['inner']):
                    train=subset(split['train_episode_ids']);test=subset(split['test_episode_ids'])
                    pp, tt=e.predict(cfg,train,test,seed+j,records,schemas)
                    inner.extend({'prefix_id':r['prefix_id'],'score':p,'inner_fold':j} for r,p in zip(test,pp))
                    stats.append(dict(tt,inner_fold=j))
                train=subset(allocation['train_episode_ids']);test=subset(allocation['test_episode_ids'])
                pp, tt=e.predict(cfg,train,test,seed,records,schemas,online=True)
                stats.append(dict(tt,phase='outer_final_fit'))
                if any(t['failure'] for t in stats):raise ValueError('Cached 4B reconstruction fit failed')
                fits.append({'seed':seed,'outer_fold':fold,'head':head,'format':fmt,'inner':inner,
                    'outer':[{'prefix_id':r['prefix_id'],'score':p} for r,p in zip(test,pp)],
                    'online_prediction_ms':tt['online_prediction_ms']})
                timings.append({'seed':seed,'outer_fold':fold,'head':head,'format':fmt,'fits':stats,
                    'wrapper_policy_reuse_count':9})
        print(json.dumps({'stage':'cached_fit','seed':seed,'outer_fold':fold}),flush=True)
    e.verify_frozen(freeze)
    e.jsonl(output/'cached-fits.jsonl',fits);e.dump(output/'timings.json',timings)
    # Legacy exact reproduction gates all new policy metric computation.
    flags,_=e.rule_flags(rows,base/'data/archive/shadow-main.jsonl.gz')
    original=e.read_jsonl(base/'results/cheap-guards/matched-reference/predictions.jsonl')
    lookup={(p['seed'],p['outer_fold'],p['arm'],p['prefix_id']):p for p in original if 'train_selected_format' not in p['arm']}
    row_by_id={r['prefix_id']:r for r in rows};allocation_by_id={(a['seed'],a['outer_fold']):a for a in alloc}
    checked=0;maxdelta=0.;decision_differences=[]
    for f in fits:
        allocation=allocation_by_id[(f['seed'],f['outer_fold'])]
        ir=[row_by_id[p['prefix_id']] for p in f['inner']];ip=[p['score'] for p in f['inner']]
        tr_out=[by_id[i] for i in allocation['train_episode_ids']]
        test=[row_by_id[p['prefix_id']] for p in f['outer']];op=[p['score'] for p in f['outer']]
        for wrapper in ref.WRAPPERS:
            threshold,_,_=e.select_threshold(ir,ip,tr_out,flags[wrapper])
            arm=f"{f['head']}:{f['format']}:{wrapper}"
            pp=e.prediction_records(test,op,threshold,flags[wrapper],f['seed'],f['outer_fold'],arm,f['head']!='scalar',False)
            for p in pp:
                old=lookup[(p['seed'],p['outer_fold'],arm,p['prefix_id'])]
                for key in ('probability','scalar_risk'):
                    if p[key] is not None:maxdelta=max(maxdelta,abs(p[key]-old[key]))
                if any(p[k]!=old[k] for k in ('threshold','block','unknown','rule_stop')):
                    decision_differences.append({k:p[k] for k in ('seed','outer_fold','arm','prefix_id','threshold','block')})
                checked+=1
    audit={'phase':'LEGACY_A_RECONSTRUCTION_BEFORE_NEW_POLICY_METRICS','checked_fixed_predictions':checked,
        'expected_fixed_predictions':3*176*9*2,'max_abs_score_delta':maxdelta,
        'decision_difference_count':len(decision_differences),'decision_differences':decision_differences,
        'cached_fits_sha256':e.digest(output/'cached-fits.jsonl'),'no_transformer_inference':True}
    e.dump(output/'legacy-reproduction.json',audit)
    if decision_differences or maxdelta!=0:raise ValueError('Legacy 4B reproduction mismatch; investigate before policy comparison')
    return audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=Path('experiments/local_guards'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--collect',action='store_true')
    parser.add_argument('--evaluate',action='store_true')
    args=parser.parse_args();base=args.base.resolve()
    output=(args.output or base/'results/policy-comparison/matched-reference').resolve()
    if args.evaluate:
        evaluate(base,output);return
    if not args.collect:parser.error('Use --collect or --evaluate')
    workspace=base.parents[1]
    lock=workspace/'.runtime/cheap-guards/heavy-model.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    output.mkdir(parents=True,exist_ok=True)
    with lock.open('a+') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        started=time.time()
        lease.seek(0);lease.truncate();lease.write(str(os.getpid()));lease.flush()
        execution={'started_at':started,'pid':os.getpid(),'heavy_lock':str(lock),'transformer_inference_calls':0,'paid_api_calls':0}
        try:
            collect(base,output);execution['status']='COMPLETE'
        except Exception as exc:
            execution.update(status='FAILED',error=f'{type(exc).__name__}: {exc}');raise
        finally:
            execution['finished_at']=time.time();e.dump(output/'execution.json',execution)


def evaluate(base,output):
    from . import cheap_policy_comparison as pc
    if (output/'metrics.json').exists():raise ValueError('Do not overwrite policy generation')
    old=json.loads((output/'fit-input-freeze.json').read_text());e.verify_frozen(old)
    audit=json.loads((output/'legacy-reproduction.json').read_text())
    if audit['decision_difference_count'] or audit['max_abs_score_delta']!=0:raise ValueError('Legacy reproduction failed')
    paths=[Path(__file__),Path(pc.__file__),output/'fit-input-freeze.json',output/'cached-fits.jsonl',output/'legacy-reproduction.json']
    freeze={'phase':'FROZEN_BEFORE_POLICY_METRICS','post_hoc':True,'created_at':time.time(),
        'source_files':[{'path':str(p),'sha256':e.digest(p)} for p in paths],'record_files':[],
        'policies':list(pc.POLICIES),'wrappers':list(WRAPPERS),'threshold_selection':'shared cheap_policy_comparison.choose_policy_threshold',
        'format_selection':'shared cheap_policy_comparison.policy_rank on actual final inner wrapped metrics',
        'outer_labels_used_for_selection':False,'transformer_inference_calls':0,'paid_api_calls':0}
    e.dump(output/'policy-input-freeze.json',freeze)
    rows,outcomes,records,schemas,alloc=inputs(base)
    flags,rule_times=e.rule_flags(rows,base/'data/archive/shadow-main.jsonl.gz')
    row_lookup={r['prefix_id']:r for r in rows};out_lookup={o['episode_id']:o for o in outcomes}
    alloc_lookup={(a['seed'],a['outer_fold']):a for a in alloc}
    predictions=[];folds=[];curves=[];candidates=defaultdict(list)
    for fit in e.read_jsonl(output/'cached-fits.jsonl'):
        seed,fold,head,fmt=(fit[k] for k in ('seed','outer_fold','head','format'))
        allocation=alloc_lookup[(seed,fold)];train_out=[out_lookup[i] for i in allocation['train_episode_ids']]
        ir=[row_lookup[p['prefix_id']] for p in fit['inner']];ip=[p['score'] for p in fit['inner']]
        test=[row_lookup[p['prefix_id']] for p in fit['outer']];op=[p['score'] for p in fit['outer']]
        cfg=ref.config(head,fmt)
        for policy in pc.POLICIES:
            for wrapper in WRAPPERS:
                threshold,cal,curve=pc.choose_policy_threshold(ir,ip,train_out,flags[wrapper],policy)
                arm=f'{head}:{fmt}:{wrapper}'
                pp=e.prediction_records(test,op,threshold,flags[wrapper],seed,fold,arm,head!='scalar',False)
                e.attach_guard_timing(pp,test,cfg[1],records,fit['online_prediction_ms'],rule_times[wrapper])
                predictions.extend(dict(p,policy=policy) for p in pp)
                folds.append({'seed':seed,'outer_fold':fold,'policy':policy,'arm':arm,'threshold':e.finite(threshold),
                    'calibration':cal,'train_groups':allocation['train_groups'],'test_groups':allocation['test_groups']})
                for t,m in curve:
                    curves.append({'seed':seed,'outer_fold':fold,'policy':policy,'arm':arm,'scope':'inner_OOF_calibration',
                        'threshold':e.finite(t),'metrics':{k:m[k] for k in ('harm_prevented_counterfactual','raw_episode_fpr','unknown_stop')}})
                rank=pc.policy_rank(f'{head}:{fmt}',cal,e.reconstructed_latency(ir,cfg[1],records))
                candidates[(seed,fold,head,wrapper,policy)].append((rank,fmt,pp,cal,threshold))
    for (seed,fold,head,wrapper,policy),cc in candidates.items():
        rank,fmt,pp,cal,threshold=min(cc,key=lambda c:c[0])
        arm=f'{head}:train_selected_format:{wrapper}'
        predictions.extend(dict(p,arm=arm,policy=policy,selected_format=fmt) for p in pp)
        folds.append({'seed':seed,'outer_fold':fold,'policy':policy,'arm':arm,'selected_format':fmt,
            'threshold':e.finite(threshold),'calibration':cal,
            'selection_tuple':[e.finite(x) if isinstance(x,float) else x for x in rank],
            'candidates':[{'format':c[1],'rank':[e.finite(x) if isinstance(x,float) else x for x in c[0]]} for c in cc]})
    aggregates=[]
    grouped=defaultdict(list)
    for p in predictions:grouped[(p['seed'],p['policy'],p['arm'])].append(p)
    for (seed,policy,arm),pp in sorted(grouped.items()):
        metric=e.counts(outcomes,e.decisions_from_records(pp))
        metric.update(seed=seed,policy=policy,arm=arm,prefixes=len(pp),evaluated_outcomes=214,
            complete=len(pp)==176 and len({p['prefix_id'] for p in pp})==176,evaluation_scope='full214',post_hoc=True)
        if pp[0]['learned_component']:metric.update(e.probability_metrics(rows,pp))
        aggregates.append(metric)
    e.verify_frozen(freeze);e.verify_frozen(old)
    e.jsonl(output/'predictions.jsonl',predictions);e.jsonl(output/'threshold-curves.jsonl',curves)
    e.dump(output/'folds.json',folds)
    e.dump(output/'metrics.json',{'schema_version':'posthoc-4b-policies-v1','aggregates':aggregates})
    e.dump(output/'manifest.json',dict(freeze,status='COMPLETE',
        output_files=[{'path':str(output/name),'sha256':e.digest(output/name)} for name in (
            'predictions.jsonl','threshold-curves.jsonl','folds.json','metrics.json','cached-fits.jsonl','timings.json',
            'legacy-reproduction.json','fit-input-freeze.json','policy-input-freeze.json')]))
    return aggregates


if __name__=='__main__':main()
