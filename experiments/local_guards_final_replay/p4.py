"""Validate stored requests and adapt their factual prefix for frozen P4 methods."""
import copy
import json
from pathlib import Path
from time import perf_counter

from experiments.local_guards_archive_annotation import score
from experiments.local_guards_archive_comparison import evaluation, methods, views
from experiments.local_guards_archive_comparison.collector import read_jsonl
from experiments.local_guards_archive_comparison.eliza import query_identity
from experiments.local_guards_v3 import rules_v3
from experiments.local_guards_v3.legacy import rules, rules_v2
from experiments.local_guards_v4.guard import guard as v4
from experiments.local_guards_v4_followup.guard import guard as v42

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE.parent / 'local_guards_archive_comparison'
ANNOTATION = HERE.parent / 'local_guards_archive_annotation'
ELIZA = ARCHIVE / 'results/eliza-run'
METHODS = ('v1', 'v2', 'v3', 'v4', 'v4.2', 'v4-payment', 'v4.2-payment')


def unique(rows, key):
    result = {}
    for row in rows:
        identity = row[key]
        if identity in result:
            raise ValueError(f'duplicate {key}: {identity}')
        result[identity] = row
    return result


def stored_requests(case_ids):
    mapping = unique((r for r in read_jsonl(ELIZA/'case-mapping.jsonl.gz')
                      if r['case_id'] in case_ids), 'case_id')
    queries = {r['query_id'] for r in mapping.values()}
    requests = unique((r for r in read_jsonl(ELIZA/'requests.jsonl.gz')
                       if r['query_id'] in queries), 'query_id')
    responses = unique((r for r in read_jsonl(ELIZA/'responses.jsonl.gz')
                        if r['query_id'] in queries), 'query_id')
    return mapping, requests, responses


def match_request(expected, case_id, saved, vectors):
    mapping, requests, responses = saved
    query = (mapping.get(case_id) or {}).get('query_id')
    if query not in requests or query not in responses:
        return None, 'saved_request_or_response_unavailable', query
    request = requests[query]['request']
    try:
        if query_identity(request) != query:
            raise ValueError('request identity')
        messages = request['messages']
        if [item['role'] for item in messages] != ['system', 'user']:
            raise ValueError('unexpected message roles')
        packet = json.loads(messages[1]['content'])
        payload = views.unpack_view(packet)
        if payload != expected:
            raise ValueError('packet differs from frozen action input')
        proposal = payload['raw_context']['proposed_action']
        if (payload['checkpoint'], proposal['source_event_kind'], proposal['tool_name']) != (
                'P4', 'before_tool_hook', 'finstripe__create_transfer'):
            raise ValueError('not actual P4')
        if proposal['event_seq'] != payload['event_seq']:
            raise ValueError('proposal sequence mismatch')
        response = responses[query]
        if not response['parsed'] or response['decision'] != vectors[case_id]['decision']:
            raise ValueError('stored response mismatch')
    except (KeyError, ValueError, IndexError, TypeError) as exc:
        return None, f'invalid_saved_pair:{exc}', query
    return payload, None, query


def tool_result_ok(event, value):
    return (not event.get('error') and isinstance(value, dict)
            and not value.get('error') and value.get('is_error') is not True
            and value.get('success') is not False and value.get('updated') is not False
            and all(value.get(key) is None or isinstance(value[key], str) and value[key] not in ('failed', 'error')
                    for key in ('status', 'task_status')))


def legacy_prefix(row):
    """Build the original v1/v2 input; preserve the original initial-account contract."""
    raw = row['raw_context']
    initial = evaluation.legacy_initial_state(row)
    invoice, vendor = initial.get('invoice') or {}, initial.get('vendor') or {}
    proposal = row['observation']['proposal']
    context = row['observation']['context']
    status = methods.evidenced(row, 'facts.invoice_status')
    missing = [f'invoice.{name}' for name in ('amount', 'description') if invoice.get(name) is None]
    missing += [f'vendor.{name}' for name in ('status', 'trust_level', 'risk_level', 'bank_account_number')
                if vendor.get(name) is None]
    for section, fields in (('invoice', invoice), ('vendor', vendor)):
        actual = fields.get('id', fields.get(section+'_id'))
        if actual is not None and methods.equality(actual, context.get(section+'_id')) is not True:
            missing.append(f'{section}.subject_mismatch')
    if not isinstance(initial.get('transactions'), list):
        missing.append('initial_transactions')
    if methods.evidenced(row, 'context.prefix_complete') is not True:
        missing.append('complete_raw_prefix')
    if status is None:
        missing.append('current_invoice_status')
    missing += [f'proposal.{key}' for key in ('amount', 'vendor_account_token') if proposal.get(key) is None]
    if missing:
        return None, [], missing

    transactions = copy.deepcopy(initial['transactions'])
    current_invoice, current_vendor = dict(invoice), dict(vendor)
    prior = []
    previous = -1
    for event in raw['events']:
        seq = event.get('event_seq')
        if type(seq) is not int or not previous <= seq < row['event_seq']:
            return None, [], ['future_or_invalid_raw_event']
        previous = seq
        tool = str(event.get('tool_name') or '').split('__')[-1]
        args = event.get('tool_arguments') or {}
        if (event.get('hook_kind') == 'before_tool' and tool.startswith('delegate_to_')
                and event.get('source_event_kind') != 'recorded_model_proposal' and isinstance(args, dict)):
            prior.append(dict(seq=seq, kind='delegation', task_description=args.get('task_description')))
        if event.get('hook_kind') != 'after_tool':
            continue
        value = methods._result(event.get('tool_result'))
        good = tool_result_ok(event, value)
        source = event.get('tool_source')
        # The original constructor treats any observed Fraud summary as a
        # completed review; the frozen v2 default retains that legacy contract.
        if tool.startswith('delegate_to_') and isinstance(value, dict):
            prior.append(dict(seq=seq, kind='summary', agent=tool[len('delegate_to_'):]+'_agent',
                              task_status=value.get('task_status'), task_summary=value.get('task_summary')))
        else:
            # The native hook source is an execution property, not text in a model message.
            prior.append(dict(seq=seq, kind='tool', source=source or 'unverified', name=tool,
                              arguments=args, output=value, error=None if good else 'unverified_or_failed_result'))
        if good and source == 'native' and isinstance(args, dict):
            if tool in ('get_invoice_details', 'get_invoice_for_payment', 'update_invoice_status', 'update_invoice_agent_notes'):
                if methods.equality(args.get('invoice_id'), context.get('invoice_id')) is True:
                    actual = value.get('invoice_id', value.get('id', args['invoice_id']))
                    if methods.equality(actual, args['invoice_id']) is True:
                        current_invoice.update({k: value[k] for k in ('agent_notes',) if k in value})
            if tool in ('get_vendor_details', 'update_vendor_status', 'update_vendor_risk', 'update_vendor_agent_notes'):
                if methods.equality(args.get('vendor_id'), context.get('vendor_id')) is True:
                    actual = value.get('vendor_id', value.get('id', args['vendor_id']))
                    if methods.equality(actual, args['vendor_id']) is True:
                        current_vendor.update({k: value[k] for k in ('risk_level', 'agent_notes') if k in value})
        if tool == 'create_transfer':
            if not good and not (event.get('error') or isinstance(value,dict) and
                                 (value.get('error') or value.get('success') is False or value.get('is_error') is True)):
                return None, [], ['unresolved_prior_transfer']
            if good:
                transfer = value.get('transfer', value)
                if not isinstance(transfer, dict) or transfer.get('status') not in ('completed', 'failed'):
                    return None, [], ['unresolved_prior_transfer']
                if transfer['status'] == 'completed':
                    transactions.append(transfer)
        if 'systemutils' in str(source).casefold() or 'systemutils' in str(event.get('tool_name')).casefold():
            return None, [], ['unresolved_database_effect']
    current_invoice['status'] = status
    cut = dict(seq=row['event_seq']+1, point='P4.finstripe__create_transfer',
               db_snapshot=dict(invoice=current_invoice, vendor=current_vendor, transactions=transactions),
               payload=dict(tool='finstripe__create_transfer',
                            arguments=dict(amount=proposal['amount'], vendor_account=proposal['vendor_account_token'])))
    try:
        result = evaluation._original_builder()(initial, cut, prior, {})['state']
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, [], ['original_constructor_input_unavailable']
    return result, prior, []


def legacy_diagnostics(row):
    """Availability of operands only; this path emits no partial verdict."""
    initial = evaluation.legacy_initial_state(row)
    invoice, vendor = initial.get('invoice') or {}, initial.get('vendor') or {}
    proposal = row['observation']['proposal']
    return {
        'initial_amount': invoice.get('amount') is not None,
        'initial_vendor_status': vendor.get('status') is not None,
        'current_invoice_status': methods.evidenced(row, 'facts.invoice_status') is not None,
        'proposed_amount': proposal.get('amount') is not None,
        'recipient_comparison': bool(vendor.get('bank_account_number') and proposal.get('vendor_account_token')),
        'prior_transaction_list': isinstance(initial.get('transactions'), list),
        'fraud_review': methods.evidenced(row, 'facts.fraud_delegate_completed') is not None,
        'complete_prefix': methods.evidenced(row, 'context.prefix_complete') is True,
    }


def predict(row, metadata, *, conditional=False):
    from .projection import project, v4_only

    records = {}
    if row['checkpoint'] == 'P4' and not conditional:
        start = perf_counter()
        state, prior, missing = legacy_prefix(row)
        availability = legacy_diagnostics(row)
        ready = perf_counter()
        for name in ('v1','v2'):
            decision_start = perf_counter()
            issues = [] if missing else (rules.violations(state) if name == 'v1'
                       else rules_v2.violations(rules_v2.enrich_state(state, prior)))
            records[name] = dict(decision=None if missing else 'BLOCK' if issues else 'ALLOW',
                                 adapter_applicable=not missing, reasons=missing or issues,
                                 operand_coverage=availability,
                                 adapter_ms=(ready-start)*1000,
                                 decision_ms=None if missing else (perf_counter()-decision_start)*1000)
    start = perf_counter()
    old, modern, provenance = project(row, metadata, conditional=conditional)
    ready = perf_counter()
    for name in METHODS[2:]:
        if row['checkpoint'] != 'P4' and name not in ('v4', 'v4.2'):
            continue
        if conditional and name == 'v3':
            continue
        started = perf_counter()
        policy = {'profile':'A', 'enabled_requirements':['A08']} if name.endswith('-payment') else 'A'
        if name == 'v3':
            result = rules_v3.guard(old)
        elif name.startswith('v4.2'):
            result = v42(modern, policy)
        else:
            result = v4(v4_only(modern), policy)
        records[name] = dict(result, adapter_applicable=True,
                             adapter_ms=(ready-start)*1000, decision_ms=(perf_counter()-started)*1000)
    return records, provenance
