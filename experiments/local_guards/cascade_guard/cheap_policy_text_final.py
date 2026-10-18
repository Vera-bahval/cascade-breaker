"""Final hardened post-hoc policies on unchanged cached text reference fits."""
from __future__ import annotations
from collections import defaultdict
import json
from pathlib import Path
import time
from . import cheap_eval as e
from . import cheap_policy_comparison as pc
from . import cheap_policy_text as source


def run(base,output):
    output.mkdir(parents=True,exist_ok=True)
    if (output/'metrics.json').exists():raise ValueError('Preserve final generation')
    cache=base/'results/policy-comparison/text-reference-verified'
    old=json.loads((cache/'fit-input-freeze.json').read_text())
    verification=[]
    for item in old['source_files']:
        actual=Path(item['path'])
        if e.digest(actual)!=item['sha256']:raise ValueError('Verified cached fit source changed: '+str(actual))
        verification.append({'original_path':item['path'],'verified_path':str(actual),'sha256':item['sha256']})
    paths=[Path(__file__),Path(pc.__file__),Path(source.__file__),cache/'cached-fits.jsonl',cache/'fit-input-freeze.json',cache/'historical-score-audit.json',cache/'repeat-score-audit.json']
    freeze={'phase':'FROZEN_BEFORE_FINAL_POLICY_METRICS','post_hoc':True,'created_unix':time.time(),
        'source_files':[{'path':str(p),'sha256':e.digest(p)} for p in paths],'record_files':[],
        'cached_fit_input_verification':verification,'policies':pc.DEFINITIONS,'wrappers':list(e.WRAPPERS),
        'B2':'threshold calibrated standalone; format selected on wrapped inner metrics',
        'Blegacy':'format selected standalone using historical nextafter grid A criteria, then unchanged decision OR rules',
        'format_tiebreak':'same inference cost0 (no pretrained feature inference), then lexical frozen format',
        'new_fits':0,'transformer_inference_calls':0,'paid_api_calls':0}
    e.dump(output/'input-freeze.json',freeze)
    rows,outcomes,alloc=source.inputs(base);lookup={r['prefix_id']:r for r in rows};olookup={o['episode_id']:o for o in outcomes}
    amap={(a['seed'],a['outer_fold']):a for a in alloc};flags,rule_times=e.rule_flags(rows,base/'data/archive/shadow-main.jsonl.gz')
    predictions=[];folds=[];curves=[];candidates=defaultdict(list);legacy=defaultdict(list)
    def prediction(fit,te,op,threshold,wrapper,policy,arm):
        pp=e.prediction_records(te,op,threshold,flags[wrapper],fit['seed'],fit['outer_fold'],arm,True,False)
        for p in pp:
            pid=p['prefix_id'];ms=fit['online_prediction_ms'][pid];rms=rule_times[wrapper][pid]
            p.update(policy=policy,inference_cost_ms=0.,decision_model_ms=ms,rule_wrapper_ms=rms,
                reconstructed_total_guard_ms=ms+rms,analysis_scope='post-hoc matched text control',format=fit['format'])
        return pp
    for fit in e.read_jsonl(cache/'cached-fits.jsonl'):
        seed,fold,fmt=(fit[k] for k in ('seed','outer_fold','format'));a=amap[seed,fold]
        ir=[lookup[p['prefix_id']] for p in fit['inner']];ip=[p['score'] for p in fit['inner']]
        te=[lookup[p['prefix_id']] for p in fit['outer']];op=[p['score'] for p in fit['outer']]
        tr_out=[olookup[i] for i in a['train_episode_ids']]
        threshold,cal,_=e.select_threshold(ir,ip,tr_out,flags['none'])
        rank=(not cal['target_feasible'],-(cal['metrics']['harm_prevented_counterfactual']['rate'] or 0),cal['metrics']['raw_episode_fpr']['k'],0.,fmt)
        legacy[seed,fold].append((rank,fmt,fit,te,op,threshold,cal))
        for policy in pc.POLICIES:
            for wrapper in e.WRAPPERS:
                threshold,cal,curve=pc.choose_policy_threshold(ir,ip,tr_out,flags[wrapper],policy)
                arm=f'tfidf_logistic:{fmt}:{wrapper}';pp=prediction(fit,te,op,threshold,wrapper,policy,arm)
                predictions.extend(pp)
                folds.append({'seed':seed,'outer_fold':fold,'policy':policy,'arm':arm,'threshold':e.finite(threshold),
                    'calibration':cal,'train_groups':a['train_groups'],'test_groups':a['test_groups']})
                curves.extend({'seed':seed,'outer_fold':fold,'policy':policy,'arm':arm,'scope':'inner_OOF_calibration',
                    'threshold':e.finite(t),'metrics':{k:m[k] for k in ('harm_prevented_counterfactual','raw_episode_fpr','unknown_stop')}} for t,m in curve)
                candidates[seed,fold,policy,wrapper].append((pc.policy_rank(fmt,cal,0.),fmt,pp,cal,threshold))
    for (seed,fold,policy,wrapper),cc in candidates.items():
        rank,fmt,pp,cal,threshold=min(cc,key=lambda c:c[0]);selection='train_selected_format_B2' if policy=='B_independent' else 'train_selected_format'
        arm=f'tfidf_logistic:{selection}:{wrapper}'
        predictions.extend(dict(p,arm=arm,selected_format=fmt) for p in pp)
        folds.append({'seed':seed,'outer_fold':fold,'policy':policy,'arm':arm,'selected_format':fmt,'threshold':e.finite(threshold),
            'calibration':cal,'candidates':[{'format':c[1],'rank':list(c[0])} for c in cc]})
    for (seed,fold),cc in legacy.items():
        rank,fmt,fit,te,op,threshold,cal=min(cc,key=lambda c:c[0])
        for wrapper in e.WRAPPERS:
            arm=f'tfidf_logistic:train_selected_Blegacy_format:{wrapper}'
            pp=prediction(fit,te,op,threshold,wrapper,'B_independent',arm)
            predictions.extend(dict(p,selected_format=fmt,selection_scope='standalone only; historical exact diagnostic',threshold_grid='legacy nextafter') for p in pp)
            folds.append({'seed':seed,'outer_fold':fold,'policy':'B_independent','arm':arm,'selected_format':fmt,
                'threshold':e.finite(threshold),'calibration':cal,'candidates':[{'format':c[1],'rank':list(c[0])} for c in cc]})
    aggregates=pc.summarize(rows,outcomes,predictions);e.verify_frozen(freeze)
    e.jsonl(output/'predictions.jsonl',predictions);e.jsonl(output/'threshold-curves.jsonl',curves);e.dump(output/'folds.json',folds)
    e.dump(output/'metrics.json',{'schema_version':'posthoc-text-policies-final-v1','aggregates':aggregates})
    e.dump(output/'manifest.json',dict(freeze,status='COMPLETE',output_files=[{'path':str(output/n),'sha256':e.digest(output/n)} for n in ['input-freeze.json','metrics.json','predictions.jsonl','threshold-curves.jsonl','folds.json']]))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',type=Path,default=Path('experiments/local_guards'));args=parser.parse_args()
    base=args.base.resolve();run(base,base/'results/policy-comparison/text-reference-verified-final')
