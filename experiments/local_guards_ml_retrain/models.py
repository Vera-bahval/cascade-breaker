"""Fixed TRAIN-only three-class models. This module performs no data-file IO."""
from collections import Counter
from importlib.metadata import version
import hashlib
import json
import time

import numpy as np
from catboost import CatBoostClassifier
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from features import features

CLASSES=('ALLOW','BLOCK','UNKNOWN')
PARAMETERS={
 'logistic':dict(C=1.,l1_ratio=0.,max_iter=2000),
 'catboost':dict(iterations=200,depth=3,learning_rate=.03,l2_leaf_reg=5,
                 thread_count=2,verbose=False,allow_writing_files=False)}


class FeatureBatch(list):
    """Explicit internal precomputed features; never inferred from arbitrary JSON."""
    def __init__(self,rows,mode):
        super().__init__(rows);self.mode=mode


def feature_rows(rows,mode='new'):
    if isinstance(rows,FeatureBatch):
        if rows.mode!=mode:raise ValueError('precomputed feature mode mismatch')
        return list(rows)
    return [features(row,mode) for row in rows]


class UnavailableModel:
    available_=False
    classes_=np.array([],dtype=str)
    def __init__(self,reason,provenance):
        self.reason_=reason;self.provenance_=provenance


def fit_model(family,rows,labels,weights,feature_mode,seed):
    if family not in PARAMETERS:raise ValueError('unknown model family')
    if feature_mode not in {'old','new'}:raise ValueError('unknown feature mode')
    rows=rows if isinstance(rows,FeatureBatch) else list(rows);labels=list(labels);weights=np.asarray(weights,dtype=float)
    if len(rows)!=len(labels) or weights.shape!=(len(rows),):raise ValueError('row/label/weight lengths differ')
    if any(x not in CLASSES for x in labels):raise ValueError('invalid label')
    if not np.isfinite(weights).all() or (weights<0).any():raise ValueError('invalid weights')
    active=weights>0
    if rows and not active.any():raise ValueError('all weights zero')
    available=sorted(set(np.asarray(labels)[active])) if labels else []
    params=dict(PARAMETERS[family]); params['random_state' if family=='logistic' else 'random_seed']=seed
    provenance=dict(family=family,feature_mode=feature_mode,seed=seed,parameters=params,
        class_counts=dict(Counter(labels)),available_classes=available,
        weights=dict(total=float(weights.sum()),rows=len(rows),mean=float(weights.mean()) if rows else None,
                     by_class={k:float(weights[np.asarray(labels)==k].sum()) for k in CLASSES}),
        versions={k:version(k) for k in ['numpy','scikit-learn','catboost']},fit_scope='TRAIN only')
    if not available:return UnavailableModel('no supported training classes',provenance)
    # One observed class is an honest constant-class fitted artifact, never a fabricated absent class.
    classifier=DummyClassifier(strategy='constant',constant=available[0]) if len(available)==1 else LogisticRegression(**params) if family=='logistic' else CatBoostClassifier(**params)
    steps=[('features',FunctionTransformer(feature_rows,kw_args={'mode':feature_mode},validate=False)),
           ('vectorizer',DictVectorizer(sparse=family=='logistic'))]
    if family=='logistic':steps.append(('scale',StandardScaler(with_mean=False)))
    steps.append(('classifier',classifier));model=Pipeline(steps)
    started=time.perf_counter();model.fit(rows,labels,classifier__sample_weight=weights)
    provenance['fit_seconds']=time.perf_counter()-started
    preprocessing=dict(train_only=True,feature_names=model.named_steps['vectorizer'].get_feature_names_out().tolist())
    if 'scale' in model.named_steps:
        scaler=model.named_steps['scale']
        preprocessing['scaler']={k:getattr(scaler,k).tolist() for k in ('mean_','var_','scale_')}
    preprocessing['sha256']=hashlib.sha256(json.dumps(preprocessing,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    provenance['preprocessing']=preprocessing
    model.provenance_=provenance;model.available_=True
    return model


def probabilities(model,rows):
    rows=list(rows)
    if not rows:return []
    if not model.available_:return [{k:0. for k in CLASSES} for _ in rows]
    scores=model.predict_proba(rows)
    indices={str(k):i for i,k in enumerate(model.classes_)}
    return [{k:float(s[indices[k]]) if k in indices else 0. for k in CLASSES} for s in scores]
