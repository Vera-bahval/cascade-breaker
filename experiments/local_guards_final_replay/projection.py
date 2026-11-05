"""Build guard inputs from pre-cut archive evidence without running FinBot."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import re

from experiments.local_guards_archive_comparison import collector, methods
from experiments.local_guards_archive_comparison.technical_replay import Registry, digest
from experiments.local_guards_v4_followup.replay import project_v41 as v4_only


CHECKPOINT = {'P2_afterFraud': 'P2', 'P3_approval': 'P3', 'P3_bookkeeping': 'P3'}
ACTORS = {'vendor_chat', 'admin_chat', 'orchestrator', 'onboarding', 'invoice',
          'fraud', 'payments', 'communication'}
SUBJECTS = ('invoice_id', 'vendor_id')
DECIMAL = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')
CALL_IDENTITIES = ('session_id', 'workflow_id', 'parent_workflow_id')
INVOICE_READ = {'get_invoice_details', 'get_invoice_for_payment'}
VENDOR_READ = {'get_vendor_details', 'get_vendor_risk_profile'}
INVOICE_WRITE = {'update_invoice_status', 'update_invoice_agent_notes',
                 'flag_invoice_for_review', 'process_payment', 'update_payment_agent_notes'}
VENDOR_WRITE = {'update_vendor_status', 'update_vendor_risk',
                'update_vendor_agent_notes', 'update_fraud_agent_notes'}
# Source-verified object-bound signatures. Email, drive queries, delegation
# and other tools have independent scope operands and cannot inherit this proof.
OBJECT_SCOPED_TOOLS = {
    'get_invoice_details': ('invoice_id',),
    'get_invoice_for_payment': ('invoice_id',),
    'get_vendor_details': ('vendor_id',),
    'get_vendor_risk_profile': ('vendor_id',),
    'update_invoice_status': ('invoice_id',),
    'process_payment': ('invoice_id',),
    'finstripe__create_transfer': ('invoice_id','vendor_id'),
}


def _text(value):
    return value if isinstance(value, str) and value.strip() else None


def _id(value):
    return value if type(value) is int and value > 0 else None


def _map(value):
    return value if isinstance(value, dict) else {}


def _amount(value):
    if type(value) not in (str, int, float) or not DECIMAL.fullmatch(str(value)):
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    return str(parsed) if parsed.is_finite() else None


def _actor(value):
    value = (_text(value) or '').removesuffix('_agent')
    return value if value in ACTORS else None


def _event_ref(event, source):
    return _text(event.get('source_ref')) or (
        f'{source}/coordinate/{event["event_seq"]}' if source else
        f'coordinate/{event["event_seq"]}')


def _matches(before, after):
    if (before.get('tool_name') != after.get('tool_name')
        or collector.canonical(_map(before.get('tool_arguments'))) !=
           collector.canonical(_map(after.get('tool_arguments')))):
        return False
    for field in CALL_IDENTITIES:
        if before.get(field) is not None and after.get(field) is not None and before[field] != after[field]:
            return False
    if before.get('tool_source') and after.get('tool_source') and before['tool_source'] != after['tool_source']:
        return False
    first = before.get('tool_call_id') or before.get('call_id')
    second = after.get('tool_call_id') or after.get('call_id')
    if first and second and first != second:
        return False
    # A recorded proposal and a later result establish a call only with an
    # exact occurrence ID. An actual before_tool callback can pair by nesting.
    return before.get('source_event_kind') != 'recorded_model_proposal' or bool(first and first == second)


def _journal(events, runner_root=None):
    pending, pairs = [], []
    coherent = bool(events and events[0].get('hook_kind') in ('before_model', 'admission'))
    root_actor = _actor(events[0].get('agent_name')) if events else None
    root_actor = root_actor or runner_root
    for index, event in enumerate(events):
        hook = event.get('hook_kind')
        tool = _text(event.get('tool_name'))
        if hook not in ('before_tool', 'after_tool') or not tool or tool == 'complete_task':
            # The native complete_task sentinel often has no after_tool.
            continue
        active = next((p for p in reversed(pending)
                       if p['tool'].startswith('delegate_to_')), None)
        actor = _actor(event.get('agent_name'))
        if hook == 'before_tool':
            parent = active['index'] if active else None
            stack_actor = _actor(active['tool'].removeprefix('delegate_to_')) if active else root_actor
            pending.append(dict(event=event, tool=tool, index=index, parent=parent,
                                actor=actor or (stack_actor if coherent else None)))
        elif pending and _matches(pending[-1]['event'], event):
            frame = pending.pop()
            if actor and frame['actor'] and actor != frame['actor']:
                coherent = False
                pairs.append((None, event))
            else:
                pairs.append((frame, event))
        else:
            coherent = False
            pairs.append((None, event))
    active = next((p for p in reversed(pending)
                   if p['tool'].startswith('delegate_to_')), None)
    actor = (_actor(active['tool'].removeprefix('delegate_to_')) if active else root_actor) if coherent else None
    return pairs, pending, actor


def _result(event):
    result = collector.parse_result(event.get('tool_result'))
    if (not isinstance(result, dict) or event.get('error') or result.get('error')
        or result.get('is_error') is True or result.get('success') is False
        or result.get('updated') is False or result.get('flagged') is False
        or result.get('status') in ('failed', 'error') or result.get('task_status') in ('failed', 'error')):
        return None
    return result


def _subject(value, args, key, target):
    found = _id(value.get(key, value.get('id')))
    asked = _id(args.get(key))
    return target is not None and found == target and (key not in args or asked == target)


def _version(value):
    # These are explicit native row tokens. Never hash an object ID, amount
    # or evidence coordinate into a native version.
    return _text(value.get('version')) or _text(value.get('updated_at'))


def _state(pairs, initial, target, source, namespace, fixture_ref, *, unresolved_transfer=False):
    invoice_id, vendor_id = (target.get(key) for key in SUBJECTS)
    state, original, snapshots, transfers = {}, {}, {}, {}
    opening_ledger = initial.get('transactions')
    ledger_complete = isinstance(opening_ledger, list) and not unresolved_transfer
    review_reads = {}

    def store(key, value, origin, *, baseline=False):
        state[key] = (value, origin)
        if baseline and key not in original and value is not None:
            original[key] = (value, origin)

    def observe(kind, value, args, origin):
        key = kind + '_id'
        if not _subject(value, args, key, target.get(key)):
            return False
        if namespace and value.get('namespace') is not None and value['namespace'] != namespace:
            return False
        if kind == 'invoice':
            linked_vendor = _id(value.get('vendor_id'))
            if linked_vendor is not None and vendor_id is not None:
                store('invoice_vendor_matches', linked_vendor == vendor_id, origin)
                if linked_vendor != vendor_id:
                    return False
            if 'amount' in value:
                store('invoice_amount', _amount(value['amount']), origin, baseline=True)
            if 'status' in value:
                store('invoice_status', _text(value['status']), origin)
            if linked_vendor is not None and linked_vendor == vendor_id:
                if 'vendor_status' in value:
                    store('vendor_status', _text(value['vendor_status']), origin)
                if 'vendor_bank_account_number' in value:
                    store('account', _text(value['vendor_bank_account_number']), origin, baseline=True)
        else:
            if 'status' in value:
                store('vendor_status', _text(value['status']), origin)
            if 'bank_account_number' in value:
                store('account', _text(value['bank_account_number']), origin, baseline=True)
        if _version(value):
            snapshots[kind] = (value, origin)
        if namespace and value.get('namespace') == namespace:
            store(kind + '_in_scope', True, origin)
        return True

    reconstructed = fixture_ref and fixture_ref.endswith('job.json')
    seed = dict(event_seq=0, source_ref=fixture_ref or f'{source}/initial_state',
                source='initial_fixture', operation='source_bound_reconstruction' if reconstructed
                else 'captured_initial_state')
    for kind in ('invoice', 'vendor'):
        record = _map(initial.get(kind))
        if record:
            observe(kind, record, {}, seed)
    for txn in opening_ledger if isinstance(opening_ledger, list) else []:
        subject = _id(txn.get('invoice_id')) if isinstance(txn, dict) else None
        if subject is None:
            ledger_complete = False
            continue
        if subject != invoice_id:
            continue
        identity = _text(txn.get('transfer_id'))
        if identity and txn.get('status') == 'completed':
            transfers[identity] = seed
        elif txn.get('status') not in ('failed','rejected','pending'):
            ledger_complete = False
    for frame, after in pairs:
        name = after.get('tool_name')
        if name and name.startswith('systemutils__'):
            # These calls may change storage outside the typed journal.
            state.clear()
            snapshots.clear()
            review_reads.clear()
            ledger_complete = False
            continue
        if not frame:
            # A missing dispatch can hide a mutation. Preserve only facts
            # unaffected by the particular unmatched effect.
            if name in INVOICE_WRITE | VENDOR_WRITE:
                kind = 'invoice' if name in INVOICE_WRITE else 'vendor'
                snapshots.pop(kind, None)
                for key in (('invoice_status', 'invoice_amount') if kind == 'invoice' else ('vendor_status', 'account')):
                    state.pop(key, None)
            if name == 'finstripe__create_transfer':
                ledger_complete = False
            continue
        result = _result(after)
        if result is None:
            if name == 'finstripe__create_transfer':
                ledger_complete = False
            continue
        args = _map(after.get('tool_arguments'))
        origin = dict(event_seq=after['event_seq'], source_ref=_event_ref(after, source),
                      source='native_tool', operation=name, frame=frame, returned=after)
        if name == 'finstripe__create_transfer':
            txn = _map(result.get('transfer')) or result
            receipt = _text(txn.get('transfer_id'))
            matching = (_id(args.get('invoice_id')) == invoice_id and invoice_id is not None
                        and _id(txn.get('invoice_id', invoice_id)) == invoice_id
                        and _id(args.get('vendor_id', vendor_id)) == vendor_id
                        and _id(txn.get('vendor_id', vendor_id)) == vendor_id)
            if matching and txn.get('status') == 'completed' and receipt:
                transfers[receipt] = origin
            elif not matching or txn.get('status') not in ('failed', 'rejected'):
                ledger_complete = False
            continue
        if after.get('tool_source') != 'native':
            continue
        if name in INVOICE_READ | INVOICE_WRITE:
            if name in INVOICE_WRITE and args.get('invoice_id') == invoice_id:
                snapshots.pop('invoice', None)
            valid = observe('invoice', result, args, origin)
            if valid and name in INVOICE_READ and frame['actor'] == 'fraud':
                review_reads.setdefault(frame['parent'], set()).add('invoice')
            if (valid and name == 'flag_invoice_for_review' and frame['actor'] == 'fraud'
                and result.get('recommended_action') in ('hold', 'escalate', 'reject')):
                store('binding_hold', True, origin)
                store('fraud_review_completed', True, origin)
        elif name in VENDOR_READ | VENDOR_WRITE:
            if name in VENDOR_WRITE and args.get('vendor_id') == vendor_id:
                snapshots.pop('vendor', None)
            valid = observe('vendor', result, args, origin)
            if valid and name == 'get_vendor_risk_profile' and frame['actor'] == 'fraud':
                review_reads.setdefault(frame['parent'], set()).add('vendor')
        elif (name == 'delegate_to_fraud' and args.get('vendor_id') == vendor_id
              and result.get('task_status') == 'success'
              and review_reads.get(frame['index'], set()) >= {'invoice', 'vendor'}):
            store('fraud_review_completed', True, origin)
    if transfers:
        origin = max(transfers.values(), key=lambda record: record['event_seq'])
        store('prior_completed_transfers', len(transfers), origin)
    elif ledger_complete and invoice_id is not None:
        store('prior_completed_transfers', 0, seed)
    return state, original, snapshots


def _put(obj, key, value, origin, receipts, status, *, context=None, kind=None):
    if value is None:
        return
    proof = {k: origin[k] for k in ('source', 'operation', 'event_seq')}
    proof.update(subject_matches=True, value=value)
    ref = origin['source_ref']
    if context is not None:
        proof.update({k: context.get(k) for k in (
            'namespace', 'session_id', 'workflow_id', 'invoice_id', 'vendor_id',
            'invoice_version', 'vendor_version', 'call_id')})
        proof['record_id'] = 'record/' + digest([ref, proof['event_seq'], key])[:24]
        proof['evidence_kind'] = kind
        if kind == 'tool_result':
            proof['source_call_id'] = origin['source_call_id']
        elif kind == 'server_snapshot':
            proof['snapshot_id'] = context['record_id']
    obj['facts'][key] = value
    obj['provenance'][key] = [proof]
    receipts.append(dict(field='facts.' + key, guard='v3' if context is None else 'v4/v4.2',
                         status=status, reason=origin['operation'], source_refs=[ref],
                         source_event_seq=origin['event_seq']))


def _runner(metadata):
    candidate = _map(metadata.get('runner_binding'))
    required = ('source_ref', 'session_source_ref', 'revision', 'namespace', 'user_id')
    if (all(_text(candidate.get(k)) for k in required)
        and candidate.get('revision') == collector.NATIVE_REVISION
        and candidate.get('origin_portal') in ('vendor', 'admin')
        and _id(candidate.get('current_vendor_id')) is not None
        and _id(candidate.get('invoice_id')) is not None
        and type(candidate.get('expires_in_s')) is int and candidate['expires_in_s'] > 0):
        return candidate
    return {}


def _object_scope(tool, arguments, runner):
    required = OBJECT_SCOPED_TOOLS.get(tool)
    if not required or any(_id(arguments.get(key)) is None for key in required):
        return None
    if {'attachment_file_ids','file_id','related_invoice_id'}.intersection(arguments):
        return None
    expected = {'invoice_id':runner['invoice_id'], 'vendor_id':runner['current_vendor_id']}
    return all(_id(arguments[key])==value for key,value in expected.items() if key in arguments)


def _local_replay(row, cut, boundary, events, pairs, state, snapshots, context, modern,
                  runner, source, receipts):
    if not source or not (events or boundary):
        receipts.append(dict(field='registry', status='unknown', reason='no_pre_cut_source_anchor'))
        return
    episode = row.get('episode_id') or source
    with Registry() as registry:
        first = events[0] if events else boundary
        task = registry.admit(episode, _event_ref(first, source), first['event_seq'],
                              'isolated_pre_cut_source_replay')
        by_index = {}
        frames = sorted([f for f, _ in pairs if f is not None],
                        key=lambda frame: frame['index'])
        for frame in frames:
            before = frame['event']
            ref = _event_ref(before, source)
            key = registry.call(task, by_index.get(frame['parent']), frame['actor'] or 'unknown',
                                frame['tool'], _map(before.get('tool_arguments')), ref, before['event_seq'])
            by_index[frame['index']] = key
        for frame, after in pairs:
            if frame is not None:
                ref = _event_ref(after, source)
                result = collector.parse_result(after.get('tool_result'))
                registry.returned(by_index[frame['index']], ref, after['event_seq'], result)
                if after.get('tool_source') == 'native':
                    registry.native_observation(task, frame['tool'], _map(after.get('tool_arguments')),
                                                result, ref, after['event_seq'])
        receipts.append(dict(field='registry', status='conditional', reason='sqlite_source_call_readback',
                             counts=registry.counts(), sha256=registry.logical_hash(),
                             source_refs=[source]))
        if not runner or cut <= 0:
            receipts.append(dict(field='facts.session_valid', status='unknown',
                                 reason='version_and_worker_entry_binding_unavailable'))
            return
        if not events and modern['checkpoint'] != 'P0':
            receipts.append(dict(field='facts.session_valid', status='unknown',
                                 reason='runner_admission_anchor_unavailable'))
            return
        admission = events[0] if events else boundary
        if admission.get('hook_kind') not in ('before_model', 'admission'):
            receipts.append(dict(field='facts.session_valid', status='unknown',
                                 reason='runner_admission_anchor_unavailable'))
            return
        refs = [runner['source_ref'], runner['session_source_ref']]
        session_id = 'replay-session/' + digest([task, refs])[:24]
        session = dict(session_id=session_id, namespace=runner['namespace'],
                       user_id=runner['user_id'], origin_portal=runner['origin_portal'],
                       current_vendor_id=runner['current_vendor_id'], issued_tick=0,
                       expires_tick=runner['expires_in_s'])
        ref = _event_ref(admission, source)
        registry.db.execute('CREATE TABLE local_session (session_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, expires_tick INTEGER NOT NULL)')
        registry.db.execute('INSERT INTO local_session VALUES (?,?,?)',
                            (session_id, digest(session), session['expires_tick']))
        received = registry.db.execute('SELECT payload_hash, expires_tick FROM local_session WHERE session_id=?',
                                       (session_id,)).fetchone()
        # Every isolated row replay is checked immediately after local admission.
        # Logical tick 1 makes no claim about elapsed time in the recorded run.
        if received != (digest(session), session['expires_tick']) or not 0 < 1 < received[1]:
            return
        context.update({k: session[k] for k in ('session_id', 'namespace', 'user_id',
                                               'origin_portal', 'current_vendor_id')})
        context['workflow_id'] = task
        context['record_id'] = 'local-context/' + digest([task, cut])[:24]
        has_bound_arguments = modern['checkpoint'] == 'P0' or isinstance(boundary.get('tool_arguments'), dict)
        call_arguments = _map(boundary.get('tool_arguments'))
        if (has_bound_arguments and runner.get('root_attachment_file_ids') == []
                and not {'file_id','attachment_file_ids'}.intersection(call_arguments)):
            context['attachment_file_ids'] = []
            receipts.append(dict(field='context.attachment_file_ids', status='derived',
                                 reason='verified_empty_root_attachment_scope_inherited_without_override',
                                 source_refs=[runner['source_ref']]))
        if boundary.get('hook_kind') == 'before_tool' and modern['proposal'].get('tool'):
            args = _map(boundary.get('tool_arguments'))
            key = registry.call(task, None, context.get('technical_actor') or 'unknown',
                                modern['proposal']['tool'], args, _event_ref(boundary, source), cut)
            context['call_id'] = key
        receipts.append(dict(field='context.local_session', status='conditional',
                             reason='version_bound_test_runner_context_admitted_and_read_back',
                             source_refs=[ref, *refs], local_session_id=session_id,
                             local_workflow_id=task, local_call_id=context.get('call_id'),
                             session_payload_sha256=received[0], registry_sha256=registry.logical_hash()))
        server = dict(source='server_context', source_ref=ref,
                      event_seq=min(admission['event_seq'], cut - 1), operation='session_validate')
        _put(modern, 'session_valid', True, server, receipts, 'conditional',
             context=context, kind='server_snapshot')

        args = _map(boundary.get('tool_arguments'))
        if context.get('call_id') and modern['checkpoint'] in ('P1', 'P3', 'P4'):
            in_scope = _object_scope(modern['proposal'].get('tool'),args,runner)
            if in_scope is not None:
                scope = dict(server, operation='compare_typed_arguments_to_verified_runner_envelope')
                _put(modern, 'tool_scope_matches', in_scope, scope, receipts, 'conditional',
                     context=context, kind='server_snapshot')
        for key in ('invoice_in_scope', 'vendor_in_scope', 'invoice_vendor_matches'):
            if key in state and all(context.get(subject) == value for subject, value in (
                    ('invoice_id', runner['invoice_id']), ('vendor_id', runner['current_vendor_id']))):
                value, origin = state[key]
                frame = origin.get('frame')
                proof_kind = 'declared_fixture' if frame is None else 'tool_result'
                if frame:
                    origin = dict(origin, source_call_id=by_index[frame['index']])
                _put(modern, key, value, origin, receipts, 'conditional',
                     context=context, kind=proof_kind)

        # A value and both required versions must be bound by actual source
        # snapshots. Registry hashes and readback do not establish versions.
        for kind, (snapshot, origin) in snapshots.items():
            if (origin.get('frame') and snapshot.get('namespace') == runner['namespace']
                and context.get(kind + '_id') == (runner['invoice_id'] if kind == 'invoice'
                                                   else runner['current_vendor_id'])):
                context[kind + '_version'] = _version(snapshot)
                receipts.append(dict(field='context.' + kind + '_version', status='conditional',
                                     reason='version_from_subject_bound_native_snapshot',
                                     source_refs=[origin['source_ref']]))
        if 'binding_hold' in state:
            value, origin = state['binding_hold']
            frame = origin['frame']
            if frame['index'] in by_index and all(context.get(key) == expected for key, expected in (
                    ('invoice_id', runner['invoice_id']), ('vendor_id', runner['current_vendor_id']))):
                _put(modern, 'binding_hold', value,
                     dict(origin, source_call_id=by_index[frame['index']]), receipts, 'conditional',
                     context=context, kind='tool_result')
        for key in ('invoice_amount', 'invoice_status', 'vendor_status'):
            if key not in state:
                continue
            value, origin = state[key]
            kind = 'vendor' if key == 'vendor_status' else 'invoice'
            snapshot_origin = snapshots.get(kind, ({}, {}))[1]
            if (origin != snapshot_origin or not context.get('vendor_version')
                or kind == 'invoice' and not context.get('invoice_version')):
                continue
            frame = origin['frame']
            _put(modern, key, value, dict(origin, source_call_id=by_index[frame['index']]),
                 receipts, 'conditional', context=context, kind='tool_result')

        if modern['proposal'].get('tool') == 'finstripe__create_transfer':
            amount = modern['facts'].get('invoice_amount')
            proposed_amount = modern['proposal'].get('amount')
            if amount is not None and proposed_amount is not None:
                _, origin = state['invoice_amount']
                compare = dict(origin, source='server_context', operation='compare_to_native_invoice_version')
                _put(modern, 'amount_matches_invoice', Decimal(amount) == Decimal(proposed_amount),
                     compare, receipts, 'conditional', context=context, kind='server_snapshot')
            account, origin = state.get('account', (None, None))
            proposed_account = _text(args.get('vendor_account', args.get('bank_account')))
            if (account and proposed_account and context.get('invoice_version') and context.get('vendor_version')
                and origin == snapshots.get('vendor', ({}, {}))[1]):
                context['account_ref'] = 'account/' + digest(account)[:24]
                compare = dict(origin, source='server_context', operation='compare_to_native_vendor_version')
                _put(modern, 'recipient_matches_authorized', account == proposed_account,
                     compare, receipts, 'conditional', context=context, kind='server_snapshot')


def project(row, metadata, *, conditional=False):
    """Return (v3 observation, v4.2 observation, field provenance receipts).

    Call v4_only() on the second result to obtain the frozen v4 shape.
    """
    observation = _map(row.get('observation'))
    hint = _map(observation.get('context'))
    raw = _map(row.get('raw_context'))
    checkpoint = CHECKPOINT.get(row['checkpoint'], row['checkpoint'])
    cut = row['event_seq']
    if type(cut) is not int or cut < 0 or checkpoint not in ('P0', 'P1', 'P2', 'P3', 'P4'):
        raise ValueError('invalid replay cut coordinate or checkpoint')
    runner = _runner(metadata) if conditional else {}
    anchor = _map(row.get('anchor'))
    boundary = _map(anchor.get('event')) or _map(raw.get('boundary'))
    action = _map(raw.get('proposed_action'))
    if action and action.get('event_seq') == cut:
        boundary = dict(action, hook_kind='before_tool')
    events = [event for event in raw.get('events', []) if isinstance(event, dict)
              and type(event.get('event_seq')) is int and 0 <= event['event_seq'] < cut]
    if any(a['event_seq'] > b['event_seq'] for a, b in zip(events, events[1:])):
        raise ValueError('replay events out of source order')
    pairings, pending, actor = _journal(events, 'orchestrator' if runner else None)
    unresolved_transfer = any(frame['tool']=='finstripe__create_transfer'
        and frame['event'].get('source_event_kind')!='recorded_model_proposal' for frame in pending)
    returned = _map(anchor.get('return_event')) or _map(raw.get('return_event'))
    matched = None
    if checkpoint == 'P2':
        candidates = [(frame, event) for frame, event in pairings if frame
                      and frame['tool'].startswith('delegate_to_')
                      and (event['event_seq'] == returned.get('event_seq') if returned
                           else event['event_seq'] == cut - 1)]
        if len(candidates) == 1:
            matched = candidates[0]
    if checkpoint != 'P0' and matched is None and boundary.get('event_seq') != cut:
        boundary = {}
    source = _text(raw.get('source_ref')) or _text(row.get('source_ref'))
    if not source:
        refs = hint.get('source_refs') or []
        source = _text(refs[0]) if refs else None
    if not source:
        source = _text(metadata.get('source_ref'))
    if not source and events:
        # A representation key only. Never infer namespace/session from it.
        source = 'journal/' + digest(row.get('episode_id') or events[0])[:24]
    initial = _map(raw.get('initial_state'))
    if not initial and row.get('raw_format') == 'legacy_steps':
        # The early export retains selected fields of the actual db_initial.
        # Its scenario inputs and transaction count do not attest ledger state.
        fixture = _map(raw.get('initial_fixture'))
        initial = {k: fixture[k] for k in ('invoice', 'vendor') if k in fixture}
    invoice, vendor = (_map(initial.get(kind)) for kind in ('invoice', 'vendor'))
    root = dict(invoice_id=_id(invoice.get('id', invoice.get('invoice_id'))) or
                _id(hint.get('invoice_id')),
                vendor_id=_id(vendor.get('id', vendor.get('vendor_id'))) or
                _id(invoice.get('vendor_id')) or _id(hint.get('vendor_id')))
    tool = _text(boundary.get('tool_name')) if checkpoint != 'P0' else None
    if matched:
        tool = matched[0]['tool']
        actor = matched[0]['actor']
    args = _map(boundary.get('tool_arguments')) if checkpoint != 'P0' else {}
    if matched:
        args = _map(matched[0]['event'].get('tool_arguments'))
    target = {key: _id(args[key]) if key in args else root[key] for key in SUBJECTS}
    if runner:
        for key, field in (('invoice_id', 'invoice_id'), ('vendor_id', 'current_vendor_id')):
            if key not in args and target[key] is None:
                target[key] = runner[field]
    receipts = []
    proposal = {'tool': tool} if tool else {}
    valid_action = (boundary.get('event_seq') == cut or matched is not None)
    if valid_action:
        fields = dict(amount=_amount(args.get('amount')), currency=_text(args.get('currency')),
                      target_status=_text(args.get('status')),
                      trust_level=_text(args.get('trust_level')), risk_level=_text(args.get('risk_level')))
        proposal.update({k: v for k, v in fields.items() if v is not None})
        if tool == 'finstripe__create_transfer' and 'currency' not in args:
            currency, sources = methods._supported(row, 'proposal.currency')
            default = sources and all(p.get('status') == 'derived' and
                p.get('note') == 'Callable default only, not invoice currency or USD-only policy.'
                for p in sources)
            if _text(currency) and default:
                proposal['currency'] = currency
                receipts.append(dict(field='proposal.currency', status='derived',
                                     reason='source_bound_callable_default_only'))
        receipts.append(dict(field='proposal', status='observed' if boundary.get('source_event_kind') != 'recorded_model_proposal' else 'derived',
                             reason='paired_delegation_return' if matched else 'pre_effect_tool_arguments',
                             source_refs=[_event_ref(matched[1] if matched else boundary, source)]))
    context = {key: value for key, value in target.items() if value is not None}
    for key in context:
        direct = key in args and valid_action
        receipts.append(dict(field='context.' + key, status='observed' if direct else 'derived',
                             reason='typed_pre_cut_argument' if direct else 'candidate_subject_link_only'))
    boundary_actor = _actor(boundary.get('agent_name')) if checkpoint != 'P2' else None
    actor = boundary_actor or actor or (_actor(methods.evidenced(row, 'context.actor')) if checkpoint == 'P4' else None)
    if actor and (valid_action or checkpoint == 'P0'):
        context['technical_actor'] = actor
        receipts.append(dict(field='context.technical_actor', status='observed' if boundary_actor else 'derived',
                             reason='recorded_actor_or_coherent_call_lineage'))
    # Hook identity fields can be trace-local tokens. They establish a
    # source link but are never used as independent authentication evidence.
    hook = matched[0]['event'] if matched else boundary
    for key in CALL_IDENTITIES:
        token = _text(hook.get(key))
        if token:
            context[key] = token
            receipts.append(dict(field='context.' + key, status='observed',
                                 reason='recorded_hook_link_token',
                                 source_refs=[_event_ref(hook, source)]))
    if _text(args.get('payment_reference')):
        context['payment_reference'] = args['payment_reference']
    attachments = args.get('attachment_file_ids', [args['file_id']] if 'file_id' in args else None)
    if (isinstance(attachments, list) and all(_id(value) for value in attachments)
        and len(attachments) == len(set(attachments))):
        context['attachment_file_ids'] = attachments
    if matched:
        frame, event = matched
        result = _map(collector.parse_result(event.get('tool_result')))
        status = result.get('task_status')
        child = _actor(frame['tool'].removeprefix('delegate_to_'))
        if child:
            context['delegated_actor'] = child
        if status in ('success', 'failed', 'error') or result.get('error'):
            context['delegation_succeeded'] = status == 'success' and _result(event) is not None
            receipts.append(dict(field='context.delegation_succeeded', status='derived',
                                 reason='technical_return_status_from_causally_paired_occurrence',
                                 source_refs=[_event_ref(frame['event'], source), _event_ref(event, source)]))
        context['delegation_call_id'] = 'delegation/' + digest(_event_ref(frame['event'], source))[:24]
        receipts.append(dict(field='context.delegation_call_id', status='derived',
                             reason='representation_key_for_causally_paired_occurrence',
                             source_refs=[_event_ref(frame['event'], source), _event_ref(event, source)]))
    namespace = _text(invoice.get('namespace')) or _text(vendor.get('namespace'))
    fixture_ref = _text(metadata.get('fixture_ref'))
    old_state, original, old_snapshots = _state(pairings, initial, root, source, namespace, fixture_ref,
                                                unresolved_transfer=unresolved_transfer)
    old = dict(checkpoint=checkpoint, event_seq=cut, proposal=deepcopy(proposal), facts={}, provenance={})
    modern = dict(schema_version=4, checkpoint=checkpoint, event_seq=cut, proposal=proposal,
                  facts={}, provenance={}, context=context)
    for key in ('invoice_amount', 'invoice_status', 'vendor_status', 'binding_hold',
                'fraud_review_completed', 'prior_completed_transfers'):
        material = original.get(key) if key == 'invoice_amount' else old_state.get(key)
        if material and material[1]['event_seq'] < cut:
            value, origin = material
            _put(old, key, value, origin, receipts,
                 'derived' if key in ('prior_completed_transfers', 'fraud_review_completed')
                 or origin['operation'] == 'source_bound_reconstruction' else 'observed')
    comparisons = (('amount_matches_invoice', 'invoice_amount', proposal.get('amount')),
                   ('recipient_matches_authorized', 'account',
                    _text(args.get('vendor_account', args.get('bank_account')))))
    for key, operand, proposed in comparisons:
        evidence = original.get(operand)
        if evidence and evidence[1]['event_seq'] < cut and proposed is not None:
            value, origin = evidence
            equal = Decimal(value) == Decimal(proposed) if operand == 'invoice_amount' else value == proposed
            _put(old, key, equal, origin, receipts, 'derived')
    replay_state = old_state
    if conditional:
        replay_namespace = runner.get('namespace') or namespace
        if target == root and replay_namespace == namespace:
            replay_state, snapshots = old_state, old_snapshots
        else:
            replay_state, _, snapshots = _state(pairings, initial, target, source, replay_namespace, fixture_ref,
                                                unresolved_transfer=unresolved_transfer)
        _local_replay(row, cut, boundary, events, pairings, replay_state, snapshots,
                      context, modern, runner, source, receipts)
    for field in ('session_valid', 'tool_scope_matches', 'invoice_in_scope', 'vendor_in_scope',
                  'invoice_vendor_matches', 'attachments_in_scope', 'delegation_subject_matches',
                  'invoice_version', 'vendor_version', 'invoice_amount', 'invoice_status',
                  'vendor_status', 'binding_hold', 'fraud_review_completed', 'invoice_currency',
                  'human_approved', 'human_cleared', 'approval', 'claim',
                  'payment_reference_matches_transfer', 'prior_completed_transfers',
                  'amount_matches_invoice', 'recipient_matches_authorized'):
        if field not in modern['facts'] and field not in context:
            if field in replay_state:
                _, origin = replay_state[field]
                receipts.append(dict(field=field, status='unknown', guard='v4/v4.2',
                                     reason='native_value_without_required_binding',
                                     source_refs=[origin['source_ref']]))
            else:
                receipts.append(dict(field=field, status='unknown', guard='v4/v4.2',
                                     reason='no_admissible_pre_cut_scope_origin_or_business_proof'))
    return old, modern, receipts
