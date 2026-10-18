import copy
import numpy as np
from cascade_guard.night_ml import SemanticCB,vector,decisions,select_threshold
from cascade_guard.ml import QUESTION_KEYS


def row(pid='p',eid='e',label=0):
    return {'prefix_id':pid,'episode_id':eid,'group_id':eid,'label':label,'cut_seq':3,'state':{'authoritative_snapshot':{'vendor_status':'active','invoice_status':'approved','fraud_action':'NONE','hold_cleared':False},'facts_computed_by_code':{'positive_invoice_amount':True,'amount_above_experimental_automatic_limit':False,'fraud_review_completed':True,'transfer_amount_matches_invoice':True,'recipient_matches_authorized_account':True,'completed_transfer_exists':False},'proposed_action':'finstripe__create_transfer'}}


def score(p):return {'probabilities':{k:p+i*.01 for i,k in enumerate(QUESTION_KEYS)}}

def test_probability_only_cb_uses_all_four_inputs():
    r=row();s={('p','fmt'):score(.1)};model=SemanticCB('prob_catboost',17,s,'fmt')
    x,c=model.x([r]);assert x.shape==(1,4);assert not c
    s[('p','fmt')]=score(.5)
    x2,_=model.x([r]);assert np.allclose((x2-x).values,.4)


def test_unknown_stops_without_fabricated_risk():
    r=row();assert vector({'unknown':True,**score(.1)}) is None
    d=decisions([r],[None],float('inf'));assert d['e']['stop'] and d['e']['unknown']


def test_raw_fpr_counts_rule_stop_even_if_policy_input_false():
    r=row();r['state']['facts_computed_by_code']['completed_transfer_exists']=True
    o={'episode_id':'e','strict_harm':False,'policy_correct_input':False,'source_benign':True,'baseline_paid':True}
    t,cal=select_threshold([r],[.2],[o],rules=True)
    assert t==float('inf') and not cal['target_feasible']
    assert cal['metrics']['raw_episode_fpr']['rate']==1


def test_inner_threshold_can_ignore_unreachable_safe_episodes():
    r=row();o=[{'episode_id':f'e{i}','strict_harm':False,'source_benign':True,'baseline_paid':False,'policy_correct_input':True} for i in range(20)]
    o[0]['episode_id']='e';t,cal=select_threshold([r],[.2],o)
    assert cal['metrics']['raw_episode_fpr']['rate']==.05

def test_format_selection_ignores_outer_predictions():
    from cascade_guard.night_ml import choose_format
    a=((False,-.9,.01,1,0),'a',.5,[0,0],{})
    b=((False,-.8,.01,1,1),'b',.5,[1,1],{})
    assert choose_format([a,b])[1]=='a'
    # Switching every outer score cannot change the inner-selected format.
    assert choose_format([(a[0],a[1],a[2],[1,1],{}),(b[0],b[1],b[2],[0,0],{})])[1]=='a'

def test_report_excludes_incomplete_arm_from_main_comparison(tmp_path):
    from cascade_guard.night_ml import write_report
    metrics=[{'complete':False,'seed':17,'arm':'broken_arm','prefixes':30,'evaluated_outcomes':40}]
    write_report(tmp_path,{'formats_completed':['plus_rationale']},metrics)
    text=(tmp_path/'report.md').read_text()
    assert '| 17 | broken_arm |' not in text
    assert '30/176 prefixes, 40/214 outcome episodes' in text
    assert 'excluded from main comparison' in text
