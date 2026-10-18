"""Public-only joblib and frozen-profiler integration, without fitting."""
import importlib.util
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch
import joblib
import pytest
from cascade_guard import v2_eval, v2_archive_latency as frozen
BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('profile_compat', BASE/'scripts/profile_guard_v2_heads_compat_05.py')
compat = importlib.util.module_from_spec(spec); spec.loader.exec_module(compat)


def legacy_public_model(path):
    """Emulate -m serialization on a never-fitted scalar head, synthetic only."""
    original = v2_eval.Model.__module__
    with compat.model_alias():
        try:
            v2_eval.Model.__module__ = '__main__'
            joblib.dump(v2_eval.Model(('scalar', ('N',), False), 17, {'N': ['risk']}, {}), path)
        finally:
            v2_eval.Model.__module__ = original


def test_real_joblib_alias_and_restore_without_fit(tmp_path):
    import __main__
    absent = not hasattr(__main__, 'Model')
    path = tmp_path/'public.joblib'; legacy_public_model(path)
    if absent:
        with pytest.raises(AttributeError, match="Can't get attribute 'Model'"): joblib.load(path)
    with compat.model_alias():
        head = joblib.load(path)
        assert type(head) is v2_eval.Model
        assert head.predict([{'prefix_id':'public'}], {('public','N'):{'status':'OK','features':{'risk':.5},'scalar_risk':.5}}) == [.5]
    assert hasattr(__main__, 'Model') is not absent
    with pytest.raises(RuntimeError):
        with compat.model_alias(): raise RuntimeError('public error')
    assert hasattr(__main__, 'Model') is not absent


def test_real_frozen_profiler_loads_legacy_public_model(tmp_path):
    def write(path, value): path.write_text(json.dumps(value))
    def entry(path): return {'path':str(path.resolve()),'sha256':frozen.sha(path)}
    def lines(path, values): path.write_text(''.join(json.dumps(v)+'\n' for v in values))
    methods = tmp_path/'methods'; (methods/'models').mkdir(parents=True)
    head = methods/'models/public.joblib'; legacy_public_model(head)
    rows = tmp_path/'archive-p4-rows.jsonl'
    lines(rows, [dict(prefix_id=f'public{i}', episode_id=f'e{i}', label=i%2, canonical={}, tabular_features={}) for i in range(176)])
    records = tmp_path/'public-records.jsonl'
    lines(records, [dict(prefix_id=f'public{i}', block='N', status='OK', features={'risk':.5}, scalar_risk=.5, input_hash='public', memory={}, model_metadata={}, provenance={}, timing_ms={'total':1.}, window_count=1) for i in range(176)])
    write(methods/'models.json', [dict(seed=17, config='public', kind='scalar', blocks=['N'], filename=head.name, sha256=frozen.sha(head))])
    write(methods/'METHODS_FROZEN.json', {'files':[entry(head),entry(methods/'models.json')]})
    write(methods/'training-input-freeze.json', {'files':[entry(rows),entry(records)],'feature_schemas':{'N':['risk']}})
    source = tmp_path/'source.json'; write(source, {'sha256':{}})
    plan = tmp_path/'plan.json'; write(plan,dict(source_sha256=frozen.sha(frozen.__file__), tests_sha256=frozen.sha(BASE/'tests/test_v2_archive_latency.py'),source_freeze_sha256=frozen.sha(source)))
    output = tmp_path/'profile.json'
    immutable = {str(p):frozen.sha(p) for p in tmp_path.rglob('*') if p.is_file()}
    # Only root-completion metadata is synthetic; the profiler/load/predict path is real.
    with patch.object(frozen, 'validate_completion', return_value=time.time()+60):
        with pytest.raises(AttributeError, match="Can't get attribute 'Model'"):
            frozen.run(methods, rows, [records], source, plan, output)
        assert not output.exists()
        with compat.model_alias(): result = frozen.run(methods, rows, [records], source, plan, output)
    assert len(result['profiles']) == 1
    assert result['profiles'][0]['warm_single_row_prediction']['n'] == 16
    assert result['profiles'][0]['failures'] == []
    assert all(frozen.sha(p)==h for p,h in immutable.items())
