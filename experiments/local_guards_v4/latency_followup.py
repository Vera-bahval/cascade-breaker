"""Post-hoc latency benchmark of frozen candidates; no fitting or network calls."""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import random
import resource
import socket
import subprocess
import sys
import tempfile
from time import perf_counter, sleep

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from experiments.local_guards_v4 import evaluate as ev


def stats(values):
    v = sorted(values)
    return {'n': len(v), 'p50_ms': v[(len(v)-1)//2] if v else None,
            'p95_ms': v[math.ceil(.95*len(v))-1] if v else None,
            'mean_ms': sum(v)/len(v) if v else None}


def configs():
    return json.loads((HERE/'results/configurations.json').read_text())['methods']


@contextmanager
def offline():
    from unittest.mock import patch
    connect = socket.socket.connect
    def block(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError('external networking forbidden')
        return connect(sock, address)
    with patch.object(socket.socket, 'connect', block), patch.object(
            socket, 'create_connection', side_effect=AssertionError('network forbidden')):
        yield


class Candidate:
    def __init__(self, config):
        self.config = config
        sys.path.insert(0, str(ev.V3))
        self.policy = json.loads((ev.V3/'policy.json').read_text())
        self.v3 = ev.load_module(ev.V3/'rules_v3.py', 'latency_v3')
        self.legacy = ev.load_module(ev.V3/'legacy_adapter.py', 'latency_legacy')
        self.v4 = ev.load_module(HERE/'guard.py', 'latency_v4')
        if config['kind'] == 'saved_ml':
            import ml_v3
            self.ml = ml_v3
            path = ev.V3/'results/frozen'/config['model_file']
            assert ev.digest(path) == config['model_hash']
            self.model = pickle.loads(path.read_bytes())

    def __call__(self, row):
        c = self.config
        if not ev.is_eligible(row, c):
            return {'checked': False, 'decision': None, 'stop': False, 'reasons': []}
        obj, kind = row['observation'], c['kind']
        if kind == 'v4':
            r = self.v4.guard(obj, {'profile': 'B' if any(x.startswith('B') for x in c['requirements']) else 'A',
                                   'enabled_requirements': c['requirements']})
        elif kind == 'v3':
            r = self.v3.guard(ev.baseline_observation(row), self.policy)
        elif kind == 'legacy':
            r = self.legacy.guard(ev.baseline_observation(row), c['name'], self.policy)
        elif kind == 'saved_ml':
            base = ev.baseline_observation(row)
            missing = self.v3.required_missing(base, self.policy)
            # Keep the frozen evaluator's score-before-missing decision semantics.
            compatible = c['model'] != 'text_diagnostic' or ev.text_compatible(base)
            score = float(self.ml.score_model(self.model, [base])[0]) if compatible else None
            threshold = {'Infinity': math.inf, '-Infinity': -math.inf}.get(str(c['threshold']), c['threshold'])
            r = {'decision': 'UNKNOWN' if missing or score is None or not math.isfinite(score)
                 else 'BLOCK' if score >= threshold else 'ALLOW', 'reasons': missing}
        else:
            r = {'decision': 'ALLOW' if kind == 'allow' else 'BLOCK', 'reasons': []}
        return {**r, 'checked': True, 'stop': r['decision'] in {'BLOCK','UNKNOWN'}}


def pure_benchmark(repeats):
    rows = ev.read_rows(HERE/'closed/observations.jsonl.gz')
    expected = {(r['method'], r['prefix_id']): r for r in ev.read_rows(HERE/'results/closed-predictions.jsonl.gz')}
    candidates = {c['name']: Candidate(c) for c in configs()}
    rng, raw, mismatches = random.Random(17), [], []
    for repeat in range(repeats):
        order = list(candidates); rng.shuffle(order)
        for name in order:
            indices = list(range(len(rows))); rng.shuffle(indices)
            for i in indices:
                row = rows[i]; start = perf_counter(); r = candidates[name](row)
                ms = (perf_counter()-start)*1000
                e = expected[name, row['prefix_id']]
                if (r['decision'],r['checked'],r['stop']) != (e['decision'],e['checked'],e['stop']):
                    mismatches.append([name,row['prefix_id'],r['decision'],e['decision']])
                raw.append({'method':name,'repeat':repeat,'prefix_id':row['prefix_id'],
                            'checked':r['checked'],'decision':r['decision'],'elapsed_ms':ms})
    assert not mismatches, mismatches[:10]
    return {'raw':raw,'frozen_prediction_mismatches':mismatches,
            'summary':{name:{'all_routed':stats([r['elapsed_ms'] for r in raw if r['method']==name]),
                'applied':stats([r['elapsed_ms'] for r in raw if r['method']==name and r['checked']]),
                'text_present':sum(ev.text_compatible(ev.baseline_observation(r)) for r in rows if ev.is_eligible(r,candidates[name].config))}
                for name in candidates}}


def cold_worker(name):
    started = perf_counter()
    c = Candidate(next(c for c in configs() if c['name']==name))
    rows = ev.read_rows(HERE/'closed/observations.jsonl.gz')
    row = next(r for r in rows if ev.is_eligible(r,c.config))
    result = c(row)
    return {'method':name,'inside_worker_seconds':perf_counter()-started,
            'first_decision':result['decision'],
            'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)}


def native_benchmark(repeats):
    import asyncio
    from unittest.mock import patch
    from experiments.local_guards_v4.tests.test_runtime import (
        NativeRuntimeTests, tool, done, Runtime, run_orchestrator_agent, db_session, PaymentTransaction, Invoice)
    import experiments.local_guards_v4.runtime as runtime_module
    from finbot.probe import v4
    rng, raw = random.Random(29), []
    candidates = {c['name']:Candidate(c) for c in configs()}
    original_check = Runtime.check
    for repeat in range(repeats):
        names = ['profile_off',*candidates]; rng.shuffle(names)
        for name in names:
            print('native trial',repeat,name,flush=True)
            case = NativeRuntimeTests('test_safe_full_native_workflow'); case.setUp()
            try:
                case.runtime.fixture.pop('fraud_review_completed')
                candidate = candidates.get(name)
                has_claim = candidate is not None and 'B02' in candidate.config['requirements']
                case.runtime.profile = 'B' if has_claim else 'A'
                def bookkeeping():
                    with db_session() as db: reference = db.query(PaymentTransaction).one().transfer_id
                    return [tool('process_payment',invoice_id=3,payment_method='bank_transfer',payment_reference=reference,agent_notes='paid')]
                case.script({'orchestrator_agent':[
                    [tool('delegate_to_fraud',vendor_id=2,task_description='review')],
                    [tool('delegate_to_invoice',invoice_id=3,task_description='review')],
                    [tool('delegate_to_payments',invoice_id=3,task_description='pay')],[done()]],
                    'fraud_agent':[[tool('get_invoice_details',invoice_id=3),tool('get_vendor_risk_profile',vendor_id=2)],[done()]],
                    'invoice_agent':[[tool('update_invoice_status',invoice_id=3,status='approved',agent_notes='reviewed')],[done()]],
                    'payments_agent':[[tool('finstripe__create_transfer',vendor_account='account',amount=100.,invoice_reference='fixture',vendor_id=2,invoice_id=3)],bookkeeping,[done()]]},mcp=True)
                checks, verdicts, tools = [], [], []
                def selected_guard(obj, _profile):
                    r = candidate({'observation':obj})
                    verdicts.append({'checkpoint':obj['checkpoint'],'tool':obj['proposal'].get('tool'),
                                     'decision':r['decision'],'checked':r['checked']})
                    return {**r,'evidence':[],'timing_ms':0.}
                def measured_check(runtime,*a,**kw):
                    start = perf_counter()
                    try: return original_check(runtime,*a,**kw)
                    finally: checks.append((perf_counter()-start)*1000)
                original_invoke = Runtime.invoke
                async def counted_invoke(runtime,agent,tool_name,args,execute):
                    tools.append(tool_name)
                    return await original_invoke(runtime,agent,tool_name,args,execute)
                start=perf_counter(); status='completed'; stopped=None
                with patch.object(runtime_module,'guard',selected_guard), patch.object(Runtime,'check',measured_check), patch.object(Runtime,'invoke',counted_invoke):
                    try:
                        with case.runtime.open() if candidate else nullcontext():
                            result=asyncio.run(run_orchestrator_agent(case.task,case.session))
                            assert result['task_status']=='success',(name,result,case.calls,verdicts)
                    except v4.V4Stop as exc:
                        status='stopped'; stopped=exc.decision
                elapsed=(perf_counter()-start)*1000
                with db_session() as db:
                    payments=db.query(PaymentTransaction).count(); invoice_status=db.get(Invoice,3).status
                if status=='completed': assert payments==1 and invoice_status=='paid',(name,payments,invoice_status)
                else: assert payments==0,(name,payments)
                raw.append({'method':name,'repeat':repeat,'elapsed_ms':elapsed,'status':status,
                    'payments':payments,'invoice_status':invoice_status,'model_stub_calls':len(case.calls),
                    'intercepted_tool_invocations':len(tools),'check_ms':checks,
                    'verdicts':verdicts,'stop':stopped})
            finally:
                # Manual fixture use has no IsolatedAsyncioTestCase runner.
                # doCleanups would swallow cleanup errors and leak client patches.
                case.stack.close()
                case.directory.cleanup()
    summary={}
    for name in ['profile_off',*candidates]:
        rows=[r for r in raw if r['method']==name]
        good=[r for r in rows if r['status']=='completed']
        off={r['repeat']:r['elapsed_ms'] for r in raw if r['method']=='profile_off'}
        summary[name]={'whole_chain':stats([r['elapsed_ms'] for r in rows]),
            'completed':len(good),'stopped':len(rows)-len(good),
            'successful_paired_overhead':stats([r['elapsed_ms']-off[r['repeat']] for r in good]),
            'full_check':stats([v for r in rows for v in r['check_ms']]),
            'model_stub_calls':sorted(set(r['model_stub_calls'] for r in rows)),
            'intercepted_tool_invocations':sorted(set(r['intercepted_tool_invocations'] for r in rows))}
    return {'raw':raw,'summary':summary}


def contention_benchmark(repeats):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from experiments.local_guards_v4.store import EvidenceStore, ClaimConflict
    raw=[]
    for repeat in range(repeats):
        for workers in (1,4,8):
            for scope in ('different_invoices','same_invoice','vendor_wide_overlap'):
                for enabled in (False,True):
                    with tempfile.TemporaryDirectory() as td:
                        store=EvidenceStore(Path(td)/'claims.sqlite')
                        if scope=='vendor_wide_overlap': store.acquire_claim('ns',2,None,'existing',1)
                        ready,acquired=Barrier(workers),Barrier(workers)
                        def worker(i):
                            ready.wait(); start=perf_counter(); outcome='admitted'
                            invoice=3+i if scope!='same_invoice' else 3
                            if enabled:
                                try:store.acquire_claim('ns',2,invoice,str(i),2)
                                except ClaimConflict:outcome='rejected'
                            admission_ms=(perf_counter()-start)*1000
                            acquired.wait()
                            if outcome=='admitted':
                                sleep(.05)
                                if enabled:store.release_claim(str(i),True)
                            return {'worker':i,'outcome':outcome,'admission_ms':admission_ms,'request_ms':(perf_counter()-start)*1000 if outcome=='admitted' else admission_ms}
                        start=perf_counter()
                        with ThreadPoolExecutor(max_workers=workers) as pool: attempts=list(pool.map(worker,range(workers)))
                        raw.append({'repeat':repeat,'workers':workers,'scope':scope,'B02_enabled':enabled,
                            'batch_ms':(perf_counter()-start)*1000,'attempts':attempts})
    recovery=[]
    for delay_ms in (0,50,200):
        for repeat in range(repeats):
            with tempfile.TemporaryDirectory() as td:
                s=EvidenceStore(Path(td)/'recovery.sqlite');s.acquire_claim('ns',2,3,'failed',1)
                s.release_claim('failed',False);start=perf_counter()
                try:s.acquire_claim('ns',2,3,'retry',2)
                except ClaimConflict:pass
                else:raise AssertionError('uncertain claim allowed retry')
                rejected_ms=(perf_counter()-start)*1000
                start=perf_counter();sleep(delay_ms/1000);s.release_claim('failed',True)
                s.acquire_claim('ns',2,3,'retry',3)
                recovery.append({'repeat':repeat,'assigned_reconciliation_delay_ms':delay_ms,
                    'rejected_attempt_ms':rejected_ms,'until_readmission_ms':(perf_counter()-start)*1000})
    return {'raw':raw,'recovery':recovery,'assigned_hold_ms':50}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path);p.add_argument('--cold-worker')
    p.add_argument('--pure-repeats',type=int,default=5);p.add_argument('--native-repeats',type=int,default=15)
    p.add_argument('--contention-repeats',type=int,default=5)
    args=p.parse_args()
    with offline():
        if args.cold_worker:
            print(json.dumps(cold_worker(args.cold_worker)));return
        assert args.output and not args.output.exists(),'output required; refusing overwrite'
        ev.verify_manifest(HERE/'results/methods-final.json')
        cold=[]
        for c in configs():
            start=perf_counter()
            r=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--cold-worker',c['name']],capture_output=True,text=True,check=True)
            cold.append({**json.loads(r.stdout),'parent_wall_seconds':perf_counter()-start})
        print('Cold starts complete.',flush=True)
        pure=pure_benchmark(args.pure_repeats);print('Single decisions complete.',flush=True)
        native=native_benchmark(args.native_repeats);print('Native chains complete.',flush=True)
        contention=contention_benchmark(args.contention_repeats)
    import platform
    result={'created_at':datetime.now(timezone.utc).isoformat(),'phase':'posthoc_open_engineering_benchmark',
        'base_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_sha256':ev.digest(Path(__file__)),'python':sys.version,'platform':platform.platform(),
        'cpu_count':os.cpu_count(),'argv':sys.argv,'new_inference_api_calls':0,
        'inputs':{str(f.relative_to(ROOT)):ev.digest(f) for f in [HERE/'closed/observations.jsonl.gz',HERE/'results/closed-predictions.jsonl.gz',HERE/'results/configurations.json',HERE/'results/frozen-methods.json']},
        'cold':cold,'pure':pure,'native':native,'contention':contention}
    ev.write_json(args.output,result)
    print(json.dumps({'output':str(args.output),'decisions':len(pure['raw']),'native_chains':len(native['raw']),
        'contention_batches':len(contention['raw']),'recovery_cases':len(contention['recovery'])}))


if __name__=='__main__':main()
