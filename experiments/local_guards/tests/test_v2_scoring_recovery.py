"""Public synthetic end-to-end scoring; never open experimental labels or models."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from cascade_guard import dataset, v2_eval
from cascade_guard.v2_preunblind import sha, validate

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery_05', BASE / 'scripts/recover_guard_v2_scoring_05.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


def fixture(root):
    methods = root / 'methods'; methods.mkdir(parents=True)
    def write(path, obj): path.write_text(json.dumps(obj))
    def lines(path, rows): path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    def entry(path): return {'path': str(path), 'sha256': sha(path)}
    rows = [dict(prefix_id=f'p{i}', episode_id=f'e{i}', cut_seq=4) for i in range(2)]
    rows_path = root / 'public-rows.jsonl'; lines(rows_path, rows)
    records = root / 'public-records.jsonl'
    lines(records, [dict(prefix_id=row['prefix_id'], block='N', status='OK') for row in rows])
    write(methods / 'training-input-freeze.json', {'files': []})
    write(methods / 'final-choices.json', [dict(policy='A_joint', denominator='reached', seed=17, arm='model', config='fixture')])
    write(methods / 'models.json', [dict(seed=17, config='fixture', blocks=['N'])])
    write(methods / 'METHODS_FROZEN.json', {'files': [entry(methods / name) for name in ('models.json', 'final-choices.json', 'training-input-freeze.json')]})
    dest = methods / 'public'; dest.mkdir()
    predictions = [dict(row, policy='A_joint', denominator='reached', seed=17, arm=arm, block=bool(i), unknown=False, probability=.8 if i else .2) for arm in ('model', 'NoDefense', 'R1', 'R2') for i, row in enumerate(rows)]
    lines(dest / 'predictions.jsonl', predictions)
    write(dest / 'PREDICTIONS_FROZEN.json', dict(rows_file=entry(rows_path), records=[entry(records)], methods_freeze_sha256=sha(methods / 'METHODS_FROZEN.json'), predictions_sha256=sha(dest / 'predictions.jsonl')))
    labels = root / 'PUBLIC_SYNTHETIC_LABELS.jsonl'
    lines(labels, [dict(episode_id=f'e{i}', pair_id='public-pair', family='synthetic', contract_requires_intervention=bool(i)) for i in range(2)])
    write(dest / 'ROOT_UNBLIND_05.json', dict(authorization='UNBLIND', labels_sha256=sha(labels), predictions_freeze_sha256=sha(dest / 'PREDICTIONS_FROZEN.json')))
    return methods, dest, labels


def test_frozen_scorer_real_string_path_failure_then_adapter_e2e(tmp_path):
    methods, dest, labels = fixture(tmp_path)
    before = {str(p): sha(p) for p in tmp_path.rglob('*') if p.is_file()}
    validate(methods, dest, expected_rows=2, labels=labels, unblind_marker=dest / 'ROOT_UNBLIND_05.json')
    with pytest.raises(AttributeError, match="'str' object has no attribute 'open'"):
        v2_eval.run_score(methods, dest, labels)
    assert not (dest / 'metrics.json').exists()
    assert not (dest / 'UNBLINDED.json').exists()
    original = v2_eval.read_jsonl
    with r.path_adapter(v2_eval, dataset):
        result = v2_eval.run_score(methods, dest, str(labels))
    assert v2_eval.read_jsonl is original is dataset.read_jsonl
    assert result['target'] == 'contract_requires_intervention'
    assert json.loads((dest / 'pair-metrics.json').read_text())['aggregates'][0]['both_correct'] == 1
    assert json.loads((dest / 'UNBLINDED.json').read_text())['rows'] == 2
    assert all(sha(path) == digest for path, digest in before.items())


def test_adapter_restores_after_exception_and_rejects_other_binding():
    fake = SimpleNamespace(read_jsonl=dataset.read_jsonl)
    with pytest.raises(RuntimeError):
        with r.path_adapter(fake, dataset): raise RuntimeError('public failure')
    assert fake.read_jsonl is dataset.read_jsonl
    with pytest.raises(ValueError, match='Unexpected evaluator'):
        with r.path_adapter(SimpleNamespace(read_jsonl=lambda _: []), dataset): pass


def four(tmp_path):
    locations = []
    labels = {}
    for i in range(4):
        methods, dest, path = fixture(tmp_path / str(i))
        locations.append((str(methods.relative_to(tmp_path)), dest.name, 2, str(i)))
        labels[str(i)] = {'path': str(path)}
    return {'root': str(tmp_path), 'labels': labels}, tuple(locations)


def test_four_real_validations_before_any_real_score(tmp_path):
    plan, destinations = four(tmp_path); events = []
    def validator(*args, **kwargs):
        events.append('validate'); return validate(*args, **kwargs)
    actual = v2_eval.run_score
    def scorer(*args):
        assert events[:4] == ['validate'] * 4
        events.append('score'); return actual(*args)
    with patch.object(r.old, 'DESTINATIONS', destinations), patch.object(r.old, 'deadline', lambda _: None), patch.object(v2_eval, 'run_score', scorer):
        checks = r.score_all(plan, v2_eval, dataset, validator)
    assert len(checks) == 4 and events == ['validate'] * 4 + ['score'] * 4
    assert all((tmp_path / folder / name / 'UNBLINDED.json').exists() for folder, name, _, _ in destinations)


def test_bad_fourth_label_join_prevents_all_scores(tmp_path):
    plan, destinations = four(tmp_path)
    Path(plan['labels']['3']['path']).write_text('{}\n')
    with patch.object(r.old, 'DESTINATIONS', destinations), patch.object(r.old, 'deadline', lambda _: None):
        with pytest.raises(ValueError, match='another label file'):
            r.score_all(plan, v2_eval, dataset, validate)
    assert all(not (tmp_path / folder / name / 'metrics.json').exists() for folder, name, _, _ in destinations)


def test_check_has_no_label_prevalidation_or_scorer(tmp_path):
    plan = {'root': str(tmp_path)}
    with patch.object(r, 'authorize', return_value=(plan, {})), patch.object(r, 'failure_gate'), patch.object(r, 'snapshot', return_value={'public-source': 'fixed'}), patch.object(r, 'score_all', side_effect=AssertionError('labels opened')):
        assert r.recover('public', 'public', 'public', execute=False)['labels_read'] is False
    assert not list(tmp_path.iterdir())
