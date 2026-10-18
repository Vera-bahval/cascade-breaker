from copy import deepcopy
import json
from pathlib import Path
import pytest
from cascade_guard.v2_feature_views import normalize_jev_record,normalize_jev_file,project_record,CLAIMS


def jev(block='J_cur'):
    return {'prefix_id':'p','block':block,'status':'OK','features':{'score':.2},'scalar_risk':.2,'input_hash':'original',
            'model_metadata':{},'provenance':{'checkpoint_inputs':[{'prefix_id':'p','input_hash':'ih'}]}}


def test_compatibility_only_adds_honest_metadata():
    before=jev();original=deepcopy(before)
    result=normalize_jev_record(before,run_manifest='run.json',export_sha='s')
    assert before==original
    for key in ('features','scalar_risk','input_hash','prefix_id','status'):assert result[key]==before[key]
    assert result['window_count']==1 and result['memory']['measurement_status']=='UNMEASURED_PER_FEATURE'
    assert result['memory']['extractor_memory_measured'] is False


def test_checkpoint_count_not_invented_for_absent_structural_stage():
    before=jev();before['provenance']['checkpoint_inputs'] += [{'prefix_id':None,'input_hash':None}]
    result=normalize_jev_record(before,run_manifest='run.json',export_sha='s')
    assert result['window_count']==1


def test_filter_structural_timeline_blocks_before_ml(tmp_path):
    source=tmp_path/'raw.jsonl';source.write_text(''.join(json.dumps(jev(b))+'\n' for b in ['J_cur','J_seq','J_agg','J_dynamic','J_prior']))
    result=normalize_jev_file(source,tmp_path/'view.jsonl',model='08',collection='raw64',run_manifest='run.json')
    rows=[json.loads(x) for x in (tmp_path/'view.jsonl').read_text().splitlines()]
    assert [r['block'] for r in rows]==['J_cur'] and len(result['excluded_structural_blocks'])==4


def nli(block='N'):
    support='entailment' if block=='N' else 'supported';features={}
    for prefix in ('local','full'):
        for c in CLAIMS:features[f'{prefix}.{c}.{support}.max']=.9 if prefix=='local' else .6
    features['explanation.untrusted_premise.missing']=1
    return {'prefix_id':'p','block':block,'status':'OK','features':features,'scalar_risk':.1,'input_hash':'h','model_metadata':{},'provenance':{}}


def test_fixed_source_only_projections_and_full_scalar():
    before=nli();saved=deepcopy(before)
    local,full,facts=[project_record(before,v) for v in ('local','full','facts')]
    assert all(k.startswith('local.') for k in local['features'])
    assert all(k.startswith('full.') for k in full['features'])
    assert all(not k.startswith('explanation.') for k in facts['features'])
    assert local['scalar_risk']==.1 and facts['scalar_risk']==.1 and full['scalar_risk']==pytest.approx(.4)
    assert before==saved and full['input_hash']==before['input_hash']


def test_projection_unknown_not_fabricated_probability():
    before=nli('M');before['status']='UNKNOWN';before['features']={};before['scalar_risk']=None
    projected=project_record(before,'full')
    assert projected['status']=='UNKNOWN' and projected['scalar_risk'] is None


def test_wrong_collection_export_fails_exact_prefix_inventory(tmp_path):
    source=tmp_path/'source.jsonl';source.write_text(json.dumps(jev())+'\n')
    with pytest.raises(ValueError,match='prefix coverage'):
        normalize_jev_file(source,tmp_path/'normalized.jsonl',model='08',collection='raw64',run_manifest='run.json',expected_prefixes={'different-p'})
