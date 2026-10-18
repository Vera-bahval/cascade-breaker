"""Prospective, label-blind metadata compatibility and feature projections.

Original exports are immutable. This module never imports an estimator, opens a
label file, chooses a threshold, or uses a score value to select a feature set.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

VERSION='guard-v2-blind-feature-views-1'
CLAIMS=('fraud_completed','hold_clear','invariants_compliant','policy_authorized')
COLLECTIONS=('archive','archive-partial','raw64','raw64-partial','independent')
FULL_TIMELINES={'archive','independent'}
JEV_NAMES={'archive':'archive-all','archive-partial':'archive-partial','raw64':'raw64','raw64-partial':'raw64-partial','independent':'independent-all'}
JEV_BLOCKS=('J_cur','J_seq','J_agg','J_dynamic','J_prior')
PROJECTIONS={'local':'only local.* fixed-claim features; original local scalar risk',
             'full':'only full.* fixed-claim features; max over four (1 - maximum window support)',
             'facts':'all local.* and full.* fixed-claim features; original local scalar risk; explanation.* excluded'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    with Path(path).open() as handle:
        for line in handle:
            if line.strip():yield json.loads(line)


def immutable(path,records):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    text=''.join(json.dumps(r,allow_nan=False,sort_keys=True,separators=(',',':'))+'\n' for r in records)
    if path.exists() and path.read_text()!=text:raise ValueError('Immutable feature view differs: '+str(path))
    path.write_text(text)
    return {'path':str(path.resolve()),'sha256':sha(path),'records':text.count('\n')}


def normalize_jev_record(record,*,run_manifest,export_sha):
    result=deepcopy(record)
    checkpoints=record['provenance']['checkpoint_inputs']
    count=sum(c.get('prefix_id') is not None and c.get('input_hash') is not None for c in checkpoints)
    if 'window_count' not in result:result['window_count']=count
    if 'memory' not in result:
        result['memory']={'measurement_status':'UNMEASURED_PER_FEATURE','extractor_memory_measured':False,
                          'run_manifest':str(run_manifest),'note':'No zero or fabricated per-feature peak; source inference memory retained separately.'}
    result.setdefault('provenance',{})['compatibility_envelope']={
        'version':VERSION,'source_export_sha256':export_sha,
        'window_count_semantics':'actual recorded checkpoint inputs used; not token sliding windows',
        'recorded_checkpoint_count':count,'numeric_features_probabilities_input_hash_unchanged':True}
    assert result['features']==record['features'] and result['scalar_risk']==record['scalar_risk'] and result['input_hash']==record['input_hash']
    return result


def normalize_jev_file(source,destination,*,model,collection,run_manifest,expected_prefixes=None):
    permitted=set(JEV_BLOCKS if collection in FULL_TIMELINES else ('J_cur',)) if model=='08' else {'J4_cur'}
    checksum=sha(source);kept=[];excluded={}
    for record in rows(source):
        if record['block'] not in permitted:
            excluded[record['block']]=excluded.get(record['block'],0)+1;continue
        kept.append(normalize_jev_record(record,run_manifest=run_manifest,export_sha=checksum))
    if not kept:raise ValueError('No compatible Jev features for '+collection+'/'+model)
    identities=[(r['prefix_id'],r['block']) for r in kept]
    if len(set(identities))!=len(identities):raise ValueError('Duplicate normalized Jev prefix/block')
    if expected_prefixes is not None and set(identities)!={(pid,b) for pid in expected_prefixes for b in permitted}:raise ValueError('Normalized Jev collection prefix coverage mismatch')
    if sha(source)!=checksum:raise ValueError('Jev source changed during compatibility export')
    output=immutable(destination,kept)
    return {'source':str(source.resolve()),'source_sha256':checksum,'model':model,'collection':collection,
            'permitted_blocks':sorted(permitted),'excluded_structural_blocks':excluded,'output':output}


def project_record(record,variant):
    if record['block'] not in ('N','M') or variant not in PROJECTIONS:raise ValueError('Unsupported projection')
    result=deepcopy(record);prefixes=('local.',) if variant=='local' else ('full.',) if variant=='full' else ('local.','full.')
    result['features']={k:v for k,v in record['features'].items() if k.startswith(prefixes)}
    result['block']=record['block']+'_'+variant
    if record['status']=='OK':
        support='entailment' if record['block']=='N' else 'supported'
        expected=[f'{"full" if variant=="full" else "local"}.{c}.{support}.max' for c in CLAIMS]
        if any(k not in result['features'] for k in expected):raise ValueError('Missing frozen fixed-claim support feature')
        if variant=='full':result['scalar_risk']=max(1-float(result['features'][k]) for k in expected)
    else:result['scalar_risk']=None
    result.setdefault('provenance',{})['feature_projection']={'version':VERSION,'variant':variant,'source_block':record['block'],
          'rule':PROJECTIONS[variant],'retained_feature_keys':sorted(result['features']),
          'input_hash_semantics':'original model input hash retained; projection identified by block/provenance and file checksum',
          'latency_semantics':'original complete extractor cost reused; no claim of a separately measured faster extraction path'}
    result['model_metadata']={**record['model_metadata'],'feature_projection':variant,'feature_projection_version':VERSION}
    return result


def project_file(source,destination):
    checksum=sha(source);source_rows=list(rows(source));block=source_rows[0]['block'] if source_rows else None
    if block not in ('N','M') or any(r['block']!=block for r in source_rows):raise ValueError('One complete N or M view required')
    outputs={variant:immutable(Path(destination)/(block+'_'+variant+'.jsonl'),[project_record(r,variant) for r in source_rows]) for variant in PROJECTIONS}
    if sha(source)!=checksum:raise ValueError('Projection source changed')
    return {'source':str(source.resolve()),'source_sha256':checksum,'outputs':outputs}


def make_views(root,jev,destination,*,inputs_directory=None,available_models=None):
    """Run only after blind N/M/PG partition; no risks printed or selected."""
    root=Path(root);jev=Path(jev);destination=Path(destination)
    inputs_directory=Path(inputs_directory) if inputs_directory is not None else root/'inputs-v5'
    available=set(('N','M','G22','G86','08','4b') if available_models is None else available_models)
    result={'version':VERSION,'available_models':sorted(available),'collections':{}}
    for collection in COLLECTIONS:
        names={'archive':'archive-p4','archive-partial':'archive-partial','raw64':'raw64','raw64-partial':'raw64-partial','independent':'independent-p4'}
        inventory=inputs_directory/(names[collection]+'-inputs.jsonl')
        expected={r['prefix_id'] for r in rows(inventory)}
        entries={}
        for model in ('08','4b'):
            if model not in available:continue
            source=jev/model/('features-'+JEV_NAMES[collection]+'.jsonl')
            entries[model]=normalize_jev_file(source,destination/collection/('Jev-'+model+'.jsonl'),model=model,collection=collection,run_manifest=jev/'runtime-run.json',expected_prefixes=expected)
        for block in ('N','M'):
            if block not in available:continue
            entries[block]=project_file(destination/collection/(block+'.jsonl'),destination/collection)
        if not available:immutable(destination/collection/'NO_COMPLETED_MODEL_BLOCKS.jsonl',[])
        result['collections'][collection]=entries
    immutable(destination/'normalization-manifest.jsonl',[result])
    return {'collections':len(result['collections']),'manifest_sha256':sha(destination/'normalization-manifest.jsonl')}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--jev',type=Path,required=True);parser.add_argument('--destination',type=Path,required=True);parser.add_argument('--inputs-directory',type=Path);parser.add_argument('--available-models',nargs='*');a=parser.parse_args()
    print(json.dumps(make_views(a.root,a.jev,a.destination,inputs_directory=a.inputs_directory,available_models=a.available_models)))
if __name__=='__main__':main()
