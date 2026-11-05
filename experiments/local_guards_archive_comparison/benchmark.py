"""Frozen shared-input latency. No refit, executor, API, gold scoring or collector.

Existing Python environment only. TRAIN JSON decoding is outside warm timings;
cold workers receive the same preselected row on stdin outside operational timing.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import importlib
import json
import math
from pathlib import Path
import random
import resource
import socket
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TRAIN = HERE/'packages/release/TRAIN-rows.jsonl.gz'
RELEASE = HERE/'results/ml-release-v2'
NATIVE_SHA = '8e7aa49c198a23f8313fdc9ee2873ad099c1112aae2d4a7d85990888be73a81b'
ML_SHA = '4be593465378240c8885d317abca80455d2695e1c66184a18606120f3bcf00ca'
EVALUATION_SHA = '86409c43c830b41ab538191472f45315da37dbe3e2305d7717d2b2e12361215d'
CONTROLS = ('v1','v2','v3','v42_payment_common','v42_fullA')
PRIMARY = tuple(f'scenario_decision-{family}-{seed}' for family in ('lr','catboost') for seed in (17,29,43))
METHODS = ('native','native_core',*CONTROLS,*PRIMARY)
COLD_METHODS = ('native','native_core',*CONTROLS,'scenario_decision-lr-17','scenario_decision-catboost-17')


def digest(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def stats(values):
    values = sorted(value for value in values if value is not None)
    return {'n':len(values), 'p50_ms':values[math.ceil(.5*len(values))-1] if values else None,
            'p95_ms':values[math.ceil(.95*len(values))-1] if values else None}


def select_inputs(path=TRAIN, count=30):
    rows = []
    with gzip.open(path,'rb') as stream:
        for line in stream:
            row = json.loads(line)
            if row.get('checkpoint')=='P4':
                rows.append({'row_sha256':hashlib.sha256(line.rstrip(b'\r\n')).hexdigest(), 'row':row})
    if len(rows)<count: raise ValueError('insufficient TRAIN P4 rows')
    return sorted(rows,key=lambda row:row['row_sha256'])[:count]


def verify_release():
    expected = {HERE/'methods.py':NATIVE_SHA, HERE/'ml.py':ML_SHA, HERE/'evaluation.py':EVALUATION_SHA}
    manifest_path = RELEASE/'freeze-manifest.json'
    release_binding = json.loads((HERE/'results/methods-freeze.json').read_text())['sources'][str(manifest_path.relative_to(ROOT))]
    if digest(manifest_path) != release_binding: raise ValueError('release manifest freeze mismatch')
    specification = json.loads(manifest_path.read_text())
    if specification['source_sha256']['methods.py']!=NATIVE_SHA or specification['source_sha256']['ml.py']!=ML_SHA:
        raise ValueError('release source identity mismatch')
    for name, value in specification['source_sha256'].items():
        expected[RELEASE/name] = value
        expected[HERE/name] = value
    for model in specification['models']:
        expected[RELEASE/(model['name']+'.joblib')] = model['model_sha256']
    for path, value in expected.items():
        if digest(path)!=value: raise ValueError('frozen source/artifact mismatch: '+str(path))
    # Preserve immutable original controls and their original constructor source.
    evaluation = importlib.import_module('experiments.local_guards_archive_comparison.evaluation')
    evaluation.verify_controls()
    return {'sources_and_weights':{str(p.relative_to(ROOT)):h for p,h in sorted(expected.items())},
        'manifest_sha256':digest(RELEASE/'freeze-manifest.json'), 'train_sha256':digest(TRAIN),
        'historical_constructor':{'revision':evaluation.LEGACY_REVISION,'path':evaluation.LEGACY_BUILDER,
            'sha256':hashlib.sha256(evaluation.legacy_builder_source()).hexdigest()}}


@contextmanager
def offline():
    original = socket.socket.connect
    def block(sock,address):
        if sock.family in (socket.AF_INET,socket.AF_INET6): raise AssertionError('external networking forbidden')
        return original(sock,address)
    with patch.object(socket.socket,'connect',block), patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')):
        yield


class Candidate:
    def __init__(self,name,verified=None):
        if name not in METHODS: raise ValueError('unknown method')
        self.name = name
        self.verified = verified or verify_release()  # Must precede any joblib load.
        self.native = importlib.import_module('experiments.local_guards_archive_comparison.methods')
        self.ml = self.predictor = self.evaluation = None
        self.call_count = 0
        if name in PRIMARY:
            self.ml = importlib.import_module('experiments.local_guards_archive_comparison.ml')
            self.predictor = self.ml.Predictor(RELEASE/(name+'.joblib'))
        elif name in CONTROLS:
            self.evaluation = importlib.import_module('experiments.local_guards_archive_comparison.evaluation')

    def __call__(self,row,measure_probability=True):
        if self.predictor:
            measurements, values = {}, {}
            order = ['probability','combined'] if self.call_count%2==0 else ['combined','probability']
            self.call_count += 1
            for stage in order:
                if stage=='probability' and not measure_probability: continue
                start = perf_counter()
                value = (self.ml.probabilities(self.predictor.payload['model'],[row])[0] if stage=='probability'
                         else self.predictor.predict(row,native_gate=True,placement='p4'))
                measurements[stage] = (perf_counter()-start)*1000
                values[stage] = value
            result = values['combined']
            parity = all(abs(values['probability'].get(k,0)-v)<=1e-12 for k,v in result['probabilities'].items()) if measure_probability else None
            if measure_probability and not parity: raise AssertionError('probability/combined parity failed')
            return {'full_ms':measurements['combined'], 'probability_ms':measurements.get('probability'),
                'calibration_and_gate_combined_ms':measurements['combined'], 'probability_parity':parity,
                'decision':result['gated_decision'], 'raw_decision':result['raw_decision'],
                'calibrated_decision':result['calibrated_decision'],
                'operating_point_status':result['operating_point_status'], 'adapter_applicable':True,
                'unavailable_fields':[], 'guard_ms':None, 'adapter_ms':None}
        start = perf_counter()
        if self.evaluation:
            result = self.evaluation.control_predict(row,self.name)
            full = (perf_counter()-start)*1000
            return {key:result[key] for key in ('decision','original_raw_decision','adapter_applicable','unavailable_fields')} | {
                'full_ms':full, 'adapter_ms':result['adapter_ms'],
                'guard_ms':result['decision_ms'] if result['adapter_applicable'] else None,
                'probability_ms':None,'calibration_and_gate_combined_ms':None}
        result = self.native.guard(row,self.name)
        elapsed = (perf_counter()-start)*1000
        return {'full_ms':elapsed,'guard_ms':elapsed,'adapter_ms':None,'decision':result['decision'],
                'adapter_applicable':True,'unavailable_fields':[], 'probability_ms':None,
                'calibration_and_gate_combined_ms':None}


def cold_worker(name):
    started = perf_counter(); row = json.loads(sys.stdin.read())
    input_decode_ms = (perf_counter()-started)*1000
    start = perf_counter(); verified = verify_release(); verification_ms = (perf_counter()-start)*1000
    started = perf_counter(); candidate = Candidate(name,verified)
    loaded = perf_counter(); result = candidate(row,measure_probability=False)
    ready = perf_counter()
    return {'method':name,'input_canonical_sha256':hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'input_decode_ms_excluded':input_decode_ms,
        'verification_ms_excluded':verification_ms,'import_and_model_load_ms':(loaded-started)*1000,
        'first_decision_ms':(ready-loaded)*1000,'import_load_first_decision_ms':(ready-started)*1000,
        'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
        'first_result':result,'model_source_sha256':ML_SHA if name in PRIMARY else None}


def benchmark(repeats=30,cold_repeats=30):
    selected = select_inputs(); verified = verify_release()
    candidates = {name:Candidate(name,verified) for name in METHODS}
    # Warm imports/vectorizer paths for every input; excluded from measured passes.
    for candidate in candidates.values():
        for item in selected: candidate(item['row'])
    rng, raw = random.Random(17), []
    for repeat in range(repeats):
        methods = list(METHODS); rng.shuffle(methods)
        for name in methods:
            order = list(selected); rng.shuffle(order)
            for item in order:
                raw.append({'method':name,'repeat':repeat,'row_sha256':item['row_sha256'],**candidates[name](item['row'])})
    cold, started = [], perf_counter()
    cold_input = json.dumps(selected[0]['row'],separators=(',',':'))
    cold_reason = None
    for repeat in range(cold_repeats):
        names = list(COLD_METHODS); rng.shuffle(names)
        for name in names:
            start = perf_counter()
            result = subprocess.run([sys.executable,'-B','-m','experiments.local_guards_archive_comparison.benchmark','--cold-worker',name],
                input=cold_input,text=True,capture_output=True,check=True,cwd=ROOT)
            cold.append({'repeat':repeat,'whole_process_ms_including_input_and_verification':(perf_counter()-start)*1000,
                         **json.loads(result.stdout)})
        # If thirty rounds would exceed the requested rough two-minute phase,
        # retain ten complete rounds per method instead of claiming thirty.
        if repeat==9 and (perf_counter()-started)*3>105 and cold_repeats>10:
            cold_reason='bounded to 10 complete rounds per method; projected 30-round cold phase exceeded 105 seconds'
            break
    summary = {}
    for name in METHODS:
        rows = [r for r in raw if r['method']==name]
        summary[name] = {'calls':len(rows),'unique_inputs':len({r['row_sha256'] for r in rows}),
            'adapter_applicable_calls':sum(r['adapter_applicable'] for r in rows),
            'unavailable_fields':dict(Counter(field for r in rows for field in r['unavailable_fields'])),
            'decisions':dict(Counter(r['decision'] for r in rows)),
            **{field:stats([r[field] for r in rows]) for field in ('full_ms','guard_ms','adapter_ms','probability_ms','calibration_and_gate_combined_ms')}}
    cold_summary = {}
    for name in COLD_METHODS:
        rows = [r for r in cold if r['method']==name]
        rss = sorted(r['peak_rss_bytes'] for r in rows)
        cold_summary[name] = {'n':len(rows),
            **{field:stats([r[field] for r in rows]) for field in ('import_and_model_load_ms','first_decision_ms','import_load_first_decision_ms','verification_ms_excluded','whole_process_ms_including_input_and_verification')},
            'peak_rss_bytes':{'p50':rss[math.ceil(.5*len(rss))-1],'p95':rss[math.ceil(.95*len(rss))-1]},
            'adapter_applicable':rows[0]['first_result']['adapter_applicable']}
    return {'created_at_utc':datetime.now(timezone.utc).isoformat(),'seed':17,'repeats':repeats,
        'selection_rule':'first30 released normalized TRAIN P4 JSONL payloads by SHA256; rule fixed by coordinator before inspection/predictions',
        'cold_input_row_sha256':selected[0]['row_sha256'],
        'selection':[{'row_sha256':r['row_sha256'],'prefix_id':r['row'].get('prefix_id')} for r in selected],
        'train_source':str(TRAIN.relative_to(ROOT)),'freeze':verified,
        'benchmark_source_sha256':digest(HERE/'benchmark.py'),'test_source_sha256':digest(HERE/'tests/test_benchmark.py'),
        'raw':raw,'summary':summary,'cold':cold,'cold_summary':cold_summary,
        'cold_phase_seconds':perf_counter()-started,'cold_bound_reason':cold_reason,
        'new_api_requests':0,'refit':False,'raw_cal_or_selected_input_used_for_timing':False,
        'disclosure':'During interface inspection author accidentally opened a frozen .cal.json containing CAL target labels; timing selection rule was predeclared, no source/config/selection adjustment or fit occurred. No selected evaluation rows were read for this task.',
        'scope':'single-row feature/adapter/model/decision timing; gzip loading, collector, diagnosis and native DB/working-store excluded'}


HOOK_METHODS = ('native_core','lr17_raw','cat17_raw','lr17_calibrated','cat17_calibrated')


def native_hook_trial(name,scenario,diagnosis=False,candidates=None):
    """Inject a verified callback into the unchanged API-free native P4 helper."""
    replay = importlib.import_module('experiments.local_guards_archive_comparison.replay')
    if name not in HOOK_METHODS: raise ValueError('hook method')
    candidates = candidates or {key:Candidate(value) for key,value in {
        'native_core':'native_core','lr17':'scenario_decision-lr-17','cat17':'scenario_decision-catboost-17'}.items()}
    def callback(row,_profile):
        if name=='native_core': return candidates['native_core'].native.guard(row,'native_core')
        candidate = candidates[name.split('_')[0]]
        if name.endswith('_raw'):
            probabilities = candidate.ml.probabilities(candidate.predictor.payload['model'],[row])[0]
            decision = max(sorted(probabilities),key=probabilities.get)
            reason = 'frozen_raw_classifier'
        else:
            result = candidate.predictor.predict(row,native_gate=False,placement='p4')
            probabilities,decision = result['probabilities'],result['calibrated_decision']
            reason = 'frozen_calibration_'+result['operating_point_status']
        return {'decision':decision,'reasons':[reason],'evidence':[],'probabilities':probabilities,'timing_ms':0.}
    # The old loader's f8... ML pin was never executed. Replace that loader,
    # not the old source: new source/weight checks happened before these loads.
    with patch.object(replay,'load_native_guard',return_value=(callback,NATIVE_SHA)):
        result = replay.native_profile_trial(scenario,diagnosis,expected_hash=NATIVE_SHA)
    result['hook_method'] = name
    result['policy_source_sha256'] = result.pop('method_sha256')
    result['bridge_profile_label'] = result.pop('profile')
    result['timings']['selected_guard_callback_ms'] = result['timings'].pop('native_guard_ms')
    return result


def native_hook_benchmark(repeats=30):
    verified = verify_release()
    candidates = {key:Candidate(value,verified) for key,value in {
        'native_core':'native_core','lr17':'scenario_decision-lr-17','cat17':'scenario_decision-catboost-17'}.items()}
    rng,raw = random.Random(17),[]
    for repeat in range(repeats):
        order = [(name,scenario,diagnosis) for name in HOOK_METHODS for scenario in ('safe','amount_mismatch') for diagnosis in (False,True)]
        rng.shuffle(order)
        for name,scenario,diagnosis in order:
            raw.append({'repeat':repeat,**native_hook_trial(name,scenario,diagnosis,candidates)})
    mismatches=[]
    for repeat in range(repeats):
        for name in HOOK_METHODS:
            for scenario in ('safe','amount_mismatch'):
                pair=[r for r in raw if (r['repeat'],r['hook_method'],r['scenario'])==(repeat,name,scenario)]
                keys=('status','payments','invoice_status','p4_verdicts','stop','model_calls')
                if {k:pair[0][k] for k in keys}!={k:pair[1][k] for k in keys}: mismatches.append([repeat,name,scenario])
    assert not mismatches,mismatches
    summary={}
    for name in HOOK_METHODS:
        for scenario in ('safe','amount_mismatch'):
            for diagnosis in (False,True):
                rows=[r for r in raw if (r['hook_method'],r['scenario'],r['diagnosis'])==(name,scenario,diagnosis)]
                summary[f'{name}/{scenario}/diagnosis_{"on" if diagnosis else "off"}']={
                    'completed':sum(r['status']=='completed' for r in rows),'stopped':sum(r['status']=='stopped' for r in rows),
                    'p4_verdicts':dict(Counter(v for r in rows for v in r['p4_verdicts'])),
                    'successful_full_chain_ms':stats([r['elapsed_ms'] for r in rows if r['status']=='completed']),
                    'time_to_stop_ms':stats([r['elapsed_ms'] for r in rows if r['status']=='stopped']),
                    **{key:stats([v for r in rows for v in r['timings'][key]]) for key in rows[0]['timings']}}
    fixture=sys.modules['experiments.local_guards_v4.tests.test_runtime'];directory=Path(fixture._TEMP.name)
    fixture.engine.dispose();fixture._TEMP.cleanup()
    return {'raw':raw,'summary':summary,'repeats':repeats,'seed':17,'diagnosis_effect_mismatches':mismatches,
        'freeze':verified,'benchmark_source_sha256':digest(HERE/'benchmark.py'),
        'test_source_sha256':digest(HERE/'tests/test_benchmark.py'),
        'unchanged_replay_helper_source_sha256':digest(HERE/'replay.py'),
        'native_source_database_removed':not directory.exists(),'new_api_requests':0,
        'scope':'actual native direct-Payments P4 callback, scripted safe/mismatch fixtures, no adaptive LLM or historical replay',
        'diagnosis':'same optional JSON serialization after decision-ready as unchanged replay helper; mandatory reasons/probabilities retained in both'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cold-worker',choices=METHODS)
    parser.add_argument('--native-hook-only',action='store_true')
    parser.add_argument('--repeats',type=int,default=30)
    parser.add_argument('--cold-repeats',type=int,default=30)
    parser.add_argument('--output',type=Path,default=HERE/'results/method-latency.json')
    args=parser.parse_args()
    if not 1<=args.repeats<=30 or not 10<=args.cold_repeats<=30: parser.error('bounded repeats:1..30; cold repeats:10..30')
    if args.native_hook_only:
        with offline(): hook=native_hook_benchmark(args.repeats)
        report=json.loads(args.output.read_text());report['native_hook']=hook
        args.output.write_text(json.dumps(report,separators=(',',':'),allow_nan=False)+'\n')
        print(json.dumps({'native_hook_chains':len(hook['raw']),'diagnosis_mismatches':hook['diagnosis_effect_mismatches']}))
        return
    with offline():
        report=cold_worker(args.cold_worker) if args.cold_worker else benchmark(args.repeats,args.cold_repeats)
    if args.cold_worker: print(json.dumps(report,allow_nan=False))
    else:
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        print(json.dumps({'output':str(args.output),'summary':report['summary'],'cold_counts':{k:v['n'] for k,v in report['cold_summary'].items()}},indent=2))


if __name__=='__main__': main()
