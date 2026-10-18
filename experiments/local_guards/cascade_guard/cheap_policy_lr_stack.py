"""Matched tabular + SecJev 0.8B Logistic Regression reference for exploratory policy comparison, without inference APIs."""
from __future__ import annotations
import argparse
from collections import defaultdict
import fcntl
import json
import os
from pathlib import Path
import time

from . import cheap_eval as e
from . import cheap_policy_comparison as pc
from .ml import Fitted, semantic_vector
from .offline import load_semantics, semantic_inference_ms

FORMATS=('plus_rationale','facts_action')


def inputs(base):
    outcomes=[o for o in e.read_jsonl(base/'data/outcomes.jsonl') if not o['legacy_ambiguous']]
    ids={o['episode_id'] for o in outcomes}
    rows=[r for r in e.read_jsonl(base/'data/prefixes.jsonl') if r['episode_id'] in ids and
          r['control_point']=='P4.finstripe__create_transfer' and not r['already_harmful']]
    alloc=json.loads((base/'results/cheap-guards/evaluation/fold-allocations.json').read_text())
    assert len(rows)==176 and len(outcomes)==214
    assert all(isinstance(r.get('text'),str) and isinstance(r.get('text_facts_action'),str) for r in rows)
    return rows,outcomes,alloc


def fit_scores(train,test,seed,fmt,semantics,online=False):
    model=Fitted('semantic_stack',seed,ablation=fmt,semantic_scores=semantics).fit(train)
    timing={'fit_ms':model.fit_ms,'online_prediction_ms':{}}
    if online:
        scores=[]
        for row in test:
            p,ms=model.predict([row]);scores.append(float(p[0]));timing['online_prediction_ms'][row['prefix_id']]=ms
    else:
        p,ms=model.predict(test);scores=list(map(float,p));timing['batch_predict_ms']=ms
    return scores,timing


def run(base,output):
    output.mkdir(parents=True,exist_ok=True)
    if (output/'fit-input-freeze.json').exists():raise ValueError('Generation exists; preserve outputs')
    rows,outcomes,alloc=inputs(base)
    semantics=load_semantics(base/'results/secjev-mps-scores.jsonl',e.read_jsonl(base/'data/prefixes.jsonl'))
    if any(semantic_vector(r,semantics,fmt) is None for r in rows for fmt in FORMATS):
        raise ValueError('Incomplete semantic scores; no zero imputation')
    paths=[Path(__file__),Path(pc.__file__),Path(e.__file__),base/'cascade_guard/ml.py',base/'cascade_guard/offline.py',base/'results/secjev-mps-scores.jsonl',base/'tests/test_cheap_policy_lr_stack.py',
           base/'data/prefixes.jsonl',base/'data/outcomes.jsonl',base/'data/archive/shadow-main.jsonl.gz',
           base/'results/cheap-guards/evaluation/fold-allocations.json',
           base/'results/p4-with-semantic/predictions.jsonl',base/'results/p4-with-semantic/cv-manifest.json']
    freeze={'phase':'FROZEN_BEFORE_FITS_OR_NEW_METRICS','created_unix':time.time(),'post_hoc':True,
        'source_files':[{'path':str(p),'sha256':e.digest(p)} for p in paths],'record_files':[],
        'model':{'kind':'tabular + SecJev 0.8B four probabilities Logistic Regression','C':1,'penalty':'l2','max_iter':2000},
        'formats':list(FORMATS),'policies':pc.DEFINITIONS,'wrappers':list(e.WRAPPERS),
        'fold_allocations_sha256':e.stable_hash(alloc),'fits':'outer3/inner2, seeds17/29/43; numeric imputation/scaling and categorical encoding fitted inside each fold',
        'training_weight':'inverse group size normalized mean1','threshold_grid':'exact unique observed scores >=, infinity',
        'format_selection':'inner final-system feasibility, recall, FP, median reconstructed original semantic inference cost, lexical format',
        'cost_scope':'reconstructed original semantic inference + measured online tabular transform/LR predict + rule wrapper; fit excluded; no new model inference',
        'missing_experiment':'Initial semantic LR stack omitted by cheap matrix; old outputs lack saved inner OOF probabilities.',
        'raw64':'UNSUPPORTED: SecJev 0.8B atomic scores not available; no invented features',
        'transformer_inference_calls':0,'paid_api_calls':0}
    e.dump(output/'fit-input-freeze.json',freeze);e.dump(output/'fold-allocations.json',alloc)
    lookup={r['prefix_id']:r for r in rows};olookup={o['episode_id']:o for o in outcomes}
    subset=lambda ids:[r for r in rows if r['episode_id'] in set(ids)]
    fits=[];timings=[]
    for a in alloc:
        for fmt in FORMATS:
            inner=[];stats=[]
            for j,s in enumerate(a['inner']):
                tr,te=subset(s['train_episode_ids']),subset(s['test_episode_ids'])
                pp,t=fit_scores(tr,te,a['seed']+j,fmt,semantics)
                inner.extend({'prefix_id':r['prefix_id'],'score':p,'inner_fold':j} for r,p in zip(te,pp));stats.append(dict(t,inner_fold=j))
            tr,te=subset(a['train_episode_ids']),subset(a['test_episode_ids'])
            pp,t=fit_scores(tr,te,a['seed'],fmt,semantics,True);stats.append(dict(t,phase='outer_final_fit'))
            fits.append({'seed':a['seed'],'outer_fold':a['outer_fold'],'format':fmt,'inner':inner,
                'outer':[{'prefix_id':r['prefix_id'],'score':p} for r,p in zip(te,pp)],'online_prediction_ms':t['online_prediction_ms']})
            timings.append({'seed':a['seed'],'outer_fold':a['outer_fold'],'format':fmt,'fits':stats})
        print(json.dumps({'stage':'lr_stack_reference_fit','seed':a['seed'],'outer_fold':a['outer_fold']}),flush=True)
    e.jsonl(output/'cached-fits.jsonl',fits);e.dump(output/'timings.json',timings)
    # Read-only historical comparability diagnostic; no thresholds copied from old evaluation.
    old={ (p['seed'],p['outer_fold'],p['ablation'],p['prefix_id']):p for p in e.read_jsonl(base/'results/p4-with-semantic/predictions.jsonl') if p['arm']=='semantic_stack'}
    deltas=[abs(p['score']-old[(f['seed'],f['outer_fold'],f['format'],p['prefix_id'])]['probability']) for f in fits for p in f['outer']]
    e.dump(output/'historical-score-audit.json',{'checked':len(deltas),'max_abs_score_delta':max(deltas),
        'note':'Same outer groups/model; old inner calibration not reused. Historical predictions can differ if original prefix fit ordering or population changed.'})
    flags,rule_times=e.rule_flags(rows,base/'data/archive/shadow-main.jsonl.gz')
    amap={(a['seed'],a['outer_fold']):a for a in alloc}
    predictions=[];folds=[];curves=[];candidates=defaultdict(list);legacy=defaultdict(list)
    def prediction(fit,te,op,threshold,wrapper,policy,arm):
        pp=e.prediction_records(te,op,threshold,flags[wrapper],fit['seed'],fit['outer_fold'],arm,True,False)
        for p in pp:
            pid=p['prefix_id'];ms=fit['online_prediction_ms'][pid];rms=rule_times[wrapper][pid]
            p.update(policy=policy,inference_cost_ms=semantic_inference_ms(semantics[pid,fit['format']]),decision_model_ms=ms,rule_wrapper_ms=rms,
                reconstructed_total_guard_ms=semantic_inference_ms(semantics[pid,fit['format']])+ms+rms,analysis_scope='post-hoc matched semantic LR stack',format=fit['format'])
        return pp
    for fit in fits:
        seed,fold,fmt=(fit[k] for k in ('seed','outer_fold','format'));a=amap[seed,fold]
        ir=[lookup[p['prefix_id']] for p in fit['inner']];ip=[p['score'] for p in fit['inner']]
        te=[lookup[p['prefix_id']] for p in fit['outer']];op=[p['score'] for p in fit['outer']]
        tr_out=[olookup[i] for i in a['train_episode_ids']]
        semantic_cost=float(__import__('numpy').median([semantic_inference_ms(semantics[r['prefix_id'],fmt]) for r in ir]))
        threshold,cal,_=e.select_threshold(ir,ip,tr_out,flags['none'])
        rank=(not cal['target_feasible'],-(cal['metrics']['harm_prevented_counterfactual']['rate'] or 0),cal['metrics']['raw_episode_fpr']['k'],semantic_cost,fmt)
        legacy[seed,fold].append((rank,fmt,fit,te,op,threshold,cal))
        for policy in pc.POLICIES:
            for wrapper in e.WRAPPERS:
                threshold,cal,curve=pc.choose_policy_threshold(ir,ip,tr_out,flags[wrapper],policy)
                arm=f'semantic_stack:{fmt}:{wrapper}';pp=prediction(fit,te,op,threshold,wrapper,policy,arm)
                predictions.extend(pp)
                folds.append({'seed':seed,'outer_fold':fold,'policy':policy,'arm':arm,'threshold':e.finite(threshold),
                    'calibration':cal,'train_groups':a['train_groups'],'test_groups':a['test_groups']})
                curves.extend({'seed':seed,'outer_fold':fold,'policy':policy,'arm':arm,'scope':'inner_OOF_calibration',
                    'threshold':e.finite(t),'metrics':{k:m[k] for k in ('harm_prevented_counterfactual','raw_episode_fpr','unknown_stop')}} for t,m in curve)
                candidates[seed,fold,policy,wrapper].append((pc.policy_rank(fmt,cal,semantic_cost),fmt,pp,cal,threshold))
    for (seed,fold,policy,wrapper),cc in candidates.items():
        rank,fmt,pp,cal,threshold=min(cc,key=lambda c:c[0]);selection='train_selected_format_B2' if policy=='B_independent' else 'train_selected_format'
        arm=f'semantic_stack:{selection}:{wrapper}'
        predictions.extend(dict(p,arm=arm,selected_format=fmt) for p in pp)
        folds.append({'seed':seed,'outer_fold':fold,'policy':policy,'arm':arm,'selected_format':fmt,'threshold':e.finite(threshold),
            'calibration':cal,'candidates':[{'format':c[1],'rank':list(c[0])} for c in cc]})
    for (seed,fold),cc in legacy.items():
        rank,fmt,fit,te,op,threshold,cal=min(cc,key=lambda c:c[0])
        for wrapper in e.WRAPPERS:
            arm=f'semantic_stack:train_selected_Blegacy_format:{wrapper}'
            pp=prediction(fit,te,op,threshold,wrapper,'B_independent',arm)
            predictions.extend(dict(p,selected_format=fmt,selection_scope='standalone only; historical exact diagnostic',threshold_grid='legacy nextafter') for p in pp)
            folds.append({'seed':seed,'outer_fold':fold,'policy':'B_independent','arm':arm,'selected_format':fmt,
                'threshold':e.finite(threshold),'calibration':cal,'candidates':[{'format':c[1],'rank':list(c[0])} for c in cc]})
    aggregates=pc.summarize(rows,outcomes,predictions);e.verify_frozen(freeze)
    e.jsonl(output/'predictions.jsonl',predictions);e.jsonl(output/'threshold-curves.jsonl',curves);e.dump(output/'folds.json',folds)
    e.dump(output/'metrics.json',{'schema_version':'posthoc-semantic-lr-policies-v1','aggregates':aggregates})
    e.dump(output/'manifest.json',dict(freeze,status='COMPLETE',output_files=[{'path':str(output/n),'sha256':e.digest(output/n)} for n in ['fit-input-freeze.json','metrics.json','predictions.jsonl','threshold-curves.jsonl','folds.json','cached-fits.jsonl','historical-score-audit.json','timings.json','fold-allocations.json']]))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,default=Path('experiments/local_guards'));p.add_argument('--output',type=Path)
    args=p.parse_args();base=args.base.resolve();output=(args.output or base/'results/policy-comparison/lr-stack-reference').resolve()
    lock=base.parents[1]/'.runtime/cheap-guards/heavy-model.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    output.mkdir(parents=True,exist_ok=True)
    with lock.open('a+') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);started=time.time()
        execution={'started_at':started,'pid':os.getpid(),'heavy_lock':str(lock),'transformer_inference_calls':0,'paid_api_calls':0}
        try:run(base,output);execution['status']='COMPLETE'
        except Exception as exc:execution.update(status='FAILED',error=f'{type(exc).__name__}: {exc}');raise
        finally:execution['finished_at']=time.time();e.dump(output/'execution.json',execution)


if __name__=='__main__':main()
