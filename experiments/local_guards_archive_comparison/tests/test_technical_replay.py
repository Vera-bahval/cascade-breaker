import copy
import sqlite3
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from technical_replay import Registry, replay_episode, digest


def pair():
    source='archive::hooks.jsonl'
    events=[{'event_seq':2,'hook_kind':'before_model','user_message':'invoice_id: 6 vendor_id: 1'},
        {'event_seq':4,'hook_kind':'before_tool','tool_name':'delegate_to_fraud','tool_arguments':{'vendor_id':1},'tool_source':'native'},
        {'event_seq':6,'hook_kind':'before_tool','tool_name':'get_invoice_details','tool_arguments':{'invoice_id':6},'tool_source':'native'},
        {'event_seq':8,'hook_kind':'after_tool','tool_name':'get_invoice_details','tool_arguments':{'invoice_id':6},'tool_result':{'invoice_id':6,'vendor_id':1,'status':'approved'},'tool_source':'native'},
        {'event_seq':10,'hook_kind':'after_tool','tool_name':'delegate_to_fraud','tool_arguments':{'vendor_id':1},'tool_result':{'task_status':'success'},'tool_source':'native'}]
    link=dict(prefix_id='p',source_ref=source+'#L5',source_event_index=5,task_admission_ref=source+'#L1',call_source_ref=source+'#L2',actor_stack=['orchestrator','fraud'],paired_return=True)
    historical=dict(prefix_id='p',episode_id='e',checkpoint='P2_afterFraud',event_seq=11,raw_context={'events':events,'initial_state':{},'initial_fixture':{}},observation={'facts':{},'proposal':{'tool':'delegate_to_fraud'},'context':{'source_refs':[source],'call_id':source+'#L2','parent_workflow_id':None,'source_binding':'captured_raw_prefix'},'provenance':{}},evidence_status={})
    technical=copy.deepcopy(historical);c=technical['observation']['context'];c.update(call_id='collector/'+digest(link)[:24],parent_workflow_id='collector/task/'+digest('e')[:24],source_binding='offline_replay_recorded_source_links')
    for field in ('call_id','parent_workflow_id','source_binding'):
        key='context.'+field
        technical['observation']['provenance'][key]=[dict(source_ref=link['source_ref'],event_seq=11,field=key,value=c[field],derived_from=[link['task_admission_ref'],link['call_source_ref']],status='instrumented',kind='declared_instrumentation')]
    return historical,technical


class ReplayTests(unittest.TestCase):
    def test_real_sqlite_registration_backs_frozen_links_and_native_state(self):
        h,t=pair();before=copy.deepcopy((h,t))
        with Registry(':memory:') as registry:
            report=replay_episode(registry,[h],[t])
            self.assertEqual(report['supported'],1)
            self.assertEqual(registry.db.execute('select count(*) from admissions').fetchone()[0],1)
            self.assertEqual(registry.db.execute('select count(*) from calls').fetchone()[0],2)
            self.assertGreater(registry.db.execute('select count(*) from observed_state').fetchone()[0],0)
            self.assertEqual(registry.db.execute('select count(*) from technical_links').fetchone()[0],3)
        self.assertEqual((h,t),before)

    def test_missing_or_ambiguous_return_is_unknown(self):
        h,t=pair();h['raw_context']['events'].pop(1);t['raw_context']=copy.deepcopy(h['raw_context'])
        with Registry(':memory:') as registry:
            report=replay_episode(registry,[h],[t])
            self.assertEqual(report['supported'],0)
            self.assertEqual(report['unknown'],1)

    def test_p4_registers_proposal_without_future_payment_result(self):
        h,t=pair();p4=copy.deepcopy(h);p4.update(prefix_id='p4',checkpoint='P4',event_seq=16)
        p4['raw_context']['events'].append({'event_seq':12,'hook_kind':'before_tool','tool_name':'delegate_to_payments','tool_arguments':{'invoice_id':6}})
        source='archive::hooks.jsonl';ref=source+'#L8'
        p4['raw_context']['proposed_action']={'event_seq':16,'source_ref':ref,'tool_name':'finstripe__create_transfer','tool_arguments':{'invoice_id':6,'vendor_id':1,'amount':50}}
        link=dict(prefix_id='p4',source_ref=ref,source_event_index=8,task_admission_ref=source+'#L1',call_source_ref=ref,actor_stack=['orchestrator','payments'],paired_return=False)
        p4['observation']['proposal']={'tool':'finstripe__create_transfer'}
        p4['observation']['context']['call_id']=ref
        t4=copy.deepcopy(p4);c=t4['observation']['context'];c.update(call_id='collector/'+digest(link)[:24],parent_workflow_id='collector/task/'+digest('e')[:24],source_binding='offline_replay_recorded_source_links')
        for field in ('call_id','parent_workflow_id','source_binding'):
            t4['observation']['provenance']['context.'+field]=[dict(source_ref=ref,event_seq=16,field='context.'+field,value=c[field],derived_from=[source+'#L1',ref],status='instrumented',kind='declared_instrumentation')]
        with Registry(':memory:') as registry:
            report=replay_episode(registry,[h,p4],[t,t4])
            self.assertEqual(report['supported'],2)
            pending=registry.db.execute("select return_event_seq from calls where tool='finstripe__create_transfer'").fetchone()
            self.assertIsNone(pending[0])

    def test_tampered_frozen_id_is_discrepancy_not_repaired(self):
        h,t=pair();t['observation']['context']['call_id']='forged'
        with Registry(':memory:') as registry:
            report=replay_episode(registry,[h],[t])
            self.assertEqual(report['discrepancies'],1)
        self.assertEqual(t['observation']['context']['call_id'],'forged')

    def test_future_event_rejected_and_admissions_independent(self):
        h,t=pair();h['raw_context']['events'].append({'event_seq':12,'hook_kind':'after_tool','tool_name':'future'})
        t['raw_context']=copy.deepcopy(h['raw_context'])
        with Registry(':memory:') as registry:
            report=replay_episode(registry,[h],[t])
            self.assertEqual(report['supported'],0)
            self.assertEqual(report['discrepancies'],1)
            self.assertEqual(registry.db.execute('select count(*) from observed_state where event_seq>11').fetchone()[0],0)
            registry.admit('another',None,None,'inventory_only')
            self.assertEqual(registry.db.execute('select count(distinct task_id) from admissions').fetchone()[0],2)

if __name__=='__main__':unittest.main()
