"""Matched text LR reference for exploratory policy comparison, without inference APIs."""
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
from .ml import Fitted

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


def fit_scores(train,test,seed,fmt,online=False):
    model=Fitted('tfidf_logistic',seed,ablation=fmt).fit(train)
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
    paths=[Path(__file__),Path(pc.__file__),Path(e.__file__),base/'cascade_guard/ml.py',
           base/'data/prefixes.jsonl',base/'data/outcomes.jsonl',base/'data/archive/shadow-main.jsonl.gz',
           base/'results/cheap-guards/evaluation/fold-allocations.json',
           base/'results/p4-with-semantic/predictions.jsonl',base/'results/p4-with-semantic/cv-manifest.json']
    freeze={'phase':'FROZEN_BEFORE_FITS_OR_NEW_METRICS','created_unix':time.time(),'post_hoc':True,
        'source_files':[{'path':str(p),'sha256':e.digest(p)} for p in paths],'record_files':[],
        'model':{'kind':'TF-IDF + Logistic Regression','C':1,'penalty':'l2','analyzer':'char_wb',
                 'ngram_range':[3,5],'min_df':2,'max_features':20000,'sublinear_tf':True,'max_iter':2000},
        'formats':list(FORMATS),'policies':pc.DEFINITIONS,'wrappers':list(e.WRAPPERS),
        'fold_allocations_sha256':e.stable_hash(alloc),'fits':'outer3/inner2, seeds17/29/43; vocabulary fitted inside each fold',
        'training_weight':'inverse group size normalized mean1','threshold_grid':'exact unique observed scores >=, infinity',
        'format_selection':'inner final-system feasibility, recall, FP, equal feature-inference cost0, lexical format',
        'cost_scope':'outer online decision cost includes TF-IDF transform + LR predict; no pretrained inference; vectorizer fit excluded',
        'missing_experiment':'Initial text control omitted by cheap matrix; old outputs lack saved inner OOF probabilities.',
        'raw64':'UNSUPPORTED: frozen archive text/text_facts_action not available; no invented serialization',
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
                pp,t=fit_scores(tr,te,a['seed']+j,fmt)
                inner.extend({'prefix_id':r['prefix_id'],'score':p,'inner_fold':j} for r,p in zip(te,pp));stats.append(dict(t,inner_fold=j))
            tr,te=subset(a['train_episode_ids']),subset(a['test_episode_ids'])
            pp,t=fit_scores(tr,te,a['seed'],fmt,True);stats.append(dict(t,phase='outer_final_fit'))
            fits.append({'seed':a['seed'],'outer_fold':a['outer_fold'],'format':fmt,'inner':inner,
                'outer':[{'prefix_id':r['prefix_id'],'score':p} for r,p in zip(te,pp)],'online_prediction_ms':t['online_prediction_ms']})
            timings.append({'seed':a['seed'],'outer_fold':a['outer_fold'],'format':fmt,'fits':stats})
        print(json.dumps({'stage':'text_reference_fit','seed':a['seed'],'outer_fold':a['outer_fold']}),flush=True)
    e.jsonl(output/'cached-fits.jsonl',fits);e.dump(output/'timings.json',timings)
    # Read-only historical comparability diagnostic; no thresholds copied from old evaluation.
    old={ (p['seed'],p['outer_fold'],p['ablation'],p['prefix_id']):p for p in e.read_jsonl(base/'results/p4-with-semantic/predictions.jsonl') if p['arm']=='tfidf_logistic'}
    deltas=[abs(p['score']-old[(f['seed'],f['outer_fold'],f['format'],p['prefix_id'])]['probability']) for f in fits for p in f['outer']]
    e.dump(output/'historical-score-audit.json',{'checked':len(deltas),'max_abs_score_delta':max(deltas),
        'note':'Same outer groups/model; old inner calibration not reused. Historical predictions can differ if original prefix fit ordering or population changed.'})
    flags,rule_times=e.rule_flags(rows,base/'data/archive/shadow-main.jsonl.gz')
    amap={(a['seed'],a['outer_fold']):a for a in alloc}
    predictions=[];folds=[];curves=[];candidates=defaultdict(list)
    for fit in fits:
        seed,fold,fmt=(fit[k] for k in ('seed','outer_fold','format'));a=amap[seed,fold]
        ir=[lookup[p['prefix_id']] for p in fit['inner']];ip=[p['score'] for p in fit['inner']]
        te=[lookup[p['prefix_id']] for p in fit['outer']];op=[p['score'] for p in fit['outer']]
        tr_out=[olookup[i] for i in a['train_episode_ids']]
        for policy in pc.POLICIES:
            for wrapper in e.WRAPPERS:
                threshold,cal,curve=pc.choose_policy_threshold(ir,ip,tr_out,flags[wrapper],policy)
                arm=f'tfidf_logistic:{fmt}:{wrapper}'
                pp=e.prediction_records(te,op,threshold,flags[wrapper],seed,fold,arm,True,False)
                for p in pp:
                    pid=p['prefix_id'];ms=fit['online_prediction_ms'][pid];rms=rule_times[wrapper][pid]
                    p.update(policy=policy,inference_cost_ms=0.,decision_model_ms=ms,rule_wrapper_ms=rms,
                        reconstructed_total_guard_ms=ms+rms,analysis_scope='post-hoc matched text control',format=fmt)
                predictions.extend(pp)
                folds.append({'seed':seed,'outer_fold':fold,'policy':policy,'arm':arm,'threshold':e.finite(threshold),
                    'calibration':cal,'train_groups':a['train_groups'],'test_groups':a['test_groups']})
                curves.extend({'seed':seed,'outer_fold':fold,'policy':policy,'arm':arm,'scope':'inner_OOF_calibration',
                    'threshold':e.finite(t),'metrics':{k:m[k] for k in ('harm_prevented_counterfactual','raw_episode_fpr','unknown_stop')}} for t,m in curve)
                candidates[seed,fold,policy,wrapper].append((pc.policy_rank(fmt,cal,0.),fmt,pp,cal,threshold))
    for (seed,fold,policy,wrapper),cc in candidates.items():
        rank,fmt,pp,cal,threshold=min(cc,key=lambda c:c[0]);arm=f'tfidf_logistic:train_selected_format:{wrapper}'
        predictions.extend(dict(p,arm=arm,selected_format=fmt) for p in pp)
        folds.append({'seed':seed,'outer_fold':fold,'policy':policy,'arm':arm,'selected_format':fmt,'threshold':e.finite(threshold),
            'calibration':cal,'candidates':[{'format':c[1],'rank':list(c[0])} for c in cc]})
    aggregates=pc.summarize(rows,outcomes,predictions)
    e.verify_frozen(freeze)
    e.jsonl(output/'predictions.jsonl',predictions);e.jsonl(output/'threshold-curves.jsonl',curves);e.dump(output/'folds.json',folds)
    e.dump(output/'metrics.json',{'schema_version':'posthoc-text-policies-v1','aggregates':aggregates})
    names=['fit-input-freeze.json','fold-allocations.json','cached-fits.jsonl','timings.json','historical-score-audit.json',
           'predictions.jsonl','threshold-curves.jsonl','folds.json','metrics.json']
    e.dump(output/'manifest.json',dict(freeze,status='COMPLETE',output_files=[{'path':str(output/n),'sha256':e.digest(output/n)} for n in names]))
    return aggregates


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,default=Path('experiments/local_guards'));p.add_argument('--output',type=Path)
    args=p.parse_args();base=args.base.resolve();output=(args.output or base/'results/policy-comparison/text-reference').resolve()
    lock=base.parents[1]/'.runtime/cheap-guards/heavy-model.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    output.mkdir(parents=True,exist_ok=True)
    with lock.open('a+') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);started=time.time()
        execution={'started_at':started,'pid':os.getpid(),'heavy_lock':str(lock),'transformer_inference_calls':0,'paid_api_calls':0}
        try:run(base,output);execution['status']='COMPLETE'
        except Exception as exc:execution.update(status='FAILED',error=f'{type(exc).__name__}: {exc}');raise
        finally:execution['finished_at']=time.time();e.dump(output/'execution.json',execution)


if __name__=='__main__':main()
