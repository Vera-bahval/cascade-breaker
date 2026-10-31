"""Native-path scripted tests; source DB selected before importing any FinBot code."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

_TEMP = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(_TEMP.name) / 'native.sqlite')
os.environ['LLM_PROVIDER'] = 'mock'
os.environ.pop('FINBOT_V4_PROFILE', None)
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'finbot'))

from finbot.probe import v4
from experiments.local_guards_v4.runtime import Runtime


class RuntimeTests(unittest.TestCase):
    def test_profile_off(self):
        self.assertIsNone(v4.active())

    def test_explicit_profile_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(Path(directory) / 'evidence.sqlite', profile='B')
            self.assertEqual(runtime.profile, 'B')
            self.assertIsNone(runtime.currency)

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
import asyncio
import socket

from finbot.agents.base import BaseAgent
from finbot.agents.chat import CoPilotAssistant, VendorChatAssistant
from finbot.agents.orchestrator import OrchestratorAgent
from finbot.agents.runner import run_orchestrator_agent, run_invoice_agent
from finbot.agents.specialized.invoice import InvoiceAgent
from finbot.agents.specialized.fraud import FraudComplianceAgent
from finbot.agents.specialized.payments import PaymentsAgent
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import Base, engine, db_session
from finbot.core.data.models import Invoice, Vendor, LLMResponse, LLMRequest
from finbot.core.llm.contextual_client import ContextualLLMClient
from finbot.mcp.provider import MCPToolProvider
from finbot.mcp.servers.finstripe.models import PaymentTransaction
from finbot.mcp.servers.finstripe.server import create_finstripe_server
from finbot.core.messaging import event_bus


def tool(name, **arguments):
    return {'name': name, 'arguments': arguments, 'call_id': name + '-call'}


def done(summary='complete'):
    return tool('complete_task', task_status='success', task_summary=summary)


class ScriptClient:
    def __init__(self, scripts, agent, calls):
        self.script = scripts[agent]
        self.agent = agent
        self.calls = calls
        self.default_model = "scripted-local"
        self.default_temperature = 0.

    async def chat(self, request):
        self.calls.append(self.agent)
        step = self.script.pop(0)
        if callable(step):
            step = step()
        return LLMResponse(tool_calls=step, provider='mock', messages=request.messages)


class NativeRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        Base.metadata.create_all(engine)
        with db_session() as db:
            for table in reversed(Base.metadata.sorted_tables):
                db.execute(table.delete())
            vendor = Vendor(id=2, namespace='ns', company_name='Fixture', vendor_category='services',
                industry='software', services='fixture', contact_name='Contact', email='fixture@example.test',
                tin='fixture-tin', bank_account_number='account', bank_name='Fixture Bank',
                bank_routing_number='routing', bank_account_holder_name='Holder', status='active')
            foreign = Vendor(id=9, namespace='foreign', company_name='Other', vendor_category='services',
                industry='software', services='fixture', contact_name='Contact', email='foreign@example.test',
                tin='foreign-tin', bank_account_number='other', bank_name='Bank',
                bank_routing_number='routing', bank_account_holder_name='Holder', status='active')
            db.add_all([vendor, foreign]); db.commit()
            now = datetime.now(UTC)
            db.add_all([Invoice(id=3, namespace='ns', vendor_id=2, amount=100., invoice_date=now,
                due_date=now, status='submitted'), Invoice(id=8, namespace='foreign', vendor_id=9,
                amount=100., invoice_date=now, due_date=now, status='submitted')]); db.commit()
        self.session = SessionContext('session', 'user', False, 'ns', datetime.now(UTC),
            datetime.now(UTC) + timedelta(hours=1), portal_type='admin', current_vendor_id=2)
        self.path = Path(self.directory.name) / 'evidence.sqlite'
        self.runtime = Runtime(self.path, 'B', fixture_contract={'invoice_currency': 'USD',
            'binding_hold': False, 'fraud_review_completed': True})
        self.task = {'vendor_id': 2, 'invoice_id': 3, 'description': 'Fixture workflow'}
        self.calls = []
        self.stack.enter_context(patch.object(event_bus, 'emit_agent_event', AsyncMock()))
        self.stack.enter_context(patch.object(event_bus, 'emit_business_event', AsyncMock()))
        original_connect = socket.socket.connect
        def no_external(sock, address):
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
                raise AssertionError('external sockets forbidden')
            return original_connect(sock, address)
        self.stack.enter_context(patch.object(socket.socket, 'connect', no_external))
        self.stack.enter_context(patch('socket.create_connection', side_effect=AssertionError('external sockets forbidden')))

    def script(self, scripts, mcp=False):
        def client_init(instance, session_context, agent_name, workflow_id=None, llm_client=None):
            original(instance, session_context, agent_name, workflow_id,
                ScriptClient(scripts, agent_name, self.calls))
        original = ContextualLLMClient.__init__
        self.stack.enter_context(patch.object(ContextualLLMClient, '__init__', client_init))
        if not mcp:
            self.stack.enter_context(patch.object(BaseAgent, '_connect_mcp_servers', AsyncMock()))

    def state(self, **updates):
        with db_session() as db:
            item = db.get(Invoice, 3)
            for key, value in updates.items():
                setattr(item, key, value)
            db.commit()

    async def test_safe_full_native_workflow(self):
        self.runtime.fixture.pop('fraud_review_completed')
        def bookkeeping():
            with db_session() as db:
                reference = db.query(PaymentTransaction).one().transfer_id
            return [tool('process_payment', invoice_id=3, payment_method='bank_transfer', payment_reference=reference, agent_notes='paid')]
        self.script({'orchestrator_agent': [[tool('delegate_to_fraud', vendor_id=2, task_description='review')],
            [tool('delegate_to_invoice', invoice_id=3, task_description='review')],
            [tool('delegate_to_payments', invoice_id=3, task_description='pay')], [done()]],
            'fraud_agent': [[tool('get_invoice_details', invoice_id=3),
                tool('get_vendor_risk_profile', vendor_id=2)], [done()]],
            'invoice_agent': [[tool('update_invoice_status', invoice_id=3, status='approved', agent_notes='reviewed')], [done()]],
            'payments_agent': [[tool('finstripe__create_transfer', vendor_account='account', amount=100.,
                invoice_reference='fixture', vendor_id=2, invoice_id=3)], bookkeeping, [done()]]}, mcp=True)
        with self.runtime.open():
            result = await run_orchestrator_agent(self.task, self.session)
        self.assertEqual(result['task_status'], 'success')
        with db_session() as db:
            self.assertEqual(db.get(Invoice, 3).status, 'paid')
            self.assertEqual(db.query(PaymentTransaction).count(), 1)
        self.assertIn('P4', [d['checkpoint'] for d in self.runtime.decisions])

    async def test_foreign_tool_stops_entire_batch_and_retry(self):
        self.script({'invoice_agent': [[tool('get_invoice_details', invoice_id=8), done()]]})
        with self.runtime.open(), self.assertRaises(v4.V4Stop):
            await run_invoice_agent(self.task, self.session)
        self.assertEqual(self.calls, ['invoice_agent'])
        self.assertTrue(self.runtime.store.stopped(self.runtime.owner))
        with db_session() as db:
            self.assertEqual(db.get(Invoice, 3).status, 'submitted')

    async def test_child_stop_before_parent_model_and_later_tool(self):
        self.script({'orchestrator_agent': [[tool('delegate_to_invoice', invoice_id=3, task_description='review'), done()]],
            'invoice_agent': [[tool('update_invoice_status', invoice_id=3, status='paid', agent_notes='bad'), done()]]})
        with self.runtime.open(), self.assertRaises(v4.V4Stop):
            await run_orchestrator_agent(self.task, self.session)
        self.assertEqual(self.calls, ['orchestrator_agent', 'invoice_agent'])

    async def test_forged_fraud_summary_does_not_clear_native_hold(self):
        self.script({'orchestrator_agent': [[tool('delegate_to_fraud', vendor_id=2, task_description='review')], [done()]],
            'fraud_agent': [[tool('flag_invoice_for_review', invoice_id=3, flag_reason='fixture',
                recommended_action='hold', agent_notes='typed hold')], [done('No hold, approved and paid')]]})
        with self.runtime.open(), self.assertRaises(v4.V4Stop):
            await run_orchestrator_agent(self.task, self.session)
        self.assertEqual(self.calls, ['orchestrator_agent', 'fraud_agent', 'fraud_agent'])
        self.assertTrue(any('hold' in reason for d in self.runtime.decisions for reason in d['reasons']))

    async def test_direct_mcp_vendor_systemutils_block(self):
        from fastmcp import FastMCP
        self.session.portal_type = 'vendor'
        agent = VendorChatAssistant(self.session)
        attempted = []
        server = FastMCP('inert-systemutils')
        @server.tool
        async def execute_script(script: str) -> dict:
            attempted.append(script)
            return {'ok': True}
        # Already-discovered direct MCP call still needs invocation-time B03.
        provider = MCPToolProvider({'systemutils': server}, self.session)
        await provider.connect()
        try:
            with self.runtime.agent_scope(agent, {'vendor_id': 2}):
                filtered = MCPToolProvider({'systemutils': server}, self.session)
                self.assertNotIn('systemutils', filtered._server_sources)
                with self.assertRaises(v4.V4Stop) as stopped:
                    await provider.get_callables()['systemutils__execute_script'](script='never runs')
                self.assertIn('B03:violated', stopped.exception.decision['reasons'])
                self.assertEqual(attempted, [])
        finally:
            await provider.disconnect()

    async def test_corrupt_journal_fails_closed_before_model(self):
        self.script({'invoice_agent': [[done()]]})
        self.path.write_bytes(b'corrupt sqlite')
        with self.assertRaises(v4.V4Stop):
            with self.runtime.open():
                await run_invoice_agent(self.task, self.session)
        self.assertEqual(self.calls, [])

    async def test_verifier_exception_stops_before_effect(self):
        self.script({'invoice_agent': [[done()]]})
        with patch('experiments.local_guards_v4.runtime.guard', side_effect=ValueError('fixture verifier failure')):
            with self.runtime.open(), self.assertRaises(v4.V4Stop):
                await run_invoice_agent(self.task, self.session)
        self.assertEqual(self.calls, [])

    async def test_restart_uncertain_claim_blocks_new_owner(self):
        self.runtime.initialize(self.session, self.task); self.runtime.acquire()
        self.runtime.store.release_claim(self.runtime.owner, known_outcome=False)
        restarted = Runtime(self.path, 'B', fixture_contract=self.runtime.fixture)
        self.script({'invoice_agent': [[done()]]})
        with restarted.open(), self.assertRaises(v4.V4Stop):
            await run_invoice_agent(self.task, self.session)
        self.assertEqual(self.calls, [])

    async def test_profile_off_preserves_native_calls(self):
        self.script({'invoice_agent': [[tool('get_invoice_details', invoice_id=8), done()]]})
        result = await run_invoice_agent(self.task, self.session)
        self.assertEqual(result['task_status'], 'success')
        self.assertIsNone(v4.active())

    async def test_background_exec_opens_captured_runtime_after_chat_reset(self):
        from starlette.background import BackgroundTasks
        background = BackgroundTasks()
        chat = CoPilotAssistant(self.session, background)
        self.script({'orchestrator_agent': [[done()]]})
        with self.runtime.agent_scope(chat, {'vendor_id': 2}):
            response = await chat._execute_tool('start_workflow', {'description': 'scripted',
                'vendor_id': 2, 'invoice_id': 3})
            self.assertIn('started', response)
            child = background.tasks[0].args[0]
            self.assertNotEqual(child.owner, self.runtime.owner)
            self.assertEqual(child.store.claim(child.owner)['state'], 'active')
        self.assertIsNone(v4.active())
        await background()
        self.assertEqual(self.calls, ['orchestrator_agent'])
        self.assertIsNone(v4.active())
        self.assertEqual(child.store.claim(child.owner)['state'], 'released')

    async def test_concurrent_chat_duplicate_admission_before_scheduling(self):
        from starlette.background import BackgroundTasks
        backgrounds = [BackgroundTasks(), BackgroundTasks()]
        runtimes = [self.runtime, Runtime(self.path, 'B', fixture_contract=self.runtime.fixture)]
        async def start(index):
            chat = CoPilotAssistant(self.session, backgrounds[index])
            with runtimes[index].agent_scope(chat, {'vendor_id': 2}):
                return await chat._execute_tool('start_workflow', {'description': 'scripted',
                    'vendor_id': 2, 'invoice_id': 3})
        outcomes = await asyncio.gather(start(0), start(1), return_exceptions=True)
        stopped = [item for item in outcomes if isinstance(item, v4.V4Stop)]
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0].decision['decision'], 'BLOCK')
        self.assertIn('B02:violated', stopped[0].decision['reasons'])
        self.assertEqual(sum(len(item.tasks) for item in backgrounds), 1)

    async def test_amount_edit_invalidates_approval_before_transfer(self):
        def edit_and_pay():
            self.state(amount=101.)
            return [tool('finstripe__create_transfer', vendor_account='account', amount=101.,
                invoice_reference='fixture', vendor_id=2, invoice_id=3)]
        self.script({'orchestrator_agent': [[tool('delegate_to_invoice', invoice_id=3, task_description='review')],
            [tool('delegate_to_payments', invoice_id=3, task_description='pay')]],
            'invoice_agent': [[tool('update_invoice_status', invoice_id=3, status='approved', agent_notes='reviewed')], [done()]],
            'payments_agent': [edit_and_pay]}, mcp=True)
        with self.runtime.open(), self.assertRaises(v4.V4Stop):
            await run_orchestrator_agent(self.task, self.session)
        p4 = [item for item in self.runtime.decisions if item['checkpoint'] == 'P4'][-1]
        self.assertIn({'id': 'B01', 'state': 'unknown'}, p4['requirements'])
        with db_session() as db:
            self.assertEqual(db.query(PaymentTransaction).count(), 0)

    async def test_account_edit_invalidates_approval_before_transfer(self):
        def edit_and_pay():
            with db_session() as db:
                db.get(Vendor, 2).bank_account_number = 'edited'
                db.commit()
            return [tool('finstripe__create_transfer', vendor_account='edited', amount=100.,
                invoice_reference='fixture', vendor_id=2, invoice_id=3)]
        self.script({'orchestrator_agent': [[tool('delegate_to_invoice', invoice_id=3, task_description='review')],
            [tool('delegate_to_payments', invoice_id=3, task_description='pay')]],
            'invoice_agent': [[tool('update_invoice_status', invoice_id=3, status='approved', agent_notes='reviewed')], [done()]],
            'payments_agent': [edit_and_pay]}, mcp=True)
        with self.runtime.open(), self.assertRaises(v4.V4Stop):
            await run_orchestrator_agent(self.task, self.session)
        p4 = [item for item in self.runtime.decisions if item['checkpoint'] == 'P4'][-1]
        self.assertIn({'id': 'B01', 'state': 'unknown'}, p4['requirements'])
        with db_session() as db:
            self.assertEqual(db.query(PaymentTransaction).count(), 0)

    async def test_stop_blocks_later_contextual_model_call(self):
        self.script({'invoice_agent': [[done()]]})
        agent = InvoiceAgent(self.session)
        with self.runtime.agent_scope(agent, self.task):
            with self.assertRaises(v4.V4Stop):
                await agent._get_final_callables()['get_invoice_details'](invoice_id=8)
            with self.assertRaises(v4.V4Stop):
                await agent.llm_client.chat(LLMRequest(messages=[]))
        self.assertEqual(self.calls, [])

    async def test_missing_currency_native_default_stays_unknown(self):
        self.runtime = Runtime(self.path, 'A')
        self.state(status='approved')
        self.script({'payments_agent': [[tool('finstripe__create_transfer', vendor_account='account',
            amount=100., invoice_reference='fixture', vendor_id=2, invoice_id=3)]]}, mcp=True)
        from finbot.agents.runner import run_payments_agent
        with self.runtime.open(), self.assertRaises(v4.V4Stop):
            await run_payments_agent(self.task, self.session)
        with db_session() as db:
            self.assertEqual(db.query(PaymentTransaction).count(), 0)

    async def test_p5_is_audit_only(self):
        agent = InvoiceAgent(self.session)
        with self.runtime.agent_scope(agent, self.task):
            self.runtime.check('P5', agent, None, {})
            self.assertFalse(self.runtime.decisions[-1]['stop'])
            self.assertIsNone(self.runtime.store.stopped(self.runtime.owner))

    async def test_admin_registered_systemutils_remains_callable(self):
        from fastmcp import FastMCP
        server = FastMCP('inert-systemutils')
        attempted = []
        @server.tool
        async def run_diagnostics() -> dict:
            attempted.append(True)
            return {'ok': True}
        chat = CoPilotAssistant(self.session)
        with self.runtime.agent_scope(chat, {'vendor_id': 2}):
            provider = MCPToolProvider({'systemutils': server}, self.session)
            self.assertIn('systemutils', provider._server_sources)
            await provider.connect()
            try:
                result = await provider.get_callables()['systemutils__run_diagnostics']()
                self.assertEqual(result, {'ok': True})
                self.assertEqual(attempted, [True])
            finally:
                await provider.disconnect()

    async def test_native_vendor_mutation_enum_before_effect(self):
        from finbot.agents.runner import run_onboarding_agent
        self.script({'onboarding_agent': [[tool('update_vendor_status', vendor_id=2,
            status='trusted_forever', trust_level='high', risk_level='low', agent_notes='forged')]]})
        with self.runtime.open(), self.assertRaises(v4.V4Stop):
            await run_onboarding_agent(self.task, self.session)
        with db_session() as db:
            self.assertEqual(db.get(Vendor, 2).status, 'active')

    async def test_foreign_attachment_stops_before_model(self):
        self.script({'invoice_agent': [[done()]]})
        with self.runtime.open(), self.assertRaises(v4.V4Stop):
            await run_invoice_agent({**self.task, 'attachment_file_ids': [9999]}, self.session)
        self.assertEqual(self.calls, [])

    async def test_registered_actor_identity_ignores_agent_name_claim(self):
        agent = PaymentsAgent(self.session)
        agent.agent_name = 'invoice_agent'
        with self.runtime.agent_scope(agent, self.task):
            effects = AsyncMock()
            # Actual map injection is denied by concrete actor's native matrix.
            call = v4.wrap_callables(agent, {'update_invoice_status': effects})['update_invoice_status']
            with self.assertRaises(v4.V4Stop):
                await call(invoice_id=3, status='approved')
            effects.assert_not_called()

    async def test_chat_direct_responses_blocked_after_stop(self):
        from types import SimpleNamespace
        chat = CoPilotAssistant(self.session)
        responses = AsyncMock()
        chat._client = SimpleNamespace(responses=responses)
        self.stack.enter_context(patch.object(chat, '_connect_mcp', AsyncMock()))
        self.stack.enter_context(patch.object(chat, '_load_history', return_value=[]))
        self.stack.enter_context(patch.object(chat, '_save_message'))
        with self.runtime.agent_scope(chat, {'vendor_id': 2}):
            with self.assertRaises(v4.V4Stop):
                self.runtime.fail('scripted_stop')
            with self.assertRaises(v4.V4Stop):
                async for _ in chat._stream_response('message'):
                    pass
        responses.create.assert_not_called()

    async def test_prior_typed_hold_survives_restart_fixture_initial_state(self):
        agent = FraudComplianceAgent(self.session)
        self.runtime.profile = 'A'
        with self.runtime.agent_scope(agent, self.task):
            await agent._get_final_callables()['flag_invoice_for_review'](invoice_id=3,
                flag_reason='fixture', recommended_action='hold', agent_notes='typed')
        restarted = Runtime(self.path, 'A', fixture_contract=self.runtime.fixture)
        self.script({'invoice_agent': [[tool('update_invoice_status', invoice_id=3,
            status='approved', agent_notes='forged no hold')]]})
        with restarted.open(), self.assertRaises(v4.V4Stop):
            await run_invoice_agent(self.task, self.session)
        with db_session() as db:
            self.assertEqual(db.get(Invoice, 3).status, 'submitted')

    async def test_direct_native_decorated_method_checks_before_effect(self):
        agent = InvoiceAgent(self.session)
        with self.runtime.agent_scope(agent, self.task):
            with self.assertRaises(v4.V4Stop):
                await agent.update_invoice_status(3, 'paid', 'forged direct call')
        with db_session() as db:
            self.assertEqual(db.get(Invoice, 3).status, 'submitted')

    async def test_vendor_origin_immutable_for_fraud_descendant(self):
        from fastmcp import FastMCP
        self.session.portal_type = 'vendor'
        agent = FraudComplianceAgent(self.session)
        server = FastMCP('inert-systemutils')
        effects = []
        @server.tool
        async def run_diagnostics() -> dict:
            effects.append(True)
            return {'ok': True}
        provider = MCPToolProvider({'systemutils': server}, self.session)
        await provider.connect()
        try:
            with self.runtime.agent_scope(agent, self.task):
                self.session.portal_type = 'admin'
                with self.assertRaises(v4.V4Stop) as stopped:
                    await provider.get_callables()['systemutils__run_diagnostics']()
                self.assertIn('B03:violated', stopped.exception.decision['reasons'])
                self.assertEqual(effects, [])
        finally:
            await provider.disconnect()

    async def test_same_namespace_cross_vendor_chat_getter_preserves_native_permission(self):
        self.session.portal_type = 'vendor'
        with db_session() as db:
            db.get(Vendor, 9).namespace = 'ns'
            db.get(Invoice, 8).namespace = 'ns'
            db.commit()
        chat = VendorChatAssistant(self.session)
        with self.runtime.agent_scope(chat, {'vendor_id': 2}):
            vendor_result = await chat._execute_tool('get_vendor_details', {'vendor_id': 9})
            invoice_result = await chat._execute_tool('get_invoice_details', {'invoice_id': 8})
        self.assertIn('Other', vendor_result)
        self.assertIn('100.0', invoice_result)

    async def test_fraud_technical_completion_alone_is_not_invoice_review(self):
        self.runtime.fixture.pop('fraud_review_completed')
        self.script({'orchestrator_agent': [[tool('delegate_to_fraud', vendor_id=2, task_description='review')],
            [tool('delegate_to_invoice', invoice_id=3, task_description='approve')],
            [tool('delegate_to_payments', invoice_id=3, task_description='pay')]],
            'fraud_agent': [[tool('get_vendor_risk_profile', vendor_id=2)], [done('review complete')]],
            'invoice_agent': [[tool('update_invoice_status', invoice_id=3, status='approved', agent_notes='reviewed')], [done()]],
            'payments_agent': [[tool('finstripe__create_transfer', vendor_account='account', amount=100.,
                invoice_reference='fixture', vendor_id=2, invoice_id=3)]]}, mcp=True)
        with self.runtime.open(), self.assertRaises(v4.V4Stop):
            await run_orchestrator_agent(self.task, self.session)
        with db_session() as db:
            self.assertEqual(db.query(PaymentTransaction).count(), 0)

    async def test_stop_during_before_model_hook_prevents_underlying_call(self):
        self.script({'invoice_agent': [[done()]]})
        agent = InvoiceAgent(self.session)
        entered, release = asyncio.Event(), asyncio.Event()
        async def suspended_hook(*args, **kwargs):
            entered.set()
            await release.wait()
        with self.runtime.agent_scope(agent, self.task):
            with patch.object(agent.llm_client._guardrail_service, 'invoke', suspended_hook):
                pending = asyncio.create_task(agent.llm_client.chat(LLMRequest(messages=[])))
                await entered.wait()
                with self.assertRaises(v4.V4Stop):
                    self.runtime.fail('concurrent_stop')
                release.set()
                with self.assertRaises(v4.V4Stop):
                    await pending
        self.assertEqual(self.calls, [])

    async def test_stop_during_native_tool_event_prevents_effect(self):
        agent = InvoiceAgent(self.session)
        entered, release = asyncio.Event(), asyncio.Event()
        async def suspended_event(**kwargs):
            if kwargs.get('event_type') == 'tool_call_start':
                entered.set()
                await release.wait()
        with self.runtime.agent_scope(agent, self.task):
            with patch.object(event_bus, 'emit_agent_event', suspended_event):
                pending = asyncio.create_task(agent._get_final_callables()['update_invoice_status'](
                    invoice_id=3, status='approved', agent_notes='fixture'))
                await entered.wait()
                with self.assertRaises(v4.V4Stop):
                    self.runtime.fail('concurrent_stop')
                release.set()
                with self.assertRaises(v4.V4Stop):
                    await pending
        with db_session() as db:
            self.assertEqual(db.get(Invoice, 3).status, 'submitted')

    async def test_stop_during_mcp_call_start_prevents_external_effect(self):
        from fastmcp import FastMCP
        server = FastMCP('inert-systemutils')
        effects = []
        @server.tool
        async def run_diagnostics() -> dict:
            effects.append(True)
            return {'ok': True}
        chat = CoPilotAssistant(self.session)
        entered, release = asyncio.Event(), asyncio.Event()
        async def suspended_event(**kwargs):
            if kwargs.get('event_type') == 'mcp_tool_call_start':
                entered.set()
                await release.wait()
        with self.runtime.agent_scope(chat, {'vendor_id': 2}):
            provider = MCPToolProvider({'systemutils': server}, self.session)
            await provider.connect()
            try:
                with patch.object(event_bus, 'emit_agent_event', suspended_event):
                    pending = asyncio.create_task(provider.get_callables()['systemutils__run_diagnostics']())
                    await entered.wait()
                    with self.assertRaises(v4.V4Stop):
                        self.runtime.fail('concurrent_stop')
                    release.set()
                    with self.assertRaises(v4.V4Stop):
                        await pending
                self.assertEqual(effects, [])
            finally:
                await provider.disconnect()
