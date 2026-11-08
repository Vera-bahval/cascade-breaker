import copy
import unittest

from . import p4
from .early_score import adjudicate, first_stop
from .run_p4 import matched_inputs, files
from .projection import _object_scope, project


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pairs = list(matched_inputs(files()))

    def test_all_542_stored_requests(self):
        self.assertEqual(len(self.pairs),542)
        self.assertTrue(all(row is not None and issue is None for _,_,row,issue,_ in self.pairs))

    def legacy(self):
        for _,_,row,_,_ in self.pairs:
            state, _, missing = p4.legacy_prefix(row)
            if state and not missing:
                return copy.deepcopy(row)
        self.fail('no legacy state')

    def test_empty_and_missing_history_have_different_status(self):
        row=self.legacy()
        state=row['raw_context']['initial_state']
        state['transactions']=[]
        self.assertTrue(p4.legacy_diagnostics(row)['prior_transaction_list'])
        self.assertIsNotNone(p4.legacy_prefix(row)[0])
        state.pop('transactions')
        self.assertFalse(p4.legacy_diagnostics(row)['prior_transaction_list'])
        self.assertIn('initial_transactions',p4.legacy_prefix(row)[2])

    def test_future_result_rejected(self):
        row=self.legacy()
        row['raw_context']['events'].append({'event_seq':row['event_seq']+1,
            'hook_kind':'after_tool','tool_name':'create_transfer','tool_result':{'status':'completed'}})
        self.assertIn('future_or_invalid_raw_event',p4.legacy_prefix(row)[2])

    def test_legacy_amount_and_account_are_initial_comparisons(self):
        row=self.legacy()
        row['observation']['proposal']['amount']='99999'
        row['observation']['proposal']['vendor_account_token']='different-account'
        state,_,issues=p4.legacy_prefix(row)
        self.assertEqual(issues,[])
        reasons=p4.rules.violations(state)
        self.assertIn('amount_mismatch',reasons)
        self.assertIn('account_mismatch',reasons)

    def test_failed_tool_write_not_a_state_update(self):
        self.assertFalse(p4.tool_result_ok({}, {'updated':False,'status':'approved'}))
        self.assertFalse(p4.tool_result_ok({}, {'error':'denied','status':'approved'}))
        self.assertTrue(p4.tool_result_ok({}, {'updated':True,'status':'approved'}))

    def test_stop_keeps_only_reached_prefix(self):
        rows=[dict(event_seq=i,decision=d) for i,d in enumerate(('ALLOW','UNKNOWN','BLOCK','ALLOW'))]
        self.assertEqual(first_stop(rows,stop_unknown=True),(rows[:2],rows[1]))
        self.assertEqual(first_stop(rows,stop_unknown=False),(rows[:3],rows[2]))

    def test_wrong_cut_cannot_supply_action_scope(self):
        row=dict(checkpoint='P1',event_seq=5,observation={'context':{}},
                 anchor={'event':{'event_seq':6,'agent_name':'fraud',
                                  'tool_name':'update_vendor_risk','tool_arguments':{'vendor_id':9}}},
                 raw_context={'events':[{'event_seq':2,'hook_kind':'before_model'}]})
        _, modern, _ = project(row,{})
        self.assertNotIn('vendor_id',modern['context'])
        self.assertNotIn('technical_actor',modern['context'])
        self.assertNotIn('tool',modern['proposal'])

    def test_scope_is_not_inferred_for_opaque_or_alternate_subject_arguments(self):
        runner={'invoice_id':6,'current_vendor_id':1}
        self.assertTrue(_object_scope('get_invoice_details',{'invoice_id':6},runner))
        self.assertFalse(_object_scope('get_invoice_details',{'invoice_id':7},runner))
        self.assertIsNone(_object_scope('finmail__send_email',{'related_invoice_id':7,'to':'unknown'},runner))
        self.assertIsNone(_object_scope('findrive__search_files',{'query':'invoice'},runner))

    def test_unresolved_prior_transfer_invalidates_zero_count(self):
        tool='finstripe__create_transfer'
        args=dict(invoice_id=1,vendor_id=1,amount='100',vendor_account='account/1')
        row=dict(checkpoint='P4',event_seq=9,observation={'context':{}},raw_context={
            'initial_state': {'invoice':{'id':1,'vendor_id':1,'amount':'100'},
                              'vendor':{'id':1},'transactions':[]},
            'proposed_action':dict(event_seq=9,tool_name=tool,tool_arguments=args),
            'events':[dict(event_seq=2,hook_kind='before_model'),
                      dict(event_seq=4,hook_kind='before_tool',tool_name=tool,tool_arguments=args),
                      dict(event_seq=6,hook_kind='after_tool',tool_name=tool,tool_arguments=args,tool_result=None)]})
        prior,_,_=project(row,{})
        self.assertNotIn('prior_completed_transfers',prior['facts'])
        row['raw_context']['events'].pop()
        prior,_,_=project(row,{})
        self.assertNotIn('prior_completed_transfers',prior['facts'])
        row['raw_context']['events'].pop()
        row['raw_context']['initial_state']['transactions']=[{'status':'completed'}]
        prior,_,_=project(row,{})
        self.assertNotIn('prior_completed_transfers',prior['facts'])

    def test_adjudication_requires_third_for_all_disagreements(self):
        a={'x':dict(label='ALLOW'),'y':dict(label='BLOCK')}
        b={'x':dict(label='ALLOW'),'y':dict(label='INSUFFICIENT')}
        with self.assertRaises(ValueError):
            adjudicate(a,b,{})
        self.assertEqual(adjudicate(a,b,{'y':dict(label='INSUFFICIENT')})['y']['resolution'],'third')
