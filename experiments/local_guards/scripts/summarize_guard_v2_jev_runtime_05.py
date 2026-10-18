#!/usr/bin/env python3
"""Read-only runtime metadata scan; no model loading, fitting or quality metrics."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())
def lines(path):
    with Path(path).open() as stream:
        return [json.loads(line) for line in stream if line.strip()]
def fingerprint(row): return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
def numeric(value): return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0

def statistics(values):
    values = sorted(v for v in values if numeric(v))
    def quantile(q):
        if not values: return None
        position = (len(values)-1)*q; lo = int(position)
        return values[lo] + (values[min(lo+1,len(values)-1)]-values[lo])*(position-lo)
    return {'n': len(values), 'p50_ms': quantile(.5), 'p95_ms': quantile(.95), 'max_ms': max(values) if values else None}

def memory(rows):
    return {key: {'observations': len(values), 'max_bytes': max(values) if values else None}
            for key in ('process_peak_rss_bytes','mps_allocated_bytes','mps_driver_bytes')
            for values in [[r.get('memory', {}).get(key) for r in rows if numeric(r.get('memory', {}).get(key))]]}

def metadata_summary(rows):
    measured = [r for r in rows if r.get('cache_hit') is False]
    cached = [r for r in rows if r.get('cache_hit') is True]
    unspecified = len(rows)-len(measured)-len(cached)
    loads = [r.get('model_metadata',{}).get('model_load_ms') for r in measured]
    loads = [v for v in loads if numeric(v)]
    return {'records':len(rows), 'status_counts':dict(Counter(str(r.get('status')) for r in rows)),
            'noncache': {'records':len(measured),
                         'observed_single_record_runtime_ms':{key:statistics([r.get('timing_ms',{}).get(key) for r in measured]) for key in ('total','compute','queue','tokenize')},
                         'recorded_latency_ms':statistics([r.get('latency_ms') for r in measured]),
                         'observed_memory':memory(measured),
                         'maximum_observed_model_load_metadata_ms':max(loads) if loads else None},
            'cache_hits':{'records':len(cached), 'memory_measurements_counted':0,
                          'recorded_cache_delivery_latency_ms':statistics([r.get('latency_ms') for r in cached]),
                          'note':'Copied source memory/model-load/compute metadata is excluded from new measurement summaries.'},
            'cache_flag_unspecified_records':unspecified}

def gate_summary(gate):
    cases = gate.get('cases',[])
    aa = [c['aa'] for c in cases if 'aa' in c]
    parity = [p for c in cases for p in c.get('cpu_parity',[])]
    results = [r for c in cases for r in c.get('results',[])]
    return {'status':gate.get('status'), 'passed':gate.get('passed'), 'tolerance':gate.get('tolerance'),
            'selection':gate.get('selection'), 'completed_cases':len(cases),
            'model_metadata':gate.get('model_metadata'),
            'aa': {'cases':len(aa), 'runs':sum(c.get('runs',0) for c in aa), 'valid':sum(c.get('valid',0) for c in aa),
                   'all_identical':all(c.get('identical') is True for c in aa) if aa else None,
                   'all_stable_decisions':all(c.get('stable_decisions') is True for c in aa) if aa else None,
                   'max_abs_delta':max((c.get('max_abs_delta',0) for c in aa), default=None)},
            'cpu_mps_parity':{'comparisons':len(parity), 'passed':sum(p.get('passed') is True for p in parity),
                              'max_abs_delta':max((p.get('max_abs_delta',0) for p in parity),default=None),
                              'categorical_flip_count':sum(len(p.get('categorical_flips',[])) for p in parity),
                              'threshold_flip_count':sum(len(p.get('threshold_flips',[])) for p in parity)},
            'observed_gate_result_memory':memory(results)}

def summarize(root):
    root = Path(root).resolve(); folder=root/'jev-v5/08'
    sources = [Path(__file__).resolve(), folder/'scores.jsonl', root/'jev-v5/runtime-run.json']
    raw = lines(folder/'scores.jsonl'); raw_counts = Counter(map(fingerprint,raw))
    # This generation lacks provenance.collection: prove exact export membership.
    grouped = {}; exported = Counter()
    for collection in ('archive-all','archive-partial','independent-all','raw64','raw64-partial'):
        path=folder/(collection+'-scores.jsonl'); sources.append(path)
        records=lines(path); counts=Counter(map(fingerprint,records)); exported.update(counts)
        if counts - raw_counts: raise ValueError('Collection export differs from raw runtime source: '+collection)
        grouped[collection]=metadata_summary(records)
    if exported != raw_counts: raise ValueError('Collection exports do not partition raw runtime records exactly')
    gates={}
    for name,relative in [('08_cpu','08/cpu-gate.json'),('08_mps','08/mps-gate.json'),('4b_cpu_incomplete','4b/cpu-gate.json')]:
        path=root/'jev-v5'/relative; sources.append(path); gates[name]=gate_summary(read(path))
    state=read(root/'jev-v5/runtime-run.json')
    return {'version':'guard-v2-jev-runtime-metadata-05', 'source_sha256':{str(p):sha(p) for p in sources},
            'scope':'Metadata-only summary of existing logged records; no models loaded, inference reruns, labels or classification quality metrics.',
            'collection_assignment':{'method':'Exact full-record fingerprint multiset membership in five named collection export files, verified to partition raw scores exactly.',
                                     'provenance_collection_present_rows':sum('collection' in r.get('provenance',{}) for r in raw),
                                     'limitation':'This generation has no provenance.collection; names come from pinned export paths, not invented row fields.'},
            'all_08_records':metadata_summary(raw), 'by_collection':grouped, 'gates':gates,
            '4b_technical_outcome':{k:state.get(k) for k in ('status','current_stage','error','model_cutoff','finished_at')},
            'limitations':['0.8B noncache timings describe actually computed single records across logged collections and include the first post-load record; no first-record warmup marker is available.',
                           'Process peak RSS is a running process envelope, not incremental per-head/model allocation. MPS allocated and driver fields are sampled snapshots; maxima may occur on different records and must not be added.',
                           'Cache-hit rows are separate. Their copied memory, compute and load metadata is not a fresh measurement.',
                           'Cold-load value is maximum observed metadata, never multiplied by row count. No process-start identity is recorded, so restart counts and total cold-load cost are not inferred.',
                           'CPU/MPS gates use six selected states and A/A repetitions; parity is numerical compatibility metadata, not task classification accuracy.',
                           '4B CPU gate remained RUNNING with partial cases when the technical cutoff interrupted it. This is no completed gate or classification result.',
                           'No latency-summary-05 reconstructed four-stage costs are mixed into these actual runtime measurements. No new timing or memory benchmark was run.']}

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--root',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=summarize(args.root)
    with args.output.open('x') as stream: json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'output':str(args.output.resolve()),'sha256':sha(args.output),'rows':result['all_08_records']['records'],'collections':len(result['by_collection'])}))
if __name__=='__main__': main()
