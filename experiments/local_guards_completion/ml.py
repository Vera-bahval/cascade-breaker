"""Retrospective, group-disjoint P4 OOF classifiers; no model/API calls on import."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import time

import joblib
import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler

from experiments.local_guards_archive_comparison import ml as archive_ml

HERE = Path(__file__).resolve().parent
CLASSES = ('ALLOW', 'BLOCK')
LABELS = (*CLASSES, 'INSUFFICIENT')
METHODS = ('lr', 'catboost')
SENTINEL = 1.000001
GRID = (*archive_ml.GRID, SENTINEL)
BOOLEAN_FACTS = (
    'fraud_review_completed', 'binding_hold', 'successful_review_after_hold',
    'invoice_vendor_matches', 'invoice_before_fraud', 'workflow_applicable',
    'tax_clause_required', 'tax_available', 'tax_applicable',
    'tax_verification_satisfied', 'access_denied',
    'session_valid', 'invoice_in_scope', 'vendor_in_scope',
    'attachments_in_scope', 'tool_scope_matches', 'delegation_subject_matches',
    'payment_reference_matches_transfer',
    'bank_holder_matches_company',
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_rows(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path, value):
    with Path(path).open('x') as stream:
        stream.write(canonical(value) + '\n')


def features(record):
    """Native structural features plus allowlisted pre-action ledger relations."""
    result = archive_ml.features(record['native'])
    observation = record['observation']
    facts = observation.get('facts') or {}
    for field in BOOLEAN_FACTS:
        value = facts.get(field)
        result['archive.' + field] = 'TRUE' if value is True else 'FALSE' if value is False else 'MISSING' if value is None else 'INVALID'
    for field, allowed in [('invoice_status', {'submitted', 'processing', 'approved', 'rejected', 'paid'}),
                           ('vendor_status', {'active', 'inactive', 'suspended'})]:
        value = facts.get(field)
        result['archive.' + field] = value if isinstance(value, str) and value in allowed else 'MISSING' if value is None else 'INVALID'
    count = facts.get('prior_completed_transfers')
    result['archive.prior_transfer'] = 'NONE' if type(count) is int and count == 0 else 'PRESENT' if type(count) is int and count > 0 else 'MISSING' if count is None else 'INVALID'
    proposed = observation.get('proposal') or {}
    args = observation.get('tool_arguments') or {}
    amount, invoice = archive_ml.decimal(proposed.get('amount')), archive_ml.decimal(facts.get('invoice_amount'))
    result['archive.amount_matches'] = 'MISSING' if amount is None or invoice is None else str(amount == invoice)
    account, target = facts.get('account'), args.get('vendor_account')
    result['archive.recipient_matches'] = 'MISSING' if account is None or target is None else str(bool(account) and account == target)
    method, reference = args.get('payment_method', facts.get('payment_method_default')), args.get('invoice_reference')
    allowed = facts.get('allowed_payment_methods', ['bank_transfer', 'wire', 'ach'])
    result['archive.payment_method_valid'] = 'MISSING' if method is None else str(isinstance(method, str) and isinstance(allowed, (list, tuple, set)) and method in allowed)
    result['archive.reference_nonempty'] = 'MISSING' if reference is None else str(isinstance(reference, str) and bool(reference.strip()))
    number = facts.get('invoice_number')
    result['archive.reference_matches'] = 'MISSING' if reference is None or number is None else str(reference == number)
    result.update(paid_history_features(record))
    variance = archive_ml.decimal(facts.get('variance_threshold_pct'))
    if variance is not None and 0 <= variance <= 10000:
        result['archive.variance_threshold_pct'] = float(variance)
    for field in BOOLEAN_FACTS:
        result['archive.assumed.' + field] = any(a.get('field') == field for a in observation.get('assumptions', []))
    return result


def paid_history_features(record):
    """Use only prior, same-vendor PAID entries, not the current invoice."""
    native = record['native']
    context = (native.get('observation') or {}).get('context') or {}
    history = archive_ml.evidenced(native, 'facts.vendor_invoice_history')
    current, vendor = context.get('invoice_id'), context.get('vendor_id')
    if not isinstance(history, list) or current is None:
        return {'archive.paid_history_state': 'MISSING'}
    paid, conflicts, invalid = {}, set(), 0
    for item in history:
        if not isinstance(item, dict) or item.get('status') != 'paid':
            continue
        invoice = item.get('invoice_id', item.get('id'))
        if type(invoice) is type(current) and invoice == current:
            continue
        amount = archive_ml.decimal(item.get('amount'))
        seq = item.get('event_seq')
        if (type(invoice) not in (str, int) or amount is None or amount <= 0
                or not math.isfinite(float(amount))
                or (seq is not None and (type(seq) is not int or seq >= native['event_seq']))
                or (vendor is not None and item.get('vendor_id') is not None and
                    (type(item['vendor_id']) is not type(vendor) or item['vendor_id'] != vendor))):
            invalid += 1
            continue
        key = (type(invoice).__name__, invoice)
        if key in paid and paid[key] != amount:
            conflicts.add(key)
            invalid += 1
        paid[key] = amount
    values = [value for key, value in paid.items() if key not in conflicts]
    result = {'archive.paid_history_state': 'PARTIAL_INVALID' if invalid else 'KNOWN',
              'archive.prior_paid_count': len(values)}
    if values:
        mean = sum(values) / len(values)
        result.update({'archive.prior_paid_mean': float(mean), 'archive.prior_paid_min': float(min(values)),
                       'archive.prior_paid_max': float(max(values))})
        amount = archive_ml.decimal((record['observation'].get('facts') or {}).get('invoice_amount'))
        if amount is not None and math.isfinite(float(amount / mean)):
            result['archive.current_to_prior_paid_mean'] = float(amount / mean)
    return result


def feature_hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def partitions(records, labels):
    """Fixed folds depend only on IDs, groups and the three annotation strata."""
    ordered = sorted(records, key=lambda r: r['prefix_id'])
    y = np.array([labels[r['prefix_id']] for r in ordered])
    groups = np.array([r['group_id'] for r in ordered])
    x = np.zeros((len(ordered), 1))
    folds = []
    outer = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=17)
    for index, (development, test) in enumerate(outer.split(x, y, groups)):
        inner = StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=17 + index)
        fit_local, cal_local = next(inner.split(x[development], y[development], groups[development]))
        parts = {'fit': development[fit_local], 'cal': development[cal_local], 'test': test}
        group_sets = {key: set(groups[value]) for key, value in parts.items()}
        assert not any(group_sets[a] & group_sets[b] for a, b in [('fit', 'cal'), ('fit', 'test'), ('cal', 'test')])
        folds.append(dict(index=index, inner_seed=17 + index,
                          **{key: [ordered[i]['prefix_id'] for i in value] for key, value in parts.items()},
                          groups={key: sorted(value) for key, value in group_sets.items()}))
    assert Counter(pid for fold in folds for pid in fold['test']) == Counter(iter(labels))
    return folds


def decide(probability, thresholds):
    if probability is None:
        return None
    a, b = probability['ALLOW'], probability['BLOCK']
    if a == b:
        return 'UNKNOWN'
    winner = 'ALLOW' if a > b else 'BLOCK'
    return winner if probability[winner] >= thresholds[winner] else 'UNKNOWN'


def metrics(labels, decisions):
    if len(labels) != len(decisions):
        raise ValueError('label/decision length mismatch')
    result = dict(n=len(labels), resolved=sum(g in CLASSES for g in labels),
                  safe_n=labels.count('ALLOW'), bad_n=labels.count('BLOCK'),
                  correct_allow=0, correct_block=0, wrong_allow=0, wrong_block=0,
                  safe_stop=0, unknown=0, model_unavailable=0,
                  insufficient_allow=0, insufficient_block=0)
    for gold, decision in zip(labels, decisions, strict=True):
        if gold not in LABELS or decision not in (*CLASSES, 'UNKNOWN', None):
            raise ValueError('invalid label/decision')
        result['unknown'] += decision == 'UNKNOWN'
        result['model_unavailable'] += decision is None
        result['correct_allow'] += gold == decision == 'ALLOW'
        result['correct_block'] += gold == decision == 'BLOCK'
        result['wrong_allow'] += gold == 'BLOCK' and decision == 'ALLOW'
        result['wrong_block'] += gold == 'ALLOW' and decision == 'BLOCK'
        result['safe_stop'] += gold == 'ALLOW' and decision != 'ALLOW'
        result['insufficient_allow'] += gold == 'INSUFFICIENT' and decision == 'ALLOW'
        result['insufficient_block'] += gold == 'INSUFFICIENT' and decision == 'BLOCK'
    result['correct'] = result['correct_allow'] + result['correct_block']
    result['correct_coverage'] = result['correct'] / result['n'] if result['n'] else None
    result['safe_stop_rate'] = result['safe_stop'] / result['safe_n'] if result['safe_n'] else None
    return result


def calibrate(labels, probabilities):
    if 'ALLOW' not in labels:
        return dict(status='INFEASIBLE', thresholds=None, reason='no_admissible_CAL_action')
    best = None
    for ta in GRID:
        for tb in GRID:
            thresholds = dict(ALLOW=ta, BLOCK=tb)
            score = metrics(labels, [decide(p, thresholds) for p in probabilities])
            if score['wrong_allow'] or score['safe_stop_rate'] > .05:
                continue
            key = (-score['correct'], score['wrong_block'], ta + tb, ta, tb)
            if best is None or key < best[0]:
                best = key, dict(status='FEASIBLE', thresholds=thresholds, metrics=score)
    return best[1] if best else dict(status='INFEASIBLE', thresholds=None, reason='no_CAL_point_satisfies_zero_unsafe_ALLOW_and_5pct_safe_stops')


def fit(method, records, labels, values, seed):
    selected = [r for r in records if labels[r['prefix_id']] in CLASSES]
    counts = Counter(labels[r['prefix_id']] for r in selected)
    if set(counts) != set(CLASSES):
        return dict(available=False, reason='FIT_requires_both_ALLOW_and_BLOCK', class_counts=dict(counts))
    vectorizer = DictVectorizer(sparse=method == 'lr')
    matrix = vectorizer.fit_transform([values[r['prefix_id']] for r in selected])
    weights = archive_ml.group_weights([{'base_group_id': r['group_id']} for r in selected])
    scaler = None
    if method == 'lr':
        scaler = StandardScaler(with_mean=False)
        matrix = scaler.fit_transform(matrix, sample_weight=weights)
        estimator = LogisticRegression(C=1., l1_ratio=0., max_iter=2000, random_state=seed)
    elif method == 'catboost':
        from catboost import CatBoostClassifier
        estimator = CatBoostClassifier(iterations=200, depth=3, learning_rate=.03, l2_leaf_reg=5,
                                       thread_count=2, random_seed=seed, verbose=False, allow_writing_files=False)
    else:
        raise ValueError('unknown method')
    started = time.perf_counter()
    estimator.fit(matrix, [labels[r['prefix_id']] for r in selected], sample_weight=weights)
    return dict(available=True, class_counts=dict(counts), vectorizer=vectorizer, scaler=scaler,
                estimator=estimator, fit_seconds=time.perf_counter() - started,
                resolved_fit_prefixes=[r['prefix_id'] for r in selected])


def predict(model, records, values):
    if not model['available']:
        return [None] * len(records)
    matrix = model['vectorizer'].transform([values[r['prefix_id']] for r in records])
    if model['scaler'] is not None:
        matrix = model['scaler'].transform(matrix)
    probabilities = model['estimator'].predict_proba(matrix)
    result = [dict(zip(map(str, model['estimator'].classes_), map(float, row), strict=True)) for row in probabilities]
    if any(set(p) != set(CLASSES) or not np.isfinite(list(p.values())).all() or any(v < 0 or v > 1 for v in p.values()) or not np.isclose(sum(p.values()), 1) for p in result):
        raise ValueError('invalid model probabilities')
    return result


def feature_audit(records, labels, hashes):
    groups = defaultdict(list)
    for r in records:
        groups[hashes[r['prefix_id']]].append(r['prefix_id'])
    duplicates = {key: ids for key, ids in groups.items() if len(ids) > 1}
    conflicts = {key: ids for key, ids in groups.items() if len({labels[pid] for pid in ids} & set(CLASSES)) > 1}
    return dict(rows=len(records), unique_projections=len(groups), duplicate_projections=duplicates,
                conflicting_resolved_projections=conflicts,
                interpretation='Scenario-group OOF, not projection-disjoint testing; equal feature vectors may recur across folds.')


def run(records, labels, output, labels_sha256=None):
    records_path, labels_path, output = Path(records), Path(labels), Path(output)
    if labels_sha256 is not None and digest(labels_path) != labels_sha256:
        raise ValueError('frozen labels hash mismatch')
    records = read_rows(records_path)
    label_rows = read_rows(labels_path)
    labels = {r['prefix_id']: r['action_label'] for r in label_rows}
    ids = [r['prefix_id'] for r in records]
    if len(records) != 542 or len(set(ids)) != 542 or len(labels) != len(label_rows) or set(ids) != set(labels):
        raise ValueError('expected exactly 542 unique joined records and labels')
    if len({r['group_id'] for r in records}) != 58 or any(labels[pid] not in LABELS for pid in ids):
        raise ValueError('expected 58 groups and valid action labels')
    if len({r['episode_id'] for r in records}) != 542:
        raise ValueError('expected one selected P4 action per episode')
    if any(r['observation'].get('checkpoint') != 'P4' or r['native'].get('checkpoint') != 'P4' for r in records):
        raise ValueError('new classifiers are P4 only')
    records.sort(key=lambda r: r['prefix_id'])
    by_id = {r['prefix_id']: r for r in records}
    values = {r['prefix_id']: features(r) for r in records}
    hashes = {pid: feature_hash(value) for pid, value in values.items()}
    folds = partitions(records, labels)
    output.mkdir(parents=True, exist_ok=False)
    source_paths = [Path(__file__), HERE / 'PROTOCOL.md', Path(archive_ml.__file__), Path(archive_ml.__file__).with_name('methods.py')]
    freeze = dict(records_sha256=digest(records_path), labels_sha256=digest(labels_path),
                  sources={str(p.resolve()): digest(p) for p in source_paths}, seed=17,
                  outer_splits=5, inner_splits=4, inner_CAL='first split', folds=folds,
                  target='binary action_label; INSUFFICIENT is split stratum only, never a fitted class',
                  versions={name: version(name) for name in ('numpy', 'scikit-learn', 'catboost', 'joblib')})
    write_json(output / 'folds.json', freeze)
    write_json(output / 'feature-audit.json', feature_audit(records, labels, hashes))
    predictions, models = [], []
    for fold in folds:
        fit_rows, cal_rows, test_rows = ([by_id[pid] for pid in fold[key]] for key in ('fit', 'cal', 'test'))
        seen = {hashes[r['prefix_id']] for r in fit_rows if labels[r['prefix_id']] in CLASSES}
        for method in METHODS:
            model = fit(method, fit_rows, labels, values, seed=17)
            cal_p, test_p = predict(model, cal_rows, values), predict(model, test_rows, values)
            operating = calibrate([labels[r['prefix_id']] for r in cal_rows], cal_p) if model['available'] else dict(status='MODEL_UNAVAILABLE', thresholds=None, reason=model['reason'])
            filename = f'{method}-fold{fold["index"]}.joblib'
            joblib.dump(dict(model=model, operating_point=operating, fold=fold['index'], method=method), output / filename)
            models.append(dict(method=method, fold=fold['index'], available=model['available'],
                               file=filename, sha256=digest(output / filename), operating_point=operating,
                               class_counts=model['class_counts'], fit_seconds=model.get('fit_seconds')))
            for row, probability in zip(test_rows, test_p, strict=True):
                decision = decide(probability, operating['thresholds']) if operating['status'] == 'FEASIBLE' else 'UNKNOWN' if model['available'] else None
                predictions.append(dict(prefix_id=row['prefix_id'], episode_id=row['episode_id'], group_id=row['group_id'],
                    method=method, fold=fold['index'], model_available=model['available'], probabilities=probability,
                    argmax_decision=decide(probability, dict(ALLOW=0, BLOCK=0)), decision=decision,
                    calibration_status=operating['status'], thresholds=operating['thresholds'],
                    feature_sha256=hashes[row['prefix_id']], seen_projection_in_fit=hashes[row['prefix_id']] in seen))
            print(canonical(dict(method=method, fold=fold['index'], available=model['available'], calibration=operating['status'])), flush=True)
    assert Counter((r['method'], r['prefix_id']) for r in predictions) == Counter((method, pid) for method in METHODS for pid in ids)
    with (output / 'predictions.jsonl.gz').open('xb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed:
            for r in sorted(predictions, key=lambda r: (r['method'], r['prefix_id'])):
                compressed.write((canonical(r) + '\n').encode())
    curves, summary = {}, {}
    for method in METHODS:
        selected = [r for r in predictions if r['method'] == method]
        gold = [labels[r['prefix_id']] for r in selected]
        curves[method] = [dict(thresholds=dict(ALLOW=ta, BLOCK=tb),
                               metrics=metrics(gold, [decide(r['probabilities'], dict(ALLOW=ta, BLOCK=tb)) for r in selected]))
                          for ta in GRID for tb in GRID]
        summary[method] = {key: metrics(gold, [r[field] for r in selected]) for key, field in [('calibrated', 'decision'), ('argmax_diagnostic', 'argmax_decision')]}
        summary[method]['projection_subsets'] = {kind: metrics([labels[r['prefix_id']] for r in selected if r['seen_projection_in_fit'] is seen],
                                                              [r['decision'] for r in selected if r['seen_projection_in_fit'] is seen])
                                                   for kind, seen in [('seen_in_resolved_FIT', True), ('unseen_in_resolved_FIT', False)]}
    write_json(output / 'curves.json', dict(grid=GRID, selection='descriptive fixed-grid OOF curves; no outer-test threshold selection', methods=curves))
    write_json(output / 'summary.json', dict(methods=summary, models=models, actual_fits=sum(m['available'] for m in models),
               expected_model_slots=10, labels_sha256=freeze['labels_sha256'], records_sha256=freeze['records_sha256'],
               folds_sha256=digest(output / 'folds.json'), predictions_sha256=digest(output / 'predictions.jsonl.gz'),
               interpretation='Retrospective group OOF on disclosed archive; local structural classifiers, no new closed-test generalization claim.'))
    if digest(records_path) != freeze['records_sha256'] or digest(labels_path) != freeze['labels_sha256'] or any(digest(p) != h for p, h in freeze['sources'].items()):
        raise ValueError('inputs or sources changed during OOF run')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('records', 'labels', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--labels-sha256')
    run(**vars(parser.parse_args()))


if __name__ == '__main__':
    main()
