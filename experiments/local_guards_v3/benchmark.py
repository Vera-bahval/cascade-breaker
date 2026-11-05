"""Serial, uncached single-prefix timings of frozen methods; never opens gold."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import platform
import resource
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def _read(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _worker(frozen, observations, count):
    start = time.perf_counter()
    import ml_v3
    import rules_v3
    import legacy_adapter
    import numpy as np
    imported = (time.perf_counter() - start) * 1000
    frozen = Path(frozen)
    manifest = json.loads((frozen / 'freeze-manifest.json').read_text())
    rows = [row for row in _read(observations) if row.get('checkpoint') == 'P4'
            and row.get('proposal', {}).get('tool') == 'finstripe__create_transfer'][:count]
    if not rows:
        raise ValueError('benchmark requires at least one real P4 observation')
    encoded = [json.dumps(row, ensure_ascii=False) for row in rows]
    timings = []
    workloads = [('rules', None), ('legacy_v1', None), ('legacy_v2', None)]
    for spec in manifest['methods']:
        if spec.get('seed') == 17 and spec.get('model_file'):
            item = (spec['model'], spec['model_file'])
            if item not in workloads:
                workloads.append(item)
    for name, filename in workloads:
        cold = time.perf_counter()
        model = None
        if filename:
            path = frozen / filename
            expected = next(s['model_hash'] for s in manifest['methods'] if s.get('model_file') == filename)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('model changed before benchmark')
            model = pickle.loads(path.read_bytes())
        load_ms = (time.perf_counter() - cold) * 1000

        def once(text):
            row = json.loads(text)
            if name == 'rules':
                return rules_v3.guard(row)['decision']
            if name in legacy_adapter.NAMES:
                return legacy_adapter.guard(row, name)['decision']
            score = ml_v3.score_model(model, [row])[0]
            missing = rules_v3.required_missing(row)
            return 'UNKNOWN' if missing else score

        for text in encoded[:10]:
            once(text)
        elapsed = []
        for text in encoded:
            began = time.perf_counter()
            once(text)
            elapsed.append((time.perf_counter() - began) * 1000)
        timings.append({'method': name, 'seed': 17 if filename else None, 'prefixes': len(elapsed),
                        'p50_ms': float(np.quantile(elapsed, .5)), 'p95_ms': float(np.quantile(elapsed, .95)),
                        'mean_ms': statistics.mean(elapsed), 'verified_artifact_load_ms': load_ms})
    maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    mib = maximum / (1024 ** 2 if sys.platform == 'darwin' else 1024)
    return {'measurements': timings, 'imports_ms': imported, 'process_peak_rss_mib': mib,
            'python': sys.version.split()[0], 'platform': platform.platform(),
            'mode': 'serial JSON decode + full single-prefix features/scorer/proof gate, no cache',
            'sample_source': 'first P4 rows of frozen TRAIN package; no gold',
            'external_inference_api_calls': 0, 'local_compute_cost_usd': None,
            'limitations': ['hardware and load specific; no online end-to-end latency measured',
                            'one fresh process; library imports separate from serialized artifact loading',
                            'peak RSS includes all loaded models, not a per-model isolated maximum']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=200)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    if args.worker:
        result = _worker(args.freeze, args.observations, args.count)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        return
    began = time.perf_counter()
    command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--freeze', str(args.freeze),
               '--observations', str(args.observations), '--output', str(args.output), '--count', str(args.count)]
    run = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if run.returncode:
        raise RuntimeError(run.stderr[-3000:])
    result = json.loads(args.output.read_text())
    result['fresh_process_total_s'] = time.perf_counter() - began
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'methods': len(result['measurements']), 'external_inference_api_calls': 0}))


if __name__ == '__main__':
    main()
