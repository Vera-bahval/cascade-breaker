"""Read-only offline representations. No labels, guard imports, DB or model calls.

Every non-strict wrapper carries field-level assumptions and original proof payloads.
Simulated source-call IDs describe recording instrumentation, never historical IDs.
"""
import copy
import hashlib
import json

NEW_PROOF_FIELDS = frozenset(('evidence_kind', 'snapshot_id', 'source_call_id',
    'parent_workflow_id', 'delegated_workflow_id', 'delegation_call_id'))
NEW_CONTEXT_FIELDS = frozenset(('delegated_workflow_id',))
SCOPE = ('namespace', 'session_id', 'workflow_id', 'vendor_id', 'invoice_id',
         'invoice_version', 'vendor_version', 'call_id')


def _token(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()[:24]


def _wrapper(row):
    observation = row.get('observation', row)
    result = {'observation': copy.deepcopy(observation), 'assumptions': [],
              'original_prefix_id': row.get('prefix_id')}
    if 'payment_baseline' in row:
        result['payment_baseline'] = copy.deepcopy(row['payment_baseline'])
    return result


def _change(target, key, value, path, assumptions, basis, *, absent_only=False):
    if (key in target if absent_only else target.get(key) is not None):
        return
    old_present = key in target
    old = copy.deepcopy(target.get(key))
    target[key] = copy.deepcopy(value)
    assumptions.append({'field': path + '.' + key, 'old': old, 'new': copy.deepcopy(value),
                        'basis': basis, 'old_present': old_present})


def _scope_matches(proof, context):
    for key in SCOPE:
        value = context.get(key)
        if key in ('vendor_id', 'invoice_id'):
            if type(value) is not int or value <= 0:
                return False
        elif not isinstance(value, str) or not value.strip():
            return False
        if type(proof.get(key)) is not type(value) or proof[key] != value:
            return False
    return True


def _origin(proof, field, index, context, seed, assumptions):
    """Annotate recorded origins only; leave old scope, time, value and source intact."""
    if not isinstance(proof, dict):
        return
    source = proof.get('source')
    path = 'provenance.' + field + '.' + str(index)
    add = lambda k, v, basis: _change(proof, k, v, path, assumptions, basis, absent_only=True)
    if source == 'initial_fixture':
        add('evidence_kind', 'declared_fixture', 'explicit source fixture; no native DB currency inferred')
    elif source == 'independent_registry':
        add('evidence_kind', 'independent_registry', 'original independent registry evidence, unchanged')
    elif source == 'server_context' and field == 'invoice_currency' and proof.get('operation') == 'currency_contract_attest':
        add('evidence_kind', 'declared_fixture', 'original explicit server currency contract')
    elif source == 'server_context':
        add('evidence_kind', 'server_snapshot', 'conditional replay of the already recorded server observation')
        add('snapshot_id', 'replay-snapshot/' + _token([seed, proof.get('event_seq')]),
            'simulated snapshot identity from frozen event index; not a historical snapshot ID')
    elif source == 'native_tool':
        add('evidence_kind', 'tool_result', 'conditional recording of already observed source event')
        if type(proof.get('event_seq')) is int and proof['event_seq'] >= 0:
            add('source_call_id', 'replay-source-call/' + _token([seed, proof['event_seq']]),
                'simulated producing invocation ID from frozen event index; not a historical call ID')


def payment320_variant(row):
    """Convert the synthetic v3 payment envelope, with an audit sidecar.

    The new context is a declared isolated test fixture. Its access/session facts
    are supplemental technical assumptions, not historical authorization. Existing
    facts/proofs retain null, false, absent, foreign, future and invalid semantics.
    """
    keys = ('checkpoint', 'event_seq', 'proposal', 'facts', 'provenance')
    observation = {key: copy.deepcopy(row[key]) for key in keys if key in row}
    seed = _token(observation)
    assumptions = []
    original_provenance = copy.deepcopy(observation.get('provenance'))
    observation['schema_version'] = 4
    context = {'record_id': 'payment-fixture/' + seed, 'session_id': 'fixture-session/' + seed,
        'user_id': 'fixture-user/' + seed, 'namespace': 'isolated-payment320/' + seed,
        'workflow_id': 'fixture-workflow/' + seed, 'parent_workflow_id': 'fixture-parent/' + seed,
        'origin_portal': 'vendor', 'technical_actor': 'payments', 'current_vendor_id': 1,
        'vendor_id': 1, 'invoice_id': 1, 'attachment_file_ids': [], 'call_id': 'fixture-target/' + seed,
        'invoice_version': 'fixture-invoice-revision/' + seed,
        'vendor_version': 'fixture-vendor-revision/' + seed,
        'account_ref': None, 'payment_reference': None, 'approval': None, 'claim': None,
        'delegated_actor': None, 'delegation_succeeded': None, 'delegation_call_id': None}
    observation['context'] = context
    assumptions.extend({'field': 'context.' + key, 'old': None, 'new': copy.deepcopy(value),
        'basis': 'declared isolated synthetic payment comparison fixture, not archived server authority'}
        for key, value in context.items())
    assumptions.append({'field': 'schema_version', 'old': None, 'new': 4,
                        'basis': 'representation conversion from the frozen v3 schema'})
    facts, provenance = observation.get('facts'), observation.get('provenance')
    if isinstance(facts, dict) and isinstance(provenance, dict):
        for field, proofs in provenance.items():
            if not isinstance(proofs, list):
                continue
            for index, proof in enumerate(proofs):
                if not isinstance(proof, dict):
                    continue
                path = 'provenance.' + field + '.' + str(index)
                if 'writer' in proof:
                    writer = proof.pop('writer')
                    assumptions.append({'field': path + '.writer', 'old': writer, 'new': None,
                        'basis': 'v3 audit writer retained in original_provenance sidecar, not a v4 proof field'})
                else:
                    writer = None
                # Native Invoice has no currency field. The old synthetic row's
                # supplied currency is declared as fixture data, never as a DB read.
                if field == 'invoice_currency' and proof.get('source') == 'native_tool' and writer == 'native_store':
                    old = proof['source']
                    proof['source'] = 'initial_fixture'
                    assumptions.append({'field': path + '.source', 'old': old, 'new': 'initial_fixture',
                        'basis': 'original synthetic native_store currency interpreted as declared fixture currency; original payload retained'})
                for key in SCOPE:
                    _change(proof, key, context[key], path, assumptions,
                            'declared isolated fixture scope; existing scoped values are never replaced', absent_only=True)
                _change(proof, 'record_id', context['record_id'] + '/' + field + '/' + str(index),
                        path, assumptions, 'declared fixture proof record identity', absent_only=True)
                if field in facts:
                    _change(proof, 'value', facts[field], path, assumptions,
                            'v3 schema proof refers to the original fact value', absent_only=True)
                _origin(proof, field, index, context, seed, assumptions)
        for field in ('session_valid', 'vendor_in_scope', 'invoice_in_scope',
                      'invoice_vendor_matches', 'attachments_in_scope', 'tool_scope_matches'):
            if field in facts or field in provenance:
                continue
            facts[field] = True
            proof = dict({k: context[k] for k in SCOPE}, source='server_context',
                event_seq=0, subject_matches=True, operation='session_validate' if field == 'session_valid' else 'declared_fixture_scope',
                record_id=context['record_id'] + '/' + field, value=True,
                evidence_kind='server_snapshot', snapshot_id=context['record_id'])
            provenance[field] = [proof]
            assumptions.append({'field': 'facts.' + field, 'old': None, 'new': True,
                'basis': 'declared synthetic fixture session/access infrastructure; no payment fact inferred'})
            assumptions.append({'field': 'provenance.' + field, 'old': None, 'new': copy.deepcopy([proof]),
                'basis': 'declared synthetic fixture proof of supplemental technical infrastructure'})
    return {'observation': observation, 'assumptions': assumptions,
            'original_prefix_id': row.get('prefix_id'), 'original_provenance': original_provenance,
            'payment_baseline': {key: copy.deepcopy(row[key]) for key in
                keys + ('prefix_id', 'untrusted_text') if key in row}}


def adapt_payment320(row):
    """Decision-input interface. Use payment320_variant for its required audit sidecar."""
    return payment320_variant(row)['observation']


def project_v41(observation):
    """Remove only v4.2 additions; never fill/drop old facts or repair old values."""
    result = copy.deepcopy(observation)
    if not isinstance(result, dict):
        return result
    context = result.get('context')
    if isinstance(context, dict):
        for key in NEW_CONTEXT_FIELDS:
            context.pop(key, None)
    provenance = result.get('provenance')
    if isinstance(provenance, dict):
        for proofs in provenance.values():
            if isinstance(proofs, list):
                for proof in proofs:
                    if isinstance(proof, dict):
                        for key in NEW_PROOF_FIELDS:
                            proof.pop(key, None)
    return result


def _fixture_delegation(observation, assumptions, seed):
    context, facts, provenance = (observation.get(k) for k in ('context', 'facts', 'provenance'))
    if not all(isinstance(x, dict) for x in (context, facts, provenance)):
        return
    if context.get('delegation_succeeded') is not True or facts.get('delegation_subject_matches') is not True:
        return
    if not all(isinstance(context.get(k), str) and context[k] for k in ('parent_workflow_id', 'delegated_actor', 'delegation_call_id')):
        return
    delegation_proofs = provenance.get('delegation_subject_matches')
    if not isinstance(delegation_proofs, list):
        return
    for index, proof in enumerate(delegation_proofs):
        if (not isinstance(proof, dict) or proof.get('source') != 'server_context'
            or proof.get('subject_matches') is not True or proof.get('value') is not True
            or not isinstance(proof.get('record_id'), str) or not proof['record_id'].strip()
            or type(proof.get('event_seq')) is not int
            or type(observation.get('event_seq')) is not int or not 0 <= proof['event_seq'] < observation['event_seq']
            or not _scope_matches(proof, context)):
            continue
        _change(context, 'delegated_workflow_id', 'fixture-child/' + seed, 'context', assumptions,
                'declared child identity for original successful scoped synthetic delegation', absent_only=True)
        for key in ('parent_workflow_id', 'delegated_workflow_id', 'delegation_call_id'):
            _change(proof, key, context.get(key), 'provenance.delegation_subject_matches.' + str(index),
                    assumptions, 'tuple bound to original known parent/call and declared fixture child', absent_only=True)


def adapt_v41_fixture(row):
    """Annotate old400 synthetic fixture origins without repairing its old contract."""
    result = _wrapper(row)
    observation, assumptions = result['observation'], result['assumptions']
    if not isinstance(observation, dict):
        return result
    result['original_provenance'] = copy.deepcopy(observation.get('provenance'))
    seed = _token(observation)
    context = observation.get('context') or {}
    provenance = observation.get('provenance')
    if isinstance(provenance, dict):
        for field, proofs in provenance.items():
            if isinstance(proofs, list):
                for index, proof in enumerate(proofs):
                    _origin(proof, field, index, context, seed, assumptions)
    _fixture_delegation(observation, assumptions, seed)
    return result


class ArchiveReplayRegistry:
    """Counterfactual admissions isolated by original episode and root workflow.

    Feed rows in original event order. Only original verified P0 scope establishes
    admission. A later proposed object never becomes a newly admitted root.
    This is offline state replay, not a historical registry or concurrency test.
    """
    def __init__(self):
        self._roots = {}

    def apply(self, original, observation, metadata, assumptions):
        episode = metadata.get('episode_id')
        if not isinstance(episode, str) or not episode:
            return
        context = original.get('context')
        if not isinstance(context, dict):
            return
        cut = original.get('event_seq')
        root = self._roots.get(episode)
        if root is None and original.get('checkpoint') == 'P0' and type(cut) is int and cut > 0:
            ids_known = (all(isinstance(context.get(k), str) and context[k].strip()
                             for k in ('namespace', 'session_id', 'workflow_id'))
                and all(type(context.get(k)) is int and context[k] > 0 for k in ('vendor_id', 'invoice_id', 'current_vendor_id'))
                and context.get('current_vendor_id') == context.get('vendor_id'))
            facts, provenance = original.get('facts'), original.get('provenance')
            proven = ids_known and isinstance(facts, dict) and isinstance(provenance, dict)
            if proven:
                for field in ('vendor_in_scope', 'invoice_in_scope'):
                    proofs = provenance.get(field)
                    if facts.get(field) is not True or not isinstance(proofs, list):
                        proven = False
                        break
                    candidates = [p for p in proofs if isinstance(p, dict)
                        and type(p.get('event_seq')) is int]
                    if len(candidates) != len(proofs) or not candidates:
                        proven = False
                        break
                    newest = max(candidates, key=lambda p: p['event_seq'])
                    if (not 0 <= newest['event_seq'] < cut or newest.get('source') != 'server_context'
                        or newest.get('operation') != 'verified_worker_fixture_scope'
                        or newest.get('subject_matches') is not True or newest.get('value') is not True
                        or not isinstance(newest.get('record_id'), str) or not newest['record_id'].strip()
                        or not _scope_matches(newest, context)):
                        proven = False
                        break
            if proven:
                root = {'scope': {k: context[k] for k in ('namespace', 'session_id', 'workflow_id')},
                    'claim': {'record_id': 'counterfactual-admission/' + _token([episode, context['workflow_id']]),
                        'key': json.dumps([context['namespace'], 'invoice', context['invoice_id'], context['vendor_id']],
                                          separators=(',', ':')),
                        'owner_workflow_id': context['workflow_id'], 'generation': 1,
                        'state': 'active', 'acquired_seq': 0}, 'entry_seq': cut}
                self._roots[episode] = root
        if (root is None or type(cut) is not int or cut < root['entry_seq']
            or any(context.get(k) != value for k, value in root['scope'].items())):
            return
        replay_context = observation.get('context')
        if isinstance(replay_context, dict):
            _change(replay_context, 'claim', root['claim'], 'context', assumptions,
                'declared counterfactual admission before original source-verified P0; same episode/owner/root key reused, no historical claim asserted')


def archive_variant(row, metadata, mode='strict', unknown_portal='vendor', *, registry=None):
    """Return conditional offline replay plus per-field assumptions.

    Metadata supplies only the episode join key for an optional registry. It never
    supplies authorization, actor or financial facts. Without explicit stateful
    counterfactual admission, missing claims remain unknown. Human approval binding
    remains unknown; no cross-episode admission or concurrency is constructed.
    """
    if mode not in ('strict', 'session', 'technical'):
        raise ValueError('unknown archive replay mode')
    if unknown_portal not in ('vendor', 'admin'):
        raise ValueError('unknown_portal must select vendor or admin sensitivity branch')
    result = _wrapper(row)
    if mode == 'strict':
        return result
    observation, assumptions = result['observation'], result['assumptions']
    if not isinstance(observation, dict) or not isinstance(observation.get('context'), dict):
        return result  # Preserve malformed/null contexts; do not launder an invalid envelope.
    context = observation['context']
    seed = _token([row.get('prefix_id'), context.get('workflow_id'), context.get('record_id')])
    for key, value in (('record_id', 'replay-record/' + seed), ('session_id', 'replay-session/' + seed),
                       ('user_id', 'replay-user/' + seed), ('namespace', 'isolated-replay/' + seed),
                       ('origin_portal', unknown_portal)):
        _change(context, key, value, 'context', assumptions,
                'declared valid replay SessionContext infrastructure; known values preserved')
    facts, provenance = observation.get('facts'), observation.get('provenance')
    if isinstance(facts, dict) and isinstance(provenance, dict):
        proofs = provenance.get('session_valid')
        # Contradictory existing evidence and known false values remain unchanged.
        if (facts.get('session_valid') is None or facts.get('session_valid') is True) and (proofs is None or proofs == []):
            _change(facts, 'session_valid', True, 'facts', assumptions, 'declared valid replay SessionContext')
            proof = {k: context.get(k) for k in SCOPE}
            proof.update(source='server_context', event_seq=0, subject_matches=True, operation='session_validate',
                         record_id='replay-session-proof/' + seed, value=True,
                         evidence_kind='server_snapshot', snapshot_id='replay-session-snapshot/' + seed)
            _change(provenance, 'session_valid', [proof], 'provenance', assumptions,
                    'declared replay server validation; no historical authentication claimed') if proofs is None else None
            if proofs == []:
                provenance['session_valid'] = [proof]
                assumptions.append({'field': 'provenance.session_valid', 'old': [], 'new': copy.deepcopy([proof]),
                    'basis': 'declared replay server validation; no historical authentication claimed'})
        if mode == 'technical':
            result['original_provenance'] = copy.deepcopy(row.get('observation', row).get('provenance'))
            for field, proofs in provenance.items():
                if isinstance(proofs, list):
                    for index, proof in enumerate(proofs):
                        _origin(proof, field, index, context, seed, assumptions)
            if registry is not None:
                registry.apply(row.get('observation', row), observation, metadata, assumptions)
    return result
