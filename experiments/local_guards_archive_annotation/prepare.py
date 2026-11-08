#!/usr/bin/env python3
"""Build blind action inputs and custodian-only manifest from frozen archive views.

No case content, labels, predictions, or outcome sources are used for assignment.
"""
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'local_guards_archive_comparison'
VIEW = BASE / 'views/historical.jsonl.gz'
META = BASE / 'data/split-metadata.jsonl.gz'
SEED = 'finbot-p4-annotation-2026-11-03-v1'
EXPECTED = 542


def sha(data):
    return hashlib.sha256(data).hexdigest()


def token(domain, value):
    return sha((SEED + '\0' + domain + '\0' + value).encode())


def records(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def dump(path, value):
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    path.write_bytes(data)
    return sha(data)


def main():
    selected = [r for r in records(VIEW) if r['split'] == 'REPRESENTATIVE'
                and r['input']['checkpoint'] == 'P4'
                and r['input'].get('raw_context', {}).get('proposed_action', {}).get('source_event_kind') == 'before_tool_hook']
    ids = [r['case_id'] for r in selected]
    prefixes = [r['prefix_id'] for r in selected]
    if len(selected) != EXPECTED or len(set(ids)) != EXPECTED or len(set(prefixes)) != EXPECTED:
        raise SystemExit('STOP: selection count or case/prefix uniqueness mismatch')
    selected_prefixes = set(prefixes)
    metadata = [r for r in records(META) if r['prefix_id'] in selected_prefixes]
    if len(metadata) != EXPECTED or Counter(r['prefix_id'] for r in metadata) != Counter(prefixes):
        raise SystemExit('STOP: split metadata does not map one-to-one to prefixes')
    by_prefix = {r['prefix_id']: r for r in metadata}
    if any(not by_prefix[p].get('group_id') or by_prefix[p].get('split') != 'REPRESENTATIVE' for p in prefixes):
        raise SystemExit('STOP: missing group or inconsistent split')
    groups = {}
    for row in selected:
        group = by_prefix[row['prefix_id']]['group_id']
        groups.setdefault(group, []).append(row)
    # Largest groups first; seeded hash makes ties and ordering reproducible.
    batches = [[] for _ in range(8)]
    group_batch = {}
    for group in sorted(groups, key=lambda g: (-len(groups[g]), token('group-order', g))):
        index = min(range(8), key=lambda i: (len(batches[i]), token('batch-tie', group + ':' + str(i))))
        batches[index].extend(groups[group])
        group_batch[group] = index + 1
    action_dir = HERE / 'action_inputs'
    action_dir.mkdir(exist_ok=True)
    expected_names = set()
    manifest = []
    for row in sorted(selected, key=lambda r: token('order', r['case_id'])):
        ann_id = 'a-' + token('id', row['case_id'])[:24]
        filename = ann_id + '.json'
        expected_names.add(filename)
        digest = dump(action_dir / filename, row['input'])
        # Equality is of JSON values; whitespace and key order are intentionally canonicalized.
        if json.loads((action_dir / filename).read_text()) != row['input']:
            raise SystemExit('STOP: action input changed on serialization')
        meta = by_prefix[row['prefix_id']]
        manifest.append({'annotation_id': ann_id, 'case_id': row['case_id'],
                         'prefix_id': row['prefix_id'], 'group_id': meta['group_id'],
                         'batch': group_batch[meta['group_id']], 'input_sha256': digest})
    if {p.name for p in action_dir.iterdir()} != expected_names or len(expected_names) != EXPECTED:
        raise SystemExit('STOP: unexpected or colliding action files')
    # No source/fixture labels or intent metadata appear in the action input files.
    manifest_hash = dump(HERE / 'custodian_manifest.json', {'seed': SEED, 'cases': manifest})
    # Batch lists contain opaque IDs only. The two rounds use these same groups;
    # rater identity and independent round assignment are intentionally deferred.
    batch_hashes = {}
    batch_dir = HERE / 'batch_lists'
    batch_dir.mkdir(exist_ok=True)
    for i in range(1, 9):
        entries = [m['annotation_id'] for m in manifest if m['batch'] == i]
        batch_hashes[f'batch_{i:02}.json'] = dump(batch_dir / f'batch_{i:02}.json', entries)
    report = {'expected': EXPECTED, 'selected': len(selected), 'unique_cases': len(set(ids)),
              'unique_prefixes': len(set(prefixes)), 'groups': len(groups),
              'batch_sizes': [len(b) for b in batches], 'largest_group': max(map(len, groups.values())),
              'seed': SEED, 'view_sha256': sha(VIEW.read_bytes()), 'metadata_sha256': sha(META.read_bytes()),
              'manifest_sha256': manifest_hash, 'batch_list_sha256': batch_hashes,
              'selection': 'split=REPRESENTATIVE; input.checkpoint=P4; input.raw_context.proposed_action.source_event_kind=before_tool_hook',
              'scenario_source_evidence': 'not yet extracted; not assessed as unavailable',
              'round_assignment': 'not assigned'}
    dump(HERE / 'package_receipt.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
