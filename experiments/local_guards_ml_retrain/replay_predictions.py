"""Label-blind execution of immutable classifiers with Runtime checker-error policy.

No coercion, repair or schema prefilter. Each frozen callback is revision-bound.
Generic checker exceptions yield UNKNOWN/STOP with unavailable scores; integrity
and IO failures still abort. Raw/gated thresholds and original gates are retained.
"""
from __future__ import annotations
import argparse
from collections import Counter
import importlib
import json
import os
from pathlib import Path
import pickle
import sys
import tempfile
import time
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
    os.environ.setdefault(key,'2')
    if os.environ[key]!='2':raise RuntimeError(key+' must be2')

# IO/exception helpers only. Inference never calls this module's revision2 gate
# or extractor when method_revision is original.
from evaluation_revision2 import (Shards,input_identity,validate_join,prediction_methods,
                                  execution_exception)

ERROR_POLICY='generic checker Exception -> UNKNOWN/STOP; scores unavailable; no input repair'


def load_revision(method_revision,freeze):
    if method_revision not in {'original','revision2'}:raise ValueError('unknown method revision')
    suffix='' if method_revision=='original' else '_revision2'
    modules={name:importlib.import_module(name+suffix) for name in ('experiment','features','models')}
    manifest=modules['experiment'].verify_freeze(freeze)
    if manifest.get('version')!=(1 if method_revision=='original' else 2):
        raise ValueError('method revision does not match freeze version')
    return SimpleNamespace(**modules,manifest=manifest)


def load_model(revision,freeze,method):
    path=freeze/method['model_file'];exp=revision.experiment
    if (exp.digest(path)!=method['model_sha256'] or
            revision.manifest['files'].get(path.name)!=method['model_sha256']):raise ValueError('model hash mismatch')
    if method['thresholds_file'] not in revision.manifest['files']:raise ValueError('unverified thresholds')
    model=pickle.loads(path.read_bytes())
    if model.available_:
        step=model.named_steps['features']
        if step.func is not revision.models.feature_rows or step.kw_args.get('mode')!=method['feature_mode']:
            raise ValueError('model extractor does not match declared revision/mode')
    return model,json.loads((freeze/method['thresholds_file']).read_text())


def extract_batch(revision,rows):
    result={}
    for mode in ('old','new'):
        entries=[]
        for row in rows:
            start=time.perf_counter_ns()
            try:entry=dict(features=revision.features.features(row,mode),error=None)
            except Exception as error:entry=dict(features=None,error=execution_exception(error,'features'))
            entry['feature_ms']=(time.perf_counter_ns()-start)/1e6;entries.append(entry)
        result[mode]=entries
    return result


def score_batch(revision,model,rows,entries,mode):
    """Batch only extractable rows; a failed batch retries each row unchanged."""
    results=[None]*len(rows);fallback=None
    # Frozen unavailable models bypass extraction and return all-zero scores.
    # A cache extraction failure must not invent an error in that code path.
    indices=[]
    for i,entry in enumerate(entries):
        if model.available_ and entry['error'] is not None:
            results[i]=dict(probabilities=None,error=entry['error'],model_amortized_ms=0.,feature_ms=entry['feature_ms'],scores_available=False)
        else:indices.append(i)
    if not indices:return results,None
    batch=revision.models.FeatureBatch([entries[i]['features'] for i in indices],mode) if model.available_ else rows
    start=time.perf_counter_ns()
    try:
        ps=revision.models.probabilities(model,batch)
        if len(ps)!=len(indices):raise ValueError('frozen probability coverage mismatch')
        ms=(time.perf_counter_ns()-start)/1e6/len(indices)
        for i,p in zip(indices,ps,strict=True):
            results[i]=dict(probabilities=p,error=None,model_amortized_ms=ms,
                feature_ms=entries[i]['feature_ms'] if model.available_ else 0.,scores_available=bool(model.available_))
    except Exception as error:
        fallback=dict(error_class=type(error).__name__,error_reason=str(error),failed_batch_ms=(time.perf_counter_ns()-start)/1e6)
        for i in indices:
            start=time.perf_counter_ns()
            try:
                single=revision.models.FeatureBatch([entries[i]['features']],mode) if model.available_ else [rows[i]]
                p=revision.models.probabilities(model,single)[0]
                value=dict(probabilities=p,error=None,scores_available=bool(model.available_))
            except Exception as error:value=dict(probabilities=None,error=execution_exception(error,'model'),scores_available=False)
            results[i]=dict(value,model_amortized_ms=(time.perf_counter_ns()-start)/1e6,
                feature_ms=entries[i]['feature_ms'] if model.available_ else 0.,batch_score_fallback=fallback)
    return results,fallback


def decision(revision,row,scored,thresholds,contract,variant):
    timing={k:scored[k] for k in ('feature_ms','model_amortized_ms')};timing['gate_ms']=0.
    if scored['error'] is not None:return dict(scored['error'],timing=timing)
    p=scored['probabilities'];stage='threshold';raw=None;start=time.perf_counter_ns()
    try:
        if variant=='argmax_diagnostic':
            winners=[k for k in revision.experiment.CLASSES if p[k]==max(p.values())]
            raw=winners[0] if len(winners)==1 else 'UNKNOWN'
        else:raw=revision.experiment.decide([p],thresholds[variant]['thresholds'])[0]
        gate=dict(allow=True,reasons=[])
        if variant=='gated' and raw=='ALLOW':
            stage='gate';start=time.perf_counter_ns()
            try:gate=revision.features.mandatory_proof_gate(row,contract)
            finally:timing['gate_ms']=(time.perf_counter_ns()-start)/1e6
        changed=variant=='gated' and raw=='ALLOW' and not gate['allow']
        d='UNKNOWN' if changed else raw
        return dict(checked=True,decision=d,raw_decision=raw,stop=d!='ALLOW',gate_changed=changed,
            gate_reasons=gate['reasons'],reasons=gate['reasons'],probabilities=p,
            scores_available=scored['scores_available'],timing=timing)
    except Exception as error:
        # Exception STOP is not proof-gate success or a calibrated class score.
        return dict(execution_exception(error,stage),raw_decision=raw,timing=timing)


def predict(method_revision,freeze,observations,metadata,output,batch_size=512,methods=None,contracts=None):
    if batch_size<1:raise ValueError('batch_size must be positive')
    freeze=Path(freeze);revision=load_revision(method_revision,freeze);exp=revision.experiment
    selected=[m for m in revision.manifest['methods'] if (not methods or m['name'] in methods) and (not contracts or m['contract'] in contracts)]
    if methods and set(methods)!={m['name'] for m in selected}:raise ValueError('unknown method selection')
    count=validate_join(observations,exp.keyed(metadata));identity=input_identity(observations,metadata)
    freeze_hash=exp.digest(freeze/'freeze-manifest.json');adapter_hash=exp.digest(Path(__file__))
    adapter_sources={str(p.resolve()):exp.digest(p) for p in (Path(__file__),HERE/'evaluation_revision2.py')}
    expected={};descriptors=[];errors=Counter();fallbacks=[]
    with tempfile.TemporaryDirectory(prefix='finbot-exception-replay-') as td:
        cache=Path(td)/'features.pickle';score_cache=Path(td)/'scores.pickle'
        with cache.open('wb') as stream:
            batch=[]
            for row in exp.read_lines(observations):
                batch.append(row)
                if len(batch)>=batch_size:
                    pickle.dump((batch,extract_batch(revision,batch)),stream,protocol=5);batch=[]
            if batch:pickle.dump((batch,extract_batch(revision,batch)),stream,protocol=5)
        with Shards(output) as sink:
            for method in selected:
                model,thresholds=load_model(revision,freeze,method);contract=method['contract'];mode=method['feature_mode']
                with cache.open('rb') as stream,score_cache.open('wb') as scored_stream:
                    while True:
                        try:batch,features=pickle.load(stream)
                        except EOFError:break
                        indices=[i for i,row in enumerate(batch) if exp.eligible(row,contract)]
                        rows=[batch[i] for i in indices]
                        scores,fallback=score_batch(revision,model,rows,[features[mode][i] for i in indices],mode)
                        if fallback:fallbacks.append(dict(method=method['name'],rows=len(rows),**fallback))
                        pickle.dump((rows,scores),scored_stream,protocol=5)
                for variant in ('raw','gated','argmax_diagnostic'):
                    name=method['name']+'__'+variant;descriptors.append(dict(method,name=name,variant=variant));n=0
                    with score_cache.open('rb') as stream:
                        while True:
                            try:rows,scores=pickle.load(stream)
                            except EOFError:break
                            for row,scored in zip(rows,scores,strict=True):
                                result=decision(revision,row,scored,thresholds,contract,variant)
                                if result.get('execution_error'):errors[(name,result['execution_error_stage'],result['execution_error_class'])]+=1
                                sink.write(contract,name,dict(prefix_id=row['prefix_id'],method=name,contract=contract,variant=variant,
                                    family=method['family'],arm=method['arm'],seed=method['seed'],event_seq=revision.features.obj(row)['event_seq'],**result));n+=1
                    expected[name]=n
    if (freeze_hash!=exp.digest(freeze/'freeze-manifest.json') or
            any(exp.digest(path)!=expected_hash for path,expected_hash in adapter_sources.items())):
        raise ValueError('freeze/adapter changed during replay')
    receipt=dict(version=revision.manifest['version'],**identity,files=sink.files,methods=descriptors,expected_eligible=expected,
        prefix_count=count,freeze_path=str(freeze.resolve()),freeze_sha256=freeze_hash,adapter_path=str(Path(__file__).resolve()),
        adapter_sha256=adapter_hash,adapter_sources=adapter_sources,method_revision=method_revision,labels_opened=False,prediction_dataset_labels_opened=False,fit_called=False,
        error_policy=ERROR_POLICY,error_counts=[dict(method=k[0],stage=k[1],error_class=k[2],rows=v) for k,v in sorted(errors.items())],
        batch_fallbacks=fallbacks,callback_modules={k:getattr(revision,k).__name__ for k in ('experiment','features','models')},
        latency_measured=False,timing_scope='execution diagnostics: per-row extraction; batch score amortized over successful rows, or actual singleton fallback; gate separately')
    exp.write_json(Path(output)/'receipt.json',receipt)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--method-revision',required=True,choices=['original','revision2']);parser.add_argument('--freeze',required=True)
    for name in ('observations','metadata','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--batch-size',type=int,default=512);parser.add_argument('--methods',nargs='+');parser.add_argument('--contracts',nargs='+',choices=['payment_v3','A','B'])
    predict(**vars(parser.parse_args()))

if __name__=='__main__':main()
