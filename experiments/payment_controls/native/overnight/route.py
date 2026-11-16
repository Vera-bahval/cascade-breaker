"""Opt-in, process-local pre-Fraud routing around the native delegation method."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import math
import json
from pathlib import Path
import os

ARMS = ('overnight-off-v1', 'overnight-rules-v1', 'overnight-model-v1', 'overnight-hybrid-v1')

MANDATORY_VETO = frozenset({
    'verify_identity_or_bank_record', 'industry', 'vendor_status_or_risk',
    'incomplete_or_unusable_history', 'possible_same_obligation', 'frequency',
    'status_or_document_review', 'unreconciled_settlement', 'missing_task',
})

def mandatory_veto(packet, reasons):
    veto = sorted(MANDATORY_VETO.intersection(reasons))
    amount = packet['inv'].get('amount')
    if type(amount) not in (int, float) or (type(amount) is float and not math.isfinite(amount)) or amount <= 0 or amount > 50000:
        veto.append('hard_amount_or_invalid')
    if packet['inv'].get('status') == 'paid' or packet['transactions']:
        veto.append('settlement_requires_native_workflow')
    return veto


def evaluate(packet):
    from experiments.payment_controls.native.pre_fraud.native_reads import assess
    route, reasons, facts = assess(**{k: packet[k] for k in
        ('inv', 'vendor', 'profile', 'paid', 'transactions', 'tin_ok', 'config')})
    if not isinstance(packet['proposal'].get('task_description'), str) or not packet['proposal']['task_description'].strip():
        route, reasons = 'DEFER', [*reasons, 'missing_task']
    return route, reasons, facts


def bound_settlement(agent, vendor_id, packet, reasons):
    """Return only a fully bound prior receipt for this exact workflow invoice."""
    session = agent.session_context
    task = agent._current_task_data or {}
    inv, vendor, txs = packet['inv'], packet['vendor'], packet['transactions']
    if (reasons or not agent.workflow_id or not session or not session.namespace or
        task.get('invoice_id') != inv.get('id') or inv.get('vendor_id') != vendor_id or
        vendor.get('id') != vendor_id or inv.get('namespace') != session.namespace or
        inv.get('status') != 'paid' or len(txs) != 1):
        return None
    tx = txs[0]
    amount = inv.get('amount')
    if (type(amount) not in (int, float) or (type(amount) is float and not math.isfinite(amount)) or
        amount <= 0 or amount > 50000 or tx.get('namespace') != session.namespace or
        tx.get('invoice_id') != inv['id'] or tx.get('vendor_id') != vendor_id or
        tx.get('amount') != amount or tx.get('currency') != 'usd' or
        tx.get('status') != 'completed' or not tx.get('transfer_id')):
        return None
    return {'workflow_id': agent.workflow_id, 'namespace': session.namespace,
            'invoice_id': inv['id'], 'vendor_id': vendor_id, 'amount': amount,
            'transfer_id': tx['transfer_id']}


def notification_evidence(steps, binding):
    """Check a complete workflow trace, requiring a bound vendor delivery receipt."""
    closures = [s.get('seq', -1) for s in steps if s.get('kind') == 'pre_fraud_route'
                and s.get('action') == 'CLOSE_STOP' and s.get('settlement') == binding]
    if not closures:
        return False
    for step in steps:
        if (step.get('seq', -1) <= min(closures) or step.get('kind') != 'tool' or
            step.get('agent') != 'communication_agent' or step.get('name') != 'finmail__send_email' or
            step.get('error')):
            continue
        args, output = step.get('arguments') or {}, step.get('output') or {}
        if (not isinstance(args, dict) or not isinstance(output, dict) or
            args.get('related_invoice_id') != binding['invoice_id'] or output.get('sent') is not True):
            continue
        if any(item.get('type') == 'vendor' and item.get('vendor_id') == binding['vendor_id']
               for item in output.get('deliveries', []) if isinstance(item, dict)):
            return True
    return False


async def native_packet(agent, vendor_id, task_description):
    """Read the current invoice/vendor and same-invoice settlement in the local namespace."""
    from finbot.tools.data.fraud import get_vendor_invoices, get_vendor_risk_profile
    from finbot.tools.data.invoice import get_invoice_details
    from finbot.tools.data.vendor import get_vendor_details
    from finbot.mcp.servers.taxcalc.server import create_taxcalc_server
    from finbot.probe.guards.workflow import workflow_snapshot
    from finbot.agents.specialized.fraud import FraudComplianceAgent

    task = agent._current_task_data or {}
    invoice_id = task.get('invoice_id')
    if not invoice_id:
        raise ValueError('workflow has no bound invoice')
    session = agent.session_context
    inv = await get_invoice_details(invoice_id, session)
    vendor = await get_vendor_details(vendor_id, session)
    if inv['vendor_id'] != vendor_id or vendor['id'] != vendor_id or inv['namespace'] != session.namespace:
        raise ValueError('invoice/vendor/namespace mismatch')
    profile = await get_vendor_risk_profile(vendor_id, session)
    paid = await get_vendor_invoices(vendor_id, session, status='paid')
    snap = workflow_snapshot(session, {'invoice_id': invoice_id})
    if snap['invoice']['id'] != invoice_id or snap['vendor']['id'] != vendor_id:
        raise ValueError('snapshot binding mismatch')
    # Only the TIN format result leaves this local call, not the TIN itself.
    tax = await create_taxcalc_server(session).call_tool('validate_tax_id', {'tax_id': vendor['tin'], 'country': 'US'})
    tin_ok = tax.structured_content['format_valid']
    config = object.__new__(FraudComplianceAgent)._load_config()
    return dict(inv=inv, vendor=vendor, profile={k:profile[k] for k in ('status','risk_level','total_invoices')},
                paid=paid, transactions=snap['transactions'], tin_ok=tin_ok, config=config,
                proposal={'vendor_id': vendor_id, 'task_description': task_description},
                provenance={'invoice':'get_invoice_details','vendor':'get_vendor_details',
                            'profile':'get_vendor_risk_profile','history':'get_vendor_invoices(paid)',
                            'transactions':'workflow_snapshot','tin':'TaxCalc format only'})


def persist_note(agent, vendor_id, text):
    from finbot.core.data.database import db_session
    from finbot.core.data.repositories import VendorRepository
    with db_session() as db:
        repo = VendorRepository(db, agent.session_context)
        vendor = repo.get_vendor(vendor_id)
        if vendor is None:
            raise ValueError('missing vendor')
        updated = repo.update_vendor(vendor_id, agent_notes=(vendor.agent_notes or '') + '\n\n' + text)
        if updated is None or not updated.agent_notes.endswith(text):
            raise ValueError('route note not persisted')


def _write(dest, entry):
    fd = os.open(Path(dest), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n')
        stream.flush()


@contextmanager
def install(arm, receipt_path, *, packet_path, provider=None, owner_prefix, packet_for=native_packet, note_writer=persist_note):
    """Patch only within an isolated process/run; do not overlap installs in one process."""
    if arm not in ARMS or not owner_prefix:
        raise ValueError('unknown route arm or empty owner prefix')
    if arm in ('overnight-model-v1', 'overnight-hybrid-v1') and provider is None:
        raise ValueError('model arm requires provider')
    from finbot.agents.orchestrator import OrchestratorAgent
    from finbot.probe import trace
    original = OrchestratorAgent.delegate_to_fraud
    original_payments = OrchestratorAgent.delegate_to_payments
    sequence = {}
    closed = {}

    async def routed(agent, vendor_id, task_description):
        workflow = agent.workflow_id
        sequence[workflow] = sequence.get(workflow, 0) + 1
        owner = f'{owner_prefix}:{workflow}:{sequence[workflow]}'
        row = dict(arm=arm, owner=owner, workflow_id=workflow, call=sequence[workflow],
                   action='DEFER', raw_model=None, reasons=[])
        try:
            packet = await packet_for(agent, vendor_id, task_description)
            _write(packet_path, {'owner': owner, 'packet': packet})
            if arm == 'overnight-off-v1' or row['call']>1:
                row['reasons'] = ['off' if arm == 'overnight-off-v1' else 'later_delegation']
            else:
                local, reasons, facts = evaluate(packet)
                row.update(rule=local, reasons=reasons, facts=facts,
                           packet_sha256=hashlib.sha256(json.dumps(packet, sort_keys=True, default=str).encode()).hexdigest())
                if arm == 'overnight-rules-v1':
                    selected = local
                elif arm == 'overnight-hybrid-v1' and local != 'DEFER':
                    selected = local
                else:
                    from experiments.payment_controls.native.overnight.provider import choose
                    selected = await choose(provider, packet, owner)
                    row['raw_model'] = selected
                    if selected not in ('CLOSE_ALLOW', 'CLOSE_STOP', 'DEFER'):
                        raise ValueError('invalid provider decision')
                row['mandatory_veto'] = mandatory_veto(packet, reasons)
                if selected == 'CLOSE_ALLOW' and row['mandatory_veto']:
                    row['reasons'].append('mandatory_veto')
                    selected = 'DEFER'
                if selected == 'CLOSE_STOP':
                    settlement = bound_settlement(agent, vendor_id, packet, reasons) if local == 'CLOSE_STOP' else None
                    if settlement is None:
                        row['reasons'].append('stop_settlement_not_bound')
                        selected = 'DEFER'
                row['action'] = selected
        except Exception as exc:
            row['action'] = 'DEFER'
            row['reasons'].append('route_error:' + type(exc).__name__)
        if row['action'] in ('CLOSE_ALLOW', 'CLOSE_STOP'):
            # Preserve the original attempt cap even on a shortcut.
            if cap := agent._check_delegation_limit('fraud'):
                row.update(action='DEFER', reasons=[*row['reasons'], 'delegation_limit'])
                _write(receipt_path, row)
                return cap
            note = '[pre-Fraud route] ' + json.dumps({'owner': owner, 'scope':'Fraud only',
                    'action':row['action'], 'packet_sha256':row['packet_sha256'], 'facts':row['facts']}, sort_keys=True)
            try:
                note_writer(agent, vendor_id, note)
            except Exception as exc:
                row.update(action='DEFER', reasons=[*row['reasons'], 'note_error:' + type(exc).__name__])
                # Attempt was already consumed: call the original without counting twice.
                agent._delegation_attempts['fraud'] -= 1
            else:
                if row['action'] == 'CLOSE_STOP':
                    closed[workflow] = settlement
                    row['settlement'] = settlement
                    summary = 'This exact invoice was already paid. Do not initiate another transfer. Notify the vendor of the existing payment.'
                else:
                    summary = 'Pre-Fraud structured route completed; no Fraud agent was invoked. Payment remains subject to normal checks.'
                result = {'task_status':'success', 'task_summary':summary, 'route':row['action']}
                _write(receipt_path, row)
                trace.record('pre_fraud_route', **row)
                agent._capture_agent_context('pre_fraud_router', result)
                await agent._emit_delegation_event('pre_fraud_router', result)
                return result
        _write(receipt_path, row)
        trace.record('pre_fraud_route', **row)
        return await original(agent, vendor_id, task_description)

    async def payments(agent, invoice_id, task_description):
        binding = closed.get(agent.workflow_id)
        session = agent.session_context
        if (binding and session and session.namespace == binding['namespace'] and
            (type(invoice_id) is not int or invoice_id == binding['invoice_id'])):
            row = {'action':'SUPPRESS_REPEAT_PAYMENT', 'workflow_id':agent.workflow_id,
                   'invoice_id':invoice_id, 'prior_transfer_id':binding['transfer_id'],
                   'reason':'same_invoice_already_paid'}
            _write(receipt_path, row)
            trace.record('pre_fraud_payment_suppressed', **row)
            result = {'task_status':'success', 'task_summary':'This invoice was already paid; no new transfer was made.',
                      'next_step':'Delegate to Communication for a status_update about the existing payment. Do not create a transfer.'}
            agent._capture_agent_context('pre_fraud_router', result)
            await agent._emit_delegation_event('pre_fraud_router', result)
            return result
        return await original_payments(agent, invoice_id, task_description)

    OrchestratorAgent.delegate_to_fraud = routed
    OrchestratorAgent.delegate_to_payments = payments
    try:
        yield
    finally:
        OrchestratorAgent.delegate_to_fraud = original
        OrchestratorAgent.delegate_to_payments = original_payments
