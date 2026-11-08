"""Bounded reviewer packets; no method predictions or old final labels."""
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANNOTATION = HERE.parent / 'local_guards_archive_annotation'


def run():
    manifest = json.loads((ANNOTATION / 'custodian_manifest.json').read_text())
    old = {r['annotation_id']: r for r in map(json.loads, (ANNOTATION / 'labels/consensus.jsonl').read_text().splitlines())}
    batches = [[] for _ in range(4)]
    ordered = sorted(manifest['cases'], key=lambda r: hashlib.sha256(r['annotation_id'].encode()).hexdigest())
    for i, case in enumerate(ordered):
        path = ANNOTATION / 'action_inputs' / (case['annotation_id'] + '.json')
        assert hashlib.sha256(path.read_bytes()).hexdigest() == case['input_sha256']
        data = json.loads(path.read_text())
        packet = dict(case, source_input=str(path), checkpoint=data['checkpoint'], event_seq=data['event_seq'],
                      observation=data['observation'], evidence_status=data['evidence_status'],
                      inherited_core={k: v for k, v in old[case['annotation_id']]['requirements'].items() if k in {f'N{x:02d}' for x in range(1, 9)}})
        # All raw pre-cut evidence stays available in source_input; no outcome is added.
        packet['events'] = [e for e in data['raw_context']['events'] if e.get('tool_name')]
        packet['proposed_action'] = data['raw_context']['proposed_action']
        batches[i % 4].append(packet)
    for i, batch in enumerate(batches):
        path = HERE / f'review-batch-{i}.jsonl.gz'
        if path.exists():
            raise FileExistsError(path)
        with gzip.open(path, 'wt') as f:
            for row in batch:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
    (HERE / 'review-manifest.json').write_text(json.dumps(dict(cases=len(ordered), protocol_sha256=hashlib.sha256((HERE/'PROTOCOL.md').read_bytes()).hexdigest(), batches={f'review-batch-{i}.jsonl.gz': dict(count=len(b), sha256=hashlib.sha256((HERE/f'review-batch-{i}.jsonl.gz').read_bytes()).hexdigest()) for i,b in enumerate(batches)}), indent=2) + '\n')
    print([len(b) for b in batches])


if __name__ == '__main__':
    run()
