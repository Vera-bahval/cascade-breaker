"""Restore missing session/actor links without changing canonical financial data.

Original archive hashes and journal identities are checked by raw_episodes. Only
technical headers are retained in the cache; arguments/results and model outputs
are never copied into canonical packets. Call/workflow aliases remain untouched.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from experiments.local_guards_adapter_repair.inventory import rows, sha
from experiments.local_guards_final_replay import early

EXP = Path(__file__).resolve().parent.parent
INVENTORY = EXP / 'local_guards_adapter_repair/inventory.json'
METADATA = EXP / 'local_guards_archive_comparison/data/metadata.jsonl.gz'
COLLECTOR = EXP / 'local_guards_archive_comparison/data/collector-manifest.json'
RAW_ROOT = EXP.parent.parent / 'finbot-four-model-report'
LINK_FIELDS = ('session_id', 'agent_name')
ROLES = {'orchestrator', 'invoice', 'fraud', 'payments', 'onboarding', 'communication',
         'system_maintenance', 'vendor_chat', 'admin_chat'}


def header(event):
    result = {key: event[key] for key in ('event_seq', 'hook_kind', 'tool_name', *LINK_FIELDS) if key in event}
    args = event.get('tool_arguments') or {}
    if isinstance(args, dict):
        result['subject'] = {key: args[key] for key in ('invoice_id', 'vendor_id') if key in args}
    return result


def key(event):
    return event['event_seq'], event.get('hook_kind'), event.get('tool_name')


def build_sources(episodes, raw_root=RAW_ROOT):
    result = {}
    for episode, journal, initial, _ in early.raw_episodes(episodes, raw_root):
        legacy = initial is not None
        events = early.legacy_events(journal) if legacy else early.native_events(journal)
        if legacy:
            # The reused early converter intentionally omits P4 callbacks.
            for step in journal:
                if step.get('kind') == 'guard_context' and str(step.get('point', '')).split('.')[0] == 'P4':
                    payload = step.get('payload') or {}
                    events.append(dict(event_seq=step['seq'] * 2 + 1, hook_kind='before_tool',
                        tool_name=payload.get('tool'), tool_arguments=payload.get('arguments') or {},
                        agent_name=step.get('agent'), session_id=step.get('session_id')))
        headers = {}
        for event in events:
            identity = key(event)
            if identity in headers:
                raise ValueError('duplicate source event coordinate')
            headers[identity] = header(event)
        eid = episode['episode_id']
        if eid in result:
            raise ValueError('duplicate source episode')
        result[eid] = dict(episode_id=eid, legacy=legacy, headers=headers)
    if set(result) != {e['episode_id'] for e in episodes}:
        raise ValueError('missing source episode')
    return result


@lru_cache(maxsize=1)
def source_index():
    episodes = list(json.loads(INVENTORY.read_text())['early_episodes'].values())
    metadata = {}
    for record in rows(METADATA):
        if record['checkpoint'] != 'P4':
            continue
        if record['prefix_id'] in metadata:
            raise ValueError('duplicate P4 source metadata')
        metadata[record['prefix_id']] = record
    return dict(metadata=metadata, episodes=build_sources(episodes))


def source_manifest():
    """Pinned bindings; raw_episodes verifies source archives on cache creation."""
    return dict(code_sha256=sha(Path(__file__)),
        input_sha256={str(p.resolve()): sha(p) for p in (INVENTORY, METADATA, COLLECTOR)},
        scope='Only missing session_id/agent_name restored at verified existing coordinates; source sessions become opaque tokens; no financial values, tool results or model outputs restored.')


def restore(row, source, metadata):
    bundle = row['bundle']
    cut = bundle['event_seq']
    if (row['prefix_id'] != metadata['prefix_id'] or metadata['checkpoint'] != 'P4'
            or metadata['event_seq'] != cut or metadata['episode_id'] != source['episode_id']):
        raise ValueError('foreign or mismatched P4 source metadata')
    native = row['adapters']['native']['payload']
    raw = native['raw_context']
    action = raw['proposed_action']
    if action.get('event_seq') != cut or action.get('tool_name') != bundle['proposal'].get('tool'):
        raise ValueError('P4 action/cut mismatch')
    source_action = source['headers'].get((cut, 'before_tool', action.get('tool_name')))
    if source_action is None:
        raise ValueError('missing actual P4 source anchor')
    for field in ('invoice_id', 'vendor_id'):
        actual = (source_action.get('subject') or {}).get(field)
        expected = bundle['context'].get(field)
        if actual is not None and expected is not None and (type(actual) is not type(expected) or actual != expected):
            raise ValueError('foreign P4 source anchor subject')
    pairs = []
    for event in raw['events']:
        if type(event.get('event_seq')) is not int or not 0 <= event['event_seq'] < cut:
            raise ValueError('future or invalid P4 prefix coordinate')
        actual = source['headers'].get(key(event))
        if actual is None:
            derived = source['legacy'] and (event.get('hook_kind') == 'after_model' or
                event.get('hook_kind') == 'before_tool' and event.get('source_event_kind') == 'recorded_model_proposal')
            if not derived:
                raise ValueError('canonical event/source header mismatch')
            continue
        args = event.get('tool_arguments') or {}
        for field, value in (actual.get('subject') or {}).items():
            if field in args and (type(value) is not type(args[field]) or value != args[field]):
                raise ValueError('canonical event/source subject mismatch')
        pairs.append((event, actual))
    pairs.append((action, source_action))
    sessions = {}
    for event, actual in pairs:
        before, after = actual.get('session_id'), event.get('session_id')
        if isinstance(before, str) and before and isinstance(after, str) and after:
            if before in sessions and sessions[before] != after:
                raise ValueError('conflicting canonical session aliases')
            sessions[before] = after
    replacement = deepcopy(row)
    target_raw = replacement['adapters']['native']['payload']['raw_context']
    targets = {id(original): copied for original, copied in zip(raw['events'], target_raw['events'], strict=True)}
    targets[id(action)] = target_raw['proposed_action']
    for event, actual in pairs:
        target = targets[id(event)]
        session = actual.get('session_id')
        if not target.get('session_id') and isinstance(session, str) and session:
            target['session_id'] = sessions.get(session) or 'session/' + hashlib.sha256(('session_id\0' + session).encode()).hexdigest()[:24]
        role = actual.get('agent_name')
        if not target.get('agent_name') and isinstance(role, str) and role.removesuffix('_agent') in ROLES:
            target['agent_name'] = role
    return replacement


def restore_links(row):
    index = source_index()
    metadata = index['metadata'].get(row['prefix_id'])
    if metadata is None:
        raise ValueError('missing P4 metadata')
    source = index['episodes'].get(metadata['episode_id'])
    if source is None:
        raise ValueError('P4 episode absent from verified source inventory')
    return restore(row, source, metadata)
