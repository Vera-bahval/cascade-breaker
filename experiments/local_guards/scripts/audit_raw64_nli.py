"""Post-hoc diagnosis of cached NLI features; no pretrained inference/API."""
from pathlib import Path
import fcntl
import json
import time
import numpy as np
from catboost import Pool
from cascade_guard import cheap_eval as e

base = Path(__file__).resolve().parents[1]
out = base / 'results/raw64-nli-audit'
out.mkdir(exist_ok=True)
paths = [base/'results/cheap-guards/models/N.jsonl', base/'results/cheap-guards/raw64/scores/N.jsonl']
sources = paths + [Path(__file__),Path(e.__file__),base/'cascade_guard/ml.py',base/'data/prefixes.jsonl',base/'data/outcomes.jsonl',base/'results/cheap-guards/raw64/rows.jsonl',base/'results/cheap-guards/evaluation/raw64/predictions.jsonl']
plan = {'post_hoc':True,'created_unix':time.time(),'purpose':'Reproduce cached final NLI CatBoost probabilities; diagnose feature drift and SHAP. No threshold/model selection or new pretrained inference.',
        'analyses':['all feature ranges/missingness','three exact final model reproductions','global importance and mean absolute raw SHAP'],'source_files':[{'path':str(p),'sha256':e.digest(p)} for p in sources]}
if (out/'diagnosis.json').exists():raise ValueError('Preserve completed generation')
e.dump(out/'input-freeze.json',plan)
records,schemas=e.load_records(paths)
outcomes=[r for r in e.read_jsonl(base/'data/outcomes.jsonl') if not r['legacy_ambiguous']]
ids={r['episode_id'] for r in outcomes}
rows=[r for r in e.read_jsonl(base/'data/prefixes.jsonl') if r['episode_id'] in ids and r['control_point']=='P4.finstripe__create_transfer' and not r['already_harmful']]
raw=e.read_jsonl(base/'results/cheap-guards/raw64/rows.jsonl')
old=e.read_jsonl(base/'results/cheap-guards/evaluation/raw64/predictions.jsonl')
keys=schemas['N'];x=np.array([[records[r['prefix_id'],'N']['features'][k] for k in keys] for r in rows]);y=np.array([[records[r['prefix_id'],'N']['features'][k] for k in keys] for r in raw])
drift=[{'feature':k,'archive_min':float(x[:,i].min()),'archive_max':float(x[:,i].max()),'archive_mean':float(x[:,i].mean()),'raw_min':float(y[:,i].min()),'raw_max':float(y[:,i].max()),'raw_mean':float(y[:,i].mean()),'raw_outside_archive_fraction':float(np.mean((y[:,i]<x[:,i].min())|(y[:,i]>x[:,i].max()))),'constant_in_archive':bool(np.ptp(x[:,i])==0)} for i,k in enumerate(keys)]
fits=[]
lock=base.parents[1]/'.runtime/cheap-guards/heavy-model.lock'
with lock.open('a+') as lease:
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for seed in e.SEEDS:
        model=e.BlockCB(('N',),False,seed,records,schemas).fit(rows)
        p=model.predict(raw);saved={r['prefix_id']:r['probability'] for r in old if r['seed']==seed and r['arm']=='catboost:N:none'}
        delta=max(abs(float(v)-saved[r['prefix_id']]) for r,v in zip(raw,p))
        if delta>1e-12:raise ValueError('Final cached model reproduction mismatch')
        frame,cats=model.x(raw)
        shap=model.model.get_feature_importance(Pool(frame,cat_features=cats),type='ShapValues')
        importance=model.model.get_feature_importance()
        features=[dict(drift[i],importance=float(importance[i]),raw_mean_absolute_shap=float(np.abs(shap[:,i]).mean()),raw_mean_signed_shap=float(shap[:,i].mean())) for i in range(len(keys))]
        fits.append({'seed':seed,'max_probability_reproduction_delta':delta,'raw_probability_quantiles':np.quantile(p,[0,.25,.5,.75,1]).tolist(),'top_importance':sorted(features,key=lambda r:-r['importance'])[:15],'top_raw_shap':sorted(features,key=lambda r:-r['raw_mean_absolute_shap'])[:15]})
e.verify_frozen(dict(plan,record_files=[]))
e.dump(out/'diagnosis.json',{'features':drift,'fits':fits,'raw_all_OK':all(records[r['prefix_id'],'N']['status']=='OK' for r in raw),'new_pretrained_inference':0,'new_catboost_fits':3,'interpretation':'SHAP describes frozen predictions; observational drift is not a causal intervention.'})
print(json.dumps({'fits':3,'delta':[r['max_probability_reproduction_delta'] for r in fits],'top_raw_shap':[[r['feature'] for r in f['top_raw_shap'][:4]] for f in fits]}))
