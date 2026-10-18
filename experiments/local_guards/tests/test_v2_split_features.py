import json
import pytest
from cascade_guard.v2_split_features import split


def setup_files(tmp_path, scores):
    inputs = {}
    for name in ('archive', 'independent'):
        path = tmp_path/(name+'.jsonl')
        path.write_text(json.dumps({'prefix_id':name, 'input_hash':name+'-hash'})+'\n')
        inputs[name] = path
    path = tmp_path/'scores.jsonl'
    path.write_text(''.join(json.dumps(r)+'\n' for r in scores))
    return inputs, path


def records():
    return [{'prefix_id':n, 'input_hash':n+'-hash', 'block':'N', 'status':s,
             'features':{'x':.4} if s=='OK' else {}, 'scalar_risk':.3 if s=='OK' else None}
            for n,s in [('independent','UNKNOWN'),('archive','OK')]]


def test_blind_split_preserves_unknown_and_exact_records(tmp_path):
    rows = records();inputs, scores = setup_files(tmp_path, rows)
    manifest = split(inputs, scores, tmp_path/'views')
    assert manifest['outputs']['archive']['records'] == 1
    for row in rows:
        output = json.loads((tmp_path/'views'/row['prefix_id']/'N.jsonl').read_text())
        assert output == row
    assert split(inputs, scores, tmp_path/'views') == manifest


@pytest.mark.parametrize('problem', ['missing', 'duplicate', 'wrong_hash', 'wrong_id'])
def test_partial_or_misaligned_stage_rejected(tmp_path, problem):
    rows=records()
    if problem=='missing':rows.pop()
    elif problem=='duplicate':rows.append(rows[0])
    elif problem=='wrong_hash':rows[0]['input_hash']='wrong'
    else:rows[0]['prefix_id']='foreign'
    inputs, scores=setup_files(tmp_path, rows)
    with pytest.raises(ValueError):split(inputs, scores, tmp_path/'views')
    assert not (tmp_path/'views').exists()
