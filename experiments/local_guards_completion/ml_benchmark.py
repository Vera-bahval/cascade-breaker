"""Paired single-request timings for the frozen 30-state P4 OOF cohort.

Run after OOF fitting and the rule benchmark, on a quiet local CPU. Loading models,
source preparation, integrity checks and diagnostics are outside working timers.
"""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import sqlite3
from statistics import mean
import tempfile
from time import perf_counter_ns

import joblib

from experiments.local_guards_archive_comparison.collector import canonical, digest
from experiments.local_guards_adapter_repair.prepare import preparation_fence
from . import ml
from .records import rows, sha, supplements
from .rules import prepare, guard
from .run import HERE, EXP, admitted, benchmark_cases, source_manifest, writer, write_json

SAMPLE = EXP / 'local_guards_repaired_evaluation/benchmark/latency.json'
TIMERS = ('features_ms', 'inference_ms', 'calibration_ms', 'working_ms', 'argmax_ms', 'argmax_working_ms')


def measure(db, prefix_id, bundle):
    """One prepared-source read; optional process gate and ML share its projection."""
    model, operating = bundle['model'], bundle['operating_point']
    start = perf_counter_ns()
    row = json.loads(db.execute('SELECT packet FROM packets WHERE id=?', (canonical(('p4', prefix_id)),)).fetchone()[0])
    state_ms = (perf_counter_ns() - start) / 1e6
    start = perf_counter_ns()
    observation = prepare(row, method='current', tax_mode='default')
    projection_ms = (perf_counter_ns() - start) / 1e6
    start = perf_counter_ns()
    process = guard(observation)
    process_guard_ms = (perf_counter_ns() - start) / 1e6
    result = dict(model_available=model['available'], state_ms=state_ms, projection_ms=projection_ms,
                  process_guard_ms=process_guard_ms, process_decision=process['process_decision'],
                  process_working_ms=state_ms + projection_ms + process_guard_ms,
                  calibration_status=operating['status'], probabilities=None,
                  decision=None, argmax_decision=None, **dict.fromkeys(TIMERS))
    feature_record = dict(native=row['adapters']['native']['payload'], observation=observation)
    if not model['available']:
        return result, feature_record, None, process
    start = perf_counter_ns()
    values = ml.features(feature_record)
    matrix = model['vectorizer'].transform([values])
    if model['scaler'] is not None:
        matrix = model['scaler'].transform(matrix)
    features_ms = (perf_counter_ns() - start) / 1e6
    start = perf_counter_ns()
    scores = model['estimator'].predict_proba(matrix)[0]
    probability = dict(zip(map(str, model['estimator'].classes_), map(float, scores), strict=True))
    inference_ms = (perf_counter_ns() - start) / 1e6
    start = perf_counter_ns()
    decision = ml.decide(probability, operating['thresholds']) if operating['status'] == 'FEASIBLE' else 'UNKNOWN'
    calibration_ms = (perf_counter_ns() - start) / 1e6
    start = perf_counter_ns()
    argmax = ml.decide(probability, dict(ALLOW=0, BLOCK=0))
    argmax_ms = (perf_counter_ns() - start) / 1e6
    common_ms = state_ms + projection_ms + features_ms + inference_ms
    result.update(probabilities=probability, decision=decision, argmax_decision=argmax,
                  features_ms=features_ms, inference_ms=inference_ms, calibration_ms=calibration_ms,
                  argmax_ms=argmax_ms, working_ms=common_ms + calibration_ms,
                  argmax_working_ms=common_ms + argmax_ms)
    return result, feature_record, values, process


def validate(result, feature_values, expected):
    if ml.feature_hash(feature_values) != expected['feature_sha256']:
        raise ValueError('benchmark features differ from frozen OOF input')
    for field in ('model_available', 'calibration_status', 'decision', 'argmax_decision'):
        if result[field] != expected[field]:
            raise ValueError('benchmark differs from frozen OOF ' + field)
    probability, frozen = result['probabilities'], expected['probabilities']
    if probability is None or frozen is None:
        if probability is not frozen:
            raise ValueError('OOF score availability changed')
    elif (set(probability) != set(frozen)
          or any(not math.isfinite(v) or v < 0 or v > 1 for v in probability.values())
          or abs(sum(probability.values()) - 1) > 1e-9
          or any(abs(probability[k] - frozen[k]) > 1e-10 for k in probability)):
        raise ValueError('single-query probabilities differ from frozen OOF')


def preflight(ml_output, rule_output, records_path):
    gate = admitted()
    summary = json.loads((ml_output / 'summary.json').read_text())
    folds_path = ml_output / 'folds.json'
    prediction_path = ml_output / 'predictions.jsonl.gz'
    if summary['records_sha256'] != sha(records_path) or summary['folds_sha256'] != sha(folds_path) or summary['predictions_sha256'] != sha(prediction_path):
        raise ValueError('changed OOF input/folds/predictions')
    folds = json.loads(folds_path.read_text())
    allowed_sources = {str(p.resolve()) for p in [Path(ml.__file__), HERE / 'PROTOCOL.md',
                       Path(ml.archive_ml.__file__), Path(ml.archive_ml.__file__).with_name('methods.py')]}
    if set(folds['sources']) != allowed_sources or any(sha(path) != h for path, h in folds['sources'].items()):
        raise ValueError('changed or unexpected OOF source')
    rule_prediction = json.loads((rule_output / 'prediction-freeze.json').read_text())
    rule_benchmark = json.loads((rule_output / 'benchmark-receipt.json').read_text())
    if (rule_prediction['code_freeze_sha256'] != gate['code_freeze_sha256']
            or rule_prediction['predictions_sha256'] != sha(rule_output / 'predictions.jsonl.gz')
            or rule_prediction['source_sha256'] != source_manifest()
            or rule_benchmark['code_freeze_sha256'] != gate['code_freeze_sha256']
            or rule_benchmark['benchmark_sha256'] != sha(rule_output / 'benchmark.jsonl.gz')):
        raise ValueError('rule predictions/benchmark do not match admitted sources')
    sample = json.loads(SAMPLE.read_text())['sampled_prefixes']
    if len(sample) != 30 or len(set(sample)) != 30 or any(not isinstance(pid, str) for pid in sample):
        raise ValueError('expected the saved 30-state paired timing sample')
    frozen = {(r['method'], r['prefix_id']): r for r in rows(prediction_path) if r['prefix_id'] in sample}
    if set(frozen) != {(method, pid) for method in ml.METHODS for pid in sample}:
        raise ValueError('OOF timing cohort incomplete')
    models, model_hashes = {}, {}
    for entry in summary['models']:
        name = Path(entry['file'])
        if name.is_absolute() or len(name.parts) != 1:
            raise ValueError('invalid model filename')
        path = ml_output / name
        if sha(path) != entry['sha256']:
            raise ValueError('changed OOF model')
        key = entry['method'], entry['fold']
        if key in models:
            raise ValueError('duplicate OOF model identity')
        bundle = joblib.load(path)
        if (bundle['method'], bundle['fold']) != key or bundle['model']['available'] != entry['available'] or bundle['operating_point'] != entry['operating_point']:
            raise ValueError('OOF model/operating-point metadata mismatch')
        models[key] = bundle
        model_hashes[str(path.resolve())] = entry['sha256']
    if set(models) != {(method, fold) for method in ml.METHODS for fold in range(5)}:
        raise ValueError('expected ten OOF model slots')
    process = {r['prefix_id']: r for r in rows(rule_output / 'predictions.jsonl.gz')
               if r['dataset'] == 'p4' and r['mode'] == 'common' and r['method'] == 'current' and r['prefix_id'] in sample}
    if set(process) != set(sample):
        raise ValueError('missing paired process-guard predictions')
    sources = dict(model_hashes)
    for path in [Path(__file__), Path(ml.__file__), ml_output / 'summary.json', folds_path,
                 prediction_path, rule_output / 'prediction-freeze.json', rule_output / 'predictions.jsonl.gz',
                 rule_output / 'benchmark-receipt.json', rule_output / 'benchmark.jsonl.gz', SAMPLE, records_path]:
        sources[str(path.resolve())] = sha(path)
    return gate, sample, frozen, models, process, sources


def run(ml_output=HERE / 'ml-results', rule_output=HERE / 'results', records=HERE / 'records.jsonl.gz'):
    ml_output, rule_output, records_path = Path(ml_output), Path(rule_output), Path(records)
    for name in ('benchmark.jsonl.gz', 'benchmark-receipt.json'):
        if (ml_output / name).exists():
            raise FileExistsError(ml_output / name)
    gate, sample, frozen, models, process, sources = preflight(ml_output, rule_output, records_path)
    cases = benchmark_cases(supplements())
    selected = {('p4', pid): cases['p4', pid] for pid in sample}
    count, measured, timers = 0, 0, defaultdict(list)
    rng = random.Random(17)
    with tempfile.TemporaryDirectory(prefix='finbot-completion-ml-') as directory:
        db = sqlite3.connect(str(Path(directory) / 'state.sqlite'))
        try:
            db.execute('CREATE TABLE packets (id TEXT PRIMARY KEY, packet TEXT)')
            db.executemany('INSERT INTO packets VALUES (?,?)', [(canonical(key), canonical(row)) for key, row in selected.items()])
            db.commit()
            with preparation_fence(), writer(ml_output / 'benchmark.jsonl.gz') as emit:
                for rep in range(30):
                    queries = [(method, pid) for method in ml.METHODS for pid in sample]
                    rng.shuffle(queries)
                    for method, pid in queries:
                        expected = frozen[method, pid]
                        bundle = models[method, expected['fold']]
                        result, record, values, process_result = measure(db, pid, bundle)
                        start = perf_counter_ns()
                        if values is None:
                            values = ml.features(record)
                        validate(result, values, expected)
                        if digest(record['observation']) != process[pid]['input_sha256'] or process_result != process[pid]['result']:
                            raise ValueError('paired process input/result changed')
                        diagnostics_ms = (perf_counter_ns() - start) / 1e6
                        row = dict(dataset='p4', prefix_id=pid, method=method, fold=expected['fold'], rep=rep,
                                   feature_sha256=expected['feature_sha256'], diagnostics_ms=diagnostics_ms, **result)
                        emit(row)
                        timers[method, pid].append(row)
                        count += 1
                        measured += result['model_available']
                    if rep % 10 == 9:
                        print('completion ML benchmark', rep + 1, flush=True)
        finally:
            db.close()
    if count != 1800 or set(map(len, timers.values())) != {30} or admitted() != gate or any(sha(path) != h for path, h in sources.items()):
        raise ValueError('benchmark coverage incomplete or frozen sources changed')
    means = {}
    for (method, pid), values in timers.items():
        fields = ('state_ms', 'projection_ms', 'process_guard_ms', 'process_working_ms', *TIMERS)
        means.setdefault(method, {})[pid] = {field: mean(r[field] for r in values) if all(r[field] is not None for r in values) else None for field in fields}
    receipt = dict(gate, count=count, measured_count=measured, process_count=count, repetitions=30,
                   sampled_prefixes=sample, source_sha256=sources, benchmark_sha256=sha(ml_output / 'benchmark.jsonl.gz'),
                   per_prefix_mean_ms=means, new_studied_model_calls=0,
                   source_scope='SQLite prepared-source read + JSON decoding + current/default projection + structural features/vectorizer/scaler + actual singleton estimator probabilities + calibrated selection. Process guard is timed separately on the shared projection. Argmax substitutes its own timed selection on the same acquired/scored query. Excludes initial evidence builder, supplements retrieval, model loading, hashes, output and diagnostics. No 176-state ML timing claim.',
                   unavailable_scope='Unavailable models retain actual source/projection/process-guard timings; model-path times remain null, never fabricated zero.',
                   interpretation='Fixed saved 30-state sample; 30 shuffled repetitions per state/method. Paired component sums support retrospective saved-LLM routing, not adaptive live execution.')
    write_json(ml_output / 'benchmark-receipt.json', receipt)
    print('FROZEN_COMPLETION_ML_BENCHMARK', count, measured, flush=True)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ml-output', type=Path, default=HERE / 'ml-results')
    parser.add_argument('--rule-output', type=Path, default=HERE / 'results')
    parser.add_argument('--records', type=Path, default=HERE / 'records.jsonl.gz')
    run(**vars(parser.parse_args()))


if __name__ == '__main__':
    main()
