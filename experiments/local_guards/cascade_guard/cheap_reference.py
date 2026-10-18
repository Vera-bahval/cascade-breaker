"""Cached 4B reference under the frozen cheap-guard calibration protocol.

This aligns threshold/fit/selection mechanics, not backbone or input content.
No transformer or remote inference is imported or performed.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
import numpy as np
from . import cheap_eval as e
from .ml import QUESTION_KEYS
from .night_ml import vector

FORMATS=('plus_rationale','compact_policy_facts','relevant_history_obligations')
WRAPPERS=('none','original_rules')
HEADS=('scalar','catboost','catboost_tabular')


def ordered_hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def source_cost(record, originals):
    origin=originals.get(record['input_hash']) if record.get('cache_hit') else record
    value=(origin or {}).get('timing_ms',{}).get('total')
    return float(value) if isinstance(value,(int,float)) and np.isfinite(value) else None


def load_cached(score_path,input_path,expected_ids):
    inputs={(r['prefix_id'],r['format']):r for r in e.read_jsonl(input_path)}
    scores=e.read_jsonl(score_path)
    originals={r['input_hash']:r for r in scores if not r.get('cache_hit')}
    records={};schemas={};identity=[]
    for r in scores:
        key=(r['prefix_id'],r['format'])
        if key not in inputs or r['format'] not in FORMATS or r['prefix_id'] not in expected_ids:
            raise ValueError('Unexpected cached score identity')
        if key in identity:
            raise ValueError('Duplicate cached score')
        identity.append(key)
        frozen=inputs[key]
        if ordered_hash(frozen['payload'])!=frozen['payload_hash'] or r.get('payload_hash')!=frozen['payload_hash']:
            raise ValueError('Cached payload hash mismatch')
        fingerprint=canonical_hash({k:v for k,v in r['model_metadata'].items() if k!='model_load_ms'})
        expected=ordered_hash({'payload':frozen['payload'],'scorer_fingerprint':fingerprint})
        if r['input_hash']!=expected:
            raise ValueError('Cached model/input hash mismatch')
        values=vector(r);block='B4_'+r['format']
        features={f'checkpoint.create_transfer.{q}':float(v) for q,v in zip(QUESTION_KEYS,values)} if values is not None else {}
        records[(r['prefix_id'],block)]={'prefix_id':r['prefix_id'],'block':block,'status':'OK' if values is not None else 'UNKNOWN',
            'features':features,'scalar_risk':max(values) if values is not None else None,'input_hash':r['input_hash'],
            'model_metadata':r['model_metadata'],'timing_ms':r['timing_ms'],'memory':r.get('memory',{}),
            'window_count':None,'inference_cost_ms':source_cost(r,originals),
            'provenance':{'cached_only':True,'payload_hash':r['payload_hash'],'format':r['format'],'source_full_cost':'original noncache timing_ms.total; no new scoring'}}
        if features:schemas[block]=sorted(features)
    if len(records)!=528 or any((pid,'B4_'+fmt) not in records for pid in expected_ids for fmt in FORMATS):
        raise ValueError('Require exactly176 x3 frozen cached score records')
    return records,schemas


def config(head,fmt):
    return ('scalar' if head=='scalar' else 'catboost',('B4_'+fmt,),head=='catboost_tabular')


def identity08(base,primary):
    old={};new={};oldrules={};newrules={}
    with (base/'results/night-4b/evaluation/predictions.jsonl').open() as f:
        for line in f:
            r=json.loads(line)
            if r['seed']==17 and r['arm']=='secjev:old08':old[r['prefix_id']]=r['probability']
            if r['seed']==17 and r['arm']=='Rules':oldrules[r['prefix_id']]=r['block']
    with (primary/'predictions.jsonl').open() as f:
        for line in f:
            r=json.loads(line)
            if r['seed']==17 and r['arm']=='scalar:J_cur:none':new[r['prefix_id']]=r['scalar_risk']
            if r['seed']==17 and r['arm']=='R1':newrules[r['prefix_id']]=r['block']
    if len(old)!=176 or len(oldrules)!=176 or len(newrules)!=176 or old!=new or oldrules!=newrules:
        raise ValueError('0.8 cached scalar or original-rule identity failed')
    primary_metrics=json.loads((primary/'metrics.json').read_text())['aggregates']
    arms={f'{kind}:J_cur{suffix}:{wrapper}' for kind,suffix in [('scalar',''),('catboost',''),('catboost','+tabular')] for wrapper in WRAPPERS}
    return {'prefixes':176,'scalar_exact_equal':True,'rules_exact_equal':True,'max_abs_delta':0.,'no_refit':True,
        'matched08_control':[r for r in primary_metrics if r['arm'] in arms]}


def freeze(base,primary,output):
    output.mkdir(parents=True,exist_ok=True)
    if (output/'metrics.json').exists():raise ValueError('Matched evaluation already exists; preserve this generation')
    path=output/'input-freeze.json'
    old=json.loads(path.read_text()) if path.exists() else None
    if old:e.verify_frozen(old)
    outcomes=[o for o in e.read_jsonl(base/'data/outcomes.jsonl') if not o['legacy_ambiguous']]
    ids={o['episode_id'] for o in outcomes}
    rows=[r for r in e.read_jsonl(base/'data/prefixes.jsonl') if r['episode_id'] in ids and r['control_point']=='P4.finstripe__create_transfer' and not r['already_harmful']]
    assert len(rows)==176 and len(outcomes)==214
    score_path=base/'results/night-4b/scores.jsonl';input_path=base/'results/night-4b/formats/inputs.jsonl'
    records,schemas=load_cached(score_path,input_path,{r['prefix_id'] for r in rows})
    jcur=next(r for r in e.read_jsonl(base/'results/cheap-guards/sequence/features.jsonl') if r['block']=='J_cur' and r['status']=='OK')
    if any(keys!=sorted(jcur['features']) for keys in schemas.values()):raise ValueError('Question feature column order differs from primaryJ_cur')
    allocations=json.loads((primary/'fold-allocations.json').read_text())
    if allocations!=e.allocation(outcomes,base/'results/night-4b/evaluation/folds.json'):
        raise ValueError('Primary/night fold allocation mismatch')
    files=[Path(__file__),base/'tests/test_cheap_reference.py',Path(e.__file__),base/'cascade_guard/night_ml.py',base/'cascade_guard/ml.py',base/'cascade_guard/offline.py',
        base/'cascade_guard/rules.py',base/'cascade_guard/rules_v2.py',base/'data/prefixes.jsonl',base/'data/outcomes.jsonl',
        base/'data/archive/shadow-main.jsonl.gz',input_path,base/'results/night-4b/formats/manifest.json',
        base/'results/night-4b/scores.manifest.json',base/'results/night-4b/evaluation/folds.json',
        base/'results/night-4b/evaluation/predictions.jsonl',primary/'manifest.json',primary/'input-freeze.json',
        primary/'fold-allocations.json',primary/'predictions.jsonl',primary/'metrics.json',base/'results/cheap-guards/sequence/features.jsonl']
    contract={'phase':'FROZEN_BEFORE_MATCHED_METRICS','created_unix':time.time(),'source_files':[{'path':str(p),'sha256':e.digest(p)} for p in files],
        'record_files':[{'path':str(score_path),'sha256':e.digest(score_path)}],'formats':list(FORMATS),'wrappers':list(WRAPPERS),'heads':list(HEADS),
        'schemas':schemas,'schema_sha256':e.stable_hash(schemas),'allocations_sha256':e.stable_hash(allocations),
        'catboost':e.CB_PARAMS,'seeds':list(e.SEEDS),'primary_matrix_immutable':True,'transformer_inference_calls':0,'paid_api_calls':0,
        'threshold_criterion':'cheap_eval.select_threshold verbatim: feasible rawFPR<=.05, maxinnerharmrecall,minFP,highestthreshold',
        'format_selection':'cheap_eval.selection_rank verbatim perhead andwrapper; min full source cost timing_ms.total then frozen lexical config; innerOOF only',
        'cost':'source actual noncache full timing_ms.total, including tokenize/compute/cleanup/queue; no new inference; unknown cost ranks infinity',
        'question_column_order':'same sorted checkpoint.create_transfer.<question> schema as primaryJ_cur',
        'comparison_boundary':'guard variants with aligned training/calibration; backbone and frozen input formats differ; not isolated model-size ablation'}
    if old:
        scientific=lambda m:{k:v for k,v in m.items() if k not in ('created_unix','phase')}
        if scientific(old)!=scientific(contract):raise ValueError('Matched freeze drift; use a new generation')
        for companion,expected in [(output/'feature-schema.json',schemas),(output/'fold-allocations.json',allocations)]:
            if not companion.exists() or json.loads(companion.read_text())!=expected:
                raise ValueError('Matched frozen companion drift; use a new generation')
        contract=old
    else:
        e.dump(path,contract);e.dump(output/'feature-schema.json',schemas);e.dump(output/'fold-allocations.json',allocations)
    return rows,outcomes,records,schemas,allocations,contract


def run(base,primary,output,*,freeze_only=False,fitter=None):
    rows,outcomes,records,schemas,allocations,manifest=freeze(base,primary,output)
    if freeze_only:return manifest
    e.verify_frozen(manifest)
    flags,rule_timing=e.rule_flags(rows,base/'data/archive/shadow-main.jsonl.gz')
    identity=identity08(base,primary)
    by_id={o['episode_id']:o for o in outcomes}
    subset=lambda ids:[r for r in rows if r['episode_id'] in set(ids)]
    predictions=[];folds=[];timings=[];failures=[]
    for allocation in allocations:
        seed=allocation['seed'];fold=allocation['outer_fold']
        train=subset(allocation['train_episode_ids']);test=subset(allocation['test_episode_ids'])
        trainout=[by_id[i] for i in allocation['train_episode_ids']]
        choices=defaultdict(list)
        for head in HEADS:
            for fmt in FORMATS:
                cfg=config(head,fmt);ir=[];ip=[];stats=[]
                for j,inner in enumerate(allocation['inner']):
                    tr=subset(inner['train_episode_ids']);te=subset(inner['test_episode_ids'])
                    p,t=e.predict(cfg,tr,te,seed+j,records,schemas,fitter)
                    ir.extend(te);ip.extend(p);stats.append(dict(t,inner_fold=j))
                op,ot=e.predict(cfg,train,test,seed,records,schemas,fitter,online=True)
                stats.append(dict(ot,phase='outer_final_fit'))
                failed=any(s['failure'] for s in stats)
                timings.append({'seed':seed,'outer_fold':fold,'head':head,'format':fmt,'fits':stats,'wrapper_reuse_count':2})
                if failed:failures.append({'seed':seed,'outer_fold':fold,'head':head,'format':fmt,'fits':stats})
                for wrapper in WRAPPERS:
                    threshold,cal,_=e.select_threshold(ir,ip,trainout,flags[wrapper])
                    arm=f'{head}:{fmt}:{wrapper}'
                    pp=e.prediction_records(test,op,threshold,flags[wrapper],seed,fold,arm,head!='scalar',failed)
                    e.attach_guard_timing(pp,test,cfg[1],records,ot['online_prediction_ms'],rule_timing[wrapper])
                    predictions.extend(pp)
                    folds.append({'seed':seed,'outer_fold':fold,'arm':arm,'threshold':e.finite(threshold),'calibration':cal,
                        'train_groups':allocation['train_groups'],'test_groups':allocation['test_groups'],'fit_failed':failed})
                    rank=e.selection_rank(cfg,cal,e.reconstructed_latency(ir,cfg[1],records))
                    choices[(head,wrapper)].append((rank,fmt,threshold,cal,pp,failed))
        for (head,wrapper),cc in choices.items():
            good=[c for c in cc if not c[5]]
            if not good:raise ValueError('No successful matched format candidate')
            rank,fmt,threshold,cal,pp,failed=min(good,key=lambda c:c[0])
            arm=f'{head}:train_selected_format:{wrapper}'
            predictions.extend([dict(p,arm=arm,selected_format=fmt) for p in pp])
            folds.append({'seed':seed,'outer_fold':fold,'arm':arm,'selected_format':fmt,'threshold':e.finite(threshold),'calibration':cal,
                'selection_tuple':[e.finite(x) if isinstance(x,float) else x for x in rank],
                'candidates':[{'format':c[1],'rank':[e.finite(x) if isinstance(x,float) else x for x in c[0]],'fit_failed':c[5]} for c in cc]})
        print(json.dumps({'seed':seed,'outer_fold_complete':fold,'failures':len(failures)}),flush=True)
        e.jsonl(output/'predictions.jsonl',predictions);e.dump(output/'folds.json',folds);e.dump(output/'timings.json',timings)
    e.verify_frozen(manifest)
    aggregates=[]
    for seed in e.SEEDS:
        for arm in sorted({p['arm'] for p in predictions if p['seed']==seed}):
            pp=[p for p in predictions if p['seed']==seed and p['arm']==arm]
            m=e.counts(outcomes,e.decisions_from_records(pp))
            m.update(seed=seed,arm=arm,prefixes=len(pp),evaluated_outcomes=214,
                complete=len(pp)==176 and len({p['prefix_id'] for p in pp})==176 and not any(p['fit_failed'] for p in pp),evaluation_scope='full214')
            if pp[0]['learned_component']:m.update(e.probability_metrics(rows,pp))
            aggregates.append(m)
    e.dump(output/'metrics.json',{'schema_version':'cheap-matched-4b-v1','aggregates':aggregates,'matched08_control':identity['matched08_control']})
    e.dump(output/'identity08.json',{k:v for k,v in identity.items() if k!='matched08_control'})
    e.dump(output/'failures.json',failures)
    manifest=dict(manifest,phase='COMPLETE' if not failures else 'COMPLETE_WITH_FAILURES',status='COMPLETE' if not failures else 'COMPLETE_WITH_FAILURES',
        input_freeze_sha256=e.digest(output/'input-freeze.json'),source_resources_by_format=e.resources_by_block(rows,records,schemas),
        output_files=[{'path':str(output/name),'sha256':e.digest(output/name)} for name in ('metrics.json','predictions.jsonl','folds.json','timings.json','failures.json','identity08.json','feature-schema.json','fold-allocations.json')])
    e.dump(output/'manifest.json',manifest)
    return manifest


def atomic(path,value):
    temporary=path.with_suffix('.tmp');e.dump(temporary,value);os.replace(temporary,path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=Path('experiments/local_guards'))
    parser.add_argument('--primary',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--freeze-only',action='store_true')
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--resource-lease',action='store_true')
    args=parser.parse_args();primary=args.primary or args.base/'results/cheap-guards/evaluation'
    output=args.output or args.base/'results/cheap-guards/matched-reference'
    if not args.freeze_only and not (args.run and args.resource_lease):parser.error('Use --freeze-only or --run --resource-lease')
    if args.freeze_only:
        manifest=run(args.base,primary,output,freeze_only=True);print(manifest['phase']);return
    lock=args.base/'.runtime/cheap-guards/heavy-model.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    run_path=args.base/'results/cheap-guards/run.json';started=time.time()
    with lock.open('a+') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        lease.seek(0);lease.truncate();lease.write(str(os.getpid()));lease.flush()
        state=json.loads(run_path.read_text());state.setdefault('primary_finished_at',state.get('finished_at'))
        state.update(status='EVALUATING_MATCHED_REFERENCE',lease={'owner':'matched_reference','granted_at':started,'pid':os.getpid()});atomic(run_path,state)
        execution={'argv':sys.argv,'started_at':started,'pid':os.getpid(),'heavy_lock':str(lock),'inference_calls':0,'stdout_log':str(output/'run.log')}
        try:
            manifest=run(args.base,primary,output)
            execution.update(finished_at=time.time(),exit_code=0,phase=manifest['phase'])
            state=json.loads(run_path.read_text());state.update(status='COMPLETE',lease=None,matched_reference_status=manifest['status'],matched_reference_finished_at=time.time());atomic(run_path,state)
        except Exception as exc:
            execution.update(finished_at=time.time(),exit_code=1,error=f'{type(exc).__name__}: {exc}')
            state=json.loads(run_path.read_text());state.update(status='PARTIAL',lease=None,matched_reference_error=execution['error']);atomic(run_path,state)
            raise
        finally:
            output.mkdir(parents=True,exist_ok=True);atomic(output/'execution.json',execution)
            fcntl.flock(lease,fcntl.LOCK_UN)
    print(json.dumps({'phase':manifest['phase'],'output':str(output),'wall_seconds':execution['finished_at']-started}),flush=True)
    completed=json.loads((output/'manifest.json').read_text())
    completed['execution_sha256']=e.digest(output/'execution.json')
    if (output/'run.log').exists():completed['stdout_log_sha256']=e.digest(output/'run.log')
    atomic(output/'manifest.json',completed)


if __name__=='__main__':main()
