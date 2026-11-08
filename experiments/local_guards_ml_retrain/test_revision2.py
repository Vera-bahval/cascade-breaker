"""Own policy fixtures and tiny parity checks; no research corpus is opened."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import pickle
import tempfile
import unittest

from features_revision2 import features, evidence, mandatory_proof_gate, schema_valid
from features import features as original_features
from models import FeatureBatch, fit_model as original_fit_model
from models_revision2 import fit_model, probabilities, feature_rows, PARAMETERS, bind_reused_model
import models
import experiment_revision2 as experiment

HERE=Path(__file__).resolve().parent


def fixture():
    context=dict(record_id='snapshot',namespace='fixture',session_id='session',user_id='user',
        workflow_id='child',parent_workflow_id='parent',origin_portal='vendor',
        technical_actor='orchestrator',delegated_actor='invoice',delegation_succeeded=True,
        attachment_file_ids=[],call_id='checking-call',delegation_call_id='completed-source')
    def proof(value,call):
        return dict(record_id='proof-'+call,source='server_context',event_seq=5,
            subject_matches=True,operation='runner_observed',value=value,
            namespace='fixture',session_id='session',workflow_id='child',call_id=call)
    session=proof(True,'checking-call');session['operation']='session_validate'
    return dict(schema_version=4,checkpoint='P2',event_seq=10,proposal=dict(tool='complete_task'),
        facts=dict(session_valid=True,delegation_subject_matches=True),context=context,
        provenance=dict(session_valid=[session],delegation_subject_matches=[proof(True,'completed-source')]))


def foreign(row=None):
    row=copy.deepcopy(row or fixture())
    row['provenance']['delegation_subject_matches'][0]['call_id']='foreign-source'
    return row


class PolicyFixtures(unittest.TestCase):
    def test_distinct_source_completion_is_available_and_relation_retained(self):
        row=fixture();self.assertTrue(schema_valid(row))
        self.assertTrue(evidence(row,'delegation_subject_matches')['valid'])
        self.assertTrue(mandatory_proof_gate(row,'A')['allow'])
        self.assertTrue(mandatory_proof_gate(row,'B')['allow'])
        self.assertEqual(features(row)['context.delegation_call_matches'],'False')
        self.assertNotEqual(features(row),original_features(row))
        self.assertEqual(features(row,'old'),original_features(row,'old'))

    def test_foreign_proof_is_unavailable_and_features_distinguish_it(self):
        row=foreign();self.assertFalse(evidence(row,'delegation_subject_matches')['valid'])
        self.assertFalse(mandatory_proof_gate(row,'A')['allow'])
        self.assertIn('mandatory_proof_unavailable:delegation_subject_matches',mandatory_proof_gate(row,'A')['reasons'])
        self.assertNotEqual(features(fixture()),features(row))
        self.assertNotIn('proof.delegation_subject_matches.newest.call',features(row))

    def test_missing_source_or_checking_call_is_unavailable(self):
        for key in ('delegation_call_id','call_id'):
            row=fixture();row['context'].pop(key)
            self.assertFalse(mandatory_proof_gate(row,'A')['allow'])
        row=fixture();row['context']['delegation_call_id']=None
        self.assertFalse(evidence(row,'delegation_subject_matches')['valid'])

    def test_same_call_remains_available(self):
        row=fixture();row['context']['call_id']='completed-source'
        self.assertTrue(mandatory_proof_gate(row,'A')['allow'])
        self.assertEqual(features(row)['context.delegation_call_matches'],'True')

    def test_tool_proof_binds_checking_call(self):
        row=fixture();row['checkpoint']='P1';row['facts']['tool_scope_matches']=True
        p=copy.deepcopy(row['provenance']['delegation_subject_matches'][0])
        row['provenance']['tool_scope_matches']=[p]
        self.assertFalse(evidence(row,'tool_scope_matches')['valid'])
        self.assertFalse(mandatory_proof_gate(row,'A')['allow'])
        p['call_id']='checking-call'
        self.assertTrue(evidence(row,'tool_scope_matches')['valid'])
        self.assertTrue(mandatory_proof_gate(row,'A')['allow'])

    def test_newest_foreign_ignored_newest_bound_value_not_skipped(self):
        row=fixture();proofs=row['provenance']['delegation_subject_matches']
        p=copy.deepcopy(proofs[0]);p.update(event_seq=8,call_id='foreign-source',value=False)
        proofs.append(p)
        self.assertEqual(evidence(row,'delegation_subject_matches')['newest'],5)
        self.assertTrue(mandatory_proof_gate(row,'A')['allow'])
        p['call_id']='completed-source'
        self.assertEqual(evidence(row,'delegation_subject_matches')['newest'],8)
        self.assertFalse(mandatory_proof_gate(row,'A')['allow'])
        reversed_row=copy.deepcopy(row);reversed_row['provenance']['delegation_subject_matches'].reverse()
        self.assertEqual(features(row),features(reversed_row))
        self.assertEqual(mandatory_proof_gate(row,'A'),mandatory_proof_gate(reversed_row,'A'))

    def test_conflicting_newest_value_is_unavailable(self):
        row=fixture();proofs=row['provenance']['delegation_subject_matches']
        p=copy.deepcopy(proofs[0]);p['value']=False;proofs.append(p)
        self.assertTrue(evidence(row,'delegation_subject_matches')['conflict'])
        self.assertFalse(mandatory_proof_gate(row,'A')['allow'])

    def test_renaming_opaque_ids_does_not_change_features_or_gate(self):
        row=fixture();renamed=copy.deepcopy(row)
        replacements={'snapshot':'snapshot-renamed','fixture':'ns-renamed','session':'session-renamed',
            'user':'user-renamed','child':'child-renamed','parent':'parent-renamed',
            'checking-call':'checking-renamed','completed-source':'source-renamed'}
        def rename(v):
            if isinstance(v,dict):return {k:rename(x) for k,x in v.items()}
            if isinstance(v,list):return [rename(x) for x in v]
            return replacements.get(v,v) if isinstance(v,str) else v
        renamed=rename(renamed)
        self.assertEqual(features(row),features(renamed))
        self.assertEqual(mandatory_proof_gate(row,'A'),mandatory_proof_gate(renamed,'A'))

    def test_call_binding_clarification_is_frozen(self):
        path=HERE/'P2_CALL_BINDING_CLARIFICATION.md'
        expected='85d32c17bf36f89b92383894f3710cc0057e6fc0b529d1babc1afdde23088978'
        self.assertEqual(experiment.digest(path),expected)
        self.assertEqual(experiment.sources().get(str(path.resolve())),expected)

    def test_original_sources_unchanged(self):
        log=json.loads((HERE/'revision2-read-log.json').read_text())
        for record in log['reads']:
            if Path(record['path']).name in {'features.py','models.py','experiment.py'}:
                self.assertEqual(experiment.digest(record['path']),record['sha256'])


class TinyModelParity(unittest.TestCase):
    def test_new_and_reused_pickle_raw_precomputed_parity(self):
        self.assertEqual(PARAMETERS,models.PARAMETERS)
        rows=[fixture(),foreign(),fixture(),foreign(),fixture(),foreign()]
        for i,row in enumerate(rows):row['facts'].update(invoice_amount=str(100+i*10),invoice_status=['approved','rejected','processing'][i%3])
        labels=['ALLOW','UNKNOWN','BLOCK','ALLOW','UNKNOWN','BLOCK'];weights=[1.]*len(rows)
        for family in ('logistic','catboost'):
            for mode in ('old','new'):
                batch=FeatureBatch([features(r,mode) for r in rows],mode)
                new=fit_model(family,rows,labels,weights,mode,17)
                self.assertEqual(new.named_steps['features'].func.__module__,'models_revision2')
                reuse_train=copy.deepcopy(rows)
                for row in reuse_train:row['context']['call_id']=row['context']['delegation_call_id']
                self.assertEqual([features(r,mode) for r in reuse_train],[original_features(r,mode) for r in reuse_train])
                reused=original_fit_model(family,reuse_train,labels,weights,mode,17)
                learned_before=experiment.learned_state_fingerprint(reused)
                bind_reused_model(reused)
                self.assertEqual(learned_before,experiment.learned_state_fingerprint(reused))
                self.assertEqual(reused.named_steps['features'].func.__module__,'models_revision2')
                for model in (new,reused):
                    # Unseen distinct source/checking-call fixture exercises the
                    # persisted revision2 transformer, including reused weights.
                    p=probabilities(model,rows)
                    self.assertEqual(p,probabilities(model,batch))
                    self.assertEqual(p,probabilities(pickle.loads(pickle.dumps(model,protocol=5)),rows))
                    self.assertEqual(model.predict_proba(rows).tolist(),model.predict_proba(batch).tolist())
                    self.assertEqual(pickle.loads(pickle.dumps(model,protocol=5)).predict_proba(rows).tolist(),model.predict_proba(batch).tolist())
                    direct=model.predict_proba(batch)
                    self.assertEqual([x['ALLOW'] for x in p],direct[:,list(model.classes_).index('ALLOW')].tolist())
                self.assertEqual(probabilities(new,rows),probabilities(new,batch))
                self.assertEqual(new.predict_proba(rows).tolist(),new.predict_proba(batch).tolist())
                if mode=='old':
                    original=original_fit_model(family,rows,labels,weights,mode,17)
                    self.assertEqual(original.predict_proba(rows).tolist(),original.predict_proba(batch).tolist())
                with self.assertRaises(ValueError):feature_rows(FeatureBatch([],mode),'new' if mode=='old' else 'old')
        unavailable=fit_model('logistic',[],[],[],'new',17)
        self.assertEqual(probabilities(unavailable,[fixture()]),[dict(ALLOW=0.,BLOCK=0.,UNKNOWN=0.)])
        single=fit_model('logistic',[fixture()],['ALLOW'],[1.],'new',17)
        self.assertEqual(probabilities(single,[fixture()]),[dict(ALLOW=1.,BLOCK=0.,UNKNOWN=0.)])

    def test_matrix_proof_includes_cal_and_dictionary_values(self):
        old={'train':{'x':1.},'cal':{'x':2.}}
        proof=experiment.matrix_equivalence(['train'],['cal'],['ALLOW'],['UNKNOWN'],[1.],old,copy.deepcopy(old))
        self.assertTrue(proof['identical'])
        changed=copy.deepcopy(old);changed['cal']['x']=3.
        self.assertFalse(experiment.matrix_equivalence(['train'],['cal'],['ALLOW'],['UNKNOWN'],[1.],changed,old)['identical'])

    def test_labelblind_72_methods_both_variants_and_integrity_receipt(self):
        with tempfile.TemporaryDirectory(prefix='finbot-revision2-fixture-') as temp:
            root=Path(temp);freeze=root/'freeze';freeze.mkdir()
            model=fit_model('logistic',[fixture()],['ALLOW'],[1.],'new',17)
            with (freeze/'model.pickle').open('wb') as s:pickle.dump(model,s,protocol=5)
            experiment.write_json(freeze/'thresholds.json',{v:{'thresholds':dict(ALLOW=.5,BLOCK=.5)} for v in ('raw','gated')})
            methods=[]
            for contract in experiment.CONTRACTS:
                for mode in ('old','new'):
                    for source in ('archive','mixed'):
                        for family in ('logistic','catboost'):
                            for seed in (17,29,43):
                                methods.append(dict(name=f'{contract}__{mode}__{source}__{family}__{seed}',contract=contract,
                                    arm=mode+'/'+source,family=family,seed=seed,model_file='model.pickle',
                                    model_sha256=experiment.digest(freeze/'model.pickle'),thresholds_file='thresholds.json'))
            # P4 makes this fixture eligible for payment_v3 too. These are tiny
            # protocol checks, not model-performance or research labels.
            row=fixture();row.update(prefix_id='own-fixture',checkpoint='P4');row['proposal']['tool']='finstripe__create_transfer'
            experiment.write_lines(root/'observations.jsonl.gz',[row])
            experiment.write_lines(root/'metadata.jsonl.gz',[dict(prefix_id='own-fixture',episode_id='own-episode')])
            manifest=dict(version=2,methods=methods,sources={},files={p.name:experiment.digest(p) for p in freeze.iterdir()})
            experiment.write_json(freeze/'freeze-manifest.json',manifest)
            experiment.predict(freeze,root/'observations.jsonl.gz',root/'metadata.jsonl.gz',root/'predictions.jsonl.gz')
            predictions=list(experiment.read_lines(root/'predictions.jsonl.gz'))
            self.assertEqual(len(predictions),144)
            self.assertEqual(len({p['method'] for p in predictions}),144)
            self.assertTrue(all('gold' not in p for p in predictions))
            receipt=json.loads((root/'predictions.jsonl.gz.receipt.json').read_text())
            self.assertFalse(receipt['labels_opened'])
            self.assertEqual(receipt['predictions_sha256'],experiment.digest(root/'predictions.jsonl.gz'))
            # Generic verifier accepts both manifest versions, without changing
            # original helper; corrupt pickle is rejected before unpickling.
            (freeze/'model.pickle').write_bytes(b'invalid-pickle')
            with self.assertRaisesRegex(ValueError,'frozen artifact hash mismatch'):
                experiment.predict(freeze,root/'observations.jsonl.gz',root/'metadata.jsonl.gz',root/'rejected.jsonl.gz')
            manifest['version']=1;manifest['files']['model.pickle']=experiment.digest(freeze/'model.pickle')
            (freeze/'freeze-manifest.json').unlink();experiment.write_json(freeze/'freeze-manifest.json',manifest)
            self.assertEqual(experiment.verify_freeze(freeze)['version'],1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--policy-only',action='store_true');args=parser.parse_args()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(PolicyFixtures)
    if not args.policy_only:suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TinyModelParity))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
