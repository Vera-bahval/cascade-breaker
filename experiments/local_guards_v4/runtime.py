"""Opt-in trusted native adapter. Sidecar evidence is not source-DB atomicity.

No summary/text parsing. Currency and initial typed state exist only when an
explicit local fixture contract is supplied. The default native profile leaves
unavailable business facts unknown. No new inference client or dependency.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from decimal import Decimal
from functools import wraps
import hashlib
import json
import time
from uuid import uuid4

from finbot.probe import v4
from .guard import guard
from .store import ClaimConflict, EvidenceStore

_ACTOR = ContextVar('v4_concrete_actor', default=None)
_INVOKING = ContextVar('v4_invoking_tool', default=None)
_PENDING = ContextVar('v4_admitted_background', default=None)


def technical_actor(agent):
    # Class identity, never agent_name, model role claims or class-name strings.
    from finbot.agents.chat import VendorChatAssistant, CoPilotAssistant
    from finbot.agents.orchestrator import OrchestratorAgent
    from finbot.agents.specialized.onboarding import VendorOnboardingAgent
    from finbot.agents.specialized.invoice import InvoiceAgent
    from finbot.agents.specialized.fraud import FraudComplianceAgent
    from finbot.agents.specialized.payments import PaymentsAgent
    from finbot.agents.specialized.communication import CommunicationAgent
    return {VendorChatAssistant: 'vendor_chat', CoPilotAssistant: 'admin_chat',
            OrchestratorAgent: 'orchestrator', VendorOnboardingAgent: 'onboarding',
            InvoiceAgent: 'invoice', FraudComplianceAgent: 'fraud',
            PaymentsAgent: 'payments', CommunicationAgent: 'communication'}.get(type(agent))


class Runtime:
    def __init__(self, path, profile='A', *, fixture_contract=None, owner=None):
        if profile not in {'A', 'B'}:
            raise ValueError('profile must be A or B')
        self.store = EvidenceStore(path)
        self.profile = profile
        self.fixture = deepcopy(fixture_contract or {})
        self.currency = self.fixture.get('invoice_currency')
        self.owner = owner or 'v4_' + uuid4().hex
        self.session = None
        self.envelope = None
        self.origin_portal = None
        self.local_stop = None
        self.decisions = []
        self.admitted = False
        self.agent_executions = {}
        self.fixture_seq = 0
        self.initial_versions = None

    def tick(self):
        return time.time_ns()

    @contextmanager
    def open(self):
        token = v4._CURRENT.set(self)
        try:
            self.raise_if_stopped()
            yield self
        finally:
            v4._CURRENT.reset(token)

    def fail(self, reason):
        result = dict(decision='UNKNOWN', reasons=[reason], stop=True,
                      evidence=[], timing_ms=0., requirements=[])
        self.stop(result)

    def stop(self, result):
        self.local_stop = self.local_stop or result
        try:
            self.store.mark_stop(self.owner, result['decision'], result['reasons'])
            if self.admitted:
                self.store.release_claim(self.owner, known_outcome=False)
        except Exception:
            pass  # A broken journal must not make an already-known STOP recoverable.
        raise v4.V4Stop(self.local_stop)

    def raise_if_stopped(self):
        if self.local_stop:
            raise v4.V4Stop(self.local_stop)
        try:
            result = self.store.stopped(self.owner)
        except Exception:
            self.fail('journal_unavailable')
        if result:
            self.local_stop = result
            raise v4.V4Stop(result)

    def initialize(self, session, task_data):
        if self.session is not None:
            if session.session_id != self.session.session_id or session.namespace != self.session.namespace:
                self.fail('session_context_changed')
            return
        self.session = deepcopy(session)
        self.origin_portal = session.portal_type
        self.envelope = {key: deepcopy(task_data.get(key)) for key in ('vendor_id', 'invoice_id')}
        self.envelope['attachment_file_ids'] = deepcopy(task_data.get('attachment_file_ids', []))
        # Resolve invoice relation from the current native database, never summary JSON.
        if self.envelope['invoice_id'] is not None and self.envelope['vendor_id'] is None:
            from finbot.core.data.database import db_session
            from finbot.core.data.repositories import InvoiceRepository
            with db_session() as db:
                invoice = InvoiceRepository(db, self.session).get_invoice(self.envelope['invoice_id'])
                if invoice:
                    self.envelope['vendor_id'] = invoice.vendor_id

    def acquire(self):
        if self.profile == 'B' and not self.admitted:
            try:
                self.store.acquire_claim(self.session.namespace, self.envelope['vendor_id'],
                    self.envelope['invoice_id'], self.owner, self.tick())
            except ClaimConflict:
                self.stop(dict(decision='BLOCK', reasons=['B02:violated', 'workflow_claim_conflict'],
                    stop=True, evidence=[], timing_ms=0., requirements=[{'id': 'B02', 'state': 'violated'}]))
            except Exception:
                self.fail('workflow_claim_unavailable')
            self.admitted = True

    @contextmanager
    def agent_scope(self, agent, task_data):
        try:
            self.initialize(agent.session_context, task_data)
            actor = technical_actor(agent)
            chat = actor in {'vendor_chat', 'admin_chat'}
            if not chat:
                self.acquire()
            self.agent_executions.setdefault(agent, uuid4().hex)
            token = _ACTOR.set(agent)
            try:
                with self.open():
                    self.check('P0', agent, None, task_data)
                    yield self
            finally:
                _ACTOR.reset(token)
        except v4.V4Stop:
            raise
        except Exception:
            self.fail('entry_verifier_exception')

    def _put(self, obj, key, value, source='native_tool', operation='native_snapshot', **extra):
        if value is None:
            return
        ctx = obj['context']
        proof = {key: ctx.get(key) for key in ('namespace', 'session_id', 'workflow_id',
            'vendor_id', 'invoice_id', 'invoice_version', 'vendor_version', 'call_id')}
        proof.update(source=source, operation=operation, event_seq=obj['event_seq'] - 1,
                     subject_matches=True, record_id=uuid4().hex, value=value)
        proof.update(extra)
        obj['facts'][key] = value
        obj['provenance'].setdefault(key, []).append(proof)

    def snapshot(self, checkpoint, agent, tool, arguments, **extra_context):
        from finbot.core.data.database import db_session
        from finbot.core.data.repositories import InvoiceRepository, VendorRepository
        from finbot.mcp.servers.finstripe.repositories import PaymentTransactionRepository
        from finbot.mcp.servers.findrive.repositories import FinDriveFileRepository
        args = arguments or {}
        env = self.envelope
        invoice_id = args.get('invoice_id', env['invoice_id'])
        vendor_id = args.get('vendor_id', env['vendor_id'])
        attachments = args.get('attachment_file_ids', env['attachment_file_ids'])
        if 'file_id' in args:
            attachments = [args['file_id']]
        actor = technical_actor(agent)
        is_chat = actor in {'vendor_chat', 'admin_chat'}
        if is_chat and invoice_id is not None and 'vendor_id' not in args:
            with db_session() as db:
                referenced = InvoiceRepository(db, self.session).get_invoice(invoice_id)
                if referenced:
                    vendor_id = referenced.vendor_id
        ctx = dict(record_id=uuid4().hex, session_id=self.session.session_id,
                   user_id=self.session.user_id, namespace=self.session.namespace,
                   workflow_id=None if is_chat and tool != 'start_workflow' else self.owner,
                   parent_workflow_id=None, origin_portal=self.origin_portal,
                   technical_actor=actor, current_vendor_id=self.session.current_vendor_id,
                   vendor_id=vendor_id, invoice_id=invoice_id,
                   attachment_file_ids=attachments, call_id=uuid4().hex,
                   invoice_version=None, vendor_version=None, account_ref=None,
                   payment_reference=args.get('payment_reference'))
        ctx.update(extra_context)
        proposal = {'tool': tool} if tool else {}
        for key in ('amount', 'currency', 'trust_level', 'risk_level'):
            if key in args:
                proposal[key] = str(args[key])
        if tool == 'finstripe__create_transfer':
            proposal['currency'] = str(args.get('currency', 'usd'))
        if tool in {'update_invoice_status', 'update_vendor_status'} and 'status' in args:
            proposal['target_status'] = args['status']
        obj = dict(schema_version=4, checkpoint=checkpoint, event_seq=self.tick(),
                   context=ctx, proposal=proposal, facts={}, provenance={})
        with db_session() as db:
            invoice = InvoiceRepository(db, self.session).get_invoice(invoice_id) if invoice_id is not None else None
            vendor = VendorRepository(db, self.session).get_vendor(vendor_id) if vendor_id is not None else None
            if invoice and vendor:
                account = vendor.bank_account_number
                ctx['account_ref'] = hashlib.sha256(str(account).encode()).hexdigest()
                if self.currency:
                    ctx.update(self.store.material_state(self.session.namespace, invoice.id,
                        vendor.id, str(invoice.amount), self.currency, ctx['account_ref'], obj['event_seq']))
                    ctx['approval'] = self.store.approval(ctx)
            # Preserve native same-namespace cross-vendor reads; selection is a prompt-only restriction.
            self._put(obj, 'session_valid', self.session.is_valid(), 'server_context', 'session_validate')
            if vendor_id is not None:
                self._put(obj, 'vendor_in_scope', vendor is not None, 'server_context')
            if invoice_id is not None:
                self._put(obj, 'invoice_in_scope', invoice is not None, 'server_context')
            if invoice_id is not None and vendor_id is not None:
                self._put(obj, 'invoice_vendor_matches', bool(invoice and invoice.vendor_id == vendor_id), 'server_context')
            if attachments:
                files = [FinDriveFileRepository(db, self.session).get_file(key) for key in attachments]
                self._put(obj, 'attachments_in_scope', all(f and (self.origin_portal == 'admin' or f.vendor_id is not None) for f in files), 'server_context')
            scope = (env['vendor_id'] is None or vendor_id == env['vendor_id']) and (env['invoice_id'] is None or invoice_id == env['invoice_id'])
            scope = scope and (not attachments or not env['attachment_file_ids'] or set(attachments) <= set(env['attachment_file_ids']))
            self._put(obj, 'tool_scope_matches', bool(scope or is_chat), 'server_context')
            if vendor:
                self._put(obj, 'vendor_status', vendor.status)
            if invoice:
                self._put(obj, 'invoice_status', invoice.status)
                self._put(obj, 'invoice_amount', str(invoice.amount))
                self._put(obj, 'invoice_currency', self.currency, 'initial_fixture', 'declared_currency_contract')
                if 'amount' in args:
                    self._put(obj, 'amount_matches_invoice', Decimal(str(args['amount'])) == Decimal(str(invoice.amount)), 'server_context')
                if tool == 'finstripe__create_transfer' and vendor:
                    self._put(obj, 'recipient_matches_authorized', args.get('vendor_account') == vendor.bank_account_number, 'server_context')
                transactions = PaymentTransactionRepository(db, self.session).list_for_invoice(invoice.id)
                completed = [row for row in transactions if row.status == 'completed']
                self._put(obj, 'prior_completed_transfers', len(completed))
                if tool == 'process_payment':
                    retained = [event['payload'] for event in self.store.events(self.subject_key(invoice_id, vendor_id)) if event['kind'] == 'completed_transfer']
                    def matches(item):
                        a = item['arguments']
                        return (item['reference'] == args.get('payment_reference') and
                            a.get('invoice_id') == invoice.id and a.get('vendor_id') == vendor_id and
                            Decimal(str(a.get('amount'))) == Decimal(str(invoice.amount)) and
                            a.get('currency', 'usd').upper() == self.currency and vendor and
                            a.get('vendor_account') == vendor.bank_account_number)
                    self._put(obj, 'payment_reference_matches_transfer', bool(len(completed) == 1 and
                        completed[0].transfer_id == args.get('payment_reference') and
                        completed[0].vendor_id == vendor_id and
                        Decimal(str(completed[0].amount)) == Decimal(str(invoice.amount)) and
                        completed[0].currency.upper() == self.currency and
                        any(matches(item) for item in retained)))
        if self.profile == 'B' and (not is_chat or tool == 'start_workflow'):
            ctx['claim'] = self.store.claim(self.owner)
        if checkpoint == 'P2':
            self._put(obj, 'delegation_subject_matches', bool(_INVOKING.get()), 'server_context')
        if self.initial_versions is None and ctx.get('invoice_version'):
            self.initial_versions = {key: ctx[key] for key in ('invoice_version', 'vendor_version')}
        # Fixture facts are a declared independent experiment producer, not a model return.
        for key in ('binding_hold', 'fraud_review_completed', 'human_approved', 'human_cleared'):
            if key in self.fixture:
                self._put(obj, key, self.fixture[key],
                    'independent_registry' if key.startswith('human_') else 'initial_fixture',
                    'declared_fixture_contract', event_seq=self.fixture_seq, **(self.initial_versions or {}))
        for event in self.store.events(self.subject_key(invoice_id, vendor_id)):
            payload = event['payload']
            if event['kind'] == 'typed_fact' and payload['context'].get('invoice_id') == invoice_id and payload['context'].get('vendor_id') == vendor_id:
                # Preserve original versions. A newer summary cannot clear HOLD.
                original = payload['context']
                self._put(obj, payload['key'], payload['value'], 'native_tool', payload['operation'],
                    invoice_version=original.get('invoice_version'), vendor_version=original.get('vendor_version'),
                    event_seq=event['seq'], record_id=payload['record_id'])
        return obj

    def check(self, checkpoint, agent, tool, arguments, **extra):
        self.raise_if_stopped()
        try:
            obj = self.snapshot(checkpoint, agent, tool, arguments, **extra)
            result = guard(obj, self.profile)
            self.decisions.append({'checkpoint': checkpoint, 'tool': tool, **result})
            if result['stop']:
                self.stop(result)
            return obj
        except v4.V4Stop:
            raise
        except Exception:
            self.fail('verifier_exception')

    def typed_fact(self, obj, key, value, operation):
        self.store.record_event(self.subject_key(obj['context']['invoice_id'], obj['context']['vendor_id']), 'typed_fact', dict(key=key, value=value,
            operation=operation, context=obj['context'], record_id=uuid4().hex), self.tick())

    async def invoke(self, agent, name, arguments, execute):
        self.raise_if_stopped()
        try:
            if name == 'start_workflow':
                child = self.fork_workflow(self.session, arguments, 'v4_' + uuid4().hex)
                token = _PENDING.set(child)
                try:
                    child.check('P1', agent, name, arguments)
                    return await execute()
                finally:
                    _PENDING.reset(token)
            obj = self.check('P1', agent, name, arguments)
            if name in {'update_invoice_status', 'update_vendor_status', 'update_vendor_risk', 'flag_invoice_for_review', 'process_payment'}:
                obj = self.check('P3', agent, name, arguments)
            if name == 'finstripe__create_transfer':
                obj = self.check('P4', agent, name, arguments)
            token = _INVOKING.set((agent, name, arguments, obj))
            try:
                result = await execute()
            finally:
                _INVOKING.reset(token)
            self.raise_if_stopped()
            original_result = result
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except (ValueError, TypeError):
                    pass
            if isinstance(result, dict) and result.get('error'):
                self.fail('native_tool_error')
            if isinstance(result, dict):
                if technical_actor(agent) == 'fraud':
                    subject = self.subject_key(obj['context']['invoice_id'], obj['context']['vendor_id'])
                    execution = self.agent_executions.get(agent)
                    if name in {'get_invoice_details', 'get_vendor_risk_profile'}:
                        # Typed same-invoice native reads plus successful completion are
                        # required. Vendor aggregates or task summaries alone are insufficient.
                        self.store.record_event(subject, 'fraud_review_read', dict(tool=name,
                            actor_execution=execution, context=obj['context']), self.tick())
                    if name == 'complete_task' and result.get('task_status') == 'success':
                        reads = {e['payload']['tool'] for e in self.store.events(subject)
                            if e['kind'] == 'fraud_review_read' and execution is not None and
                            e['payload'].get('actor_execution') == execution and
                            all(e['payload']['context'].get(k) == obj['context'].get(k)
                                for k in ('invoice_id', 'vendor_id', 'invoice_version', 'vendor_version'))}
                        if obj['context'].get('invoice_id') is not None and reads >= {'get_invoice_details', 'get_vendor_risk_profile'}:
                            self.typed_fact(obj, 'fraud_review_completed', True, 'typed_invoice_and_vendor_review_completed')
                if name == 'flag_invoice_for_review' and result.get('recommended_action') in {'hold', 'escalate', 'reject'}:
                    self.typed_fact(obj, 'binding_hold', True, name)
                    self.typed_fact(obj, 'fraud_review_completed', True, name)
                if name == 'update_invoice_status' and arguments.get('status') == 'approved' and result.get('status') == 'approved' and self.currency:
                    fresh = self.snapshot('P3', agent, name, arguments)
                    self.store.bind_approval(fresh['context'], fresh['facts']['invoice_amount'], self.currency, self.tick())
                if name == 'finstripe__create_transfer' and result.get('status') == 'completed' and result.get('transfer_id'):
                    self.store.record_event(self.subject_key(obj['context']['invoice_id'], obj['context']['vendor_id']), 'completed_transfer', dict(arguments=arguments, reference=result['transfer_id']), self.tick())
            return original_result
        except v4.V4Stop as error:
            if not self.local_stop:
                self.stop(error.decision)
            raise
        except Exception:
            self.fail('tool_outcome_or_journal_uncertain')

    def wrap_callables(self, agent, callables):
        def wrap(name, function):
            @wraps(function)
            async def call(**arguments):
                return await self.invoke(agent, name, arguments, lambda: function(**arguments))
            return call
        return {name: wrap(name, function) for name, function in callables.items()}

    async def invoke_mcp(self, provider, name, arguments, execute):
        self.raise_if_stopped()
        info = provider._tools.get(name)
        if not info or provider._tool_server_map.get(name) != info.get('server_name'):
            self.fail('mcp_callable_not_registered')
        current = _INVOKING.get()
        if current and current[1] == name:
            self.raise_if_stopped()
            return await execute()
        agent = _ACTOR.get()
        if agent is None or provider._session_context.session_id != self.session.session_id:
            self.fail('mcp_actor_or_session_unavailable')
        return await self.invoke(agent, name, arguments, execute)

    def child_complete(self, agent, result):
        parent = _INVOKING.get()
        if parent and parent[1].startswith('delegate_to_'):
            source, name, args, obj = parent
            self.store.record_event(self.owner, 'technical_delegation', dict(
                actor=technical_actor(agent), succeeded=result.get('task_status') == 'success',
                parent_call_id=obj['context']['call_id'], context=obj['context']), self.tick())
            self.check('P2', source, name, args,
                delegated_actor=technical_actor(agent), delegation_succeeded=result.get('task_status') == 'success',
                delegation_call_id=obj['context']['call_id'])
        elif self.admitted:
            self.store.release_claim(self.owner, known_outcome=result.get('task_status') == 'success')

    def fork_workflow(self, session, task_data, owner):
        child = Runtime(self.store.path, self.profile, fixture_contract=self.fixture, owner=owner)
        child.initialize(session, task_data)
        child.acquire()
        return child

    def subject_key(self, invoice_id, vendor_id):
        return json.dumps(['subject', self.session.namespace, vendor_id, invoice_id])

    def pending_workflow(self):
        child = _PENDING.get()
        if child is None:
            self.fail('workflow_not_admitted_before_scheduling')
        self.raise_if_stopped()
        return child

    def is_invoking(self, agent, name):
        invocation = _INVOKING.get()
        return bool(invocation and invocation[0] is agent and invocation[1] == name)
