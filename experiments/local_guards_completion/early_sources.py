"""Restore source-bound pre-cut events omitted from the saved early adapters."""
from bisect import bisect_left
from pathlib import Path
import json

from experiments.local_guards_adapter_repair.inventory import rows
from experiments.local_guards_final_replay import early

EXP = Path(__file__).resolve().parent.parent
REPAIR = EXP / 'local_guards_adapter_repair'


def source_events(episodes, raw_root):
    result = {}
    for episode, journal, initial, _ in early.raw_episodes(episodes, raw_root):
        legacy = initial is not None
        events = early.legacy_events(journal) if legacy else early.native_events(journal)
        eid = episode['episode_id']
        if eid in result:
            raise ValueError('duplicate early source episode')
        result[eid] = dict(events=events, sequences=[e['event_seq'] for e in events],
                           anchors=early.index_anchors(eid, events, legacy))
    if set(result) != {e['episode_id'] for e in episodes}:
        raise ValueError('missing early source episode')
    return result


def attach(row, source):
    anchor = source['anchors'].get(row['prefix_id'])
    bundle = row['bundle']
    if anchor is None or (anchor['event_seq'], anchor['checkpoint'], anchor['tool']) != (bundle['event_seq'], bundle['checkpoint'], bundle['proposal'].get('tool')):
        raise ValueError('early row/source boundary mismatch')
    boundary = dict(anchor['event'])
    # P0's first before-model record supplies the admitted request, not a model
    # response; P2's bound result is already strictly before its callback cut.
    boundary['source_event_seq'] = boundary['event_seq']
    boundary['event_seq'] = bundle['event_seq']
    raw = dict(events=source['events'][:bisect_left(source['sequences'], bundle['event_seq'])],
               proposed_action=boundary, initial_state=bundle['initial'])
    return dict(row, raw_context=raw)


def iter_early_rows():
    episodes = list(json.loads((REPAIR / 'inventory.json').read_text())['early_episodes'].values())
    sources = source_events(episodes, EXP.parent.parent / 'finbot-four-model-report')
    seen = set()
    for path in sorted((REPAIR / 'inputs').glob('early-inputs-*.jsonl.gz')):
        for row in rows(path):
            key = row['prefix_id'], row['mode']
            if key in seen or row['mode'] not in ('historical', 'conditional'):
                raise ValueError('duplicate/unknown early row mode')
            seen.add(key)
            yield attach(row, sources[row['episode_id']])
    if len(seen) != 37352:
        raise ValueError('incomplete early source/input coverage')
