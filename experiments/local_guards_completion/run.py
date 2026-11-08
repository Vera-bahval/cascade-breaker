"""Frozen offline rule predictions and prepared-packet timing; no model calls."""
import argparse
from collections import Counter
from contextlib import contextmanager
import gzip
import json
from pathlib import Path
import random
import sqlite3
import tempfile
from time import perf_counter_ns

from experiments.local_guards_archive_comparison.collector import canonical, digest
from experiments.local_guards_adapter_repair.prepare import preparation_fence
from .early_sources import iter_early_rows
from .records import attach, rows, sha, supplements, policy_path
from .source_links import source_manifest as links_manifest
from .rules import prepare, guard

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
INPUTS = {'p4': EXP / 'local_guards_adapter_repair/inputs/p4-inputs.jsonl.gz',
          'legacy176': EXP / 'local_guards_legacy176/prepared-inputs.jsonl.gz'}
VARIANTS = (('current', 'current', 'default'), ('baseline', 'baseline', 'default'),
            ('current_unknown_unavailable', 'current', 'unknown_unavailable'))
REQUIRED_CODE = {'PROTOCOL.md', 'prepare.py', 'rules.py', 'early_sources.py', 'source_links.py', 'records.py', 'run.py'}


def admitted():
    path = HERE / 'code-freeze.json'
    freeze = json.loads(path.read_text())
    if freeze.get('status') != 'FROZEN' or not REQUIRED_CODE <= set(freeze.get('code_sha256', {})):
        raise ValueError('completion code has not been frozen')
    for name, expected in freeze['code_sha256'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts or sha(HERE / name) != expected:
            raise ValueError('changed frozen code: ' + name)
    for name, expected in freeze.get('project_dependency_sha256', {}).items():
        if Path(name).is_absolute() or '..' in Path(name).parts or sha(EXP.parent/name) != expected:
            raise ValueError('changed frozen project dependency: ' + name)
    label_hash = sha(HERE / 'labels-freeze.json')
    if label_hash != freeze.get('labels_freeze_sha256'):
        raise ValueError('labels freeze changed or was not accepted')
    return dict(code_freeze_sha256=sha(path), labels_freeze_sha256=label_hash,
                code_sha256=freeze['code_sha256'])


@contextmanager
def writer(path):
    with Path(path).open('xb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as stream:
        yield lambda value: stream.write((canonical(value) + '\n').encode())


def write_json(path, value):
    with Path(path).open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


def source_manifest():
    annotation = EXP / 'local_guards_archive_annotation'
    paths = [*INPUTS.values(), EXP / 'local_guards_adapter_repair/inventory.json',
             policy_path(), annotation / 'custodian_manifest.json']
    paths.extend(sorted((EXP / 'local_guards_adapter_repair/inputs').glob('early-inputs-*.jsonl.gz')))
    paths.extend(annotation / folder / 'availability.json' for folder in ('supplementary_evidence', 'supplementary_evidence_v2'))
    hashes = {str(path.relative_to(EXP.parent)): sha(path) for path in paths}
    hashes.update(links_manifest()['input_sha256'])
    return hashes


def iter_cases(supplement):
    for dataset, path in INPUTS.items():
        for row in rows(path):
            if dataset == 'p4' and row['mode'] in ('common', 'expanded'):
                yield dataset, attach(row, supplement)
            elif dataset == 'legacy176' and row['mode'] == 'full':
                yield dataset, row


def predict(dataset, row, variant, source_hash):
    name, method, tax_mode = variant
    observation = prepare(row, method=method, tax_mode=tax_mode)
    record = {key: row[key] for key in ('prefix_id', 'episode_id', 'case_id', 'query_id', 'mode') if key in row}
    record.update(dataset=dataset, method=name, guard_method=method, tax_mode=tax_mode,
                  checkpoint=observation['checkpoint'], event_seq=observation['event_seq'],
                  input_sha256=digest(observation), source_input_sha256=source_hash,
                  source_packet_sha256=digest(row), result=guard(observation))
    return record


def run(output):
    gate = admitted()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    source_hashes = source_manifest()
    supplement = supplements()
    counts = Counter()
    seen = set()
    with preparation_fence(), writer(output / 'predictions.jsonl.gz') as emit:
        for dataset, row in iter_cases(supplement):
            source_hash = source_hashes[str(INPUTS[dataset].relative_to(EXP.parent))]
            for variant in VARIANTS:
                key = dataset, row['mode'], variant[0], row['prefix_id']
                if key in seen:
                    raise ValueError('duplicate prediction identity')
                seen.add(key)
                emit(predict(dataset, row, variant, source_hash))
                counts['/'.join(key[:3])] += 1
    expected = {f'{dataset}/{mode}/{variant[0]}': n for dataset, mode, n in
                [('legacy176', 'full', 176), ('p4', 'common', 542), ('p4', 'expanded', 542)] for variant in VARIANTS}
    if dict(counts) != expected:
        raise ValueError('prediction cohort mismatch')
    print('completion payment predictions', sum(counts.values()), flush=True)
    early_counts = Counter()
    with preparation_fence(), writer(output / 'early-predictions.jsonl.gz') as emit:
        for row in iter_early_rows():
            emit(predict('early', row, VARIANTS[0], digest(dict(source=row['bundle']['source'], raw_context=row['raw_context']))))
            early_counts[row['mode']] += 1
            if sum(early_counts.values()) % 5000 == 0:
                print('completion early predictions', sum(early_counts.values()), flush=True)
    if dict(early_counts) != {'historical': 18676, 'conditional': 18676}:
        raise ValueError('early prediction cohort mismatch')
    if admitted() != gate:
        raise ValueError('code changed during predictions')
    receipt = dict(gate, counts=dict(counts), early_counts=dict(early_counts), source_sha256=source_hashes,
                   predictions_sha256=sha(output / 'predictions.jsonl.gz'),
                   early_predictions_sha256=sha(output / 'early-predictions.jsonl.gz'),
                   label_reads=0, new_model_calls=0, no_model_calls=True)
    write_json(output / 'prediction-freeze.json', receipt)
    print('FROZEN_COMPLETION', sum(counts.values()), sum(early_counts.values()), flush=True)


def benchmark_cases(supplement):
    cases = {}
    for dataset, row in iter_cases(supplement):
        if row['mode'] not in ('common', 'full'):
            continue
        case = {key: row[key] for key in ('bundle', 'completion_evidence', 'action_boundary') if key in row}
        case['adapters'] = {'native': row['adapters']['native']}
        cases[dataset, row['prefix_id']] = case
    if len(cases) != 718:
        raise ValueError('benchmark cohort mismatch')
    return cases


def benchmark(output):
    gate = admitted()
    output = Path(output)
    for name in ('benchmark.jsonl.gz', 'benchmark-receipt.json'):
        if (output / name).exists():
            raise FileExistsError(output / name)
    receipt_path = output / 'prediction-freeze.json'
    receipt = json.loads(receipt_path.read_text())
    if receipt['code_freeze_sha256'] != gate['code_freeze_sha256'] or receipt['labels_freeze_sha256'] != gate['labels_freeze_sha256'] or receipt['predictions_sha256'] != sha(output / 'predictions.jsonl.gz'):
        raise ValueError('prediction freeze does not match current code/answers')
    if receipt['source_sha256'] != source_manifest():
        raise ValueError('prediction sources changed')
    frozen = {(r['dataset'], r['prefix_id'], r['method']): r for r in rows(output / 'predictions.jsonl.gz')
              if r['mode'] in ('common', 'full') and r['method'] in ('current', 'baseline')}
    cases = benchmark_cases(supplements())
    expected_keys = {(dataset, pid, method) for dataset, pid in cases for method in ('current', 'baseline')}
    if set(frozen) != expected_keys:
        raise ValueError('missing frozen benchmark identities')
    rng = random.Random(17)
    count = 0
    with tempfile.TemporaryDirectory(prefix='finbot-completion-') as directory:
        db = sqlite3.connect(str(Path(directory) / 'state.sqlite'))
        try:
            db.execute('CREATE TABLE packets (id TEXT PRIMARY KEY, packet TEXT)')
            for key, case in cases.items():
                db.execute('INSERT INTO packets VALUES (?,?)', (canonical(key), canonical(case)))
            db.commit()
            with preparation_fence(), writer(output / 'benchmark.jsonl.gz') as emit:
                for rep in range(30):
                    keys = list(cases)
                    rng.shuffle(keys)
                    for dataset, pid in keys:
                        start = perf_counter_ns()
                        row = json.loads(db.execute('SELECT packet FROM packets WHERE id=?', (canonical((dataset, pid)),)).fetchone()[0])
                        state_ms = (perf_counter_ns() - start) / 1e6
                        variants = list(VARIANTS[:2])
                        rng.shuffle(variants)
                        for name, method, tax_mode in variants:
                            start = perf_counter_ns()
                            observation = prepare(row, method=method, tax_mode=tax_mode)
                            projection_ms = (perf_counter_ns() - start) / 1e6
                            start = perf_counter_ns()
                            result = guard(observation)
                            guard_ms = (perf_counter_ns() - start) / 1e6
                            start = perf_counter_ns()
                            expected = frozen[dataset, pid, name]
                            if digest(observation) != expected['input_sha256'] or result != expected['result']:
                                raise ValueError('benchmark changed frozen input/result')
                            diagnostics_ms = (perf_counter_ns() - start) / 1e6
                            emit(dict(dataset=dataset, prefix_id=pid, method=name, rep=rep,
                                      state_ms=state_ms, projection_ms=projection_ms, guard_ms=guard_ms,
                                      working_ms=state_ms + projection_ms + guard_ms, diagnostics_ms=diagnostics_ms))
                            count += 1
                    if rep % 10 == 9:
                        print('completion benchmark', rep + 1, flush=True)
        finally:
            db.close()
    if count != 43080 or admitted() != gate:
        raise ValueError('benchmark incomplete or code changed')
    write_json(output / 'benchmark-receipt.json', dict(gate, count=count, repetitions=30,
               benchmark_sha256=sha(output / 'benchmark.jsonl.gz'),
               prediction_freeze_sha256=sha(receipt_path), no_model_calls=True, new_model_calls=0,
               source_scope='SQLite prepared-source read + JSON decoding + projection + guard; excludes initial evidence builder, source retrieval, output/hashing and diagnostics'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=HERE / 'results')
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args()
    benchmark(args.output_dir) if args.benchmark else run(args.output_dir)


if __name__ == '__main__':
    main()
