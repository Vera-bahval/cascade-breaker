"""Validate and freeze adjudicated labels without opening method predictions."""
import collections
import copy
import json
from pathlib import Path
from validate_ratings import E, REQ, FIRST, check, rows, sha


def indexed(path):
    data = rows(path)
    result = {r['annotation_id']: r for r in data}
    if len(data) != len(result):
        raise ValueError(f'duplicate IDs in {path}')
    return result


def aggregate(requirements):
    states = [r['status'] for r in requirements]
    return 'BLOCK' if 'violated' in states else 'INSUFFICIENT' if 'unknown' in states else 'ALLOW'


def validate(row, case):
    key = case['annotation_id']
    if row['input_sha256'] != case['input_sha256']:
        raise ValueError(f'{key}: input hash')
    req = row['requirements']
    if set(req) != set(REQ):
        raise ValueError(f'{key}: requirement IDs')
    for name, value in req.items():
        if value['status'] not in ('satisfied', 'violated', 'unknown', 'not_applicable', 'not applicable'):
            raise ValueError(f'{key}: {name} status')
        if not value.get('rationale') or not value.get('evidence'):
            raise ValueError(f'{key}: {name} evidence/rationale')
    if row['status'] not in ('resolved', 'unresolved'):
        raise ValueError(f'{key}: annotation status')
    if row['status'] == 'unresolved':
        if row['label'] is not None:
            raise ValueError(f'{key}: unresolved label must be null')
    elif row['label'] != aggregate(req.values()):
        raise ValueError(f'{key}: overall aggregation')
    if row['core_label'] != aggregate([req[f'N{i:02d}'] for i in range(1, 9)]):
        raise ValueError(f'{key}: core aggregation')
    if not row.get('rationale'):
        raise ValueError(f'{key}: overall rationale')


def assemble():
    validation = check()
    if any(v.get('issues') or v.get('rows') != v.get('expected') for v in validation.values()):
        raise ValueError('independent ratings incomplete/invalid')
    manifest_path = E / 'custodian_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    cases = {r['annotation_id']: r for r in manifest['cases']}
    for key, case in cases.items():
        if sha(E/'action_inputs'/f'{key}.json') != case['input_sha256']:
            raise ValueError(f'{key}: changed action input bytes')
    intent_path = E / 'labels/intent-adjudicated.jsonl'
    category_path = E / 'labels/author-category-reviewed.jsonl'
    intents, categories = indexed(intent_path), indexed(category_path)
    n14_path = E/'labels/n14-final.jsonl'
    n14 = indexed(n14_path)
    expected_tax = {key for key in cases if json.loads((E/'supplementary_evidence/blind_inputs'/f'{key}.json').read_text()).get('precut_taxcalc_calls')}
    if set(n14) != expected_tax:
        raise ValueError('N14 targeted review must match every positive pre-cut call inventory')
    for key, review in n14.items():
        if review['input_sha256'] != cases[key]['input_sha256'] or review['n14_status'] not in ('satisfied','violated','unknown') or not review.get('evidence') or not review.get('rationale'):
            raise ValueError(f'{key}: N14 review schema/hash')
    if set(intents) != set(cases) or set(categories) != set(cases):
        raise ValueError('intent/category ID sets')
    if any(r['intent_label'] not in ('benign','attack','unknown') for r in intents.values()):
        raise ValueError('intent schema')
    if any(r['author_category'] not in ('legit','injection','policy','fraud','unknown') for r in categories.values()):
        raise ValueError('author category schema')
    sources = {str(p.relative_to(E)): sha(p) for p in (manifest_path, intent_path, category_path, E/'PROTOCOL.md', n14_path, E/'N14_CLARIFICATION.md', E/'N14_REVIEW.md')}
    output, comparisons = [], []
    for batch in range(1, 9):
        packet_path = E / f'adjudication/batch_{batch:02d}.json'
        receipt_path = E / f'adjudication/batch_{batch:02d}.freeze.json'
        adjud_path = E / f'labels/adjud-b{batch:02d}.jsonl'
        receipt = json.loads(receipt_path.read_text())
        if sha(packet_path) != receipt['package_sha256']:
            raise ValueError(f'batch {batch}: changed adjudication package')
        for path, digest in receipt['rater_sources'].items():
            if sha(Path(path)) != digest:
                raise ValueError(f'changed sealed rater {path}')
        assigned = {r['annotation_id'] for r in json.loads(packet_path.read_text())}
        adjudicated = indexed(adjud_path)
        if set(adjudicated) != assigned:
            raise ValueError(f'batch {batch}: adjudication incomplete, {len(adjudicated)}/{len(assigned)}')
        inherited = set(receipt['unreviewed_agreements'])
        pair_paths = [E/'labels'/f'{FIRST[batch]}.jsonl', E/'labels'/f'b{batch:02d}-r2.jsonl']
        if set(receipt['rater_sources']) != {str(p) for p in pair_paths}:
            raise ValueError(f'batch {batch}: rater source identity')
        first, second = [indexed(p) for p in pair_paths]
        if assigned & inherited or assigned | inherited != set(first) or set(first) != set(second):
            raise ValueError(f'batch {batch}: assignment partition')
        for p in (packet_path, receipt_path, adjud_path, *pair_paths):
            sources[str(p.relative_to(E))] = sha(p)
        for key in sorted(first):
            a, b = first[key], second[key]
            review = key in assigned
            if not review:
                if any(a.get(k)!=b.get(k) for k in ('status','label','core_label','semantic_label')) or any(a['requirements'][k]['status'].replace('_',' ')!=b['requirements'][k]['status'].replace('_',' ') for k in REQ):
                    raise ValueError(f'{key}: inherited disagreement')
            final = copy.deepcopy(adjudicated[key] if review else a)
            validate(final, cases[key])
            before_clarification = {'label': final['label'], 'status': final['status'], 'N14': final['requirements']['N14']}
            if key in n14:
                q = n14[key]
                final['requirements']['N14'] = {'status':q['n14_status'], 'evidence':q['evidence'], 'rationale':q['rationale']}
                if final['status'] == 'resolved':
                    final['label'] = aggregate(final['requirements'].values())
                final['rationale'] += ' Supplemental N14 review: '+q['rationale']
                validate(final, cases[key])
            comparisons.append({'annotation_id': key, 'first_label': a['label'], 'second_label': b['label'],
                                'final_label': final['label'], 'adjudicated': review,
                                'requirement_disagreements': [k for k in REQ if a['requirements'][k]['status'].replace('_',' ') != b['requirements'][k]['status'].replace('_',' ')]})
            output.append({'annotation_id': key, 'action_label': final['label'],
                'annotation_status': final['status'], 'core_label': final['core_label'],
                'semantic_label': aggregate([final['requirements'][k] for k in ('N09','N10','N11','N14')]),
                'scenario_intent': intents[key]['intent_label'], 'author_category': categories[key]['author_category'],
                'input_sha256': cases[key]['input_sha256'], 'requirements': final['requirements'],
                'rationale': final['rationale'], 'provenance': {
                    'action': str((adjud_path if review else pair_paths[0]).relative_to(E)),
                    'independent_ratings': [str(p.relative_to(E)) for p in pair_paths],
                    'action_selection': 'adjudicated' if review else 'two agreeing ratings, no third review',
                    'intent': str(intent_path.relative_to(E)), 'author_category': str(category_path.relative_to(E))}})
            if key in n14:
                output[-1]['provenance']['n14_clarification'] = str(n14_path.relative_to(E))
                output[-1]['before_n14_clarification'] = before_clarification
    if len(output) != 542 or {r['annotation_id'] for r in output} != set(cases):
        raise ValueError('final 542-case coverage')
    target = E/'labels/consensus.jsonl'
    receipt_path = E/'consensus-freeze.json'
    agreement = E/'labels/agreement.json'
    if target.exists() or receipt_path.exists() or agreement.exists():
        raise ValueError('refuse to overwrite frozen consensus')
    target.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True)+'\n' for r in sorted(output, key=lambda r:r['annotation_id'])))
    agreement.write_text(json.dumps(comparisons, ensure_ascii=False, indent=2)+'\n')
    receipt = {'cases': len(output), 'source_sha256': sources, 'consensus_sha256': sha(target),
        'assemble_sha256': sha(Path(__file__)), 'agreement_sha256': sha(agreement),
        'validator_sha256': sha(E/'validate_ratings.py'),
        'freeze_complete_when_receipt_present': True,
        'action_counts': dict(collections.Counter(r['action_label'] for r in output)),
        'status_counts': dict(collections.Counter(r['annotation_status'] for r in output)),
        'author_counts': dict(collections.Counter(r['author_category'] for r in output)),
        'adjudicated': sum(r['adjudicated'] for r in comparisons),
        'action_pair_agreement': sum(r['first_label']==r['second_label'] for r in comparisons),
        'method_outputs_read': False, 'annotation_type': 'posthoc independent Terra ratings; not human gold'}
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='source_sha256'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    assemble()
