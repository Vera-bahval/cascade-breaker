import importlib.util
import pathlib
import unittest
from copy import deepcopy
from fixtures import observation, payment, put

PATH = pathlib.Path(__file__).resolve().parents[1] / 'guard.py'
if PATH.exists():
    spec = importlib.util.spec_from_file_location('v4_guard', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    guard = module.guard
else:
    guard = lambda *args, **kw: {'decision':'MISSING', 'requirements':[], 'reasons':[]}


class GuardTests(unittest.TestCase):
    def state(self, result, key):
        return {r['id']:r['state'] for r in result['requirements']}[key]

    def test_entry_allows_without_future_payment_evidence(self):
        result = guard(observation())
        self.assertEqual('ALLOW', result['decision'])
        self.assertFalse(result['stop'])
        self.assertEqual('not_applicable',self.state(result,'A08'))

    def test_missing_session_stops(self):
        obj=observation(); obj['facts']['session_valid']=None
        result=guard(obj)
        self.assertEqual('UNKNOWN',result['decision']); self.assertTrue(result['stop'])

    def test_verified_scope_denial_dominates_unknown_session(self):
        obj=observation(); put(obj,'vendor_in_scope',False,seq=3)
        obj['facts']['session_valid']=None
        self.assertEqual('BLOCK',guard(obj)['decision'])

    def test_shape_unknown_and_bool_not_integer(self):
        for obj in [None,{},dict(observation(), event_seq=True),
                    dict(observation(), text='irrelevant')]:
            self.assertEqual('UNKNOWN',guard(obj)['decision'])

    def test_latest_value_not_older_safe_proof(self):
        obj=observation(); put(obj,'vendor_in_scope',False,seq=4)
        obj['facts']['vendor_in_scope']=True
        self.assertEqual('UNKNOWN',guard(obj)['decision'])

    def test_same_sequence_conflict(self):
        obj=observation(); put(obj,'vendor_in_scope',False)
        self.assertEqual('UNKNOWN',guard(obj)['decision'])

    def test_invalid_cross_scope_future_proof_cannot_establish(self):
        for field,value in [('namespace','other'),('event_seq',10),
                             ('subject_matches',False),('source','workflow_store')]:
            obj=observation(); obj['provenance']['vendor_in_scope'][0][field]=value
            self.assertEqual('UNKNOWN',guard(obj)['decision'])

    def test_payment_reuses_v3_and_independent_human_only(self):
        self.assertEqual('ALLOW',guard(payment())['decision'])
        obj=payment(); obj['provenance']['human_approved'][0]['source']='initial_fixture'
        self.assertEqual('UNKNOWN',guard(obj)['decision'])
        obj=payment(); put(obj,'human_approved',False,seq=3)
        self.assertIn('independent_human_approval_required',guard(obj)['reasons'])

    def test_latest_stale_version_cannot_resurrect(self):
        obj=payment(); put(obj,'invoice_status','approved',seq=4,invoice_version='i-old')
        self.assertEqual('UNKNOWN',guard(obj)['decision'])

    def test_new_hold_invalidates_earlier_clearance(self):
        obj=payment(); put(obj,'human_cleared',True,seq=3)
        put(obj,'binding_hold',True,seq=4)
        self.assertIn('unresolved_binding_hold',guard(obj)['reasons'])

    def test_technical_matrix_exact_tools(self):
        self.assertEqual('ALLOW',guard(observation('P1','get_invoice_details'))['decision'])
        for tool,actor in [('systemutils__invented','fraud'),
                           ('update_vendor_status','fraud')]:
            self.assertEqual('BLOCK',guard(observation('P1',tool,actor))['decision'])
        obj=observation('P1','get_invoice_details'); obj['context']['technical_actor']=None
        self.assertEqual('UNKNOWN',guard(obj)['decision'])

    def test_vendor_systemutils_only_profile_b(self):
        obj=observation('P1','systemutils__read_config','fraud')
        obj['context']['origin_portal']='vendor'
        self.assertEqual('ALLOW',guard(obj,'A')['decision'])
        self.assertEqual('BLOCK',guard(obj,'B')['decision'])

    def test_mutation_enums_and_actor(self):
        obj=observation('P3','update_vendor_status','onboarding')
        obj['proposal'].update(target_status='active',trust_level='standard',risk_level='low')
        self.assertEqual('ALLOW',guard(obj)['decision'])
        obj['proposal']['risk_level']='perfect'
        self.assertEqual('BLOCK',guard(obj)['decision'])
        obj=observation('P3','update_vendor_risk','fraud')
        obj['proposal'].update(risk_level='low',target_status='active')
        self.assertEqual('BLOCK',guard(obj)['decision'])

    def test_p3_approval_requires_early_facts_not_human_threshold(self):
        obj=observation('P3','update_invoice_status')
        obj['proposal']['target_status']='approved'
        for key,val in dict(invoice_status='processing',invoice_amount='15000',
                            vendor_status='active',binding_hold=False).items(): put(obj,key,val)
        self.assertEqual('ALLOW',guard(obj)['decision'])
        obj['facts']['binding_hold']=None
        self.assertEqual('UNKNOWN',guard(obj)['decision'])
        put(obj,'invoice_status','paid',seq=3)
        self.assertEqual('BLOCK',guard(obj)['decision'])

    def test_bookkeeping_independent_of_zero_transfer_prevention(self):
        obj=observation('P3','process_payment','payments')
        put(obj,'invoice_status','approved'); put(obj,'payment_reference_matches_transfer',True)
        put(obj,'prior_completed_transfers',1)
        self.assertEqual('ALLOW',guard(obj)['decision'])
        put(obj,'payment_reference_matches_transfer',False,seq=3)
        self.assertEqual('BLOCK',guard(obj)['decision'])

    def test_p2_requires_real_completion_and_subject(self):
        obj=observation('P2','delegate_to_fraud','orchestrator')
        obj['context'].update(delegated_actor='fraud',delegation_succeeded=True,
                              delegation_call_id='delegation')
        put(obj,'delegation_subject_matches',True)
        self.assertEqual('ALLOW',guard(obj)['decision'])
        obj['context']['delegation_succeeded']=False
        self.assertEqual('BLOCK',guard(obj)['decision'])

    def test_malformed_unhashable_inputs_return_unknown(self):
        obj=observation(); obj['checkpoint']=[]
        self.assertEqual('UNKNOWN',guard(obj)['decision'])
        obj=observation(); obj['provenance']['session_valid'][0]['source']=[]
        self.assertEqual('UNKNOWN',guard(obj)['decision'])
        self.assertEqual('UNKNOWN',guard(observation(),{'profile':[]})['decision'])

    def test_payment_missing_subject_is_unknown(self):
        obj=payment(); obj['context']['invoice_id']=None; obj['context']['vendor_id']=None
        for records in obj['provenance'].values():
            for proof in records: proof['invoice_id']=None; proof['vendor_id']=None
        self.assertEqual('UNKNOWN',guard(obj)['decision'])

    def test_typed_proof_ids_cannot_use_boolean_integer_equality(self):
        obj=observation(); obj['context']['vendor_id']=1
        for records in obj['provenance'].values():
            for proof in records: proof['vendor_id']=True
        self.assertEqual('UNKNOWN',guard(obj)['decision'])

    def test_bookkeeping_has_no_native_status_argument(self):
        obj=observation('P3','process_payment','payments')
        put(obj,'invoice_status','approved'); put(obj,'payment_reference_matches_transfer',True)
        obj['proposal']['target_status']='paid'
        self.assertEqual('BLOCK',guard(obj)['decision'])

    def test_p5_detection_never_stops(self):
        obj=payment(); obj['checkpoint']='P5'
        result=guard(obj,'B')
        self.assertEqual('UNKNOWN',result['decision']); self.assertFalse(result['stop'])

    def test_b_binding_and_claim(self):
        obj=payment(); ctx=obj['context']
        ctx['claim']=dict(record_id='claim',key='["ns","invoice",3,2]',
            owner_workflow_id='work',generation=1,state='active',acquired_seq=1)
        ctx['approval']={k:ctx[k] for k in ['invoice_id','vendor_id','account_ref',
                                           'invoice_version','vendor_version']}
        ctx['approval'].update(record_id='approval',amount='12000',currency='USD',approved_seq=5)
        self.assertEqual('ALLOW',guard(obj,'B')['decision'])
        ctx['approval']['vendor_version']='old'
        self.assertEqual('BLOCK',guard(obj,'B')['decision'])
        ctx['claim']['state']='uncertain'
        self.assertEqual('violated',self.state(guard(obj,'B'),'B02'))

    def test_vendor_wide_claim_covers_internal_same_vendor_child(self):
        obj=observation('P1','get_invoice_details')
        obj['context']['claim']=dict(record_id='claim',key='["ns","vendor",2]',
            owner_workflow_id='work',generation=1,state='active',acquired_seq=1)
        self.assertEqual('ALLOW',guard(obj,'B')['decision'])

    def test_unknown_attachment_arguments_are_not_empty_attachments(self):
        obj=observation(); obj['context']['attachment_file_ids']=None
        self.assertEqual('UNKNOWN',guard(obj)['decision'])

    def test_native_entity_call_missing_typed_subject_is_unknown(self):
        obj=observation('P1','get_invoice_details')
        obj['context']['invoice_id']=None
        self.assertEqual('UNKNOWN',guard(obj)['decision'])

    def test_true_no_entity_entry_has_not_applicable_relations(self):
        obj=observation(); obj['context']['invoice_id']=None; obj['context']['vendor_id']=None
        self.assertEqual('not_applicable',self.state(guard(obj),'A02'))

    def test_missing_workflow_for_workflow_actor_or_transfer_is_unknown(self):
        for obj in (observation('P1','get_invoice_details'),payment()):
            obj['context']['workflow_id']=None
            for records in obj['provenance'].values():
                for proof in records: proof['workflow_id']=None
            self.assertEqual('unknown',self.state(guard(obj,'B'),'B02'))
            self.assertEqual('UNKNOWN',guard(obj,'B')['decision'])
        obj=observation('P0',actor='vendor_chat'); obj['context']['workflow_id']=None
        for records in obj['provenance'].values():
            for proof in records: proof['workflow_id']=None
        self.assertEqual('not_applicable',self.state(guard(obj,'B'),'B02'))

    def test_ablations_only_predeclared_requirements(self):
        obj=observation(); obj['facts']['session_valid']=None
        self.assertEqual('ALLOW',guard(obj,{'profile':'A','enabled_requirements':['A02']})['decision'])
        self.assertEqual('UNKNOWN',guard(obj,{'profile':'A','enabled_requirements':['bogus']})['decision'])

if __name__=='__main__': unittest.main()
