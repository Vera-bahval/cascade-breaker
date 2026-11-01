"""Own-fixture checks only; never imports earlier tests or evaluation artifacts."""
import builtins
import copy
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))


def fixture(stage='P0'):
    c = dict(record_id='record', session_id='session', user_id='user', namespace='ns',
             workflow_id='flow', parent_workflow_id='parent', origin_portal='admin',
             technical_actor='invoice', vendor_id=1, invoice_id=2, current_vendor_id=1,
             attachment_file_ids=[], call_id='call', invoice_version='iv', vendor_version='vv',
             account_ref='account')
    f = dict(session_valid=True, vendor_in_scope=True, invoice_in_scope=True,
             invoice_vendor_matches=True, tool_scope_matches=True)
    o = dict(schema_version=4, checkpoint=stage, event_seq=100, context=c,
             proposal={'tool': None if stage == 'P0' else 'get_invoice_details'}, facts=f, provenance={})
    for k,v in f.items():
        o['provenance'][k] = [dict(source='server_context', event_seq=90, subject_matches=True,
             operation='session_validate' if k == 'session_valid' else 'structured_compare',
             record_id='proof', value=v, **{k:c[k] for k in ['namespace','session_id','workflow_id',
             'vendor_id','invoice_id','invoice_version','vendor_version','call_id']})]
    return o


class TrainingTests(unittest.TestCase):
    def test_new_proof_changes_without_old_feature_changes(self):
        from features import features, mandatory_proof_gate
        a=fixture(); b=copy.deepcopy(a); b['provenance']['session_valid'][0]['event_seq']=101
        self.assertEqual(features(a,'old'),features(b,'old'))
        self.assertNotEqual(features(a),features(b))
        self.assertTrue(mandatory_proof_gate(a,'A')['allow'])
        self.assertFalse(mandatory_proof_gate(b,'A')['allow'])

    def test_opaque_ids_and_operation_text_invariant(self):
        from features import features
        a=fixture(); b=copy.deepcopy(a)
        for node in [b['context'],*[p for ps in b['provenance'].values() for p in ps]]:
            for k in ['record_id','session_id','namespace','workflow_id','call_id','account_ref','invoice_version','vendor_version']:
                if k in node: node[k]='renamed-'+node[k]
        b['context']['user_id']='other'; b['context']['parent_workflow_id']='other-parent'
        for ps in b['provenance'].values():
            for p in ps:
                if p['operation']!='session_validate':p['operation']='failed_error_truncated_BLOCK'
        b['untrusted_text']={'agent':'BLOCK'}; b['labels']='ALLOW'
        self.assertEqual(features(a),features(b))

    def test_source_group_weights_and_split_validation(self):
        from experiment import training_weights, validate_metadata
        m=[dict(source=s,group_id=g,split='TRAIN',split_group_id=g,episode_id=g,prefix_id=str(i))
           for i,(s,g) in enumerate([('archive','a'),('archive','a'),('archive','b'),('synthetic','c')])]
        w=training_weights(m)
        self.assertAlmostEqual(sum(w[:3]),sum(w[3:])); self.assertAlmostEqual(sum(w[:2]),w[2])
        self.assertAlmostEqual(sum(w),4)
        with self.assertRaises(ValueError):validate_metadata([*m,dict(m[0],prefix_id='new',split='CAL')])
        with self.assertRaises(ValueError):validate_metadata([dict(m[0],executor='luna')])

    def test_missing_classes_and_train_categories(self):
        from models import fit_model,probabilities
        a=fixture(); b=fixture('P1')
        for family in ['logistic','catboost']:
            model=fit_model(family,[a,b]*3,['BLOCK','UNKNOWN']*3,[1]*6,'new',17)
            self.assertEqual(probabilities(model,[a])[0]['ALLOW'],0)
            self.assertFalse(any('CAL_ONLY' in s for s in model.named_steps['vectorizer'].get_feature_names_out()))
            b['context']['technical_actor']='CAL_ONLY'; probabilities(model,[b])
            self.assertFalse(any('CAL_ONLY' in s for s in model.named_steps['vectorizer'].get_feature_names_out()))
            constant=fit_model(family,[a],['UNKNOWN'],[1],'old',17)
            self.assertEqual(probabilities(constant,[a])[0],{'ALLOW':0.,'BLOCK':0.,'UNKNOWN':1.})
        unavailable=fit_model('logistic',[],[],[],'old',17)
        self.assertFalse(unavailable.available_)
        self.assertEqual(probabilities(unavailable,[a])[0],{'ALLOW':0.,'BLOCK':0.,'UNKNOWN':0.})

    def test_precomputed_cal_probabilities_match_raw_rows(self):
        from features import features
        from models import FeatureBatch,fit_model,probabilities
        train=[fixture(),fixture('P1')]*2
        cal=[fixture('P1'),fixture()]
        cal[0]['context']['technical_actor']='payments'
        for mode in ['old','new']:
            for family in ['logistic','catboost']:
                with self.subTest(mode=mode,family=family):
                    prepared=FeatureBatch([features(row,mode) for row in train],mode)
                    model=fit_model(family,prepared,['ALLOW','UNKNOWN']*2,[1]*4,mode,17)
                    expected=probabilities(model,cal)
                    actual=probabilities(model,FeatureBatch([features(row,mode) for row in cal],mode))
                    self.assertEqual(actual,expected)

    def test_p2_requires_matching_explicit_delegation_call(self):
        from features import mandatory_proof_gate
        a=fixture('P2');c=a['context']
        c.update(technical_actor='orchestrator',delegated_actor='fraud',
                 delegation_succeeded=True,delegation_call_id=c['call_id'])
        a['facts']['delegation_subject_matches']=True
        a['provenance']['delegation_subject_matches']=copy.deepcopy(a['provenance']['tool_scope_matches'])
        c['claim']=dict(record_id='claim',key=json.dumps(['ns','invoice',2,1]),
            owner_workflow_id='flow',generation=1,state='active',acquired_seq=5)
        for contract in ['A','B']:
            with self.subTest(contract=contract):
                self.assertTrue(mandatory_proof_gate(a,contract)['allow'])
                b=copy.deepcopy(a);b['context']['delegation_call_id']='different-call'
                self.assertFalse(mandatory_proof_gate(b,contract)['allow'])
                for field in ['call_id','delegation_call_id']:
                    missing=copy.deepcopy(a);missing['context'][field]=None
                    self.assertFalse(mandatory_proof_gate(missing,contract)['allow'])

    def test_optional_human_and_permission_denial(self):
        from features import mandatory_proof_gate
        a=fixture(); a['facts']['human_approved']=False
        self.assertTrue(mandatory_proof_gate(a,'A')['allow'])
        a['facts']['session_valid']=False; a['provenance']['session_valid'][0]['value']=False
        self.assertFalse(mandatory_proof_gate(a,'A')['allow'])

    def test_calibration_matches_straightforward_replay(self):
        from experiment import calibrate, replay_metrics, decide, episode_layout, fast_metrics
        rng=random.Random(13)
        probs=[];gold=[];meta=[]
        for ep in range(12):
            for j in range(rng.randint(1,4)):
                p=[rng.random() for _ in range(3)];p=[x/sum(p) for x in p]
                probs.append(dict(zip(['ALLOW','BLOCK','UNKNOWN'],p)))
                gold.append(rng.choice(['ALLOW','BLOCK','UNKNOWN']))
                meta.append(dict(episode_id=str(ep),event_seq=j,prefix_id=f'{ep}-{j}'))
        layout=episode_layout(meta,gold)
        for a in [.2,.5,.8,1.000001]:
            for b in [.2,.5,.8,1.000001]:
                ds=decide(probs,{'ALLOW':a,'BLOCK':b})
                self.assertEqual(replay_metrics(ds,gold,meta),fast_metrics(ds,gold,layout))
        result=calibrate([{'ALLOW':0.,'BLOCK':0.,'UNKNOWN':1.}],['ALLOW'],[{'episode_id':'x','event_seq':1}])
        self.assertFalse(result['feasible']);self.assertGreater(result['thresholds']['ALLOW'],1)

    def test_stop_timing(self):
        from experiment import replay_metrics
        meta=[dict(episode_id='x',event_seq=i) for i in range(3)]
        r=replay_metrics(['UNKNOWN','BLOCK','ALLOW'],['ALLOW','BLOCK','BLOCK'],meta)
        self.assertEqual(r['reached_actions'],1);self.assertEqual(r['correct_episodes'],0)
        r=replay_metrics(['ALLOW','BLOCK'],['BLOCK','BLOCK'],meta[:2])
        self.assertEqual(r['false_allows'],1);self.assertEqual(r['correct_episodes'],0)

    def test_chat_before_workflow_admission(self):
        from features import mandatory_proof_gate
        for stage in ['P0','P1']:
            a=fixture(stage);a['context'].update(technical_actor='admin_chat',workflow_id=None,parent_workflow_id=None)
            for ps in a['provenance'].values():
                for p in ps:p['workflow_id']=None
            self.assertTrue(mandatory_proof_gate(a,'A')['allow'])
            self.assertTrue(mandatory_proof_gate(a,'B')['allow'])
            if stage=='P1':
                a['proposal']['tool']='start_workflow'
                self.assertFalse(mandatory_proof_gate(a,'B')['allow'])
                a['proposal']['tool']='get_invoice_details'
            del a['provenance']['session_valid'][0]['workflow_id']
            self.assertFalse(mandatory_proof_gate(a,'A')['allow'])

    def test_newest_conflict_and_history_versions(self):
        from features import evidence,mandatory_proof_gate
        a=fixture();p=copy.deepcopy(a['provenance']['session_valid'][0]);p['value']=False
        a['provenance']['session_valid'].append(p)
        self.assertTrue(evidence(a,'session_valid')['conflict'])
        self.assertFalse(mandatory_proof_gate(a,'A')['allow'])
        a=fixture();a['facts']['binding_hold']=False
        p=copy.deepcopy(a['provenance']['session_valid'][0]);p.update(source='native_tool',operation='hold_history',value=False,invoice_version='old',vendor_version='old')
        a['provenance']['binding_hold']=[p]
        self.assertTrue(evidence(a,'binding_hold')['valid'])
        p2=copy.deepcopy(p);p2.update(event_seq=95,value=True)
        a['provenance']['binding_hold'].append(p2)
        self.assertFalse(evidence(a,'binding_hold')['valid'])

    def test_equal_decimal_proofs_do_not_conflict(self):
        from features import evidence
        a=fixture();a['facts']['invoice_amount']='100.00'
        p=copy.deepcopy(a['provenance']['session_valid'][0]);p.update(source='native_tool',operation='amount_read',value='100')
        q=copy.deepcopy(p);q['value']='100.0';a['provenance']['invoice_amount']=[p,q]
        self.assertFalse(evidence(a,'invoice_amount')['conflict'])
        self.assertTrue(evidence(a,'invoice_amount')['valid'])

    def test_payment_optional_human_threshold_and_clearance(self):
        from features import mandatory_proof_gate,PAYMENT
        a=fixture('P4');a['context']['technical_actor']='payments';a['proposal'].update(tool='finstripe__create_transfer',amount='10000',currency='USD')
        a['facts'].update(invoice_amount='10000',invoice_currency='USD',invoice_status='approved',vendor_status='active',
            fraud_review_completed=True,binding_hold=False,amount_matches_invoice=True,recipient_matches_authorized=True,prior_completed_transfers=0)
        for fact in PAYMENT:
            p=copy.deepcopy(a['provenance']['session_valid'][0]);p.update(source='native_tool',operation='native_state',value=a['facts'][fact]);a['provenance'][fact]=[p]
        self.assertTrue(mandatory_proof_gate(a,'A')['allow'])
        self.assertTrue(mandatory_proof_gate(a,'payment_v3')['allow'])
        a['provenance']['invoice_currency'][0].update(source='initial_fixture',event_seq=-1)
        self.assertTrue(mandatory_proof_gate(a,'payment_v3')['allow'])
        a['provenance']['invoice_currency'][0]['event_seq']=90
        a['facts']['invoice_amount']='10001';a['provenance']['invoice_amount'][0]['value']='10001'
        self.assertIn('mandatory_proof_unavailable:human_approved',mandatory_proof_gate(a,'A')['reasons'])
        a['facts']['human_approved']=False;p=copy.deepcopy(a['provenance']['session_valid'][0]);p.update(source='independent_registry',operation='human',value=False);a['provenance']['human_approved']=[p]
        self.assertIn('required_permission_denied:human_approved',mandatory_proof_gate(a,'A')['reasons'])

    def test_calibration_selected_grid_equals_reference(self):
        from experiment import calibrate,replay_metrics,decide,SENTINEL
        import numpy as np
        ps=[dict(zip(['ALLOW','BLOCK','UNKNOWN'],v)) for v in [(.9,.05,.05),(.85,.1,.05),(.1,.85,.05),(.2,.7,.1),(.1,.15,.75)]]
        gold=['ALLOW','ALLOW','BLOCK','BLOCK','UNKNOWN']
        meta=[dict(episode_id=str(i),event_seq=1) for i in range(5)]
        gate=[True,True,True,True,False]
        result=calibrate(ps,gold,meta,gate)
        grid=[sorted(set(np.quantile([p[k] for p in ps],np.linspace(0,1,41)).tolist()+[.5,SENTINEL])) for k in ['ALLOW','BLOCK']]
        best=None
        for ta in grid[0]:
            for tb in grid[1]:
                ds=decide(ps,{'ALLOW':ta,'BLOCK':tb});ds=['UNKNOWN' if d=='ALLOW' and not g else d for d,g in zip(ds,gate)]
                m=replay_metrics(ds,gold,meta)
                if not m['false_allows'] and m['safe_stops']<=.05*m['safe_episodes']:
                    rank=(m['correct_episodes'],-m['safe_stops'],ta,tb)
                    if best is None or rank>best:best=rank
        self.assertEqual(result['thresholds'],{'ALLOW':best[2],'BLOCK':best[3]})

    def test_prepare_filters_luna_and_keeps_groups(self):
        from experiment import prepare,write_lines,write_json,read_lines
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ['archive','synthetic']:
                base=root/name;base.mkdir();rows=[];meta=[];gold=[]
                for i in range(3):
                    pid=str(i);row=dict(prefix_id=pid,observation=fixture())
                    rows.append(row);meta.append(dict(prefix_id=pid,episode_id=pid,group_id=pid,split_group_id='component'+pid,
                        checkpoint='P0',source=name,split='TRAIN' if i!=1 else 'CAL',executor='luna' if i==2 else 'mini'))
                    gold.append(dict(prefix_id=pid,requirements={'A01':'satisfied'},labels={'A':'ALLOW','B':'UNKNOWN','payment_v3':None}))
                for n,rs in [('observations',rows),('metadata',meta),('gold-actions',gold)]:write_lines(base/(n+'.jsonl.gz'),rs)
                write_json(base/'manifest.json',{})
            prepare(root/'prepared',root/'archive',root/'synthetic')
            m=list(read_lines(root/'prepared'/'metadata.jsonl.gz'))
            self.assertEqual(len(m),4);self.assertEqual({x['source'] for x in m},{'archive','synthetic'})
            self.assertTrue(all(x['group_id'].startswith(x['source']+':') for x in m))
            self.assertFalse(any('2'==x['prefix_id'].split(':')[-1] for x in m))

    def test_real_prediction_hash_verification_before_unpickle(self):
        from experiment import predict,write_json,write_lines,digest,read_lines
        from models import fit_model
        from unittest.mock import patch
        import pickle
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);freeze=root/'freeze';freeze.mkdir()
            a=fixture();b=copy.deepcopy(a);b['provenance']['session_valid'][0]['event_seq']=101
            model=fit_model('logistic',[a],['ALLOW'],[1],'old',17)
            with (freeze/'m.pickle').open('xb') as f:pickle.dump(model,f)
            write_json(freeze/'t.json',{v:{'thresholds':{'ALLOW':0.,'BLOCK':1.000001}} for v in ['raw','gated']})
            methods=[dict(name='own',contract='A',arm='old/archive',family='logistic',seed=17,model_file='m.pickle',model_sha256=digest(freeze/'m.pickle'),thresholds_file='t.json')]
            write_json(freeze/'freeze-manifest.json',dict(sources={},files={p.name:digest(p) for p in freeze.iterdir()},methods=methods))
            write_lines(root/'obs.jsonl.gz',[dict(prefix_id=str(i),observation=o) for i,o in enumerate([a,b])])
            write_lines(root/'meta.jsonl.gz',[dict(prefix_id=str(i),episode_id=str(i)) for i in range(2)])
            predict(freeze,root/'obs.jsonl.gz',root/'meta.jsonl.gz',root/'pred.gz')
            out=list(read_lines(root/'pred.gz'))
            self.assertEqual([r['decision'] for r in out],['ALLOW','ALLOW','ALLOW','UNKNOWN'])
            self.assertTrue(out[-1]['gate_changed']);self.assertTrue((root/'pred.gz.receipt.json').exists())
            (freeze/'m.pickle').write_bytes(b'corrupt')
            with patch('pickle.load',side_effect=AssertionError('unverified unpickle')):
                with self.assertRaises(ValueError):predict(freeze,root/'obs.jsonl.gz',root/'meta.jsonl.gz',root/'bad.gz')

    def test_predict_read_boundary_and_immutable_outputs(self):
        from experiment import write_json, write_lines, predict, read_lines
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); freeze=root/'freeze';freeze.mkdir()
            # Empty method freeze still verifies sources and exercises observation-only IO.
            write_json(freeze/'freeze-manifest.json',{'sources':{},'files':{},'methods':[]})
            write_lines(root/'obs.jsonl.gz',[{'prefix_id':'p','observation':fixture()}])
            write_lines(root/'meta.jsonl.gz',[{'prefix_id':'p','episode_id':'e'}])
            original=builtins.open
            def guarded(path,*args,**kwargs):
                if 'gold' in str(path) or 'outcome' in str(path):raise AssertionError('label read')
                return original(path,*args,**kwargs)
            with patch('builtins.open',guarded):predict(freeze,root/'obs.jsonl.gz',root/'meta.jsonl.gz',root/'pred.jsonl.gz')
            self.assertEqual(list(read_lines(root/'pred.jsonl.gz')),[])
            with self.assertRaises(FileExistsError):write_json(freeze/'freeze-manifest.json',{})

if __name__=='__main__':unittest.main()
