"""Compare independent source reviews before freezing revised action targets."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
CHANGED = ('N09_process', 'N09_merit', 'N10_process', 'N10_merit', 'N11', 'N14')
STATES = {'satisfied', 'violated', 'unknown', 'not_applicable'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def aggregate(requirements):
    values = [r['status'] for r in requirements]
    if not values or any(x not in STATES for x in values):
        raise ValueError('missing/invalid requirement states')
    return 'BLOCK' if 'violated' in values else 'INSUFFICIENT' if 'unknown' in values else 'ALLOW'


def targets(core, revised):
    unchanged = list(core.values())
    process = unchanged + [revised[k] for k in ('N09_process', 'N10_process', 'N14')]
    substance = unchanged + [revised[k] for k in ('N09_merit', 'N10_merit', 'N11')]
    return dict(process_label=aggregate(process), substantive_label=aggregate(substance),
                action_label=aggregate(process + substance),
                without_tax_label=aggregate(unchanged + [revised[k] for k in CHANGED if k != 'N14']))


def compare():
    import gzip
    packets = {}; samples = []
    for batch in range(4):
        with gzip.open(HERE / f'review-batch-{batch}.jsonl.gz', 'rt') as f:
            expected = {r['annotation_id']: r for r in map(json.loads, f)}
        sides = []
        for side in 'ab':
            path = HERE / f'labels-{side}{batch}.jsonl'
            data = rows(path)
            by_id = {r['annotation_id']: r for r in data}
            assert len(data) == len(by_id) and set(by_id) == set(expected), (path, len(data), len(expected))
            for aid, row in by_id.items():
                p = expected[aid]
                assert row['prefix_id'] == p['prefix_id'] and row['read_input_sha256'] == p['input_sha256']
                assert sha(p['source_input']) == p['input_sha256']
                for key in CHANGED:
                    r = row['requirements'][key]
                    assert r['status'] in STATES and r['evidence'] and r['rationale'], (aid, key)
                assert row['source_intent'] in ('benign', 'attack', 'ambiguous')
            sides.append(by_id)
        batch_packets = []
        for aid, p in expected.items():
            a, b = [s[aid] for s in sides]
            differences = [k for k in CHANGED if a['requirements'][k]['status'] != b['requirements'][k]['status']]
            if a['source_intent'] != b['source_intent']:
                differences.append('source_intent')
            packets[aid] = dict(annotation_id=aid, prefix_id=p['prefix_id'], source_input=p['source_input'],
                                input_sha256=p['input_sha256'], inherited_core=p['inherited_core'], differences=differences, a=a, b=b)
            batch_packets.append(packets[aid])
        agreed = sorted(r['annotation_id'] for r in batch_packets if not r['differences'])
        sample = random.Random(17+batch).sample(agreed, min(8, len(agreed)))
        samples.extend(sample)
        selected = [r for r in batch_packets if r['differences'] or r['annotation_id'] in sample]
        path = HERE / f'adjudication-inputs-{batch}.jsonl'
        if path.exists():
            assert rows(path) == selected, 'changed adjudication input'
        else:
            path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in selected))
    assert len(packets) == 542
    disagreements = [r for r in packets.values() if r['differences']]
    (HERE / 'review-comparison.json').write_text(json.dumps(dict(n=542, status_agreements=542-len(disagreements),
        disagreements=len(disagreements), by_requirement=dict(Counter(k for r in disagreements for k in r['differences'])),
        audited_agreement_ids=samples, source_sha256={p.name: sha(p) for p in HERE.glob('labels-*.jsonl')}), indent=2)+'\n')
    print('cases', len(packets), 'disagreements', len(disagreements), 'agreement_sample', len(samples))
    return packets


def freeze():
    packets = compare()
    path = HERE/'labels.jsonl'
    if path.exists():
        raise FileExistsError(path)
    judged = {}; expanded = set()
    for batch in range(4):
        selected = {r['annotation_id']:r for r in rows(HERE/f'adjudication-inputs-{batch}.jsonl')}
        data = rows(HERE/f'adjudicated-{batch}.jsonl')
        assert len(data) == len(selected) and {r['annotation_id'] for r in data} == set(selected)
        for r in data:
            p = selected[r['annotation_id']]
            assert r['prefix_id'] == p['prefix_id'] and r['read_input_sha256'] == p['input_sha256']
            assert r['adjudication_reason']
            for key in CHANGED:
                req = r['requirements'][key]
                assert req['status'] in STATES and req['evidence'] and req['rationale']
            judged[r['annotation_id']] = r
    extra_inputs = {r['annotation_id']:r for r in rows(HERE/'extra-agreement-inputs.jsonl')}
    extra = rows(HERE/'extra-adjudicated.jsonl')
    assert len(extra) == len(extra_inputs) and {r['annotation_id'] for r in extra} == set(extra_inputs)
    for r in extra:
        aid = r['annotation_id']; p = extra_inputs[aid]
        assert aid not in judged and r['prefix_id'] == p['prefix_id'] and r['read_input_sha256'] == p['input_sha256']
        assert r['adjudication_reason']
        for key in CHANGED:
            req = r['requirements'][key]
            assert req['status'] in STATES and req['evidence'] and req['rationale']
        judged[aid] = r; expanded.add(aid)
    corrections = {r['annotation_id']:r for r in rows(HERE/'core-corrections.jsonl')}
    assert len(corrections) == 4
    readlogs = list(HERE.glob('readlog-*.jsonl')) + list(HERE.glob('adjudication-readlog-*.jsonl')) + [HERE/'extra-adjudication-readlog.jsonl']
    for log in readlogs:
        data = rows(log)
        assert len(data) == len({r['annotation_id'] for r in data})
        for r in data:
            aid = r['annotation_id']; p = packets[aid]
            assert r['source_input_sha256'] == p['input_sha256'] and r['reviewed'] is True
            assert r['policy_refs'] and r['relevant_event_seqs']
    counts = Counter()
    with path.open('x') as out:
        for aid,p in sorted(packets.items()):
            selected = judged.get(aid,p['a'])
            requirements = {k:selected['requirements'][k] for k in CHANGED}
            core = dict(p['inherited_core'])
            if aid in corrections:
                correction = corrections[aid]; key = correction['requirement']
                assert correction['prefix_id'] == p['prefix_id'] and core[key]['status'] == correction['previous_status']
                assert correction['status'] in STATES and correction['evidence'] and correction['rationale']
                core[key] = {k:correction[k] for k in ('status','evidence','rationale','assumptions')}
            row = dict(annotation_id=aid,prefix_id=p['prefix_id'],input_sha256=p['input_sha256'],
                requirements=requirements,inherited_core=p['inherited_core'],core_requirements=core,
                **targets(core,requirements), source_intent=selected['source_intent'],
                source_intent_reason=selected['source_intent_reason'],
                provenance='expanded_agreement_audit' if aid in expanded else 'third_review' if aid in judged else 'independent_agreement',
                initial_disagreements=p['differences'])
            out.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
            counts[row['action_label']] += 1
    sources = list(HERE.glob('labels-*.jsonl')) + list(HERE.glob('readlog-*.jsonl')) + list(HERE.glob('adjudicated-*.jsonl')) + list(HERE.glob('adjudication-readlog-*.jsonl')) + [HERE/'extra-adjudicated.jsonl',HERE/'extra-adjudication-readlog.jsonl',HERE/'core-corrections.jsonl']
    freeze = dict(n=542,labels_sha256=sha(path),counts=dict(counts),adjudicated=len(judged),
        protocol_sha256=sha(HERE/'PROTOCOL.md'),clarifications_sha256=sha(HERE/'REVIEW_CLARIFICATIONS.md'),
        code_sha256=sha(Path(__file__)),sources={p.name:sha(p) for p in sources},
        limit='Model-assisted retrospective labels on disclosed archive; not human gold, no technical rater isolation.')
    (HERE/'labels-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    print('FROZEN',dict(counts))


if __name__ == '__main__':
    import sys
    freeze() if '--freeze' in sys.argv else compare()
