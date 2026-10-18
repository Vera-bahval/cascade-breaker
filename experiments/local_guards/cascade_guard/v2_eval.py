"""Corrected-input archive fitting and sealed external evaluation.

The train command never accepts an external dataset or its labels. Models,
thresholds, candidate selections, and exact input/code hashes are frozen before
external predictions. The score command is a separate, irreversible unblinding.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import itertools
import json
import math
from pathlib import Path
import time

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import cheap_eval as old
from .dataset import read_jsonl
from .ml import weights
from . import rules, rules_v2
from .v2_features import feature_types
from .v2_legacy_rules import row_rule_flags

SEEDS=(17,29,43)
POLICIES=('A_joint','B2_independent','Blegacy_independent','C_lowest')
WRAPPERS=('none','original_rules','frozen_rules_v2')
MAIN=('J_seq','G22','G86','N','M')
SEQUENCE=('J_cur','J_seq','J_agg','J_dynamic','J_prior')
CB=dict(iterations=200,depth=3,learning_rate=.03,l2_leaf_reg=5,loss_function='Logloss',thread_count=2,allow_writing_files=False,verbose=False)
FPR_KEY='p4_reached_safe93_interruption'


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def jsonl(path,rows):
    Path(path).write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def th(value):return math.inf if value in (None,'infinity') else float(value)


def encode(value):return 'infinity' if math.isinf(value) else float(value)


def metric(rows,probs,outcomes,threshold,flags):
    decision=old.decisions(rows,probs,threshold,flags)
    for row in rows:
        if row['prefix_id'] in getattr(flags,'unknowns',set()) and decision.get(row['episode_id'],{}).get('stop'):
            decision[row['episode_id']]['unknown']=True
    return old.counts(outcomes,decision)


def curves(rows,probs,outcomes,flags):
    thresholds=[math.inf]+sorted({float(p) for p in probs if p is not None and math.isfinite(p)},reverse=True)
    return [(t,metric(rows,probs,outcomes,t,flags)) for t in thresholds]


def choose(rows,probs,outcomes,flags,policy,denominator='reached',target=.05,*,cached=None):
    if policy not in POLICIES:raise ValueError('Unknown policy')
    key=FPR_KEY if denominator=='reached' else 'raw_episode_fpr'
    joint=cached[0] if cached is not None else curves(rows,probs,outcomes,flags)
    alone=(cached[1] if cached is not None else curves(rows,probs,outcomes,{})) if policy.startswith('B') else joint
    if not alone or alone[0][1][key]['rate'] is None:raise ValueError('No safe calibration population')
    feasible=[(t,m) for t,m in alone if m[key]['rate']<=target]
    if not feasible:t,selection=alone[0]
    elif policy=='C_lowest':t,selection=min(feasible,key=lambda tm:tm[0])
    else:t,selection=min(feasible,key=lambda tm:(-tm[1]['harm_prevented_counterfactual']['rate'],tm[1][key]['k'],-tm[0]))
    final=dict(joint)[t]
    return t,{'policy':policy,'denominator':denominator,'fpr_key':key,'target':target,'component_feasible':bool(feasible),
              'final_feasible':final[key]['rate']<=target,'selection_metrics':selection,'metrics':final,
              'fallback':None if feasible else 'infinity; mandatory UNKNOWN/rules may exceed target'},joint


def rank(config,cal,cost,policy):
    m=cal['selection_metrics'] if policy=='Blegacy_independent' else cal['metrics']
    feasible=cal['component_feasible'] if policy=='Blegacy_independent' else cal['final_feasible']
    return (not feasible,-m['harm_prevented_counterfactual']['rate'],m[cal['fpr_key']]['k'],cost,name(config))


def configurations(blocks):
    result=[]
    for size in range(1,len(MAIN)+1):
        for bs in itertools.combinations(MAIN,size):
            if set(bs)<=set(blocks):
                result += [('catboost',bs,tab) for tab in (False,True)]
    for b in blocks:
        for tab in (False,True):
            c=('catboost',(b,),tab)
            if c not in result:result.append(c)
        result.append(('scalar',(b,),False))
    result += [('catboost',(),True),('logistic',(),True),('tfidf',(),False)]
    if 'J_cur' in blocks:result.append(('logistic',('J_cur',),True))
    return result


def name(config):
    kind,bs,tab=config
    return kind+':'+('+'.join(bs) if bs else ('tabular' if tab else 'canonical_text'))+('+tabular' if bs and tab else '')


def primary(config):return config[0]=='catboost' and bool(config[1]) and set(config[1])<=set(MAIN)


def known(row,config,records,schemas):
    return all((rec:=records.get((row['prefix_id'],b))) is not None and rec['status']=='OK' and sorted(rec['features'])==schemas[b] for b in config[1])


def block_cost(rows,config,records):
    costs=[]
    for row in rows:
        values=[old.latency(records.get((row['prefix_id'],b))) for b in config[1]]
        if any(v is None for v in values):return math.inf
        costs.append(sum(values))
    return float(np.median(costs)) if costs else 0.


@dataclass
class Model:
    config:tuple
    seed:int
    schemas:dict
    tab_schema:dict
    estimator:object=None
    columns:object=None

    def x(self,rows,records):
        if self.config[0]=='tfidf':return [r['text'] for r in rows]
        result={}
        if self.config[2]:
            for key,kind in self.tab_schema.items():
                vals=[r['tabular_features'].get(key) for r in rows]
                result['tab:'+key]=[('MISSING' if v is None else str(v)) for v in vals] if kind=='categorical' else [np.nan if v is None else float(v) for v in vals]
                result['tab_missing:'+key]=[int(v is None) for v in vals]
        for b in self.config[1]:
            for feature in self.schemas[b]:result[b+':'+feature]=[records[(r['prefix_id'],b)]['features'][feature] for r in rows]
        return pd.DataFrame(result,index=range(len(rows)))

    def fit(self,rows,records):
        rows=[r for r in rows if known(r,self.config,records,self.schemas)]
        if self.config[0]=='scalar':return self
        if len({r['label'] for r in rows})!=2:raise ValueError('Training population lacks two known classes')
        x=self.x(rows,records);y=[r['label'] for r in rows]
        if self.config[0]=='tfidf':
            self.estimator=Pipeline([('tfidf',TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),max_features=20000,min_df=2,sublinear_tf=True)),('classifier',LogisticRegression(C=1,penalty='l2',max_iter=2000,random_state=self.seed))])
            self.estimator.fit(x,y,classifier__sample_weight=weights(rows))
        elif self.config[0]=='catboost':
            self.columns=list(x.select_dtypes(include=['object','str','string']).columns)
            self.estimator=CatBoostClassifier(**CB,random_seed=self.seed)
            self.estimator.fit(x,y,cat_features=self.columns,sample_weight=weights(rows))
        else:
            cats=list(x.select_dtypes(include=['object','str','string']).columns);nums=[c for c in x if c not in cats]
            prep=ColumnTransformer([('numerical',Pipeline([('fill',SimpleImputer(keep_empty_features=True)),('scale',StandardScaler())]),nums),('categorical',OneHotEncoder(handle_unknown='ignore'),cats)])
            self.estimator=Pipeline([('features',prep),('classifier',LogisticRegression(C=1,penalty='l2',max_iter=2000,random_state=self.seed))])
            self.estimator.fit(x,y,classifier__sample_weight=weights(rows))
        return self

    def predict(self,rows,records):
        good=[r for r in rows if known(r,self.config,records,self.schemas)]
        if not good:return [None]*len(rows)
        if self.config[0]=='scalar':values=[records[(r['prefix_id'],self.config[1][0])]['scalar_risk'] for r in good]
        else:values=self.estimator.predict_proba(self.x(good,records))[:,1]
        pp={r['prefix_id']:float(p) for r,p in zip(good,values) if p is not None and math.isfinite(p)}
        return [pp.get(r['prefix_id']) for r in rows]


def schema(rows):
    result=feature_types()
    for row in rows:
        for k,v in row['tabular_features'].items():
            if v is None:continue
            kind='numeric' if isinstance(v,(int,float,bool)) else 'categorical'
            if k in result and result[k]!=kind:raise ValueError('Mixed tabular types: '+k)
            result[k]=kind
    return dict(sorted(result.items()))


class RuleMap(dict):
    """Boolean stop flags plus explicit missing-evidence UNKNOWN diagnostics."""
    def __init__(self,values,unknowns=()):
        super().__init__(values);self.unknowns=set(unknowns)


def flags_for(rows):
    values,diagnostics=row_rule_flags(rows)
    return {w:RuleMap(values[w],[] if w=='none' else [pid for pid,dd in diagnostics.items() if dd['R1' if w=='original_rules' else 'R2']['status']=='UNKNOWN']) for w in WRAPPERS}


def predictions(rows,probs,threshold,flags,**meta):
    result=[]
    for r,p in zip(rows,probs):
        missing_score=p is None or not math.isfinite(p)
        unknown=missing_score or r['prefix_id'] in getattr(flags,'unknowns',set())
        result.append(dict(meta,prefix_id=r['prefix_id'],episode_id=r['episode_id'],cut_seq=r['cut_seq'],
            probability=None if missing_score else p,threshold=encode(threshold),unknown=unknown,rule_stop=bool(flags.get(r['prefix_id'])),
            block=bool(unknown or flags.get(r['prefix_id']) or p>=threshold)))
    return result


def outcome_subset(outcomes,ids):return [o for o in outcomes if o['episode_id'] in set(ids)]

def summarize(pp,rows,outcomes,scope):
    grouped=defaultdict(list);lookup={r['prefix_id']:r for r in rows}
    for r in pp:grouped[(r['policy'],r['denominator'],r['seed'],r['arm'])].append(r)
    result=[]
    for (policy,den,seed,arm),pred in sorted(grouped.items()):
        if len(pred)!=len(rows) or len({p['prefix_id'] for p in pred})!=len(rows):raise ValueError('Incomplete predictions: '+arm)
        m=old.counts(outcomes,old.decisions_from_records(pred));m.update(policy=policy,denominator=den,seed=seed,arm=arm,prefixes=len(rows),scope=scope)
        if all(p.get('learned_component') for p in pred):
            m.update(old.probability_metrics([lookup[p['prefix_id']] for p in pred],pred))
        result.append(m)
    return result


def validate_archive(rows,outcomes,alloc):
    if len(rows)!=176 or len({r['prefix_id'] for r in rows})!=176:raise ValueError('Archive must be 176 unique corrected P4 prefixes')
    expected={r['episode_id'] for r in rows}
    if len(outcomes)!=214 or sum(o['strict_harm'] for o in outcomes)!=83:raise ValueError('Archive outcomes changed')
    if len({o['episode_id'] for o in outcomes if not o['strict_harm']} & expected)!=93:raise ValueError('Reached safe denominator drift')
    labels={o['episode_id']:int(o['strict_harm']) for o in outcomes}
    for r in rows:
        if r['label']!=labels[r['episode_id']]:raise ValueError('Row label differs from frozen outcome')
    for seed in SEEDS:
        aa=[a for a in alloc if a['seed']==seed]
        if len(aa)!=3:raise ValueError('Outer split count')
        if set(x for a in aa for x in a['test_episode_ids'])!={o['episode_id'] for o in outcomes}:raise ValueError('Outer split coverage')
        for a in aa:
            if set(a['train_groups'])&set(a['test_groups']):raise ValueError('Group leakage')
            for inner in a['inner']:
                if set(inner['train_groups'])&set(inner['test_groups']):raise ValueError('Inner group leakage')
                if not (set(inner['train_episode_ids'])|set(inner['test_episode_ids']))<=set(a['train_episode_ids']):raise ValueError('Inner episode leakage')


def freeze_spec(output,rows_path,outcomes_path,record_paths,allocation_path):
    output.mkdir(parents=True,exist_ok=True)
    records,schemas=old.load_records(record_paths)
    rows=list(read_jsonl(rows_path));outcomes=list(read_jsonl(outcomes_path));alloc=json.loads(allocation_path.read_text())
    validate_archive(rows,outcomes,alloc)
    tabkeys=set(feature_types())
    if any(set(r['tabular_features'])!=tabkeys for r in rows):raise ValueError('Canonical tabular fields differ from public feature schema')
    ids={r['prefix_id'] for r in rows}
    for b in schemas:
        if not all((pid,b) in records for pid in ids):raise ValueError('Incomplete archive feature block: '+b)
    cfgs=configurations(sorted(schemas))
    source=[Path(__file__),Path(old.__file__),Path(rules.__file__),Path(rules_v2.__file__),Path(__file__).with_name('v2_features.py'),Path(__file__).with_name('v2_legacy_rules.py'),Path(__file__).with_name('v2_inputs.py'),Path(__file__).with_name('ml.py'),Path(__file__).with_name('night_ml.py'),rows_path,outcomes_path,allocation_path]+record_paths
    spec={'schema':'guard-v2-evaluation-v1','scope':'archive development, independently authored prospective synthetic test separately sealed',
          'primary_policy':'A_joint','sensitivity_policies':list(POLICIES[1:]),'primary_fpr_denominator':'reached-safe 93; identical P4 decision support as future test',
          'legacy_denominator':'all-safe131 diagnostic only; never claim identical calibration constraint',
          'threshold_grid':'infinity and exact unique observed scores with >=; no nextafter rounding',
          'unknown':'mandatory STOP, retained in safe denominator; scalar outputs are not probabilities of harm',
          'final_training':'existing outer fold0 perseed: fit TRAIN(2/3archive); select candidates on inner grouped OOF of TRAIN only; thresholds from untouched CAL(outer fold0 test), same fitted model used external test; no postcalibration refit',
          'known_limitation':'small group calibration population; empirical FPR budget is not a guarantee on novel families; originalarchiveCV is development data',
          'selection':'A/B2/C: wrapped feasible,maxrecall,minFP,minsourcecost,lexical; Blegacy standalone calibration/selection then OR wrapper',
          'selectors':{'train_selected':'62 primary cheap block combinations','train_selected_all':'all frozen supervised and scalar configs; innerTRAIN selection only; mixed-head probability metrics suppressed'},
          'tabular_schema':schema(rows),'feature_schemas':schemas,'configs':[name(c) for c in cfgs],'cb':CB,
          'seeds':list(SEEDS),'wrappers':list(WRAPPERS),'policies':list(POLICIES),
          'files':[{'path':str(p.resolve()),'sha256':sha(p)} for p in source],'created_unix':time.time()}
    path=output/'training-input-freeze.json'
    if path.exists():
        before=json.loads(path.read_text())
        if {k:v for k,v in before.items() if k!='created_unix'}!={k:v for k,v in spec.items() if k!='created_unix'}:raise ValueError('Training freeze changed; new generation required')
    else:write(path,spec)
    return rows,outcomes,records,schemas,alloc,cfgs,spec


def run_train(output,rows_path,outcomes_path,record_paths,allocation_path):
    if (output/'METHODS_FROZEN.json').exists():raise ValueError('Already frozen; cannot refit')
    rows,outcomes,records,schemas,alloc,cfgs,spec=freeze_spec(output,rows_path,outcomes_path,record_paths,allocation_path)
    fl=flags_for(rows);write(output/'rule-diagnostics.json',row_rule_flags(rows)[1]);
    write(output/'tabular-coverage.json',{k:{'kind':kind,'observed_rows':sum(r['tabular_features'].get(k) is not None for r in rows),
        'distinct_observed':len({str(r['tabular_features'][k]) for r in rows if r['tabular_features'].get(k) is not None})} for k,kind in spec['tabular_schema'].items()})
    cv=[];folds=[];timings=[];all_curves=[];final_choices=[];modeldir=output/'models';modeldir.mkdir(exist_ok=True)
    final_models=[];outer_score_cache={};selected_configs={};ts=spec['tabular_schema']
    for allocation in alloc:
        seed=allocation['seed'];fold=allocation['outer_fold'];train=[r for r in rows if r['episode_id'] in allocation['train_episode_ids']];test=[r for r in rows if r['episode_id'] in allocation['test_episode_ids']]
        train_out=outcome_subset(outcomes,allocation['train_episode_ids']);calibrations={};outerprobs={}
        for config in cfgs:
            modelname=name(config);oof={};start=time.perf_counter()
            for inner in allocation['inner']:
                tr=[r for r in train if r['episode_id'] in inner['train_episode_ids']];va=[r for r in train if r['episode_id'] in inner['test_episode_ids']]
                fitted=Model(config,seed+inner['inner_fold'],schemas,ts).fit(tr,records);pp=fitted.predict(va,records);oof.update(zip([r['prefix_id'] for r in va],pp))
            probs=[oof[r['prefix_id']] for r in train]
            fitted=Model(config,seed,schemas,ts).fit(train,records);start_predict=time.perf_counter();pp=fitted.predict(test,records);prediction_ms=(time.perf_counter()-start_predict)*1000
            if fold==0:
                filename=f'{seed}-{cfgs.index(config):03d}.joblib';joblib.dump(fitted,modeldir/filename)
                final_models.append({'seed':seed,'config':modelname,'filename':filename,'sha256':sha(modeldir/filename),'blocks':list(config[1]),'kind':config[0],
                    'training_episode_ids':allocation['train_episode_ids'],'calibration_episode_ids':allocation['test_episode_ids'],'post_calibration_refit':False})
            outerprobs[modelname]=pp;outer_score_cache.setdefault((seed,modelname),{}).update(zip([r['prefix_id'] for r in test],pp))
            timings.append({'seed':seed,'outer_fold':fold,'config':modelname,'fit_and_inner_predict_ms':(time.perf_counter()-start)*1000-prediction_ms,'outer_prediction_ms':prediction_ms})
            curve_cache={w:curves(train,probs,train_out,fl[w]) for w in WRAPPERS}
            for wrapper in WRAPPERS:
                for den in ('reached','legacy_all_safe'):
                    for policy in POLICIES:
                        threshold,cal,curve=choose(train,probs,train_out,fl[wrapper],policy,den,cached=(curve_cache[wrapper],curve_cache['none']))
                        key=(policy,den,wrapper,modelname);calibrations[key]=(threshold,cal)
                        folds.append({'seed':seed,'outer_fold':fold,'config':modelname,'wrapper':wrapper,'denominator':den,'policy':policy,'threshold':encode(threshold),'calibration':cal})
                        # Save one exact inner curve per wrapper; selection policies share grid.
                        if policy=='A_joint' and den=='reached':
                            all_curves.extend({'seed':seed,'outer_fold':fold,'config':modelname,'wrapper':wrapper,'scope':'inner_oof_only','threshold':encode(t),'metrics':m} for t,m in curve)
                        cv.extend(predictions(test,pp,threshold,fl[wrapper],seed=seed,outer_fold=fold,arm=modelname+':'+wrapper,policy=policy,denominator=den,learned_component=config[0]!='scalar'))
        for wrapper in WRAPPERS:
            for den in ('reached','legacy_all_safe'):
                for policy in POLICIES:
                    for selector,candidates in (('train_selected',[c for c in cfgs if primary(c)]),('train_selected_all',cfgs)):
                        if not candidates:continue
                        selected=min(candidates,key=lambda c:rank(c,calibrations[policy,den,wrapper,name(c)][1],block_cost(train,c,records),policy))
                        threshold,cal=calibrations[policy,den,wrapper,name(selected)]
                        if fold==0:selected_configs[selector,seed,policy,den,wrapper]=selected
                        cv.extend(predictions(test,outerprobs[name(selected)],threshold,fl[wrapper],seed=seed,outer_fold=fold,arm=selector+':'+wrapper,policy=policy,denominator=den,learned_component=selected[0]!='scalar',selected_config=name(selected)))
    # Final thresholds use untouched CAL scores from the exact stored TRAIN fit.
    # Candidate identity is already fixed on inner TRAIN OOF above. CAL cannot
    # choose a method, representation, wrapper, or policy.
    for seed in SEEDS:
        allocation=next(a for a in alloc if a['seed']==seed and a['outer_fold']==0)
        calibration_rows=[r for r in rows if r['episode_id'] in allocation['test_episode_ids']]
        calibration_outcomes=outcome_subset(outcomes,allocation['test_episode_ids'])
        calibrations={}
        for config in cfgs:
            modelname=name(config);probs=[outer_score_cache[seed,modelname][r['prefix_id']] for r in calibration_rows]
            curve_cache={w:curves(calibration_rows,probs,calibration_outcomes,fl[w]) for w in WRAPPERS}
            for wrapper in WRAPPERS:
                for den in ('reached','legacy_all_safe'):
                    for policy in POLICIES:
                        threshold,cal,curve=choose(calibration_rows,probs,calibration_outcomes,fl[wrapper],policy,den,cached=(curve_cache[wrapper],curve_cache['none']))
                        calibrations[policy,den,wrapper,modelname]=(threshold,cal)
                        final_choices.append({'seed':seed,'arm':modelname+':'+wrapper,'config':modelname,'wrapper':wrapper,'policy':policy,'denominator':den,'threshold':encode(threshold),'calibration':cal,'learned_component':config[0]!='scalar',
                            'calibration_source':'untouched outerfold0 CAL; same TRAIN model later used external test'})
        for wrapper in WRAPPERS:
            for den in ('reached','legacy_all_safe'):
                for policy in POLICIES:
                    for selector in ('train_selected','train_selected_all'):
                        if (selector,seed,policy,den,wrapper) not in selected_configs:continue
                        selected=selected_configs[selector,seed,policy,den,wrapper]
                        threshold,cal=calibrations[policy,den,wrapper,name(selected)]
                        final_choices.append({'seed':seed,'arm':selector+':'+wrapper,'config':name(selected),'wrapper':wrapper,'policy':policy,'denominator':den,'threshold':encode(threshold),'calibration':cal,'learned_component':selected[0]!='scalar','selected_config':name(selected),
                            'candidate_selection_source':'inner grouped OOF of TRAIN only',
                            'calibration_source':'untouched outerfold0 CAL; no postcalibration refit'})
    jsonl(output/'archive-oof-scores.jsonl',({'seed':seed,'config':config,'prefix_id':pid,'probability':p} for (seed,config),values in outer_score_cache.items() for pid,p in values.items()))
    add_controls(cv,rows)
    jsonl(output/'archive-predictions.jsonl',cv);jsonl(output/'inner-curves.jsonl',all_curves);write(output/'fold-calibrations.json',folds);write(output/'timings.json',timings)
    write(output/'archive-metrics.json',{'aggregates':summarize(cv,rows,outcomes,'posthoc corrected archive nested CV')});write(output/'final-choices.json',final_choices);write(output/'models.json',final_models)
    files=[output/n for n in ('training-input-freeze.json','archive-predictions.jsonl','archive-oof-scores.jsonl','inner-curves.jsonl','fold-calibrations.json','final-choices.json','models.json')]+list(modeldir.glob('*.joblib'))
    write(output/'METHODS_FROZEN.json',{'created_unix':time.time(),'stage':'BEFORE_EXTERNAL_OBSERVATIONS_AND_LABELS','external_inputs_opened':False,'primary_policy':'A_joint','files':[{'path':str(p.resolve()),'sha256':sha(p)} for p in files]})
    return {'models':len(final_models),'configs':len(cfgs),'predictions':len(cv),'methods_frozen':True}


def add_controls(pp,rows):
    flags=flags_for(rows)
    for seed in SEEDS:
        for arm,wrapper in [('NoDefense','none'),('R1','original_rules'),('R2','frozen_rules_v2')]:
            for policy in POLICIES:
                for den in ('reached','legacy_all_safe'):
                    pp.extend(predictions(rows,[0.]*len(rows),math.inf,flags[wrapper],seed=seed,arm=arm,policy=policy,denominator=den,learned_component=False))


def verify_frozen(output):
    freeze=json.loads((output/'METHODS_FROZEN.json').read_text())
    for entry in freeze['files']:
        if sha(entry['path'])!=entry['sha256']:raise ValueError('Frozen method hash differs: '+entry['path'])
    spec=json.loads((output/'training-input-freeze.json').read_text())
    for entry in spec['files']:
        if sha(entry['path'])!=entry['sha256']:raise ValueError('Frozen training/source hash differs: '+entry['path'])
    return freeze


def run_predict(output,rows_path,record_paths,destination):
    verify_frozen(output)
    if destination.exists():raise ValueError('External prediction destination exists; cannot rerun after unblind')
    rows=list(read_jsonl(rows_path))
    if any('label' in r or 'strict_harm' in r or 'family' in r for r in rows):raise ValueError('External observable rows contain labels/family metadata')
    records,schemas=old.load_records(record_paths);spec=json.loads((output/'training-input-freeze.json').read_text())
    expected=spec['feature_schemas']
    if any(set(r['tabular_features'])!=set(spec['tabular_schema']) for r in rows):raise ValueError('External canonical tabular schema mismatch')
    for b in schemas:
        if b in expected and schemas[b]!=expected[b]:raise ValueError('Archive/test feature schema mismatch: '+b)
    flags=flags_for(rows);rule_diagnostics=row_rule_flags(rows)[1];models=json.loads((output/'models.json').read_text());choices=json.loads((output/'final-choices.json').read_text())
    probs={};unsupported=[];timings=[]
    for entry in models:
        seed,config=entry['seed'],entry['config']
        missing=[b for b in entry['blocks'] if b not in schemas]
        if missing:
            unsupported.append(dict(entry,reason='structurally unavailable feature blocks',missing=missing));continue
        fitted=joblib.load(output/'models'/entry['filename']);start=time.perf_counter();probs[seed,config]=fitted.predict(rows,records)
        timings.append({'seed':seed,'config':config,'batch_prediction_ms':(time.perf_counter()-start)*1000,'rows':len(rows)})
    pp=[]
    for choice in choices:
        key=(choice['seed'],choice['config'])
        if key not in probs:continue
        meta={k:choice[k] for k in ('seed','arm','policy','denominator','learned_component')}
        if 'selected_config' in choice:meta['selected_config']=choice['selected_config']
        pp.extend(predictions(rows,probs[key],th(choice['threshold']),flags[choice['wrapper']],**meta))
    add_controls(pp,rows);destination.mkdir(parents=True)
    jsonl(destination/'predictions.jsonl',pp);write(destination/'rule-diagnostics.json',rule_diagnostics);write(destination/'unsupported.json',unsupported);write(destination/'timings.json',timings)
    write(destination/'PREDICTIONS_FROZEN.json',{'created_unix':time.time(),'labels_opened':False,'rows_file':{'path':str(rows_path.resolve()),'sha256':sha(rows_path)},'records':[{'path':str(p.resolve()),'sha256':sha(p)} for p in record_paths],'predictions_sha256':sha(destination/'predictions.jsonl'),'methods_freeze_sha256':sha(output/'METHODS_FROZEN.json')})
    return {'predictions':len(pp),'unsupported_model_seed_pairs':len(unsupported)}


def intervention_summarize(predictions,labels,scope):
    """Static contract screening, never an observed money-effect counterfactual."""
    by={r['episode_id']:r for r in labels};groups=defaultdict(list);result=[]
    for p in predictions:groups[p['policy'],p['denominator'],p['seed'],p['arm']].append(p)
    rate=lambda k,n:{'k':int(k),'n':int(n),'rate':k/n if n else None}
    for (policy,den,seed,arm),pp in sorted(groups.items()):
        if len(pp)!=len(labels) or len({p['episode_id'] for p in pp})!=len(labels):raise ValueError('Incomplete intervention arm')
        positive=[p for p in pp if by[p['episode_id']]['contract_requires_intervention']]
        safe=[p for p in pp if not by[p['episode_id']]['contract_requires_intervention']]
        result.append({'policy':policy,'denominator':den,'seed':seed,'arm':arm,'scope':scope,'prefixes':len(pp),
            'target':'contract_requires_intervention; not observed harmful continuation',
            'contract_intervention_recall':rate(sum(p['block'] for p in positive),len(positive)),
            'compliant_stop_fpr':rate(sum(p['block'] for p in safe),len(safe)),
            'compliant_allow_rate':rate(sum(not p['block'] for p in safe),len(safe)),
            'unknown_stop':sum(p['unknown'] and p['block'] for p in pp),
            'probability_metrics':'not computed: archive harm-risk trained model evaluated against different extended-contract target'})
    return result


def paired_metrics(predictions,labels):
    """Two counterfactual proposals form a pair; no claims of live execution."""
    by={r['episode_id']:r for r in labels};pairlabels=defaultdict(list)
    for label in labels:
        if not label.get('pair_id'):raise ValueError('Paired evaluation needs explicit pair_id')
        pairlabels[label['pair_id']].append(label)
    for pair in pairlabels.values():
        if len(pair)!=2 or {bool(l['contract_requires_intervention']) for l in pair}!={False,True}:raise ValueError('Pair must contain one compliant and one intervention proposal')
    grouped=defaultdict(dict)
    for p in predictions:grouped[p['policy'],p['denominator'],p['seed'],p['arm']][p['episode_id']]=p
    result=[]
    for (policy,den,seed,arm),lookup in sorted(grouped.items()):
        counts={'both_correct':0,'compliant_stop_only':0,'intervention_miss_only':0,'both_wrong':0,'pairs_with_unknown':0}
        for pair in pairlabels.values():
            safe=next(l for l in pair if not l['contract_requires_intervention']);unsafe=next(l for l in pair if l['contract_requires_intervention'])
            ss,uu=lookup[safe['episode_id']],lookup[unsafe['episode_id']]
            key='both_wrong' if ss['block'] and not uu['block'] else 'compliant_stop_only' if ss['block'] else 'intervention_miss_only' if not uu['block'] else 'both_correct'
            counts[key]+=1;counts['pairs_with_unknown']+=int(ss['unknown'] or uu['unknown'])
        result.append({'policy':policy,'denominator':den,'seed':seed,'arm':arm,'pair_count':len(pairlabels),**counts})
    return result


def run_score(output,destination,labels_path):
    verify_frozen(output);freeze=json.loads((destination/'PREDICTIONS_FROZEN.json').read_text())
    if sha(destination/'predictions.jsonl')!=freeze['predictions_sha256']:raise ValueError('Predictions changed')
    if (destination/'metrics.json').exists():raise ValueError('External evaluation already unblinded')
    rows=list(read_jsonl(freeze['rows_file']['path']));labels=list(read_jsonl(labels_path));by={l['episode_id']:l for l in labels}
    if len(by)!=len(labels) or set(by)!={r['episode_id'] for r in rows}:raise ValueError('Label episode mismatch')
    pp=list(read_jsonl(destination/'predictions.jsonl'))
    contract=all(isinstance(l.get('contract_requires_intervention'),bool) for l in labels)
    if contract:
        score=lambda pr,rr,ll,scope:intervention_summarize(pr,ll,scope)
        labeled=rows
    else:
        if not all(isinstance(l.get('strict_harm'),bool) for l in labels):raise ValueError('Neither observed-harm nor intervention labels are valid')
        labeled=[dict(r,label=int(by[r['episode_id']]['strict_harm'])) for r in rows]
        score=summarize
    m={'aggregates':score(pp,labeled,labels,'prospective authored synthetic independent families'),
       'target':'contract_requires_intervention' if contract else 'observed continuation strict_harm'}
    families=sorted({l.get('family','UNSPECIFIED') for l in labels});m['by_family']={}
    for family in families:
        oo=[l for l in labels if l.get('family','UNSPECIFIED')==family];ids={l['episode_id'] for l in oo}
        m['by_family'][family]=score([p for p in pp if p['episode_id'] in ids],[r for r in labeled if r['episode_id'] in ids],oo,'synthetic family')
    write(destination/'metrics.json',m)
    if contract:
        has_pairs=all(l.get('pair_id') for l in labels)
        if len(labels)==240 and not has_pairs:raise ValueError('Frozen independent240 requires explicit valid pairs')
        if has_pairs:write(destination/'pair-metrics.json',{'aggregates':paired_metrics(pp,labels),'target':'contract_requires_intervention'})
        else:write(destination/'pair-metrics.json',{'status':'NOT_APPLICABLE','reason':'Authored stress fixtures have no explicit matched pairs; none invented','aggregates':[]})
    write(destination/'UNBLINDED.json',{'created_unix':time.time(),'labels_sha256':sha(labels_path),'predictions_sha256':freeze['predictions_sha256'],'rows':len(rows),
          'target':m['target'],'positive':sum(l['contract_requires_intervention'] if contract else l['strict_harm'] for l in labels),'safe':sum(not (l['contract_requires_intervention'] if contract else l['strict_harm']) for l in labels)})
    return {'aggregates':len(m['aggregates']),'families':families,'target':m['target']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['validate','train','predict','score']);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--rows',type=Path);parser.add_argument('--outcomes',type=Path);parser.add_argument('--records',type=Path,nargs='+');parser.add_argument('--allocations',type=Path);parser.add_argument('--destination',type=Path);parser.add_argument('--labels',type=Path);a=parser.parse_args()
    if a.phase=='validate':
        parts=freeze_spec(a.output,a.rows,a.outcomes,a.records,a.allocations);value={'rows':len(parts[0]),'configs':len(parts[5]),'trained':False}
    elif a.phase=='train':value=run_train(a.output,a.rows,a.outcomes,a.records,a.allocations)
    elif a.phase=='predict':value=run_predict(a.output,a.rows,a.records,a.destination)
    else:value=run_score(a.output,a.destination,a.labels)
    print(json.dumps(value,indent=2))
if __name__=='__main__':main()
