"""Singleton latency on ready observations; no IO/diagnostics inside timed calls."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import platform
from random import Random
import resource
import sys
import time

from .run import HERE,REPAIR,INPUTS,configs,checker,call_one,validate
from experiments.local_guards_adapter_repair.inventory import rows,sha,write_json
from experiments.local_guards_adapter_repair.prepare import preparation_fence


def quantiles(values):
    values=sorted(values);n=len(values)
    return dict(n=n,p50_ms=values[math.ceil(.5*n)-1] if n else None,
                p95_ms=values[math.ceil(.95*n)-1] if n else None)


def run(output):
    validate();output.mkdir(parents=True,exist_ok=False)
    ids=sorted({r['prefix_id'] for r in rows(INPUTS/'p4-inputs.jsonl.gz')})
    chosen=set(Random(17).sample(ids,30))
    inputs=defaultdict(list)
    for r in rows(INPUTS/'p4-inputs.jsonl.gz'):
        if r['prefix_id'] not in chosen:continue
        for family,adapted in r['adapters'].items():
            inputs[family].append(dict(prefix_id=r['prefix_id'],mode=r['mode'],
                payload=adapted['payload'],applicable=adapted['applicable'],input_sha256=r['payload_sha256'][family]))
    selected=[c for c in configs() if c['variant']!='argmax_diagnostic']
    Random(17).shuffle(selected);results={};singletons=[]
    with preparation_fence():
        for config in selected:
            started=time.perf_counter_ns();fn=checker(config)
            load_ms=(time.perf_counter_ns()-started)/1e6
            mode_times=defaultdict(list);first=None
            for r in inputs[config['family']]:
                if not r['applicable']:continue
                started=time.perf_counter_ns();decision=call_one(fn,r['payload'])
                elapsed=(time.perf_counter_ns()-started)/1e6
                if first is None:
                    first=elapsed
                    # First call is recorded separately, not folded into the warm sample.
                    started=time.perf_counter_ns();decision=call_one(fn,r['payload'])
                    elapsed=(time.perf_counter_ns()-started)/1e6
                mode_times[r['mode']].append(elapsed)
                singletons.append(dict(config=config['id'],prefix_id=r['prefix_id'],mode=r['mode'],
                    input_sha256=r['input_sha256'],decision=decision.get('decision'),
                    elapsed_ms=elapsed,execution_error=bool(decision.get('execution_error'))))
            results[config['id']]=dict(load_ms=load_ms,first_call_ms=first,
                modes={mode:quantiles(mode_times[mode]) for mode in ('common','expanded','conditional')})
    write_json(output/'latency.json',dict(seed=17,sampled_prefixes=sorted(chosen),methods=results,
        scope='single call on prepared observation, includes original ML features and gate; excludes file IO and diagnostic collection',
        cold_scope='checker construction and first call in one reused process; not isolated process cold start',
        peak_process_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform=='darwin' else 1024),
        python=sys.version,platform=platform.platform(),model_api_calls=0))
    from experiments.local_guards_adapter_repair.prepare import writer
    with writer(output/'singleton-decisions.jsonl.gz') as emit:
        for r in singletons:emit(r)
    write_json(output/'receipt.json',dict(benchmark_sha256=sha(Path(__file__)),
        configuration_sha256=sha(HERE/'configuration.json'),
        input_manifest_sha256=sha(INPUTS/'manifest.json'),
        outputs={p.name:sha(p) for p in output.iterdir() if p.is_file()}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
