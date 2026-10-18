from copy import deepcopy
import math

import numpy as np
import pytest

from cascade_guard.cheap_policy_comparison import (
    choose_from_curves, choose_policy_threshold, convert_saved_curve,
    exact_curve, policy_rank, threshold_number, validate_cached_inputs,
)


def metric(tp, fp, positive=10, safe=100):
    return {'harm_prevented_counterfactual': {'k': tp, 'n': positive, 'rate': tp/positive},
            'raw_episode_fpr': {'k':fp, 'n':safe, 'rate':fp/safe}, 'unknown_stop':0}


def test_three_policies_have_distinct_intended_objectives():
    joint = [(math.inf,metric(8,0)),(.8,metric(8,0)),(.4,metric(8,4)),(.1,metric(9,6))]
    standalone = [(math.inf,metric(0,0)),(.8,metric(2,0)),(.4,metric(7,4)),(.1,metric(9,6))]
    assert choose_from_curves(joint,standalone,'A_joint')[0] == math.inf
    assert choose_from_curves(joint,standalone,'B_independent')[0] == .4
    assert choose_from_curves(joint,standalone,'C_lowest')[0] == .4


def test_independent_threshold_preserves_component_constraint_separately():
    joint = [(math.inf,metric(3,4)),(.5,metric(8,8))]
    independent = [(math.inf,metric(0,0)),(.5,metric(7,4))]
    t,cal = choose_from_curves(joint,independent,'B_independent')
    assert t == .5 and cal['target_feasible'] and not cal['final_system_target_feasible']
    assert cal['threshold_selection_metrics']['raw_episode_fpr']['k'] == 4
    assert cal['metrics']['raw_episode_fpr']['k'] == 8


def test_infeasible_wrapper_has_explicit_conservative_fallback():
    curve = [(math.inf,metric(5,7)),(.3,metric(9,9))]
    t,cal = choose_from_curves(curve,curve,'A_joint')
    assert math.isinf(t) and not cal['target_feasible'] and cal['fallback']


def test_exact_grid_does_not_include_adjacent_lower_float():
    hi=.5;lo=float(np.nextafter(hi,-np.inf))
    rows = [{'episode_id':'harm','prefix_id':'h','cut_seq':1},
            {'episode_id':'safe','prefix_id':'s','cut_seq':1}]
    out = [{'episode_id':'harm','strict_harm':True,'strict_harm_seq':2,'source_benign':False,'policy_correct_input':False},
           {'episode_id':'safe','strict_harm':False,'source_benign':False,'policy_correct_input':True}]
    curve=exact_curve(rows,[hi,lo],out,{})
    assert dict(curve)[hi]['raw_episode_fpr']['k'] == 0
    assert dict(curve)[lo]['raw_episode_fpr']['k'] == 1
    assert choose_policy_threshold(rows,[hi,lo],out,{},'A_joint')[0] == hi


def test_saved_adjacent_grid_is_rejected_not_silently_relabelled():
    hi=.5;lo=float(np.nextafter(hi,-np.inf))
    records=[{'threshold':'infinity','metrics':metric(0,0)}]
    records += [{'threshold':float(np.nextafter(v,-np.inf)),'metrics':metric(1,0)} for v in [hi,lo]]
    with pytest.raises(ValueError,match='Adjacent inner scores'):
        convert_saved_curve(records)


def test_ordinary_saved_grid_inversion_and_source_immutability():
    records=[{'threshold':'infinity','metrics':metric(0,0)},
             {'threshold':float(np.nextafter(.7,-np.inf)),'metrics':metric(3,0)}]
    before=deepcopy(records)
    assert convert_saved_curve(records)[1][0] == .7
    assert records == before
    assert math.isinf(threshold_number(None))


def test_unknown_remains_stop_with_null_score():
    rows=[{'episode_id':'safe','prefix_id':'s','cut_seq':1}]
    out=[{'episode_id':'safe','strict_harm':False,'source_benign':False,'policy_correct_input':True}]
    t,cal,curve=choose_policy_threshold(rows,[None],out,{},'A_joint')
    assert math.isinf(t) and curve[0][1]['unknown_stop'] == 1
    assert not cal['target_feasible']


def test_nested_rank_prefers_final_system_feasibility():
    a={'final_system_target_feasible':True,'metrics':metric(7,4)}
    b={'final_system_target_feasible':False,'metrics':metric(9,6)}
    assert policy_rank('a',a,100) < policy_rank('b',b,1)


def test_zero_safe_population_rejected():
    m=metric(1,0);m['raw_episode_fpr'].update(n=0,rate=None)
    with pytest.raises(ValueError,match='No safe'):
        choose_from_curves([(math.inf,m)],[(math.inf,m)],'A_joint')


@pytest.mark.parametrize('problem',['episode','cutoff','duplicate','fold','unknown'])
def test_strict_cached_prediction_join_rejects_corruption(problem):
    rows=[dict(prefix_id=str(i),episode_id='e'+str(i),cut_seq=3) for i in range(176)]
    allocations=[];predictions=[]
    arms=['scalar:X:'+w for w in ('none','original_rules','frozen_rules_v2')]
    arms+=['train_selected_combo:'+w for w in ('none','original_rules','frozen_rules_v2')]
    arms+=['NoDefense','R1','R2']
    for seed in (17,29,43):
        for fold in range(3):
            test=[r['episode_id'] for i,r in enumerate(rows) if i%3==fold]
            train=[r['episode_id'] for i,r in enumerate(rows) if i%3!=fold]
            allocations.append(dict(seed=seed,outer_fold=fold,train_groups=['tr'],test_groups=['te'],
                train_episode_ids=train,test_episode_ids=test,
                inner=[dict(train_groups=['a'],test_groups=['b'],train_episode_ids=train[::2],test_episode_ids=train[1::2])]))
            for arm in arms:
                for r in rows:
                    if r['episode_id'] in test:
                        predictions.append(dict(r,seed=seed,outer_fold=fold,arm=arm,
                            learned_component=False,probability=None,scalar_risk=.3,unknown=False))
    cfgs={'scalar:X':('scalar',('X',),False)}
    validate_cached_inputs(predictions,allocations,rows,cfgs)
    if problem=='duplicate':predictions.append(dict(predictions[0]))
    else:
        key,value={'episode':('episode_id','bad'),'cutoff':('cut_seq',4),'fold':('outer_fold',1),'unknown':('unknown',True)}[problem]
        predictions[0][key]=value
    with pytest.raises(ValueError):
        validate_cached_inputs(predictions,allocations,rows,cfgs)
