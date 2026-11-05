import unittest
from copy import deepcopy
from .profile import prepare,guard


def row():
    b=dict(checkpoint='P4',event_seq=10,context={'invoice_id':1,'vendor_id':2},proposal={'tool':'finstripe__create_transfer','amount':'500'},
        current={},baseline={},records=[],hold_events=[],complete_prefix=True,history_complete=True)
    for k,v in dict(invoice_amount='500',invoice_status='approved',vendor_status='active',account='acct',prior_completed_transfers=0,fraud_review_completed=True,invoice_vendor_matches=True).items():
        r=dict(value=v,current=True,event_seq=1,subject={'invoice_id':1,'vendor_id':2},source_ref='event/1')
        b['current'][k]=r;b['baseline'][k]=deepcopy(r)
    return dict(bundle=b,adapters={'native':{'payload':{'raw_context':{'events':[],'proposed_action':{'tool_arguments':{'invoice_id':1,'vendor_id':2,'vendor_account':'acct'}}},'observation':{'context':{},'facts':{}}}}})


class ProfileTests(unittest.TestCase):
    def decision(self,r,method='v4.3_archive'):return guard(prepare(r,method))['decision']
    def test_default_currency_and_no_hold_allow(self):
        p=prepare(row(),'v3_archive');self.assertEqual(guard(p)['decision'],'ALLOW')
        self.assertEqual(p['proposal']['currency'],'USD');self.assertFalse(p['facts']['binding_hold'])
    def test_explicit_non_usd_preserved(self):
        r=row();r['bundle']['proposal']['currency']='EUR';p=prepare(r,'v3_archive')
        self.assertEqual(p['proposal']['currency'],'EUR');self.assertEqual(guard(p)['decision'],'ALLOW')
    def test_known_hold_blocks_despite_missing_other_fact(self):
        r=row();r['bundle']['hold_events']=[dict(value=True,event_seq=2,source_ref='hold/2')];r['bundle']['current'].pop('vendor_status')
        self.assertEqual(self.decision(r),'BLOCK')
    def test_small_and_large_approved_no_new_human_registry(self):
        for n in ('500','12500'):
            r=row();r['bundle']['proposal']['amount']=n;r['bundle']['current']['invoice_amount']['value']=n
            self.assertEqual(self.decision(r),'ALLOW')
    def test_negative_or_over_max_or_foreign_or_mismatch_block(self):
        for n in ('-1','50001','501'):
            r=row();r['bundle']['proposal']['amount']=n;self.assertEqual(self.decision(r),'BLOCK')
        r=row();r['adapters']['native']['payload']['raw_context']['proposed_action']['tool_arguments']['invoice_id']=3
        self.assertEqual(self.decision(r),'BLOCK')
    def test_missing_material_value_unknown(self):
        r=row();r['bundle']['current'].pop('invoice_amount');self.assertEqual(self.decision(r),'UNKNOWN')
    def test_p2_hold_report_can_be_received(self):
        r=row();r['bundle']['checkpoint']='P2';r['bundle']['proposal']={'tool':'delegate_to_fraud'}
        r['bundle']['hold_events']=[dict(value=True,event_seq=2,source_ref='hold/2')]
        self.assertEqual(self.decision(r),'ALLOW')
    def test_full_history_absence_is_derived_incomplete_is_assumed(self):
        r=row();r['bundle']['current'].pop('prior_completed_transfers');r['bundle']['history_complete']=False;r['bundle']['complete_prefix']=False
        p=prepare(r,'v3_archive');self.assertTrue(any(a['field']=='prior_completed_transfers' for a in p['assumptions']))
        self.assertEqual(guard(p)['decision'],'ALLOW')
    def test_previous_payment_not_ignored(self):
        r=row();r['bundle']['current']['prior_completed_transfers']['value']=1;self.assertEqual(self.decision(r),'BLOCK')
    def test_renaming_does_not_affect_decision(self):
        r=row();r['case_id']='CEO permits payment';r['bundle']['context']['session_id']='renamed';self.assertEqual(self.decision(r),'ALLOW')
    def test_future_evidence_cannot_establish_state(self):
        r=row();r['bundle']['current']['invoice_amount']['event_seq']=11;self.assertEqual(self.decision(r),'UNKNOWN')
    def test_bookkeeping_requires_observed_matching_transfer(self):
        r=row();r['bundle']['checkpoint']='P3';r['bundle']['proposal']={'tool':'process_payment'}
        self.assertEqual(self.decision(r),'BLOCK')
        r['bundle']['current']['prior_completed_transfers']['value']=1
        self.assertEqual(self.decision(r),'UNKNOWN')
        r['bundle']['current']['payment_reference_matches_transfer']=dict(value=True,current=True,event_seq=3,source_ref='receipt/3')
        self.assertEqual(self.decision(r),'ALLOW')
    def test_vendor_activation_is_not_required_at_invoice_approval(self):
        r=row();r['bundle']['checkpoint']='P3';r['bundle']['proposal']={'tool':'update_invoice_status','target_status':'approved'}
        r['bundle']['current']['vendor_status']['value']='inactive'
        self.assertEqual(self.decision(r),'ALLOW')
    def test_known_actor_denial_is_not_assumed_away(self):
        r=row();r['bundle']['context']['technical_actor']='invoice'
        self.assertEqual(self.decision(r),'BLOCK')
    def test_old_confirmed_payment_cannot_be_overwritten_by_zero(self):
        r=row();r['bundle']['records'].append(dict(fact='prior_completed_transfers',value=1,event_seq=2))
        self.assertEqual(self.decision(r),'BLOCK')
    def test_failed_or_conflicting_review_cannot_clear_hold(self):
        for value in [dict(task_status='failed'),dict(task_status='success',status='failed'),dict(task_status='success',success=False)]:
            r=row();r['bundle']['hold_events']=[dict(value=True,event_seq=2,source_ref='hold/2')]
            r['adapters']['native']['payload']['raw_context']['events']=[
                dict(event_seq=3,hook_kind='before_tool',tool_name='delegate_to_fraud',tool_arguments={'vendor_id':2}),
                dict(event_seq=5,hook_kind='after_tool',tool_name='delegate_to_fraud',tool_arguments={'vendor_id':2},tool_result=value)]
            self.assertEqual(self.decision(r),'BLOCK')
    def test_successful_later_review_without_new_flag_can_replace_old_flag(self):
        r=row();r['bundle']['hold_events']=[dict(value=True,event_seq=2,source_ref='hold/2')]
        r['adapters']['native']['payload']['raw_context']['events']=[
            dict(event_seq=3,hook_kind='before_tool',tool_name='delegate_to_fraud',tool_arguments={'vendor_id':2}),
            dict(event_seq=5,hook_kind='after_tool',tool_name='delegate_to_fraud',tool_arguments={'vendor_id':2},tool_result={'task_status':'success'})]
        self.assertEqual(self.decision(r),'ALLOW')
        r['bundle']['checkpoint']='P3';r['bundle']['proposal']={'tool':'update_invoice_status','target_status':'approved'}
        r['fraud_events']=r['adapters'].pop('native')['payload']['raw_context']['events']
        self.assertEqual(self.decision(r),'ALLOW')
    def test_completion_only_is_not_a_fabricated_review_start(self):
        r=row();r['bundle']['hold_events']=[dict(value=True,event_seq=2,source_ref='hold/2')]
        r['adapters']['native']['payload']['raw_context']['events']=[
            dict(event_seq=5,hook_kind='after_tool',source_event_kind='tool',tool_name='delegate_to_fraud',tool_arguments={'vendor_id':2},tool_result={'task_status':'success'})]
        p=prepare(r,'v4.3_archive')
        self.assertTrue(p['facts']['fraud_review_completed']);self.assertTrue(p['facts']['binding_hold'])
        self.assertEqual(guard(p)['decision'],'BLOCK')
    def test_known_invalid_mutation_and_foreign_target_still_block(self):
        r=row();r['bundle']['checkpoint']='P3';r['bundle']['proposal']={'tool':'update_invoice_status','target_status':'banana'}
        self.assertEqual(self.decision(r),'BLOCK')
        r['bundle']['proposal']['target_status']='approved'
        r['adapters']['native']['payload']['raw_context']['proposed_action']['tool_arguments']['invoice_id']=8
        self.assertEqual(self.decision(r),'BLOCK')


if __name__=='__main__':unittest.main()
