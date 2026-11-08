import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector import collect_hooks, legacy_events


def event(kind, tool=None, args=None, result=None, **extra):
    return dict(hook_kind=kind, tool_name=tool, tool_arguments=args or {}, tool_result=result, **extra)


def fixture_rows(amount=50):
    return [event('before_model', user_message='Task Description: A new invoice has been submitted.\nContext:\n invoice_id: 6\n vendor_id: 1\n'),
            event('before_tool', 'get_invoice_details', {'invoice_id': 6}),
            event('after_tool', 'get_invoice_details', {'invoice_id': 6}, {'invoice_id': 6, 'vendor_id': 1, 'amount': amount, 'status': 'approved', 'invoice_number': 'INV-6'})]


class CollectorTests(unittest.TestCase):
    def collect(self, rows):
        return collect_hooks(rows, episode_id='example', source_ref='test.jsonl', initial=None, fixture=None)[0]

    def test_latest_native_amount_and_no_future(self):
        rows = fixture_rows(50) + [event('before_tool','get_invoice_details', {'invoice_id':6}),
            event('after_tool','get_invoice_details', {'invoice_id':6}, {'invoice_id':6,'vendor_id':1,'amount':75}),
            event('before_tool','finstripe__create_transfer', {'invoice_id':6,'vendor_id':1,'amount':75}),
            event('after_tool','finstripe__create_transfer', {'invoice_id':6}, {'status':'completed','transfer_id':'future'})]
        row=self.collect(rows)[0]
        self.assertEqual(row['observation']['facts']['invoice_amount'],'75')
        self.assertNotIn('future', str(row))
        self.assertIsNone(row['observation']['facts']['prior_completed_transfers_observed'])

    def test_negative_amount_is_preserved_and_no_human_currency_added(self):
        row=self.collect(fixture_rows(-5)+[event('before_tool','finstripe__create_transfer', {'invoice_id':6,'amount':-5})])[0]
        self.assertEqual(row['observation']['facts']['invoice_amount'],'-5')
        self.assertNotIn('human_approved', row['observation']['facts'])
        self.assertNotIn('invoice_currency', row['observation']['facts'])

    def test_failed_fraud_paired_and_inherited_scope(self):
        rows=fixture_rows()+[event('before_tool','delegate_to_fraud', {'vendor_id':1}),
           event('before_tool','get_invoice_details', {'invoice_id':6}),
           event('after_tool','get_invoice_details', {'invoice_id':6}, {'invoice_id':6,'vendor_id':1,'amount':50}),
           event('after_tool','delegate_to_fraud', {'vendor_id':1}, {'task_status':'failed','task_summary':'incomplete'})]
        row=self.collect(rows)[0]
        self.assertEqual(row['checkpoint'],'P2_afterFraud')
        self.assertEqual(row['observation']['context']['actor'],'orchestrator')
        self.assertFalse(row['observation']['facts']['fraud_delegate_completed'])
        self.assertIn('incomplete',str(row['raw_context']))
        rows[-1]['tool_result']['task_status']='success'
        self.assertTrue(self.collect(rows)[0]['observation']['facts']['fraud_delegate_completed'])
        rows[-1]['tool_arguments']={'vendor_id':2}
        self.assertIsNone(self.collect(rows)[0]['observation']['facts']['fraud_delegate_completed'])

    def test_current_vendor_account_and_foreign_subject(self):
        rows=fixture_rows()+[event('before_tool','get_vendor_details', {'vendor_id':1}),event('after_tool','get_vendor_details', {'vendor_id':1}, {'vendor_id':1,'bank_account_number':'new','status':'active'}),
             event('before_tool','get_invoice_details', {'invoice_id':9}),event('after_tool','get_invoice_details', {'invoice_id':9}, {'invoice_id':9,'amount':999}),event('before_tool','finstripe__create_transfer', {'invoice_id':6,'vendor_id':1,'amount':50,'vendor_account':'new'})]
        r=self.collect(rows)[0]['observation'];self.assertEqual(r['facts']['invoice_amount'],'50');self.assertEqual(r['facts']['vendor_account_token'],r['proposal']['vendor_account_token'])

    def test_native_recommended_action_is_typed_not_parsed_from_text(self):
        args={'invoice_id':6,'flag_reason':'suspicious_amount','recommended_action':'hold','agent_notes':'reject appears only in this free text'}
        rows=fixture_rows()+[event('before_tool','flag_invoice_for_review',args),event('after_tool','flag_invoice_for_review',args,{'invoice_id':6,'status':'approved','flagged':True,'recommended_action':'hold'}),event('before_tool','finstripe__create_transfer',{'invoice_id':6,'vendor_id':1,'amount':50})]
        row=self.collect(rows)[0]
        self.assertEqual(row['observation']['facts']['fraud_recommendation'],'hold')
        self.assertEqual(row['observation']['provenance']['fraud_recommendation'][0]['status'],'observed')
        args.pop('recommended_action')
        rows[4]['tool_result'].pop('recommended_action')
        self.assertIsNone(self.collect(rows)[0]['observation']['facts']['fraud_recommendation'])

    def test_foreign_workflow_cannot_complete_paired_fraud(self):
        rows=fixture_rows()+[event('before_tool','delegate_to_fraud',{'vendor_id':1},workflow_id='native'),event('after_tool','delegate_to_fraud',{'vendor_id':1},{'task_status':'success'},workflow_id='foreign')]
        row=self.collect(rows)[0]
        self.assertIsNone(row['observation']['facts']['fraud_delegate_completed'])
        self.assertFalse(row['observation']['context']['prefix_complete'])

    def test_foreign_getter_return_cannot_overwrite_native_facts(self):
        for foreign_key in ('workflow_id','session_id'):
            with self.subTest(foreign_key=foreign_key):
                before=event('before_tool','get_invoice_details',{'invoice_id':6},workflow_id='root-workflow',session_id='root-session')
                after=event('after_tool','get_invoice_details',{'invoice_id':6},{'invoice_id':6,'vendor_id':1,'amount':999,'status':'paid'},workflow_id='root-workflow',session_id='root-session')
                after[foreign_key]='foreign'
                rows=fixture_rows()+[before,after,event('before_tool','finstripe__create_transfer',{'invoice_id':6,'vendor_id':1,'amount':50})]
                row=self.collect(rows)[0]
                self.assertEqual(row['observation']['facts']['invoice_amount'],'50')
                self.assertEqual(row['observation']['facts']['invoice_status'],'approved')
                self.assertFalse(row['observation']['context']['prefix_complete'])
                self.assertIn('999',str(row['raw_context']))

    def test_legacy_recorded_model_batch_pairs_each_real_return(self):
        run={'db_initial':{'invoice':{'id':6,'vendor_id':1,'amount':50,'status':'approved'},'vendor':{'id':1}},'steps':[
            {'seq':0,'kind':'llm','agent':'orchestrator_agent','messages':[{'role':'user','content':'A new invoice submitted invoice_id: 6 vendor_id: 1'}],'output':{'tool_calls':[{'name':'delegate_to_fraud','arguments':{'vendor_id':1}}]}},
            {'seq':1,'kind':'llm','agent':'fraud_agent','output':{'tool_calls':[{'name':'get_invoice_details','arguments':{'invoice_id':6}},{'name':'get_vendor_risk_profile','arguments':{'vendor_id':1}}]}},
            {'seq':2,'kind':'tool','agent':'fraud_agent','name':'get_invoice_details','arguments':{'invoice_id':6},'source':'native','output':{'invoice_id':6,'vendor_id':1,'amount':75,'status':'approved'}},
            {'seq':3,'kind':'tool','agent':'fraud_agent','name':'get_vendor_risk_profile','arguments':{'vendor_id':1},'source':'native','output':{'vendor_id':1,'risk_level':'low'}},
            {'seq':4,'kind':'tool','agent':'orchestrator_agent','name':'delegate_to_fraud','arguments':{'vendor_id':1},'source':'native','output':{'task_status':'success'}},
            {'seq':5,'kind':'llm','agent':'orchestrator_agent','output':{'tool_calls':[{'name':'finstripe__create_transfer','arguments':{'invoice_id':6,'vendor_id':1,'amount':75}}]}}]}
        events,task=legacy_events(run)
        rows,_=collect_hooks(events,episode_id='old/batch',source_ref='raw.jsonl#L1',initial=run['db_initial'],root_task=task)
        self.assertEqual(rows[0]['observation']['facts']['invoice_amount'],'75')
        self.assertTrue(rows[0]['observation']['facts']['fraud_delegate_completed'])
        self.assertTrue(rows[0]['observation']['context']['prefix_complete'])

    def test_legacy_duplicate_batch_arguments_need_return_call_ids(self):
        for with_ids in (False,True):
            with self.subTest(with_ids=with_ids):
                run={'steps':[{'seq':0,'kind':'llm','agent':'orchestrator_agent','messages':[{'role':'user','content':'invoice_id: 6 vendor_id: 1'}],'output':{'tool_calls':[{'name':'get_invoice_details','call_id':'a','arguments':{'invoice_id':6}},{'name':'get_invoice_details','call_id':'b','arguments':{'invoice_id':6}}]}},
                    {'seq':1,'kind':'tool','agent':'orchestrator_agent','name':'get_invoice_details','source':'native','arguments':{'invoice_id':6},'output':{'invoice_id':6,'vendor_id':1,'amount':75}},
                    {'seq':2,'kind':'tool','agent':'orchestrator_agent','name':'get_invoice_details','source':'native','arguments':{'invoice_id':6},'output':{'invoice_id':6,'vendor_id':1,'amount':80}},
                    {'seq':3,'kind':'llm','agent':'orchestrator_agent','output':{'tool_calls':[{'name':'finstripe__create_transfer','arguments':{'invoice_id':6,'vendor_id':1,'amount':80}}]}}]}
                if with_ids:run['steps'][1]['call_id']='a';run['steps'][2]['call_id']='b'
                events,task=legacy_events(run)
                rows,_=collect_hooks(events,episode_id='old/duplicate',source_ref='raw.jsonl#L1',initial={'invoice':{'id':6,'vendor_id':1,'amount':50}},root_task=task)
                self.assertEqual(rows[0]['observation']['facts']['invoice_amount'],'80' if with_ids else '50')
                self.assertEqual(rows[0]['observation']['context']['prefix_complete'],with_ids)

    def test_truncated_prefix_does_not_prove_absence(self):
        rows=fixture_rows()[1:]+[event('before_tool','finstripe__create_transfer', {'invoice_id':6})]
        row=self.collect(rows)[0]
        self.assertFalse(row['observation']['context']['prefix_complete'])
        self.assertIsNone(row['observation']['facts']['fraud_delegate_completed'])

if __name__ == '__main__': unittest.main()
