"""Cached-only contract tests; fitted models are stubs."""
import json
from pathlib import Path
import pytest
from cascade_guard import cheap_reference as ref

BASE=Path(__file__).resolve().parents[1]
PRIMARY=BASE/'results/cheap-guards/evaluation'


def test_cached_scores_have_verified_payload_and_model_hashes():
    rows=ref.e.read_jsonl(BASE/'data/prefixes.jsonl')
    ids={r['prefix_id'] for r in rows if r['control_point']=='P4.finstripe__create_transfer' and not r['ambiguity']}
    records,schemas=ref.load_cached(BASE/'results/night-4b/scores.jsonl',BASE/'results/night-4b/formats/inputs.jsonl',ids)
    assert len(records)==528 and len(schemas)==3
    assert all(r['status']=='OK' for r in records.values())
    assert all(r['inference_cost_ms']==r['timing_ms']['total'] for r in records.values())
    assert all(len(v)==4 for v in schemas.values())


def test_cached_payload_or_model_drift_is_rejected(tmp_path):
    scores=ref.e.read_jsonl(BASE/'results/night-4b/scores.jsonl')
    inputs=ref.e.read_jsonl(BASE/'results/night-4b/formats/inputs.jsonl')
    ids={r['prefix_id'] for r in scores}
    inputs[0]['payload']['changed']='drift'
    path=tmp_path/'inputs.jsonl';ref.e.jsonl(path,inputs)
    with pytest.raises(ValueError,match='payload hash mismatch'):
        ref.load_cached(BASE/'results/night-4b/scores.jsonl',path,ids)
    scores[0]['model_metadata']['temperature']=999
    score_path=tmp_path/'scores.jsonl';ref.e.jsonl(score_path,scores)
    with pytest.raises(ValueError,match='model/input hash mismatch'):
        ref.load_cached(score_path,BASE/'results/night-4b/formats/inputs.jsonl',ids)


def test_full_source_cost_and_cache_original_are_preserved():
    actual={'input_hash':'a','timing_ms':{'total':10,'compute':2}}
    assert ref.source_cost(actual,{})==10
    cached={'input_hash':'a','cache_hit':True,'timing_ms':{'total':.01}}
    assert ref.source_cost(cached,{'a':actual})==10
    assert ref.source_cost(cached,{}) is None


def test_existing_08_control_is_exact_and_has_no_refit():
    result=ref.identity08(BASE,PRIMARY)
    assert result['prefixes']==176 and result['scalar_exact_equal'] and result['rules_exact_equal']
    assert result['max_abs_delta']==0 and result['no_refit']
    assert len(result['matched08_control'])==18


def test_mock_run_uses_primary_folds_and_reuses_fits_across_wrappers(tmp_path,monkeypatch):
    monkeypatch.setattr(ref,'HEADS',('catboost',))
    fits=[];calls=[]
    class Model:
        def fit(self,rows):fits.append(len(rows));return self
        def predict(self,rows):calls.append(len(rows));return [.5]*len(rows)
    freeze=ref.run(BASE,PRIMARY,tmp_path,freeze_only=True)
    frozen=(tmp_path/'input-freeze.json').read_bytes()
    result=ref.run(BASE,PRIMARY,tmp_path,fitter=lambda *a:Model())
    assert result['phase']=='COMPLETE' and len(fits)==81 # 3formats*9folds*(2inner+1final)
    assert sum(n>1 for n in calls)==54
    assert sum(n==1 for n in calls)==3*3*176
    assert (tmp_path/'input-freeze.json').read_bytes()==frozen
    metrics=json.loads((tmp_path/'metrics.json').read_text())['aggregates']
    assert len(metrics)==24 and all(r['complete'] for r in metrics)
    assert all(r['raw_episode_fpr']['n']==131 for r in metrics)
    selected=[r for r in json.loads((tmp_path/'folds.json').read_text()) if 'train_selected_format' in r['arm']]
    assert len(selected)==18
    for r in selected:
        chosen=min(r['candidates'],key=lambda c:c['rank'])
        assert chosen['format']==r['selected_format']
    assert result['question_column_order'].startswith('same sorted')
