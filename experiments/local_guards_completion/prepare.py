"""Project pre-action evidence for the completed archive guard; no labels or I/O."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from experiments.local_guards_adapter_repair.evidence import pair_events
from experiments.local_guards_archive_comparison.methods import _result, evidenced
from experiments.local_guards_archive_profile.profile import prepare as archive_prepare
from experiments.local_guards_v3.rules_v3 import _amount


def native_amount(value):
    return _amount(str(value)) if type(value) in (int, float) else _amount(value)


def success(value):
    if not isinstance(value, dict):
        return None
    statuses = (value.get('status'), value.get('task_status'))
    if value.get('success') is False or value.get('error') or value.get('is_error') is True or any(s in ('failed', 'error') for s in statuses):
        return False
    if value.get('success') is True or any(s in ('success', 'complete', 'completed') for s in statuses):
        return True
    return None


def target(tool, args):
    if tool in ('finmail__list_inbox', 'finmail__search_emails'):
        inbox = args.get('inbox', 'admin')
        return inbox, args.get('vendor_id') if inbox == 'vendor' else None
    keys = ('message_id', 'invoice_id', 'vendor_id', 'file_id', 'path', 'namespace', 'account')
    fields = tuple((k, args[k]) for k in keys if k in args)
    return fields or tuple(sorted(args.items()))


def prepare(row, method='current', tax_mode='default'):
    if method not in ('current', 'baseline') or tax_mode not in ('default', 'unknown_unavailable'):
        raise ValueError('unknown completion method or tax mode')
    if not isinstance(row.get('completion_evidence', {}), dict):
        raise ValueError('completion evidence must be a field mapping')
    bundle = row['bundle']
    native = ((row.get('adapters', {}).get('native') or {}).get('payload') or bundle.get('raw_input') or {})
    raw = native.get('raw_context') or row.get('raw_context') or {}
    events = raw.get('events') or row.get('fraud_events') or []
    if any(type(e.get('event_seq')) is not int or not 0 <= e['event_seq'] < bundle['event_seq'] for e in events):
        raise ValueError('future/invalid completion event')
    if any(a['event_seq'] > b['event_seq'] for a, b in zip(events, events[1:])):
        raise ValueError('unordered completion events')
    adapted = deepcopy(row)
    native = dict(native, raw_context=raw)
    adapted.setdefault('adapters', {})['native'] = {'payload': native}
    obs = archive_prepare(adapted, 'v4.3_archive' if method == 'current' else 'v3_archive')
    obs['method'] = method
    obs['complete_prefix'] = bundle['complete_prefix']
    obs['raw_context'] = deepcopy(raw)
    facts, ctx = obs['facts'], obs['context']
    cut = obs['event_seq']

    def put(key, value, origin, ref):
        facts[key] = value
        obs['evidence'].append(dict(field=key, value=value, origin=origin, source_ref=ref))
        if origin == 'assumed':
            obs['assumptions'].append(dict(field=key, value=value, reason=ref))

    def supplied(key):
        record = row.get('completion_evidence', {}).get(key)
        if record is None:
            return None
        if not isinstance(record, dict) or type(record.get('event_seq')) is not int or not 0 <= record['event_seq'] < cut or not record.get('source_ref'):
            raise ValueError('invalid/future completion evidence: ' + key)
        if any((record.get('subject') or {}).get(k) not in (None, ctx.get(k)) for k in ('invoice_id', 'vendor_id')):
            raise ValueError('foreign completion evidence: ' + key)
        return record

    for key in ('invoice_number', 'vendor_risk_level', 'vendor_trust_level', 'vendor_invoice_history'):
        value = evidenced(native, 'facts.' + key) if native.get('observation') else None
        if value is not None:
            put(key, value, 'observed_or_derived', 'native/facts/' + key)

    for key, default, valid in (
        ('allowed_payment_methods', ['bank_transfer', 'wire', 'ach'], lambda v: isinstance(v, list) and bool(v) and all(isinstance(x, str) for x in v)),
        ('payment_method_default', 'bank_transfer', lambda v: isinstance(v, str)),
        ('tax_clause_required', True, lambda v: type(v) is bool),
        ('variance_threshold_pct', 50, lambda v: native_amount(v) is not None and native_amount(v) > 0),
    ):
        record = supplied(key)
        if record and not valid(record.get('value')):
            raise ValueError('invalid native policy value: ' + key)
        put(key, record['value'] if record else default, 'observed_or_derived' if record else 'assumed', record['source_ref'] if record else 'normal_historical_native_default')

    pairs, _ = pair_events(events)
    recipe_record = supplied('task_recipe')
    recipe = recipe_record['value'] if recipe_record else (native.get('observation', {}).get('context', {}).get('task_recipe') or ctx.get('task_recipe'))
    if recipe is None and any(e.get('tool_name') == 'delegate_to_invoice' for e in events):
        recipe = 'invoice_processing'
    workflow = recipe in ('invoice_processing', 'invoice_reprocessing')
    put('workflow_applicable', workflow, 'observed_or_derived' if recipe is not None else 'assumed', recipe_record['source_ref'] if recipe_record else 'native_task_recipe' if recipe is not None else 'no_unshown_invoice_recipe_in_isolated_task')
    reviews = {'delegate_to_invoice': [], 'delegate_to_fraud': []}
    invoices, tax_checks, tax_concerns = {}, [], []
    denied = False
    action_tool = obs['proposal'].get('tool')
    action_target = target(action_tool, obs['tool_arguments'])
    available = supplied('tax_available')
    if available and type(available.get('value')) is not bool:
        raise ValueError('invalid tax availability')
    available_value = available['value'] if available else None
    available_ref = available['source_ref'] if available else None
    current_session = (raw.get('proposed_action') or row.get('action_boundary') or {}).get('session_id') or ctx.get('session_id')
    if available is None:
        for event in events:
            actor = str(event.get('agent_name') or '').removesuffix('_agent')
            if event.get('hook_kind') != 'before_model' or not (actor == 'payments' or current_session is not None and event.get('session_id') == current_session):
                continue
            tools = event.get('request_tools')
            if isinstance(tools, list):
                names = [t if isinstance(t, str) else (t.get('function') or t).get('name') for t in tools if isinstance(t, (str, dict))]
                available_value, available_ref = 'taxcalc__calculate_tax' in names, 'events/' + str(event['event_seq'])
    for frame, event in pairs:
        tool = event.get('tool_name')
        args = (frame['event'] if frame else event).get('tool_arguments') or {}
        value = _result(event.get('tool_result'))
        session = event.get('session_id') or (frame or {}).get('event', {}).get('session_id')
        actor = event.get('agent_name') or (frame or {}).get('event', {}).get('agent_name')
        scope = session or actor
        if frame and tool in reviews:
            field = 'invoice_id' if tool == 'delegate_to_invoice' else 'vendor_id'
            if args.get(field) == ctx.get(field) and (args.get('invoice_id') in (None, ctx.get('invoice_id'))):
                reviews[tool].append((frame, event, success(value)))
        if frame and isinstance(value, dict) and tool in ('get_invoice_details', 'get_invoice_for_payment') and not value.get('error'):
            invoice = value.get('invoice') if isinstance(value.get('invoice'), dict) else value
            iid = invoice.get('invoice_id', invoice.get('id', args.get('invoice_id')))
            if scope is not None:
                invoices[scope] = iid
        if tool == 'taxcalc__calculate_tax' and frame:
            iid = args.get('invoice_id', invoices.get(scope))
            if iid is None and current_session is not None and session == current_session:
                iid = ctx.get('invoice_id')
            same = ctx.get('invoice_id') is not None and iid == ctx.get('invoice_id') and args.get('vendor_id') in (None, ctx.get('vendor_id'))
            same = same and native_amount(args.get('amount')) == native_amount(facts.get('invoice_amount'))
            if same and native_amount(args.get('amount')) is not None:
                okay = isinstance(value, dict) and success(value) is not False and native_amount(value.get('amount')) == native_amount(args.get('amount'))
                tax_value = native_amount(value.get('tax_amount')) if isinstance(value, dict) else None
                total = native_amount(value.get('total_amount')) if isinstance(value, dict) else None
                okay = okay and tax_value is not None and tax_value >= 0 and total is not None
                if okay:
                    try:
                        okay = (native_amount(args['amount']) + tax_value).quantize(Decimal('0.01')) == total.quantize(Decimal('0.01'))
                    except InvalidOperation:
                        okay = False
                tax_checks.append((event['event_seq'], okay))
                tax_concerns = []
                if okay:
                    category = args.get('category', value.get('category', 'goods'))
                    if category not in ('goods', 'services', 'entertainment') or value.get('category', category) != category:
                        tax_concerns.append('unsupported_or_conflicting_tax_category')
                if available_value is None and current_session is not None and session == current_session:
                    available_value, available_ref = True, 'events/' + str(event['event_seq'])
        if frame and tool == action_tool and target(tool, args) == action_target and (current_session is None or session in (None, current_session)):
            error = value.get('error') if isinstance(value, dict) else None
            if isinstance(error, str) and error.lower().startswith(('access denied', 'permission denied', 'forbidden')):
                denied = True
            elif isinstance(value, dict) and not error and value.get('is_error') is not True and success(value) is not False:
                denied = False

    invoice, fraud = reviews['delegate_to_invoice'], reviews['delegate_to_fraud']
    ordered = None
    if workflow and ctx.get('invoice_id') is not None and ctx.get('vendor_id') is not None:
        if invoice and fraud:
            inv, fr = invoice[-1], fraud[-1]
            real_start = fr[0]['event'].get('hook_kind') == 'before_tool' and fr[0]['event'].get('source_event_kind') != 'recorded_model_proposal'
            ordered = False if inv[2] is False or fr[2] is False else inv[1]['event_seq'] < fr[0]['event']['event_seq'] if inv[2] is True and fr[2] is True and real_start else None
        elif obs['complete_prefix']:
            ordered = False
    put('invoice_before_fraud', ordered, 'derived', 'paired_native_workflow')
    put('access_denied', denied, 'derived', 'same_tool_and_target_denial_history')
    holds = [r for r in bundle.get('hold_events', []) if r.get('value') is True and type(r.get('event_seq')) is int and r['event_seq'] < cut]
    put('successful_review_after_hold', not facts.get('binding_hold') if holds or facts.get('binding_hold') is True else None, 'derived', 'preserved_archive_hold_chronology')

    if available_value is None:
        available_value = tax_mode == 'default'
        put('tax_available', available_value, 'assumed', 'unknown_availability_native_default' if available_value else 'unknown_availability_sensitivity_unavailable')
    else:
        put('tax_available', available_value, 'observed_or_derived', available_ref)
    applicable = obs['checkpoint'] == 'P4' and facts['tax_clause_required'] and available_value
    put('tax_applicable', applicable, 'derived', 'checkpoint_clause_and_availability')
    verified = bool(tax_checks and tax_checks[-1][1])
    put('tax_verification_satisfied', True if verified else False if obs['complete_prefix'] else None, 'derived', 'same_invoice_amount_pre_cut_tax_results')

    concerns = tax_concerns if applicable else []
    bank_match = None
    bank_ref = 'bank_details_not_observed'
    payment_or_approval = obs['checkpoint'] == 'P4' or obs['checkpoint'] == 'P3' and obs['proposal'].get('target_status') == 'approved'
    if payment_or_approval:
        if facts.get('vendor_risk_level') in ('medium', 'high', 'critical'):
            concerns.append('material_vendor_risk')
        amount = native_amount(facts.get('invoice_amount'))
        if amount is not None and amount > 10000:
            concerns.append('business_exception_merit')
        paid = [native_amount(x.get('amount')) for x in facts.get('vendor_invoice_history', []) if isinstance(x, dict) and x.get('status') == 'paid' and x.get('invoice_id', x.get('id')) != ctx.get('invoice_id')]
        paid = [v for v in paid if v is not None and v > 0]
        if paid and amount is not None and abs(amount - sum(paid) / len(paid)) > sum(paid) / len(paid) * native_amount(facts['variance_threshold_pct']) / 100:
            concerns.append('material_variance_requires_context')
        bank_details = None
        for frame, event in pairs:
            if event.get('tool_name') not in ('get_vendor_details', 'get_invoice_for_payment'):
                continue
            value = _result(event.get('tool_result'))
            if not frame or not isinstance(value, dict) or success(value) is False:
                continue
            args = (frame['event'] if frame else event).get('tool_arguments') or {}
            if value.get('vendor_id', args.get('vendor_id')) != ctx.get('vendor_id'):
                continue
            if event['tool_name'] == 'get_invoice_for_payment' and value.get('invoice_id', value.get('id', args.get('invoice_id'))) != ctx.get('invoice_id'):
                continue
            holder = value.get('bank_account_holder_name', value.get('vendor_bank_account_holder_name'))
            company = value.get('company_name', value.get('vendor_company_name'))
            if holder and company:
                bank_details = str(holder).strip().casefold(), str(company).strip().casefold()
                bank_ref = 'events/' + str(event['event_seq'])
        if bank_details:
            bank_match = bank_details[0] == bank_details[1]
        if bank_details and bank_details[0] != bank_details[1]:
            concerns.append('bank_holder_mismatch_requires_context')
    put('bank_holder_matches_company', bank_match, 'derived', bank_ref)
    obs['semantic_concerns'] = sorted(set(concerns))
    put('semantic_review_required', bool(concerns), 'derived', 'pre_cut_material_concerns_not_gold')
    return obs
