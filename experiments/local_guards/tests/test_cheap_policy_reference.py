"""Artifact invariants for reconstructed cached-only 4B comparison."""
import json
from pathlib import Path
from collections import defaultdict
import pytest
from cascade_guard import cheap_policy_reference as p
from cascade_guard import cheap_policy_comparison as c

BASE=Path(__file__).resolve().parents[1]
OUTPUT=BASE/'results/policy-comparison/matched-reference'


def test_all_cached_fit_ids_obey_inner_and_outer_allocation():
    if not (OUTPUT/'cached-fits.jsonl').exists():pytest.skip('Generate cached-fit artifacts first')
    rows,_,_,_,alloc=p.inputs(BASE)
    episode={r['prefix_id']:r['episode_id'] for r in rows}
    allocation={(a['seed'],a['outer_fold']):a for a in alloc}
    fits=p.e.read_jsonl(OUTPUT/'cached-fits.jsonl')
    assert len(fits)==81
    for fit in fits:
        a=allocation[fit['seed'],fit['outer_fold']]
        for record in fit['inner']:
            assert episode[record['prefix_id']] in a['inner'][record['inner_fold']]['test_episode_ids']
            assert episode[record['prefix_id']] not in a['test_episode_ids']
        assert {episode[r['prefix_id']] for r in fit['outer']} <= set(a['test_episode_ids'])
        assert len({r['prefix_id'] for r in fit['inner']})==len(fit['inner'])
    audit=json.loads((OUTPUT/'legacy-reproduction.json').read_text())
    assert audit['checked_fixed_predictions']==9504
    assert audit['max_abs_score_delta']==0
    assert audit['decision_difference_count']==0


def test_policy_comparison_complete_and_no_score_mutation():
    if not (OUTPUT/'metrics.json').exists():pytest.skip('Generate policy artifacts first')
    records=p.e.read_jsonl(OUTPUT/'predictions.jsonl')
    metrics=json.loads((OUTPUT/'metrics.json').read_text())['aggregates']
    assert len(metrics)==324 and len(records)==57024
    assert all(m['complete'] and m['raw_episode_fpr']['n']==131 for m in metrics)
    same=defaultdict(set)
    for r in records:
        if 'train_selected_format' not in r['arm']:
            head,fmt,_=r['arm'].split(':')
            same[r['seed'],r['outer_fold'],head,fmt,r['prefix_id']].add((r['probability'],r['scalar_risk']))
    assert all(len(v)==1 for v in same.values())
    folds=json.loads((OUTPUT/'folds.json').read_text())
    for r in folds:
        if 'selected_format' in r:
            assert min(r['candidates'],key=lambda t:t['rank'])['format']==r['selected_format']
        if r['policy']!='B_independent':
            assert r['calibration']['target_feasible']==r['calibration']['final_system_target_feasible']
    assert {m['policy'] for m in metrics}==set(c.POLICIES)
