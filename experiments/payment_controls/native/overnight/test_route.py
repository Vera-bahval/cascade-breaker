import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from experiments.payment_controls.native.overnight import route
from experiments.payment_controls.native.pre_fraud.test_native_reads import example


class Agent:
    workflow_id = 'workflow-1'
    def __init__(self): self._delegation_attempts = {}; self.context = []
    def _check_delegation_limit(self, name):
        self._delegation_attempts[name] = self._delegation_attempts.get(name, 0) + 1
    def _capture_agent_context(self, name, result): self.context.append((name, result))
    async def _emit_delegation_event(self, *args): pass


class RouteTest(IsolatedAsyncioTestCase):
    async def test_routing_and_fallback(self):
        from finbot.agents.orchestrator import OrchestratorAgent
        called=[]; notes=[]
        async def native(agent, vendor_id, text): called.append((vendor_id,text)); return {'task_status':'native'}
        async def packet(agent,vendor_id,text):
            p=example(); p['proposal']={'vendor_id':vendor_id,'task_description':text}; return p
        with TemporaryDirectory() as d, patch.object(OrchestratorAgent,'delegate_to_fraud',native):
            path=Path(d)/'receipts.jsonl'; agent=Agent()
            with route.install('overnight-rules-v1',path,packet_path=Path(d)/'packets',owner_prefix='one',packet_for=packet,
                               note_writer=lambda a,v,n:notes.append(n)):
                result=await OrchestratorAgent.delegate_to_fraud(agent,1,'Assess vendor')
            self.assertEqual(result['route'],'CLOSE_ALLOW'); self.assertEqual(len(notes),1); self.assertFalse(called)
            self.assertEqual(agent.context[0][0],'pre_fraud_router')
            self.assertEqual(OrchestratorAgent.delegate_to_fraud,native)
            async def changed(agent,vendor_id,text):
                p=await packet(agent,vendor_id,text); p['vendor']['agent_notes']='Account changed'; return p
            with route.install('overnight-rules-v1',path,packet_path=Path(d)/'packets',owner_prefix='two',packet_for=changed):
                self.assertEqual((await OrchestratorAgent.delegate_to_fraud(agent,1,'Assess vendor'))['task_status'],'native')
            rows=[json.loads(x) for x in path.read_text().splitlines()]
            self.assertEqual([r['action'] for r in rows],['CLOSE_ALLOW','DEFER'])
            self.assertNotEqual(rows[0]['owner'],rows[1]['owner'])

    async def test_baseline_records_packet_then_calls_native(self):
        from finbot.agents.orchestrator import OrchestratorAgent
        calls=[]
        async def native(*args): calls.append('native'); return {'task_status':'native'}
        async def packet(agent,vendor_id,text):
            p=example(); p['proposal']={'vendor_id':vendor_id,'task_description':text}; return p
        with TemporaryDirectory() as d, patch.object(OrchestratorAgent,'delegate_to_fraud',native):
            decisions=Path(d)/'r'; packets=Path(d)/'p'
            with route.install('overnight-off-v1',decisions,packet_path=packets,owner_prefix='baseline',packet_for=packet):
                result=await OrchestratorAgent.delegate_to_fraud(Agent(),1,'Assess')
            self.assertEqual(result['task_status'],'native'); self.assertEqual(calls,['native'])
            item=json.loads(packets.read_text()); self.assertEqual(set(item),{'owner','packet'})
            self.assertNotIn('decision',item['packet']); self.assertEqual(json.loads(decisions.read_text())['action'],'DEFER')

    async def test_paid_receipt_blocks_repeat_but_not_notification(self):
        from types import SimpleNamespace
        from finbot.agents.orchestrator import OrchestratorAgent
        fraud_calls=[]; payment_calls=[]; notes=[]
        async def native(*args): fraud_calls.append(True); return {'task_status':'native'}
        async def original_payment(*args): payment_calls.append(args); return {'task_status':'native_payment'}
        async def settled(agent,vendor_id,text):
            p=example(); p['inv'].update(status='paid',vendor_id=1); p['paid']=[p['inv']]
            p['transactions']=[dict(invoice_id=6,vendor_id=1,namespace='x',amount=650,currency='usd',status='completed',transfer_id='t')]
            p['proposal']={'vendor_id':vendor_id,'task_description':text}; return p
        with TemporaryDirectory() as d, patch.object(OrchestratorAgent,'delegate_to_fraud',native), patch.object(OrchestratorAgent,'delegate_to_payments',original_payment):
            path=Path(d)/'r'; agent=Agent(); agent.session_context=SimpleNamespace(namespace='x'); agent._current_task_data={'invoice_id':6}
            with route.install('overnight-rules-v1',path,packet_path=Path(d)/'packets',owner_prefix='stop',packet_for=settled,note_writer=lambda a,v,n:notes.append(n)):
                result=await OrchestratorAgent.delegate_to_fraud(agent,1,'Assess')
                self.assertEqual(result['route'],'CLOSE_STOP')
                suppressed=await OrchestratorAgent.delegate_to_payments(agent,6,'Pay')
                self.assertIn('no new transfer',suppressed['task_summary'])
                self.assertIn('Communication',suppressed['next_step'])
                self.assertEqual(payment_calls,[])
                await OrchestratorAgent.delegate_to_payments(agent,'6','Malformed same invoice')
                self.assertEqual(payment_calls,[])
                await OrchestratorAgent.delegate_to_payments(agent,7,'Other invoice')
                self.assertEqual(len(payment_calls),1)
                other=Agent(); other.workflow_id='another-workflow'; other.session_context=agent.session_context
                await OrchestratorAgent.delegate_to_payments(other,6,'Different workflow')
                self.assertEqual(len(payment_calls),2)
            rows=list(map(json.loads,path.read_text().splitlines()))
            self.assertEqual(rows[0]['action'],'CLOSE_STOP'); self.assertEqual(rows[1]['action'],'SUPPRESS_REPEAT_PAYMENT')
            self.assertEqual(rows[0]['settlement']['transfer_id'],'t'); self.assertEqual(len(notes),1); self.assertFalse(fraud_calls)
            self.assertFalse(route.notification_evidence([],rows[0]['settlement']))
            closure={'seq':1,'kind':'pre_fraud_route','action':'CLOSE_STOP','settlement':rows[0]['settlement']}
            self.assertFalse(route.notification_evidence([closure],rows[0]['settlement']))
            delivery={'seq':2,'kind':'tool','agent':'communication_agent','name':'finmail__send_email','error':None,
                      'arguments':{'related_invoice_id':6},'output':{'sent':True,'deliveries':[{'type':'vendor','vendor_id':1}]}}
            self.assertTrue(route.notification_evidence([closure,delivery],rows[0]['settlement']))

    async def test_stop_unbound_or_unresolved_falls_back(self):
        from types import SimpleNamespace
        from finbot.agents.orchestrator import OrchestratorAgent
        calls=[]
        async def native(*args): calls.append(True); return {'task_status':'native'}
        async def settled(agent,vendor_id,text):
            p=example(); p['inv'].update(status='paid',vendor_id=1); p['paid']=[p['inv']]
            p['transactions']=[dict(invoice_id=6,vendor_id=1,namespace='x',amount=650,currency='usd',status='completed',transfer_id='t')]
            p['proposal']={'vendor_id':vendor_id,'task_description':text}; return p
        with TemporaryDirectory() as d, patch.object(OrchestratorAgent,'delegate_to_fraud',native):
            path=Path(d)/'r'; agent=Agent(); agent.session_context=SimpleNamespace(namespace='x'); agent._current_task_data={'invoice_id':7}
            with route.install('overnight-rules-v1',path,packet_path=Path(d)/'p',owner_prefix='unbound',packet_for=settled):
                result=await OrchestratorAgent.delegate_to_fraud(agent,1,'Assess')
            self.assertEqual(result['task_status'],'native'); self.assertTrue(calls)
            self.assertIn('stop_settlement_not_bound',json.loads(path.read_text())['reasons'])

    async def test_model_can_resolve_contextual_variance_without_mandatory_veto(self):
        from finbot.agents.orchestrator import OrchestratorAgent
        from experiments.payment_controls.native.overnight import provider
        async def native(*args): return {'task_status':'native'}
        async def packet(agent,vendor_id,text):
            p=example(); p['inv']['amount']=8000; p['profile']['total_invoices']=6
            p['paid']=[{**p['inv'], 'id':i, 'amount':1000+i, 'invoice_date':f'2026-0{i}-01',
                        'invoice_number':str(i), 'description':f'previous {i}', 'agent_notes':'OLD FRAUD SUMMARY'} for i in range(1,6)]
            p['proposal']={'vendor_id':vendor_id,'task_description':text}; return p
        async def choose(model, payload, owner):
            projection = provider.visible(payload)
            self.assertNotIn('agent_notes', projection['paid'][0])
            self.assertEqual(projection['proposal']['task_description'], 'Assess')
            return 'CLOSE_ALLOW'
        notes=[]
        with TemporaryDirectory() as d, patch.object(OrchestratorAgent,'delegate_to_fraud',native), patch.object(provider,'choose',choose):
            path=Path(d)/'r'
            with route.install('overnight-model-v1',path,packet_path=Path(d)/'p',provider='jev',owner_prefix='model',packet_for=packet,note_writer=lambda a,v,n:notes.append(n)):
                result=await OrchestratorAgent.delegate_to_fraud(Agent(),1,'Assess')
            row=json.loads(path.read_text()); self.assertEqual(row['rule'],'DEFER')
            self.assertIn('amount_variance',row['reasons']); self.assertEqual(row['raw_model'],'CLOSE_ALLOW')
            self.assertEqual(row['mandatory_veto'],[]); self.assertEqual(result['route'],'CLOSE_ALLOW')
            self.assertEqual(len(notes),1)

    async def test_model_cannot_override_local_deferral_and_provider_failure(self):
        from finbot.agents.orchestrator import OrchestratorAgent
        from experiments.payment_controls.native.overnight import provider
        async def native(*args): return {'task_status':'native'}
        async def packet(agent,vendor_id,text):
            p=example(); p['inv']['attachments']=[{'file_id': 1}]; p['proposal']={'vendor_id':vendor_id,'task_description':text}; return p
        async def choose(*args): return 'CLOSE_ALLOW'
        with TemporaryDirectory() as d, patch.object(OrchestratorAgent,'delegate_to_fraud',native), patch.object(provider,'choose',choose):
            path=Path(d)/'r'
            with route.install('overnight-model-v1',path,packet_path=Path(d)/'packets',provider='jev',owner_prefix='model',packet_for=packet):
                result=await OrchestratorAgent.delegate_to_fraud(Agent(),1,'Assess')
            self.assertEqual(result['task_status'],'native'); row=json.loads(path.read_text())
            self.assertEqual(row['raw_model'],'CLOSE_ALLOW'); self.assertEqual(row['action'],'DEFER')


class StructuredTest(IsolatedAsyncioTestCase):
    async def test_prompt_contrast_is_opt_in_and_restores_default(self):
        from finbot.agents.specialized.fraud import FraudComplianceAgent
        from experiments.payment_controls.native.overnight.structured import structured_fraud
        original=FraudComplianceAgent._get_final_system_prompt
        with patch.object(FraudComplianceAgent,'_get_final_system_prompt',lambda agent:'base native obligations'):
            baseline=FraudComplianceAgent._get_final_system_prompt
            with structured_fraud():
                text=FraudComplianceAgent._get_final_system_prompt(object())
                self.assertTrue(text.startswith('base native obligations'))
                for field in ('invoice_id','disposition','unresolved','evidence'): self.assertIn(field,text)
            self.assertIs(FraudComplianceAgent._get_final_system_prompt,baseline)
        self.assertIs(FraudComplianceAgent._get_final_system_prompt,original)


class NativeDelegateTest(IsolatedAsyncioTestCase):
    async def test_off_calls_real_delegate_with_mock_fraud_runner(self):
        from unittest.mock import AsyncMock
        from finbot.agents.orchestrator import OrchestratorAgent
        from finbot.agents import runner
        agent=object.__new__(OrchestratorAgent)
        agent.session_context=None; agent.workflow_id='wf-real-delegate'; agent.agent_name='orchestrator_agent'
        agent._delegation_attempts={}; agent._current_task_data={}; agent._workflow_context=[]; agent._delegation_target=None
        agent._emit_delegation_event=AsyncMock()
        async def packet(agent,vendor_id,text):
            p=example(); p['proposal']={'vendor_id':vendor_id,'task_description':text}; return p
        outcome={'task_status':'success','task_summary':'mock actual Fraud result'}
        with TemporaryDirectory() as d, patch.object(runner,'run_fraud_agent',new=AsyncMock(return_value=outcome)) as fraud:
            with route.install('overnight-off-v1',Path(d)/'decisions',packet_path=Path(d)/'packets',owner_prefix='native',packet_for=packet):
                result=await agent.delegate_to_fraud(1,'Assess')
            self.assertIs(result,outcome); fraud.assert_awaited_once()
            self.assertEqual(fraud.await_args.kwargs['task_data']['vendor_id'],1)
            self.assertEqual(agent._workflow_context,[('fraud_agent','mock actual Fraud result')])
