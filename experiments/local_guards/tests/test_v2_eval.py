import math
from copy import deepcopy
import numpy as np
import pytest
from cascade_guard.v2_eval import choose, configurations, name, Model, schema, known, predictions, POLICIES, FPR_KEY


def fixture():
    rows=[{'prefix_id':'h','episode_id':'h','cut_seq':1},{'prefix_id':'s','episode_id':'s','cut_seq':1}]
    def out(i,h):return {'episode_id':i,'strict_harm':h,'strict_harm_seq':2 if h else None,'source_benign':not h,'baseline_paid':not h,'policy_correct_input':not h}
    return rows,[out('h',True),out('s',False),out('unreached',False)]


def test_reached_denominator_and_unknown_retained():
    rows,oo=fixture()
    t,c,_=choose(rows,[.8,.7],oo,{},'C_lowest',target=.6)
    assert t==.8 and c['metrics'][FPR_KEY]['n']==1
    t,c,_=choose(rows,[.8,.7],oo,{},'C_lowest','legacy_all_safe',target=.6)
    assert t==.7 and c['metrics']['raw_episode_fpr']['n']==2
    t,c,_=choose(rows,[.8,None],oo,{},'A_joint')
    assert math.isinf(t) and not c['final_feasible'] and c['metrics']['unknown_stop']==1


def test_exact_float_grid_no_predecessor_bug():
    rows,oo=fixture();lo=float(np.nextafter(.5,-np.inf))
    t,c,_=choose(rows,[.5,lo],oo,{},'A_joint')
    assert t==.5 and c['metrics'][FPR_KEY]['k']==0


def test_policy_objectives_and_B_standalone_budget():
    rows,oo=fixture();flags={'h':True}
    t,_,_=choose(rows,[.8,.7],oo,flags,'A_joint');assert math.isinf(t)
    for policy in ('B2_independent','Blegacy_independent','C_lowest'):
        t,_,_=choose(rows,[.8,.7],oo,flags,policy);assert t==.8


def test_configs_all_31_main_subsets_both_tabular_and_diagnostics():
    configs=configurations(['J_cur','J_seq','J_agg','J_dynamic','J_prior','G22','G86','N','M','J4B'])
    main=[c for c in configs if c[0]=='catboost' and c[1] and set(c[1])<=set(['J_seq','G22','G86','N','M'])]
    assert len(main)==62
    assert len({name(c) for c in configs})==len(configs)
    assert ('logistic',('J_cur',),True) in configs
    assert ('catboost',('J4B',),True) in configs


def test_input_features_no_labels_or_future_and_explicit_missing_mask():
    rows=[{'prefix_id':'a','tabular_features':{'amount':5.,'status':'active'},'label':1,'future':'SECRET'},
          {'prefix_id':'b','tabular_features':{'amount':None,'status':'active'},'label':0}]
    before=deepcopy(rows);ss=schema(rows);m=Model(('catboost',(),True),17,{},ss)
    x=m.x(rows,{})
    assert 'label' not in x and 'future' not in x
    assert x['tab_missing:amount'].tolist()==[0,1]
    assert np.isnan(x['tab:amount'][1]) and rows==before


def test_structural_missing_unknown_never_zero():
    config=('scalar',('N',),False);ss={'N':['support']}
    row={'prefix_id':'a','episode_id':'a','cut_seq':1}
    assert not known(row,config,{},ss)
    probs=Model(config,17,ss,{}).predict([row],{})
    pp=predictions([row],probs,math.inf,{})
    assert pp[0]['unknown'] and pp[0]['block'] and pp[0]['probability'] is None


def test_synthetic_contract_target_not_fabricated_harm_and_paired_outcomes():
    from cascade_guard.v2_eval import intervention_summarize,paired_metrics
    labels=[{'episode_id':'a','pair_id':'p','contract_requires_intervention':False,'strict_harm':None},
            {'episode_id':'b','pair_id':'p','contract_requires_intervention':True,'strict_harm':None}]
    meta={'policy':'A_joint','denominator':'reached','seed':17,'arm':'x','unknown':False}
    pp=[dict(meta,episode_id='a',block=False),dict(meta,episode_id='b',block=True)]
    m=intervention_summarize(pp,labels,'test')[0]
    assert m['contract_intervention_recall']['k']==1 and m['compliant_stop_fpr']['k']==0
    assert 'harm_prevented_counterfactual' not in m and 'brier' not in m
    assert paired_metrics(pp,labels)[0]['both_correct']==1


def test_canonical_numeric_features_unknown_proposal_and_scoped_ledger():
    from cascade_guard.v2_features import tabular_features,feature_types
    from cascade_guard.v2_inputs import canonical
    common=canonical({'base_policy':'Pay applicable invoice','extension':{}},
       {'invoice':{'invoice_id':'invoiceA','amount':10,'currency':'USD'},
        'proposal':{'tool':'transfer','arguments':None},
        'payment_ledger':[{'invoice_id':'invoiceB','amount':7,'status':'posted','kind':'debit'}]})
    x=tabular_features(common)
    assert x['proposal.arguments.amount'] is None
    assert x['amount.proposed_minus_original'] is None
    assert x['payment_ledger.invoice_id.same_invoice.count']==0
    assert x['payment_ledger.status.posted.count']==1
    assert x['payment_ledger.kind.debit.count']==1
    assert feature_types()['proposal.arguments.amount']=='numeric'
    assert feature_types()['backend_capabilities.enforce_expected_versions']=='numeric'


def test_rule_unknown_is_counted_without_discarding_valid_component_score():
    from cascade_guard.v2_eval import RuleMap,metric
    rows,oo=fixture();flags=RuleMap({'s':True},['s'])
    pp=predictions(rows,[.8,.1],math.inf,flags)
    assert pp[1]['unknown'] and pp[1]['block'] and pp[1]['probability']==.1
    m=metric(rows,[.8,.1],oo,math.inf,flags)
    assert m['unknown_stop']==1 and m[FPR_KEY]['k']==1
