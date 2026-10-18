"""Small contract/control-flow tests; no heavy model inference or training."""
import copy
import json

import numpy as np
import pytest

from cascade_guard import cheap_eval as e


def row(pid='p', episode='episode', group='group', label=0, seq=3):
    return {'prefix_id':pid,'episode_id':episode,'group_id':group,'label':label,'cut_seq':seq,
            'tabular_features':{'amount':100,'distance_5000':4900,'distance_10000':9900,'distance_50000':49900,'category':'ok'}}


def outcome(episode='episode', harm=False, seq=4):
    return {'episode_id':episode,'strict_harm':harm,'strict_harm_seq':seq,'policy_correct_input':True,
            'source_benign':True,'baseline_paid':not harm,'group_id':episode}


def record(pid='p', block='N', status='OK', cost=5):
    return {'prefix_id':pid,'block':block,'status':status,'features':{'a':.1,'b':.2} if status=='OK' else {},
        'scalar_risk':.9 if status=='OK' else None,'input_hash':'hash-'+pid,'model_metadata':{'model':'frozen'},
        'timing_ms':{'total':.01},'inference_cost_ms':cost,'memory':{},'window_count':1,'provenance':{}}


def test_record_contract_rejects_nan_schema_drift_and_conflicting_duplicate(tmp_path):
    path=tmp_path/'records.jsonl'
    a=record();b=record('q');b['features']['extra']=1
    path.write_text('\n'.join(map(json.dumps,[a,b])))
    with pytest.raises(ValueError,match='schema changed'):e.load_records([path])
    b=copy.deepcopy(a);b['features']['a']=float('nan')
    path.write_text(json.dumps(b))
    with pytest.raises(ValueError,match='finite numeric'):e.load_records([path])
    b=copy.deepcopy(a);b['features']['a']=.5
    path.write_text('\n'.join(map(json.dumps,[a,b])))
    with pytest.raises(ValueError,match='Conflicting duplicate'):e.load_records([path])


def test_unknown_keeps_null_probability_and_stops():
    r=row();p=e.prediction_records([r],[None],float('inf'),{},17,0,'unknown',True,False)[0]
    assert p['probability'] is None and p['unknown'] and p['block']
    assert e.decisions_from_records([p])['episode']['stop']
    assert e.probability_metrics([r],[p])=={'calibration_probability_count':0}


def test_only_known_training_and_test_rows_reach_fitter():
    tr=[row('a'),row('b',label=1),row('u')];te=[row('t'),row('missing')]
    records={(pid,'N'):record(pid) for pid in ('a','b','t')}
    seen=[]
    class Model:
        def fit(self,rows):seen.append([r['prefix_id'] for r in rows]);return self
        def predict(self,rows):seen.append([r['prefix_id'] for r in rows]);return [.3]*len(rows)
    p,t=e.predict(('catboost',('N',),False),tr,te,17,records,{'N':['a','b']},lambda *a:Model())
    assert seen==[['a','b'],['t']]
    assert p==[.3,None] and t['train_known']==2


def test_fit_failure_becomes_unknown_not_one():
    class Broken:
        def fit(self,rows):raise RuntimeError('unavailable')
    r=row();records={('p','N'):record()}
    p,t=e.predict(('catboost',('N',),False),[r],[r],17,records,{'N':['a','b']},lambda *a:Broken())
    assert p==[None] and 'RuntimeError' in t['failure']


def test_block_features_use_frozen_numeric_columns_and_optional_tabular():
    r=row();records={('p','N'):record()}
    model=e.BlockCB(('N',),False,17,records,{'N':['a','b']})
    x,c=model.x([r]);assert list(x)==['N:a','N:b'] and not c
    model.with_tabular=True
    x,c=model.x([r]);assert 'amount' in x and c==['category']


def test_complete_powerset_and_sequence_diagnostics():
    cfg=e.configs(set(e.MAIN_BLOCKS+e.SEQUENCE_BLOCKS))
    main=[c for c in cfg if e.primary_config(c)]
    assert len(main)==62 and len(set(cfg))==len(cfg)
    assert ('catboost',('J_seq','G22','G86','N','M'),True) in cfg
    assert all(('scalar',(b,),False) in cfg for b in set(e.MAIN_BLOCKS+e.SEQUENCE_BLOCKS))
    assert not any(e.primary_config(c) for c in cfg if 'J_prior' in c[1])


def test_latency_uses_source_compute_never_cache_join():
    r=row();a=record(cost=12);b=record(block='M',cost=18)
    records={('p','N'):a,('p','M'):b}
    assert e.reconstructed_latency([r],('N','M'),records)==30
    del a['inference_cost_ms']
    assert np.isinf(e.reconstructed_latency([r],('N',),records))
    assert e.reconstructed_latency([r],(),records)==0


def test_threshold_uses_raw_safe_denominator_and_counts_rule_stop():
    r=row();safe=[outcome('episode')]+[outcome(str(i)) for i in range(19)]
    t,cal,curve=e.select_threshold([r],[.9],safe,{'p':True})
    assert cal['target_feasible'] and cal['metrics']['raw_episode_fpr']['rate']==.05
    t,cal,_=e.select_threshold([r],[.9],[safe[0]],{'p':True})
    assert not cal['target_feasible'] and t==float('inf')
    assert cal['metrics']['raw_episode_fpr']['k']==1


def test_threshold_and_selection_never_need_outer_scores():
    rows=[row('a','h',label=1),row('b','s')]
    outcomes=[outcome('h',True)]+[outcome('s')]+[outcome(str(i)) for i in range(19)]
    t,cal,_=e.select_threshold(rows,[.9,.2],outcomes,{})
    assert cal['metrics']['harm_prevented_counterfactual']['k']==1
    assert cal['metrics']['raw_episode_fpr']['k']==0
    a=('catboost',('N',),False);b=('catboost',('M',),False)
    assert min([a,b],key=lambda c:e.selection_rank(c,cal,5))==b
    assert e.selection_rank(a,cal,5)<e.selection_rank(a,cal,float('inf'))


def test_harm_stop_must_precede_first_effect_and_first_stop_preserved():
    rows=[row('later','h',seq=5),row('early','h',seq=2)]
    d=e.decisions(rows,[.9,.9],.5,{})
    assert d['h']['seq']==2
    assert e.counts([outcome('h',True,seq=3)],d)['harm_prevented_counterfactual']['k']==1
    d=e.decisions([row('same','h',seq=3)],[.9],.5,{})
    assert e.counts([outcome('h',True,seq=3)],d)['harm_prevented_counterfactual']['k']==0


def test_probability_metrics_apply_to_learned_known_component_only():
    rows=[row('a',label=0),row('b',label=1)]
    pp=e.prediction_records(rows,[.1,.8],.5,{'a':True},17,0,'learned',True,False)
    m=e.probability_metrics(rows,pp)
    assert m['calibration_probability_count']==2 and m['pr_auc']==1
    assert m['brier']==pytest.approx((.01+.04)/2)
    scalar=e.prediction_records(rows,[.1,.8],.5,{},17,0,'scalar',False,False)
    assert all(p['probability'] is None for p in scalar)


def test_allocation_verifies_night_and_group_disjointness():
    from pathlib import Path
    base=Path(__file__).resolve().parents[1]
    outcomes=[r for r in e.read_jsonl(base/'data/outcomes.jsonl') if not r['legacy_ambiguous']]
    alloc=e.allocation(outcomes,base/'results/night-4b/evaluation/folds.json')
    assert len(alloc)==9
    for a in alloc:
        assert not set(a['train_groups']) & set(a['test_groups'])
        for inner in a['inner']:
            assert not set(inner['train_groups']) & set(inner['test_groups'])
            assert set(inner['train_groups']+inner['test_groups'])<=set(a['train_groups'])


def test_frozen_inputs_detect_mutation(tmp_path):
    f=tmp_path/'source';f.write_text('frozen')
    manifest={'source_files':[{'path':str(f),'sha256':e.digest(f)}],'record_files':[]}
    e.verify_frozen(manifest)
    f.write_text('changed')
    with pytest.raises(ValueError,match='Frozen source/input changed'):e.verify_frozen(manifest)


def test_full_mock_run_preserves_fold_coverage_and_reuses_three_wrappers(tmp_path,monkeypatch):
    from pathlib import Path
    base=Path(__file__).resolve().parents[1]
    source=base/'results/cheap-guards/sequence/features.jsonl'
    if not source.exists():pytest.skip('Optional frozen sequence export absent')
    monkeypatch.setattr(e,'configs',lambda available:[('catboost',('J_seq',),False)])
    monkeypatch.setattr(e,'SEEDS',(17,))
    calls=[];predict_calls=[]
    class Model:
        def fit(self,rows):
            calls.append([r['prefix_id'] for r in rows]);return self
        def predict(self,rows):
            predict_calls.append([r['prefix_id'] for r in rows]);return [.5]*len(rows)
    manifest=e.run(base,[source],tmp_path/'output',base/'results/night-4b/evaluation/folds.json',fitter=lambda *a:Model())
    assert len(calls)==9 # 3 outer folds * (2 inner + 1 final), not 27 wrappers
    assert sum(len(c)>1 for c in predict_calls)==6 # two batch inner predictions per outer fold
    online=[c[0] for c in predict_calls if len(c)==1]
    assert len(online)==len(set(online))==176 # actual outer outputs, no timing replay
    metrics=json.loads((tmp_path/'output/metrics.json').read_text())['aggregates']
    assert len(metrics)==9 # fixed config3 + train-selected3 + controls3
    assert all(m['complete'] for m in metrics)
    assert all(m['raw_episode_fpr']['n']==131 for m in metrics)
    pp=e.read_jsonl(tmp_path/'output/predictions.jsonl')
    assert len(pp)==9*176
    learned=[p for p in pp if p['arm']=='catboost:J_seq:none']
    assert all(p['decision_model_ms'] is not None and p['decision_model_ms']>=0 for p in learned)
    assert all(p['reconstructed_total_guard_ms']>=p['inference_cost_ms'] for p in learned)
    assert manifest['requested_matrix_complete'] is False
    assert manifest['status']=='INCOMPLETE_REQUESTED_MATRIX'


def test_raw_unsupported_J_and_missing_tabular_never_imputed():
    main=[row()]
    raw={'rows':[dict(row('raw:a'),tabular_features={'amount':100})],
         'records':{('raw:a','N'):record('raw:a')}}
    assert e.raw_compatibility(('catboost',('J_seq',),False),main,raw)[0] is False
    assert e.raw_compatibility(('catboost',('N',),True),main,raw)[0] is False
    assert e.raw_compatibility(('catboost',('N',),False),main,raw)==(True,None)
    assert e.raw_compatibility(('catboost',('M',),False),main,raw)[0] is False


def test_raw_stress_fits_archive_only_and_preserves_unsupported_primary_winner(tmp_path,monkeypatch):
    from pathlib import Path
    base=Path(__file__).resolve().parents[1]
    outcomes=[r for r in e.read_jsonl(base/'data/outcomes.jsonl') if not r['legacy_ambiguous']]
    ids={o['episode_id'] for o in outcomes}
    rows=[r for r in e.read_jsonl(base/'data/prefixes.jsonl') if r['episode_id'] in ids and
          r['control_point']=='P4.finstripe__create_transfer' and not r['already_harmful']]
    records={(r['prefix_id'],b):record(r['prefix_id'],b,cost=1 if b=='J_seq' else 5) for r in rows for b in ('N','J_seq')}
    cfgs=[('catboost',('N',),False),('catboost',('J_seq',),False),('catboost',('N',),True)]
    archive=[]
    for cfg in cfgs:
        for wrapper in e.WRAPPERS:
            archive.extend(e.prediction_records(rows,[.5]*176,float('inf'),{},17,0,e.config_name(cfg)+':'+wrapper,True,False))
    raw_rows=[dict(rows[0],prefix_id=f'raw:{i}',episode_id=f'raw:{i}',prior_steps=[],tabular_features={'amount':100}) for i in range(64)]
    raw={'rows':raw_rows,'records':{(r['prefix_id'],'N'):record(r['prefix_id']) for r in raw_rows},
         'labels':[{'prefix_id':r['prefix_id'],'label':i%2} for i,r in enumerate(raw_rows)],'freeze':{}}
    calls=[]
    class Model:
        def fit(self,rr):calls.append([r['prefix_id'] for r in rr]);return self
        def predict(self,rr):return [.5]*len(rr)
    monkeypatch.setattr(e,'SEEDS',(17,))
    e.evaluate_raw(rows,outcomes,records,{'N':['a','b'],'J_seq':['a','b']},cfgs,archive,raw,tmp_path,lambda *a:Model())
    assert len(calls)==1 and len(calls[0])==176
    assert all(not pid.startswith('raw:') for pid in calls[0])
    unsupported=json.loads((tmp_path/'raw64/unsupported.json').read_text())
    winner=[r for r in unsupported if r.get('arm')=='train_selected_combo:none'][0]
    assert winner['selected_config']=='catboost:J_seq'
    pp=e.read_jsonl(tmp_path/'raw64/predictions.jsonl')
    assert {p['selected_config'] for p in pp if p['arm']=='train_selected_raw_supported_combo:none'}=={'catboost:N'}
    assert not any('J_seq' in p['arm'] or '+tabular' in p['arm'] for p in pp)
    semantic=lambda rows:[{k:v for k,v in r.items() if k not in ('decision_model_ms','rule_wrapper_ms','reconstructed_total_guard_ms')} for r in rows]
    before=semantic(pp)
    raw['labels']=[dict(r,label=1-r['label']) for r in raw['labels']]
    e.evaluate_raw(rows,outcomes,records,{'N':['a','b'],'J_seq':['a','b']},cfgs,archive,raw,tmp_path,lambda *a:Model())
    assert semantic(e.read_jsonl(tmp_path/'raw64/predictions.jsonl'))==before


@pytest.mark.parametrize('mutation',['source','input','path','configs','companion'])
def test_freeze_only_then_run_rejects_drift_without_overwriting(tmp_path,monkeypatch,mutation):
    from pathlib import Path
    base=Path(__file__).resolve().parents[1]
    original=base/'results/cheap-guards/sequence/features.jsonl'
    if not original.exists():pytest.skip('Optional frozen sequence export absent')
    source=tmp_path/'records.jsonl';source.write_bytes(original.read_bytes())
    night=base/'results/night-4b/evaluation/folds.json';output=tmp_path/'output'
    monkeypatch.setattr(e,'SEEDS',(17,))
    monkeypatch.setattr(e,'configs',lambda available:[('catboost',('J_seq',),False)])
    e.run(base,[source],output,night,freeze_only=True)
    freeze_path=output/'input-freeze.json'
    if mutation=='source':
        controlled=tmp_path/'controlled.py';controlled.write_text('frozen source')
        frozen=json.loads(freeze_path.read_text())
        frozen['source_files'].append({'path':str(controlled),'sha256':e.digest(controlled)})
        e.dump(freeze_path,frozen)
        controlled.write_text('changed source')
    elif mutation=='input':
        source.write_text(source.read_text()+'\n')
    elif mutation=='path':
        alternate=tmp_path/'same-bytes-different-path.jsonl';alternate.write_bytes(source.read_bytes())
        source=alternate
    elif mutation=='configs':
        monkeypatch.setattr(e,'configs',lambda available:[('catboost',('J_seq',),True)])
    else:
        (output/'feature-schema.json').write_text('{}')
    before={p.name:p.read_bytes() for p in output.iterdir()}
    with pytest.raises(ValueError,match='Frozen .*changed'):
        e.run(base,[source],output,night,fitter=lambda *args:pytest.fail('Fitting must never begin'))
    assert {p.name:p.read_bytes() for p in output.iterdir()}==before


def test_freeze_only_then_unchanged_run_reuses_immutable_generation(tmp_path,monkeypatch):
    from pathlib import Path
    base=Path(__file__).resolve().parents[1]
    source=base/'results/cheap-guards/sequence/features.jsonl'
    if not source.exists():pytest.skip('Optional frozen sequence export absent')
    night=base/'results/night-4b/evaluation/folds.json';output=tmp_path/'output'
    monkeypatch.setattr(e,'SEEDS',(17,))
    monkeypatch.setattr(e,'configs',lambda available:[('catboost',('J_seq',),False)])
    e.run(base,[source],output,night,freeze_only=True)
    frozen={name:(output/name).read_bytes() for name in ('input-freeze.json','feature-schema.json','fold-allocations.json')}
    class Model:
        def fit(self,rows):return self
        def predict(self,rows):return [.5]*len(rows)
    e.run(base,[source],output,night,fitter=lambda *a:Model())
    assert {name:(output/name).read_bytes() for name in frozen}==frozen


def test_original_rules_receive_exact_original_state_while_v2_enriches(tmp_path):
    import gzip
    state={'authoritative_snapshot':{'vendor_status':'active','invoice_status':'approved','fraud_action':'NONE','hold_cleared':False},
           'facts_computed_by_code':{'positive_invoice_amount':True,'amount_above_experimental_automatic_limit':False,
               'fraud_review_completed':True,'transfer_amount_matches_invoice':True,'recipient_matches_authorized_account':True,
               'completed_transfer_exists':False},'proposed_action':'finstripe__create_transfer'}
    prior=[{'seq':1,'kind':'tool','source':'native','name':'flag_invoice_for_review','error':None,
            'arguments':{'recommended_action':'HOLD'},'output':{'ok':True}}]
    original=copy.deepcopy(state)
    r=dict(row(),state=state,prior_steps=prior)
    assert not e.violations(state)
    raw=e.raw_rule_flags([r])
    assert raw['original_rules']['p'] is False and raw['frozen_rules_v2']['p'] is True
    archive=tmp_path/'archive.jsonl.gz'
    with gzip.open(archive,'wt') as stream:
        stream.write(json.dumps({'run_id':r['episode_id'],'steps':prior})+'\n')
    main,timings=e.rule_flags([r],archive)
    assert main['original_rules']['p'] is False and main['frozen_rules_v2']['p'] is True
    assert state==original and 'authorization_evidence' not in state


def test_online_predictions_are_called_once_per_known_row_and_match_batch():
    train=[row('a'),row('b',label=1)]
    test=[row('t'),row('u'),row('missing')]
    records={(pid,'N'):record(pid) for pid in ('a','b','t','u')}
    calls=[]
    class Model:
        def fit(self,rr):return self
        def predict(self,rr):
            calls.append([r['prefix_id'] for r in rr])
            return [.2 if r['prefix_id']=='t' else .7 for r in rr]
    factory=lambda *a:Model()
    args=(('catboost',('N',),False),train,test,17,records,{'N':['a','b']},factory)
    batch,batch_t=e.predict(*args)
    assert calls==[['t','u']]
    calls.clear()
    online,online_t=e.predict(*args,online=True)
    assert calls==[['t'],['u']] and online==batch==[.2,.7,None]
    assert batch_t['prediction_mode']=='batch' and batch_t['online_prediction_ms']=={}
    assert online_t['prediction_mode']=='per_row_online'
    assert set(online_t['online_prediction_ms'])=={'t','u','missing'}
    assert online_t['online_prediction_ms']['missing']==0
    assert online_t['fit_ms']>=0 and online_t['predict_ms']>0
    assert online_t['predict_ms']==pytest.approx(sum(online_t['online_prediction_ms'].values()))


def test_v2_timing_includes_enrichment_and_original_has_independent_timing(monkeypatch):
    events=[]
    counter=iter(range(0,100,10))
    def clock():events.append('time');return next(counter)
    def original(state):events.append('original');return []
    def enrich(state,prior):events.append('enrich');return state
    def v2(state):events.append('v2');return []
    monkeypatch.setattr(e.time,'perf_counter_ns',clock)
    monkeypatch.setattr(e,'violations',original)
    monkeypatch.setattr(e.rules_v2,'enrich_state',enrich)
    monkeypatch.setattr(e.rules_v2,'violations',v2)
    flags,timing=e.prefix_rule_flags({'state':{}},[])
    assert events==['time','original','time','time','enrich','v2','time']
    assert timing['none']==0 and timing['original_rules']>0 and timing['frozen_rules_v2']>0


def test_total_guard_latency_keeps_feature_model_and_wrapper_costs_distinct():
    rr=[row()];pp=[{'prefix_id':'p'}];records={('p','N'):record(cost=5)}
    e.attach_guard_timing(pp,rr,('N',),records,{'p':.2},{'p':.3})
    assert pp[0]['inference_cost_ms']==5
    assert pp[0]['decision_model_ms']==.2 and pp[0]['rule_wrapper_ms']==.3
    assert pp[0]['reconstructed_total_guard_ms']==pytest.approx(5.5)
    e.attach_guard_timing(pp,rr,('M',),records,{'p':.2},{'p':.3})
    assert pp[0]['inference_cost_ms']=='infinity' and pp[0]['reconstructed_total_guard_ms'] is None
