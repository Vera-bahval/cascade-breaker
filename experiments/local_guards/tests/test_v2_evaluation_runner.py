import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('guard_evaluation_runner',Path(__file__).parents[1]/'scripts/run_guard_v2_evaluation.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


def prepared(tmp_path):
    (tmp_path/'scores-v5').mkdir();(tmp_path/'jev-v5').mkdir();inputs=tmp_path/'inputs-v5';inputs.mkdir()
    inventory=[];per_collection={}
    for (collection,suffix),count in zip(runner.COLLECTIONS.items(),(176,176,64,64,240)):
        rr=[{'prefix_id':collection+str(i),'input_hash':'ih'+collection+str(i)} for i in range(count)]
        inventory.extend(rr);per_collection[collection]=rr
        (inputs/(suffix+'-inputs.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rr))
    prior={'status':'COMPLETE','models_unloaded':True,'freeze_manifest_sha256':'method','stages':[{'block':b,'exit_code':0} for b in runner.BLOCKS]}
    jev={'status':'COMPLETE','method_freeze_sha256':'method','jev_input_freeze_sha256':'jev','models_unloaded':True,'exports':{}}
    source_names={'archive':'archive-all','archive-partial':'archive-partial','raw64':'raw64','raw64-partial':'raw64-partial','independent':'independent-all'}
    for model in ('08','4b'):
        folder=tmp_path/'jev-v5'/model;folder.mkdir();entries=[];combined=[]
        for collection,name in source_names.items():
            records=[]
            for r in per_collection[collection]:
                for block in (('J_cur','J_seq','J_agg','J_dynamic','J_prior') if model=='08' else ('J4_cur',)):
                    size=1 if block in ('J_cur','J4_cur') else 3 if block=='J_prior' else 4
                    records.append({'prefix_id':r['prefix_id'],'block':block,'provenance':{'checkpoint_inputs':[{'prefix_id':r['prefix_id']+'-stage'+str(i),'input_hash':'h'} for i in range(size)]}})
            text=''.join(json.dumps(r)+'\n' for r in records);combined.append(text)
            target=folder/('features-'+name+'.jsonl');target.write_text(text)
            entries.append({'collection':name,'file':str(target),'sha256':runner.sha(target)})
        target=folder/'features.jsonl';target.write_text(''.join(combined))
        jev['exports'][model]={'collections':entries,'all_features':str(target),'sha256':runner.sha(target)}
    (tmp_path/'scores-v5/runtime-run.json').write_text(json.dumps(prior));(tmp_path/'jev-v5/runtime-run.json').write_text(json.dumps(jev))
    for b in runner.BLOCKS:
        (tmp_path/'scores-v5'/(b+'.jsonl')).write_text(''.join(json.dumps(dict(r,block=b))+'\n' for r in inventory))
        (tmp_path/'scores-v5'/(b+'.manifest.json')).write_text(json.dumps({'status':'COMPLETE'}))
    return prior,jev


def test_exact_barriers_and_unload_required(tmp_path):
    prior,jev=prepared(tmp_path)
    assert runner.barrier(tmp_path,{'method':'method','jev':'jev'},scan=lambda:[])[0]
    jev['models_unloaded']=False;(tmp_path/'jev-v5/runtime-run.json').write_text(json.dumps(jev))
    assert not runner.barrier(tmp_path,{'method':'method','jev':'jev'},scan=lambda:[])[0]


def test_any_active_heavy_child_rejects(tmp_path):
    prepared(tmp_path)
    assert not runner.barrier(tmp_path,{'method':'method','jev':'jev'},scan=lambda:[{'pid':5,'module':'v2_jev'}])[0]


def test_training_is_archive_only_and_both_freeze_before_external(tmp_path):
    plan=runner.commands(tmp_path)
    trains=[(i,n,c) for i,(n,c,m) in enumerate(plan) if n.startswith('train-')]
    external=[i for i,(n,c,m) in enumerate(plan) if n.startswith('predict-')]
    assert len(trains)==2 and max(i for i,n,c in trains)<min(external)
    for i,n,c in trains:
        assert c[c.index('--rows')+1].endswith('archive-p4-rows.jsonl' if n=='train-full' else 'archive-partial-rows.jsonl')
        assert all('combined' not in p and 'independent' not in p for p in c[c.index('--records')+1:])
    assert not any('score' in c or '--labels' in c for n,c,m in plan)


def test_lease_exclusive(tmp_path):
    with runner.heavy_lease(tmp_path/'lease.lock'):
        with pytest.raises(BlockingIOError):
            with runner.heavy_lease(tmp_path/'lease.lock'):pass


def test_frozen_source_tamper_rejected(tmp_path):
    source=tmp_path/'source';source.write_text('first')
    manifest=tmp_path/'freeze';manifest.write_text(json.dumps({'sha256':{str(source):runner.sha(source)}}))
    expected=runner.sha(manifest);runner.verify(manifest,expected)
    source.write_text('changed')
    with pytest.raises(ValueError,match='drift'):runner.verify(manifest,expected)


def test_old_runtime_freeze_is_rejected(tmp_path):
    prior,jev=prepared(tmp_path);prior['freeze_manifest_sha256']='older-method'
    (tmp_path/'scores-v5/runtime-run.json').write_text(json.dumps(prior))
    with pytest.raises(ValueError,match='another method freeze'):
        runner.barrier(tmp_path,{'method':'method','jev':'jev'},scan=lambda:[])


def test_export_hash_tamper_is_rejected(tmp_path):
    prepared(tmp_path);(tmp_path/'jev-v5/08/features-raw64.jsonl').write_text('changed')
    with pytest.raises(ValueError,match='export path/hash'):
        runner.barrier(tmp_path,{'method':'method','jev':'jev'},scan=lambda:[])


def test_wrong_block_under_expected_score_filename_rejected(tmp_path):
    prepared(tmp_path);(tmp_path/'scores-v5/N.jsonl').write_text(json.dumps({'block':'G22'})+'\n')
    with pytest.raises(ValueError,match='filename/model block'):
        runner.barrier(tmp_path,{'method':'method','jev':'jev'},scan=lambda:[])


def test_cutoff_fallback_only_completed_available_models(tmp_path):
    prior,jev=prepared(tmp_path)
    prior['status']='DEADLINE';prior['stages']=[s for s in prior['stages'] if s['block']!='M']
    jev['status']='DEADLINE';jev['exports'].pop('4b')
    (tmp_path/'scores-v5/runtime-run.json').write_text(json.dumps(prior));(tmp_path/'jev-v5/runtime-run.json').write_text(json.dumps(jev))
    assert not runner.barrier(tmp_path,{'method':'method','jev':'jev'},scan=lambda:[],now=9,cutoff=10)[0]
    ready,proof=runner.barrier(tmp_path,{'method':'method','jev':'jev'},scan=lambda:[],now=11,cutoff=10)
    assert ready and proof['available_models']==['N','G22','G86','08']
    assert set(proof['unavailable_models'])=={'M','4b'}
    plan=runner.commands(tmp_path,proof['available_models'])
    assert not any(n=='blind-split-M' for n,c,m in plan)
    training=next(c for n,c,m in plan if n=='train-full')
    assert all('/M' not in p and '4b' not in p for p in training[training.index('--records')+1:])


def test_zero_completed_neural_models_does_not_invent_features(tmp_path):
    plan=runner.commands(tmp_path,[])
    assert not any(n.startswith('blind-split-') for n,c,m in plan)
    training=next(c for n,c,m in plan if n=='train-full')
    assert training[-1].endswith('NO_COMPLETED_MODEL_BLOCKS.jsonl')


def test_model_cutoff_real_status_with_missing_exit_zero_artifact_keeps_healthy(tmp_path):
    prior,jev=prepared(tmp_path);prior['status']='MODEL_CUTOFF';jev['status']='DEADLINE';jev['exports'].pop('4b')
    (tmp_path/'scores-v5/runtime-run.json').write_text(json.dumps(prior));(tmp_path/'jev-v5/runtime-run.json').write_text(json.dumps(jev))
    (tmp_path/'scores-v5/M.jsonl').unlink()
    ready,proof=runner.barrier(tmp_path,{'method':'method','jev':'jev'},scan=lambda:[],now=11,cutoff=10)
    assert ready and 'M' not in proof['available_models'] and 'G22' in proof['available_models']


def test_partial_manifest_exit_zero_not_treated_complete(tmp_path):
    prior,jev=prepared(tmp_path);prior['status']='PARTIAL';jev['status']='DEADLINE';jev['exports'].pop('4b')
    (tmp_path/'scores-v5/runtime-run.json').write_text(json.dumps(prior));(tmp_path/'jev-v5/runtime-run.json').write_text(json.dumps(jev))
    (tmp_path/'scores-v5/M.manifest.json').write_text(json.dumps({'status':'PARTIAL'}))
    ready,proof=runner.barrier(tmp_path,{'method':'method','jev':'jev'},scan=lambda:[],now=11,cutoff=10)
    assert ready and 'M' not in proof['available_models'] and proof['artifact_availability']['M']['reason']=='per-model manifest not COMPLETE'
