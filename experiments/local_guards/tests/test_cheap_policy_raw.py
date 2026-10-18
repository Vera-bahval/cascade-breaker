from cascade_guard.cheap_policy_raw import redecide, decode_threshold
import math


def row(p=.3):
    return {'seed':17,'arm':'catboost:N:none','prefix_id':'x','cut_seq':None,
        'probability':p,'scalar_risk':None,'learned_component':True,
        'block':False,'unknown':False,'rule_stop':False,'inference_cost_ms':2.,
        'decision_model_ms':.1,'rule_wrapper_ms':0.}


def control(block=False):
    return {(17,'original_rules','x'):{'cut_seq':None,'block':block,'rule_wrapper_ms':.05}}


def test_raw_policy_or_and_probability_preserved():
    source=row(); result=redecide([source],.5,'original_rules',control(True),'B_independent')[0]
    assert result['block'] and result['rule_stop'] and result['probability']==.3
    assert not source['block'] and result['reconstructed_total_guard_ms']==2.15


def test_raw_unknown_not_zero_and_stops():
    result=redecide([row(None)],math.inf,'original_rules',control(),'A_joint')[0]
    assert result['unknown'] and result['block'] and result['probability'] is None


def test_exact_score_boundary_and_infinity():
    assert redecide([row()],.3,'original_rules',control(),'C_lowest')[0]['block']
    assert not redecide([row()],math.inf,'original_rules',control(),'A_joint')[0]['block']
    assert decode_threshold('infinity')==decode_threshold(None)==math.inf
