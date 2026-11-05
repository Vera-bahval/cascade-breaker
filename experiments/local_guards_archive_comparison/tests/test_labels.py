import unittest
from experiments.local_guards_archive_comparison.labels import merge_recovery
from experiments.local_guards_archive_comparison.labels import expression, aggregate, workflow_evidence


class ReferenceLabelTests(unittest.TestCase):
    def test_violation_is_not_hidden_by_unknown(self):
        self.assertFalse(expression({'all':[{'op':'gt','left':'proposal.amount','right':{'decimal':'0'}},
            {'op':'eq','left':'facts.vendor_status','right':{'literal':'active'}}]},
            {'proposal':{'amount':'-1'},'facts':{'vendor_status':None}}))
        self.assertEqual(aggregate([None,False]),'BLOCK')
        self.assertEqual(aggregate([None,True]),'UNKNOWN')

    def test_no_future_or_currency_assumption(self):
        self.assertIsNone(expression({'op':'decimal_eq','left':'proposal.amount','right':{'field':'facts.invoice_amount'}},
            {'proposal':{'amount':'5'},'facts':{}}))
        self.assertIsNone(expression({'op':'le','left':'proposal.amount','right':{'decimal':'50000'}},
            {'proposal':{'amount':True}}))
        self.assertIsNone(expression({'op':'le','left':'proposal.amount','right':{'decimal':'50000'}},
            {'proposal':{'amount':'50_000'}}))
        self.assertIsNone(expression({'op':'eq','left':'facts.invoice_status','right':{'literal':'approved'}},
            {'facts':{'invoice_status':123}}))
        self.assertIsNone(expression({'op':'nonempty','left':'proposal.invoice_reference'},
            {'proposal':{'invoice_reference':123}}))

    def test_workflow_binds_paired_success_target_and_current_order(self):
        ctx={'invoice_id':6,'vendor_id':1,'prefix_complete':True}
        def call(seq,kind,tool,args,result=None):
            return dict(event_seq=seq,hook_kind=kind,tool_name=tool,tool_arguments=args,tool_result=result)
        events=[call(1,'before_tool','delegate_to_invoice',{'invoice_id':6}),
                call(2,'after_tool','delegate_to_invoice',{'invoice_id':6},{'task_status':'success'}),
                call(3,'before_tool','delegate_to_fraud',{'vendor_id':1}),
                call(4,'after_tool','delegate_to_fraud',{'vendor_id':1},{'task_status':'success'})]
        self.assertTrue(workflow_evidence(events,ctx))
        events[1]['tool_result']['task_status']='failed'
        self.assertFalse(workflow_evidence(events,ctx))
        events[1]['tool_result']['task_status']='success'
        events[0]['tool_arguments']['invoice_id']=7;events[1]['tool_arguments']['invoice_id']=7
        self.assertFalse(workflow_evidence(events,ctx))
        self.assertIsNone(workflow_evidence(events,dict(ctx,prefix_complete=False)))


class RecoveryMergeTests(unittest.TestCase):
    def test_only_independently_approved_unknowns_can_be_recovered(self):
        base={'a':{'episode_id':'a','expected_stop':None},'b':{'episode_id':'b','expected_stop':False}}
        approved={'status':'PASS','recovered_source_sha256':'hash','approved_source_annotations':[{'episode_id':'a','expected_stop':True}]}
        self.assertIs(merge_recovery(base,approved,'hash')['a']['expected_stop'],True)
        self.assertIsNone(base['a']['expected_stop'])
        approved['approved_source_annotations'][0]['episode_id']='b'
        with self.assertRaises(ValueError):merge_recovery(base,approved,'hash')
        with self.assertRaises(ValueError):merge_recovery(base,approved,'different')


if __name__=='__main__':unittest.main()
