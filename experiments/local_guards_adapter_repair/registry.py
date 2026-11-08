"""Frozen inference contracts. Hash assets without loading fitted models."""
import json
from .inventory import ROOT, EXP, HERE, sha, write_json
from experiments.local_guards_archive_comparison.collector import digest


def contract_registry():
    entries=[{'method':'v4.3','kind':'rule','implementation':str((HERE/'guard43.py').relative_to(ROOT)),
              'implementation_sha256':sha(HERE/'guard43.py'),'placement':['P0','P1','P2','P3','P4'],'profiles':['A','A08','B']}]
    rules={
        'v1':'local_guards_v3/legacy/rules.py','v2':'local_guards_v3/legacy/rules_v2.py',
        'v3':'local_guards_v3/rules_v3.py','v4':'local_guards_v4/guard.py',
        'v4.2':'local_guards_v4_followup/guard.py','native':'local_guards_archive_comparison/methods.py',
        'native_core':'local_guards_archive_comparison/methods.py'}
    for name,rel in rules.items():
        entry={'method':name,'kind':'rule','implementation':rel,'implementation_sha256':sha(EXP/rel),
               'placement':['P4'] if name not in ('v4','v4.2') else ['P0','P1','P2','P3','P4'],
               'profiles':['A','A08','B'] if name in ('v4','v4.2') else [name]}
        entries.append(entry)
    v3=EXP/'local_guards_v3'
    v3_release=v3/'results/frozen'
    v3_manifest=json.loads((v3_release/'freeze-manifest.json').read_text())
    for spec in v3_manifest['methods']:
        if not spec.get('model_file'):
            continue
        path=v3_release/spec['model_file']
        if sha(path)!=spec['model_hash']:
            raise ValueError('v3 model changed')
        config={k:spec[k] for k in ('method','kind','model','seed','strategy','combined','threshold','low','high','model_file','model_hash') if k in spec}
        entries.append({'method':'v3_ml/'+spec['method']+'/'+str(spec['seed'])+'/'+spec['strategy'],
            'kind':'ml','payload_family':'v3_ml','features':'v3_text' if spec['model']=='text_diagnostic' else 'v3_structured',
            'model_file':str(path.relative_to(ROOT)),'model_sha256':sha(path),'configuration':config,
            'extractor_sha256':sha(v3/'ml_v3.py'),'text_recipe_sha256':sha(v3/'prepare_data.py'),
            'gate_sha256':sha(v3/'evaluate_v3.py'),'threshold_manifest_sha256':sha(v3_release/'freeze-manifest.json'),
            'vectorizer_scaler':'inside hashed fitted pickle pipeline','placement':[spec['strategy']],'variants':['frozen']})
    archive=EXP/'local_guards_archive_comparison'
    release=archive/'results/ml-release-v2'
    manifest=json.loads((release/'freeze-manifest.json').read_text())
    for model in manifest['models']:
        path=release/(model['name']+'.joblib')
        if sha(path)!=model['model_sha256']:
            raise ValueError('archive model changed')
        entries.append({'method':'archive_ml/'+model['name'],'kind':'ml',
            'payload_family':'archive_ml','features':'archive',
            'model_file':str(path.relative_to(ROOT)),'model_sha256':sha(path),
            'extractor_sha256':sha(archive/'ml.py'),'gate_sha256':sha(archive/'methods.py'),
            'calibration_sha256':sha(release/'freeze-manifest.json'),
            'vectorizer_scaler':'inside hashed joblib payload',
            'variants':['raw','calibrated','gated'],'placement':['p4','both']})
    for folder,feature_name in [('frozen','retrain_original'),('frozen_revision2','retrain_revision2')]:
        root=EXP/'local_guards_ml_retrain'
        release=root/folder
        manifest=json.loads((release/'freeze-manifest.json').read_text())
        source=root/('features_revision2.py' if folder.endswith('revision2') else 'features.py')
        for model in manifest['methods']:
            if not model.get('available'):
                continue
            files={key:str((release/model[key]).relative_to(ROOT)) for key in ('model_file','thresholds_file')}
            hashes={key:sha(ROOT/path) for key,path in files.items()}
            if hashes['model_file']!=manifest['files'][model['model_file']]:
                raise ValueError('retrain model changed')
            entries.append({'method':folder+'/'+model['name'],'kind':'ml',
                'payload_family':'retrain_ml','features':feature_name+'_'+model['feature_mode'],
                'contract':model['contract'],'files':files,'file_hashes':hashes,
                'extractor_sha256':sha(source),'gate_sha256':sha(source),
                'model_loader_sha256':sha(root/('models_revision2.py' if folder.endswith('revision2') else 'models.py')),
                'vectorizer_scaler':'inside hashed fitted pickle pipeline',
                'variants':['raw','gated'],'placement':['P4'] if model['contract']=='payment_v3' else ['P0','P1','P2','P3','P4']})
    if len({entry['method'] for entry in entries})!=len(entries):
        raise ValueError('duplicate inference contract name')
    for entry in entries:
        entry['contract_sha256']=digest(entry)
    return {'methods':entries,'saved_predictions_reuse':'requires same payload, feature vector, full contract and placement',
            'deepseek_pairing':'exact original request hash including system prompt and parameters; common mode only'}


if __name__=='__main__':
    result=contract_registry()
    write_json(HERE/'methods.json',result)
    print(json.dumps({'inference_contracts':len(result['methods'])}))
