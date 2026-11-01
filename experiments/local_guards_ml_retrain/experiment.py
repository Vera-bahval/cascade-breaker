"""Immutable TRAIN/CAL preparation, calibration/freezing, label-blind prediction.

No test/gold inference in predict. Fit never opens outcomes. Invoke individual
CLI stages explicitly; fit is intentionally never run on import or prepare.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import io
import json
from pathlib import Path
import pickle
import sys
import time

import numpy as np
from features import HERE, OLD_SOURCE, POLICY, VERSION_KEYS, obj, features, mandatory_proof_gate
from models import CLASSES, fit_model, probabilities, FeatureBatch

CONTRACTS=('payment_v3','A','B')
SENTINEL=1.000001


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as s:
        for chunk in iter(lambda:s.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def write_json(path,value):
    with Path(path).open('x',encoding='utf8') as s:s.write(canonical(value)+'\n')


def write_lines(path,rows):
    with Path(path).open('xb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as s:
            for row in rows:s.write((canonical(row)+'\n').encode())


def read_lines(path):
    path=Path(path)
    opener=gzip.open if path.suffix=='.gz' else open
    with opener(path,'rt',encoding='utf8') as s:
        for line in s:
            if line.strip():yield json.loads(line)


def keyed(path):
    result={}
    for row in read_lines(path):
        key=row['prefix_id']
        if key in result:raise ValueError('duplicate prefix '+key)
        result[key]=row
    return result


def eligible(row,contract):
    o=obj(row)
    return o.get('checkpoint') in {'P0','P1','P2','P3','P4'} and (contract!='payment_v3' or (o.get('checkpoint')=='P4' and o.get('proposal',{}).get('tool')=='finstripe__create_transfer'))


def reduce_requirements(states):
    values=list(states)
    return 'BLOCK' if 'violated' in values else 'UNKNOWN' if 'unknown' in values or not any(v!='not_applicable' for v in values) else 'ALLOW'


def validate_metadata(metadata):
    ids=set();splits={};base_splits={};episodes={}
    for m in metadata:
        if m['prefix_id'] in ids:raise ValueError('duplicate prefix')
        ids.add(m['prefix_id'])
        if str(m.get('executor','')).lower()=='luna' or m['split'] not in {'TRAIN','CAL'}:raise ValueError('excluded executor/split')
        source=m['source'];split=m['split'];component=(source,m.get('split_group_id',m['group_id']));base=(source,m['group_id']);ep=(source,m['episode_id'])
        for mapping,key in [(splits,component),(base_splits,base),(episodes,ep)]:
            if key in mapping and mapping[key]!=split:raise ValueError('group/episode overlap across TRAIN/CAL')
            mapping[key]=split


def training_weights(metadata):
    """Equal source mass, equal base-group mass; total sample weight = N."""
    if not metadata:return []
    counts=Counter((m['source'],m['group_id']) for m in metadata)
    groups=Counter(s for s,g in counts);n=len(metadata);sources=len(groups)
    return [n/(sources*groups[m['source']]*counts[m['source'],m['group_id']]) for m in metadata]


def prepare(output,archive=None,synthetic=None):
    archive=Path(archive or HERE.with_name('local_guards_v4')/'data');synthetic=Path(synthetic or HERE/'data');output=Path(output)
    if output.exists():raise FileExistsError(output)
    observations=[];metadata=[];labels=[];inputs={}
    for source,base in [('archive',archive),('synthetic',synthetic)]:
        # Metadata chooses TRAIN/CAL before any observation/gold is retained.
        meta={r['prefix_id']:r for r in read_lines(base/'metadata.jsonl.gz') if r.get('split') in {'TRAIN','CAL'} and str(r.get('executor','')).lower()!='luna'}
        keep=set(meta)
        obs={r['prefix_id']:r for r in read_lines(base/'observations.jsonl.gz') if r['prefix_id'] in keep}
        gold={r['prefix_id']:r for r in read_lines(base/'gold-actions.jsonl.gz') if r['prefix_id'] in keep}
        if set(obs)!=keep or set(gold)!=keep:raise ValueError('missing observation/gold')
        for pid,m in meta.items():
            row=obs[pid];new_id=source+':'+pid
            observations.append(dict(row,prefix_id=new_id))
            clean={k:m[k] for k in ('split','checkpoint') if k in m}
            clean.update(prefix_id=new_id,source=source,group_id=source+':'+m['group_id'],
                split_group_id=source+':'+m.get('split_group_id',m['group_id']),episode_id=source+':'+m['episode_id'],event_seq=obj(row)['event_seq'])
            metadata.append(clean)
            if source=='synthetic':ls=gold[pid]['labels']
            else:
                states=gold[pid]['requirements']
                ls={c:reduce_requirements(states.get(k,'not_applicable') for k in POLICY['profiles'][c]) for c in ('A','B')}
                ls['payment_v3']=reduce_requirements([states.get('A08','not_applicable')]) if eligible(row,'payment_v3') else None
            labels.append(dict(prefix_id=new_id,labels={c:ls.get(c) if eligible(row,c) else None for c in CONTRACTS}))
        for n in ('metadata.jsonl.gz','observations.jsonl.gz','gold-actions.jsonl.gz','manifest.json'):
            inputs[str((base/n).resolve())]=digest(base/n)
    validate_metadata(metadata)
    output.mkdir(parents=True)
    for name,rs in [('observations',observations),('metadata',metadata),('labels',labels)]:write_lines(output/(name+'.jsonl.gz'),rs)
    write_json(output/'manifest.json',dict(version=1,inputs=inputs,rows=len(observations),counts=dict(Counter(m['source']+':'+m['split'] for m in metadata)),
        label_recipe='Archive A/B stored independent requirement reducer; payment_v3 stored A08 on compatible baseline scope; synthetic independent supplied labels',
        no_outcomes_loaded=True,test_retained=False,files={n:digest(output/n) for n in ('observations.jsonl.gz','metadata.jsonl.gz','labels.jsonl.gz')}))


def decide(probabilities_,thresholds):
    p=np.asarray([[r[k] for k in CLASSES] for r in probabilities_],dtype=float).reshape(-1,3)
    return decisions_array(p,thresholds['ALLOW'],thresholds['BLOCK']).tolist()


def decisions_array(p,ta,tb):
    a=(p[:,0]>=ta)&(p[:,0]>p[:,1])&(p[:,0]>p[:,2]);b=(p[:,1]>=tb)&(p[:,1]>p[:,0])&(p[:,1]>p[:,2])
    return np.where(a,'ALLOW',np.where(b,'BLOCK','UNKNOWN'))


def episode_layout(metadata,gold):
    order=np.array(sorted(range(len(metadata)),key=lambda i:(metadata[i]['episode_id'],metadata[i].get('event_seq',0),metadata[i].get('prefix_id',''))),dtype=int)
    if not len(order):return dict(order=order,starts=np.array([],int),lengths=np.array([],int),safe=np.array([],bool))
    ids=[metadata[i]['episode_id'] for i in order];starts=np.array([i for i in range(len(ids)) if i==0 or ids[i]!=ids[i-1]],int)
    lengths=np.diff(np.r_[starts,len(order)]);g=np.asarray(gold)[order]
    return dict(order=order,starts=starts,lengths=lengths,safe=np.logical_and.reduceat(g=='ALLOW',starts))


def metric_counts(d,g,layout):
    order=layout['order'];starts=layout['starts'];lengths=layout['lengths'];n=len(order)
    if not n:return dict(episodes=0,correct_episodes=0,safe_episodes=0,safe_stops=0,false_allows=0,reached_actions=0,correct_decisive_actions=0,eligible_actions=0)
    d=np.asarray(d)[order];g=np.asarray(g)[order];idx=np.arange(n)
    if d.dtype.kind in 'iu':
        allow,unknown=0,2
    else:allow,unknown='ALLOW','UNKNOWN'
    stop=np.minimum.reduceat(np.where(d!=allow,idx,n),starts)
    reached=idx<=np.repeat(stop,lengths)
    correct=(d==g)&(d!=unknown)
    return dict(episodes=len(starts),correct_episodes=int(np.logical_and.reduceat(~reached|correct,starts).sum()),
                safe_episodes=int(layout['safe'].sum()),safe_stops=int((layout['safe']&(stop<n)).sum()),
                false_allows=int((reached&(d==allow)&(g!=allow)).sum()),reached_actions=int(reached.sum()),
                correct_decisive_actions=int((reached&correct).sum()),eligible_actions=n)


def rates(counts):
    return dict(counts,correct_episode_coverage=counts['correct_episodes']/counts['episodes'] if counts['episodes'] else 0.,
       safe_stop_fpr=counts['safe_stops']/counts['safe_episodes'] if counts['safe_episodes'] else None,
       correct_action_coverage=counts['correct_decisive_actions']/counts['eligible_actions'] if counts['eligible_actions'] else 0.)


def fast_metrics(decisions,gold,layout):return rates(metric_counts(decisions,gold,layout))


def replay_metrics(decisions,gold,metadata):
    """Straightforward reference replay, intentionally independent from reduceat."""
    groups=defaultdict(list)
    for i,m in enumerate(metadata):groups[m['episode_id']].append(i)
    c=dict(episodes=len(groups),correct_episodes=0,safe_episodes=0,safe_stops=0,false_allows=0,reached_actions=0,correct_decisive_actions=0,eligible_actions=len(metadata))
    for indices in groups.values():
        indices.sort(key=lambda i:(metadata[i].get('event_seq',0),metadata[i].get('prefix_id','')))
        safe=all(gold[i]=='ALLOW' for i in indices);c['safe_episodes']+=safe;solved=True
        for i in indices:
            d=decisions[i];g=gold[i];c['reached_actions']+=1
            c['false_allows']+=d=='ALLOW' and g!='ALLOW'
            correct=d==g and d!='UNKNOWN';c['correct_decisive_actions']+=correct
            solved=solved and correct
            if d!='ALLOW':
                c['safe_stops']+=safe
                break
        c['correct_episodes']+=solved
    return rates(c)


def action_metrics(decisions,gold,metadata):
    layout=episode_layout(metadata,gold);summary=fast_metrics(decisions,gold,layout)
    d=np.asarray(decisions);g=np.asarray(gold)
    summary['per_action_confusion_all_eligible']={a:{b:int(((g==a)&(d==b)).sum()) for b in CLASSES} for a in CLASSES}
    summary['per_action_correct_decisive_all_eligible']=float(((g==d)&(d!='UNKNOWN')).mean()) if len(g) else 0.
    return summary


def calibrate(probabilities_,gold,metadata,gate_allow=None):
    """CAL only. Vectorized first-STOP replay; finite >1 abstention sentinel."""
    p=np.asarray([[r[k] for k in CLASSES] for r in probabilities_],dtype=float).reshape(-1,3)
    if not np.isfinite(p).all() or (p<0).any() or (p>1).any():raise ValueError('invalid probabilities')
    if len(gold)!=len(p) or len(metadata)!=len(p):raise ValueError('CAL length mismatch')
    gate=np.ones(len(p),bool) if gate_allow is None else np.asarray(gate_allow,bool)
    if gate.shape!=(len(p),):raise ValueError('gate length mismatch')
    layout=episode_layout(metadata,gold);g=np.asarray(gold);best=None
    order=layout['order'];p=p[order];gate=gate[order];g=g[order]
    numeric_gold=np.array([CLASSES.index(x) for x in g],dtype=np.uint8)
    ordered_layout=dict(layout,order=np.arange(len(order)))
    grid=[sorted(set(np.quantile(p[:,i],np.linspace(0,1,41)).tolist()+[.5,SENTINEL])) if len(p) else [.5,SENTINEL] for i in (0,1)]
    win_a=(p[:,0]>p[:,1])&(p[:,0]>p[:,2])&gate;win_b=(p[:,1]>p[:,0])&(p[:,1]>p[:,2])
    # Precompute all confidence masks; no feature/proof/episode Python work per grid pair.
    am=[win_a&(p[:,0]>=t) for t in grid[0]];bm=[win_b&(p[:,1]>=t) for t in grid[1]]
    for ta,a in zip(grid[0],am):
        for tb,b in zip(grid[1],bm):
            d=np.where(a,0,np.where(b,1,2)).astype(np.uint8);m=metric_counts(d,numeric_gold,ordered_layout)
            feasible=m['episodes']>0 and m['safe_episodes']>0 and m['false_allows']==0 and m['safe_stops']<=.05*m['safe_episodes']
            if feasible:
                rank=(m['correct_episodes'],-m['safe_stops'],ta,tb)
                if best is None or rank>best[0]:best=(rank,ta,tb,m)
    inverse=np.argsort(order);p=p[inverse];gate=gate[inverse]
    argmax=np.array(CLASSES)[p.argmax(axis=1)] if len(p) else np.array([],str)
    # Tied argmax is UNKNOWN; gates apply only to raw ALLOW.
    if len(p):argmax[(p==p.max(axis=1)[:,None]).sum(axis=1)>1]='UNKNOWN'
    argmax[(argmax=='ALLOW')&~gate]='UNKNOWN'
    if best is None:ta=tb=SENTINEL;feasible=False
    else:_,ta,tb,_=best;feasible=True
    raw=decisions_array(p,ta,tb);gated=raw.copy();gated[(raw=='ALLOW')&~gate]='UNKNOWN'
    return dict(thresholds={'ALLOW':ta,'BLOCK':tb},feasible=feasible,
        infeasibility_reason=None if feasible else 'unassessable_safe_denominator' if not bool(layout['safe'].sum()) else 'no_threshold_satisfies_cal_constraints',
        objective='correct decisive episode coverage; zero reached false ALLOW; safe episode stops <=0.05 including UNKNOWN',
        no_safe_cal_episodes=not bool(layout['safe'].sum()),grid_points={CLASSES[i]:len(grid[i]) for i in (0,1)},
        metrics=action_metrics(gated.tolist(),gold,metadata),unconstrained_argmax=action_metrics(argmax.tolist(),gold,metadata),
        zero_cal_error_is_not_test_guarantee=True)


def sources():
    paths=[HERE/n for n in ('features.py','models.py','experiment.py','v4-policy.json','v4-schema.json','v4-POLICY.md','v3-policy.json','v3-schema.json','v3-POLICY.md','PLAN.md')]+[OLD_SOURCE]
    return {str(p.resolve()):digest(p) for p in paths}


def verify_freeze(freeze):
    freeze=Path(freeze);manifest=json.loads((freeze/'freeze-manifest.json').read_text())
    for path,expected in manifest['sources'].items():
        if digest(path)!=expected:raise ValueError('frozen source hash mismatch: '+path)
    for name,expected in manifest['files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('invalid freeze member')
        if digest(freeze/name)!=expected:raise ValueError('frozen artifact hash mismatch: '+name)
    return manifest


def load_prepared(data):
    data=Path(data);manifest=json.loads((data/'manifest.json').read_text())
    for n,h in manifest['files'].items():
        if digest(data/n)!=h:raise ValueError('prepared hash mismatch: '+n)
    observations=keyed(data/'observations.jsonl.gz');metadata=keyed(data/'metadata.jsonl.gz');labels=keyed(data/'labels.jsonl.gz')
    if set(observations)!=set(metadata) or set(observations)!=set(labels):raise ValueError('prepared prefix mismatch')
    validate_metadata(list(metadata.values()))
    for pid,row in labels.items():
        if any(v not in (*CLASSES,None) for v in row['labels'].values()):raise ValueError('invalid supervision')
    return observations,metadata,labels


def collision_audit(ids,feature_cache,metadata,labels):
    """Diagnostics only: archive split is preserved even if generic vectors repeat."""
    output={}
    for mode,cache in feature_cache.items():
        fingerprints={pid:hashlib.sha256(canonical(cache[pid]).encode()).hexdigest() for pid in ids}
        for contract in CONTRACTS:
            for source in ('archive','mixed'):
                train=[pid for pid in ids if metadata[pid]['split']=='TRAIN' and labels[pid]['labels'].get(contract) is not None and (source=='mixed' or metadata[pid]['source']=='archive')]
                cal=[pid for pid in ids if metadata[pid]['split']=='CAL' and labels[pid]['labels'].get(contract) is not None]
                train_vectors=defaultdict(list)
                for pid in train:train_vectors[fingerprints[pid]].append(labels[pid]['labels'][contract])
                overlap=set(train_vectors)&{fingerprints[pid] for pid in cal}
                conflicts={h:vs for h,vs in train_vectors.items() if len(set(vs))>1}
                output[contract+'__'+mode+'__'+source]=dict(train_rows=len(train),cal_rows=len(cal),train_unique_vectors=len(train_vectors),
                    train_cal_identical_vectors=len(overlap),cal_rows_matching_train=sum(fingerprints[pid] in overlap for pid in cal),
                    train_vectors_with_conflicting_labels=len(conflicts),train_rows_in_label_conflicts=sum(map(len,conflicts.values())))
    return output


def fit(data,output):
    """Explicit full72 fitting entry point, called only after code/data review."""
    data=Path(data);output=Path(output)
    if output.exists():raise FileExistsError(output)
    observations,metadata,labels=load_prepared(data)
    before=sources();output.mkdir(parents=True);methods=[]
    ids=list(observations)
    feature_cache={mode:{pid:features(observations[pid],mode) for pid in ids} for mode in ('old','new')}
    write_json(output/'feature-collisions.json',collision_audit(ids,feature_cache,metadata,labels))
    for contract in CONTRACTS:
        selected=[pid for pid in ids if eligible(observations[pid],contract) and labels[pid]['labels'].get(contract) is not None]
        cal=[pid for pid in selected if metadata[pid]['split']=='CAL'];cal_rows=[observations[pid] for pid in cal]
        gold=[labels[pid]['labels'][contract] for pid in cal];cm=[metadata[pid] for pid in cal]
        gate_started=time.perf_counter();gates=[mandatory_proof_gate(row,contract) for row in cal_rows]
        cal_gate_seconds=time.perf_counter()-gate_started
        for source in ('archive','mixed'):
            train=[pid for pid in selected if metadata[pid]['split']=='TRAIN' and (source=='mixed' or metadata[pid]['source']=='archive')]
            weights=training_weights([metadata[pid] for pid in train]);ys=[labels[pid]['labels'][contract] for pid in train]
            for mode in ('old','new'):
                tr=FeatureBatch([feature_cache[mode][pid] for pid in train],mode)
                cr=FeatureBatch([feature_cache[mode][pid] for pid in cal],mode)
                for family in ('logistic','catboost'):
                    for seed in (17,29,43):
                        name=f'{contract}__{mode}__{source}__{family}__{seed}'
                        model=fit_model(family,tr,ys,weights,mode,seed)
                        model.provenance_.update(training_prefix_hash=hashlib.sha256(canonical(train).encode()).hexdigest(),
                           training_weights_hash=hashlib.sha256(canonical(weights).encode()).hexdigest(),
                           input_manifest_hash=digest(data/'manifest.json'),source_hashes=before)
                        filename=name+'.pickle'
                        with (output/filename).open('xb') as s:pickle.dump(model,s,protocol=5)
                        write_json(output/(name+'.model.json'),model.provenance_)
                        start=time.perf_counter();ps=probabilities(model,cr);inference_seconds=time.perf_counter()-start
                        raw=calibrate(ps,gold,cm);gated=calibrate(ps,gold,cm,[g['allow'] for g in gates])
                        write_json(output/(name+'.thresholds.json'),{'raw':raw,'gated':gated})
                        for variant,threshold in [('raw',raw),('gated',gated)]:
                            ds=decide(ps,threshold['thresholds'])
                            write_lines(output/(name+'.'+variant+'.cal.jsonl.gz'),(
                                dict(prefix_id=pid,decision='UNKNOWN' if variant=='gated' and d=='ALLOW' and not gate['allow'] else d,
                                raw_decision=d,gate_changed=variant=='gated' and d=='ALLOW' and not gate['allow'],
                                gate_reasons=gate['reasons'] if variant=='gated' and d=='ALLOW' else [],probabilities=p,
                                gold=g,event_seq=obj(observations[pid])['event_seq'],checked=True)
                                for pid,d,gate,p,g in zip(cal,ds,gates,ps,gold)))
                        methods.append(dict(name=name,contract=contract,arm=mode+'/'+source,feature_mode=mode,source=source,
                            family=family,seed=seed,model_file=filename,model_sha256=digest(output/filename),
                            thresholds_file=name+'.thresholds.json',available=model.available_,
                            cal_batch_inference_seconds=inference_seconds,cal_gate_batch_seconds=cal_gate_seconds,cal_rows=len(cal),train_rows=len(train)))
    if before!=sources():raise ValueError('sources changed during fit; incomplete output is not a valid freeze')
    files={p.name:digest(p) for p in sorted(output.iterdir()) if p.is_file()}
    write_json(output/'freeze-manifest.json',dict(version=1,methods=methods,sources=before,files=files,
       data_manifest=str((data/'manifest.json').resolve()),data_manifest_sha256=digest(data/'manifest.json'),
       gate_material_version_keys=VERSION_KEYS,gate_nonmaterial_history=['binding_hold','human_cleared','prior_completed_transfers'],
       threshold_sentinel=SENTINEL,threshold_tie='coverage; fewer safe stops; larger ALLOW then BLOCK threshold',
       unavailable='no classes -> scores all0, UNKNOWN; one class -> constant observed class',
       producer_trust='trusted adapter/declared fixture only; source tags do not authenticate JSON',
       timing='CAL batch score time; prediction records amortized batch model score time separately from gate time',
       proof_gate_attribution='separately calibrated raw and gated; ALLOW->UNKNOWN only; gate not ML',
       cal='same archive+synthetic CAL across all arms, no hyperparameter search/refit; no safe denominator is flagged, not a measured FPR'))


def predict(freeze,observations_path,metadata_path,output):
    """Label-blind inference: freeze + observation file + non-label metadata only."""
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    freeze=Path(freeze);manifest=verify_freeze(freeze)
    observations=keyed(observations_path);meta=keyed(metadata_path)
    if set(observations)!=set(meta):raise ValueError('prediction metadata mismatch')
    # Receipt hashes observation/metadata and freeze before scoring, never opens gold.
    receipt=output.with_name(output.name+'.receipt.json')
    if receipt.exists():raise FileExistsError(receipt)
    receipt_data=dict(freeze_sha256=digest(freeze/'freeze-manifest.json'),observations_sha256=digest(observations_path),metadata_sha256=digest(metadata_path),labels_opened=False)
    def predictions():
        for method in manifest['methods']:
            filename=method['model_file']
            if filename not in manifest['files'] or digest(freeze/filename)!=method['model_sha256']:raise ValueError('unverified pickle')
            with (freeze/filename).open('rb') as s:model=pickle.load(s)
            ids=[pid for pid,row in observations.items() if eligible(row,method['contract'])];rs=[observations[pid] for pid in ids]
            started=time.perf_counter();ps=probabilities(model,rs);model_ms=(time.perf_counter()-started)*1000/max(1,len(rs))
            if method['thresholds_file'] not in manifest['files']:raise ValueError('unverified thresholds')
            thresholds=json.loads((freeze/method['thresholds_file']).read_text())
            decisions={variant:decide(ps,thresholds[variant]['thresholds']) for variant in ('raw','gated')}
            gates=[]
            for i,row in enumerate(rs):
                started=time.perf_counter()
                gate=mandatory_proof_gate(row,method['contract']) if decisions['gated'][i]=='ALLOW' else {'allow':True,'reasons':[]}
                gate['timing_ms']=(time.perf_counter()-started)*1000;gates.append(gate)
            for variant in ('raw','gated'):
                ds=decisions[variant]
                for pid,d,p,gate in zip(ids,ds,ps,gates):
                    changed=variant=='gated' and d=='ALLOW' and not gate['allow']
                    yield dict(method=method['name']+'__'+variant,contract=method['contract'],arm=method['arm'],family=method['family'],seed=method['seed'],variant=variant,
                        prefix_id=pid,decision='UNKNOWN' if changed else d,raw_decision=d,gate_changed=changed,
                        gate_reasons=gate['reasons'] if variant=='gated' and d=='ALLOW' else [],probabilities=p,
                        timing={'model_amortized_ms':model_ms,'gate_ms':gate['timing_ms'] if variant=='gated' and d=='ALLOW' else 0.},
                        checked=True,event_seq=obj(observations[pid])['event_seq'])
    write_lines(output,predictions())
    receipt_data['predictions_sha256']=digest(output);write_json(receipt,receipt_data)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--output',required=True);p.add_argument('--archive');p.add_argument('--synthetic')
    p=sub.add_parser('fit');p.add_argument('--data',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('predict');p.add_argument('--freeze',required=True);p.add_argument('--observations',required=True);p.add_argument('--metadata',required=True);p.add_argument('--output',required=True)
    args=vars(parser.parse_args());command=args.pop('command')
    if command=='predict':args['observations_path']=args.pop('observations');args['metadata_path']=args.pop('metadata')
    globals()[command](**args)

if __name__=='__main__':main()
