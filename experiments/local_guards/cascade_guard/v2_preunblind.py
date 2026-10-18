"""Read-only integrity/identity gate around the immutable v2 scorer.

No model imports. Label files are opened only after an explicit root UNBLIND
marker binds their hash and the prediction-freeze hash. This module never
creates that authorization and never changes an existing experiment artifact.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys


class IntegrityError(ValueError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def jsonl(path):
    with Path(path).open() as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def require(condition, reason):
    if not condition:
        raise IntegrityError(reason)


def verify_entry(entry):
    path = Path(entry['path'])
    require(path.is_file(), 'Pinned file is missing')
    require(sha(path) == entry['sha256'], 'Pinned file hash changed')


def arm(row):
    return tuple(row[k] for k in ('policy', 'denominator', 'seed', 'arm'))


def validate(methods, destination, *, expected_rows=None, labels=None, unblind_marker=None):
    """Validate hashes and observation identities; optionally prevalidate labels.

    Report only counts and hashes, never observation fields or label values.
    Merely supplying a label path does not authorize opening it.
    """
    methods, destination = Path(methods), Path(destination)
    require(not (destination / 'metrics.json').exists(), 'Already unblinded or partial metrics exist')
    require(not (destination / 'UNBLINDED.json').exists(), 'Already unblinded')
    pf_path = destination / 'PREDICTIONS_FROZEN.json'
    pf = read(pf_path)
    mf_path = methods / 'METHODS_FROZEN.json'
    require(sha(mf_path) == pf['methods_freeze_sha256'], 'Methods freeze differs from prediction freeze')
    mf = read(mf_path)
    for entry in mf['files']:
        verify_entry(entry)
    training = read(methods / 'training-input-freeze.json')
    for entry in training['files']:
        verify_entry(entry)
    verify_entry(pf['rows_file'])
    for entry in pf['records']:
        verify_entry(entry)
    pred_path = destination / 'predictions.jsonl'
    require(sha(pred_path) == pf['predictions_sha256'], 'Predictions changed')

    # Observation admission here is identity/count only; no feature values,
    # policy observations, model probabilities or labels enter decisions.
    rows = {}
    episodes = set()
    for row in jsonl(pf['rows_file']['path']):
        pid, eid = row['prefix_id'], row['episode_id']
        require(pid not in rows, 'Duplicate observable prefix')
        require(eid not in episodes, 'Expected one P4 observation per episode')
        require(not {'label', 'strict_harm', 'family', 'contract_requires_intervention'} & row.keys(), 'Evaluation metadata in observable rows')
        rows[pid] = (eid, row['cut_seq'])
        episodes.add(eid)
    require(bool(rows), 'Empty observable population')
    if expected_rows is not None:
        require(len(rows) == expected_rows, 'Observable count differs from expected count')

    records = {}
    block_ids = defaultdict(set)
    schema_blocks = set()
    for entry in pf['records']:
        for record in jsonl(entry['path']):
            key = record['prefix_id'], record['block']
            fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            require(key not in records or records[key] == fingerprint, 'Conflicting feature identity')
            records[key] = fingerprint
            # Match immutable cheap_eval.load_records: only an OK feature row
            # establishes an available numeric schema. All-UNKNOWN blocks do
            # not support a model merely because explicit rows are present.
            if record.get('status') == 'OK':
                schema_blocks.add(key[1])
            if key[0] in rows:
                block_ids[key[1]].add(key[0])
    for ids in block_ids.values():
        require(ids == set(rows), 'Partially present feature block: explicit records required for every observation')

    choices = read(methods / 'final-choices.json')
    models = {(m['seed'], m['config']): m for m in read(methods / 'models.json')}
    expected_arms = set()
    available = set(block_ids) & schema_blocks
    for choice in choices:
        model = models.get((choice['seed'], choice['config']))
        require(model is not None, 'Choice has no frozen model')
        if set(model['blocks']) <= available:
            expected_arms.add(arm(choice))
    for policy, denominator, seed in {(c['policy'], c['denominator'], c['seed']) for c in choices}:
        expected_arms.update((policy, denominator, seed, name) for name in ('NoDefense', 'R1', 'R2'))
    require(bool(expected_arms), 'No expected frozen arms')

    grouped = defaultdict(set)
    prediction_episodes = defaultdict(set)
    for prediction in jsonl(pred_path):
        pid = prediction['prefix_id']
        require(pid in rows, 'Prediction references an unknown prefix')
        require((prediction['episode_id'], prediction['cut_seq']) == rows[pid], 'Prediction/observation episode or cutoff mismatch')
        key = arm(prediction)
        require(pid not in grouped[key], 'Duplicate prediction prefix within arm')
        require(isinstance(prediction['block'], bool) and isinstance(prediction['unknown'], bool), 'Prediction decisions must be booleans')
        require(not prediction['unknown'] or prediction['block'], 'UNKNOWN must stop')
        probability = prediction.get('probability')
        require(probability is None or (not isinstance(probability, bool) and isinstance(probability, (int, float)) and math.isfinite(probability) and 0 <= probability <= 1), 'Invalid prediction score')
        grouped[key].add(pid)
        prediction_episodes[key].add(prediction['episode_id'])
    require(set(grouped) == expected_arms, 'Prediction arm set differs from frozen available models and controls')
    require(all(ids == set(rows) for ids in grouped.values()), 'Incomplete prediction arm')
    require(all(ids == episodes for ids in prediction_episodes.values()), 'Prediction episode set differs')

    report = {'status': 'PASS_OBSERVATION_IDENTITIES_AND_HASHES', 'rows': len(rows),
              'arms': len(grouped), 'feature_blocks': len(available), 'labels_opened': False,
              'prediction_freeze_sha256': sha(pf_path), 'methods_freeze_sha256': sha(mf_path),
              'predictions_sha256': sha(pred_path)}
    if labels is not None:
        require(unblind_marker is not None, 'Root UNBLIND marker required before label access')
        marker = read(unblind_marker)
        require(marker.get('authorization') == 'UNBLIND', 'Root marker does not authorize UNBLIND')
        require(marker.get('predictions_freeze_sha256') == sha(pf_path), 'Root marker binds another prediction freeze')
        # Hashing is permitted only after authorization; parse labels afterwards.
        require(marker.get('labels_sha256') == sha(labels), 'Root marker binds another label file')
        annotations = list(jsonl(labels))
        by = {item['episode_id']: item for item in annotations}
        require(len(by) == len(annotations) and set(by) == episodes, 'Label identities do not match observations exactly')
        require(all(isinstance(item.get('contract_requires_intervention'), bool) for item in annotations), 'Invalid static intervention target')
        has_pairs = all(item.get('pair_id') for item in annotations)
        require(len(rows) != 240 or has_pairs, 'Independent240 requires explicit matched pair identities')
        pairs = defaultdict(list)
        if has_pairs:
            for item in annotations:
                pairs[item['pair_id']].append(item)
            for pair in pairs.values():
                require(len(pair) == 2 and {item['contract_requires_intervention'] for item in pair} == {False, True}, 'Pair must have exactly two opposite intervention targets')
                require(len({item.get('family') for item in pair}) == 1, 'Pair crosses family identities')
            if len(rows) == 240:
                require(len(pairs) == 120, 'Independent240 requires 120 pair groups')
                family_counts = defaultdict(int)
                for item in annotations:
                    require(isinstance(item.get('family'), str) and bool(item['family']), 'Missing independent family identity')
                    family_counts[item['family']] += 1
                require(len(family_counts) == 6 and set(family_counts.values()) == {40}, 'Independent240 requires six families with 40 observations each')
        report.update(status='PASS_AUTHORIZED_LABEL_JOINS_AND_PAIRS', labels_opened=True,
                      labels_sha256=sha(labels), pair_count=len(pairs),
                      authorization_sha256=sha(unblind_marker))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--methods', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--expected-rows', type=int)
    parser.add_argument('--labels', type=Path)
    parser.add_argument('--unblind-marker', type=Path)
    parser.add_argument('--score', action='store_true', help='Invoke immutable scorer only after authorized full prevalidation')
    args = parser.parse_args()
    require(not args.score or args.labels is not None, 'Scoring requires authorized label prevalidation')
    report = validate(args.methods, args.destination, expected_rows=args.expected_rows,
                      labels=args.labels, unblind_marker=args.unblind_marker)
    print(json.dumps(report, sort_keys=True), flush=True)
    if args.score:
        command = [sys.executable, '-m', 'cascade_guard.v2_eval', 'score',
                   '--output', str(args.methods), '--destination', str(args.destination),
                   '--labels', str(args.labels)]
        # No local training/refitting or alternate scorer is introduced.
        return subprocess.run(command, check=False).returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
