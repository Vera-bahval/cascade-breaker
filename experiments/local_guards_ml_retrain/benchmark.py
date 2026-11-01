"""Offline post-freeze engineering benchmarks; never opens new target labels.

single: true single-state inference (features included), five randomized passes.
load: fresh interpreter per model; response availability separate from teardown.
native: identical enriched native source adapter for all candidates, five passes.
smoke: bounded diagnostic subset only; not a72-model performance result.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from contextlib import contextmanager, nullcontext
import json
import os
from pathlib import Path
import random
import resource
import socket
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
THREAD_ENV=('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','VECLIB_MAXIMUM_THREADS')
for key in THREAD_ENV:
    os.environ.setdefault(key,'2')
    if os.environ[key]!='2':raise RuntimeError(key+' must be2 for every benchmark/control')
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'finbot'))


def evaluation():
    import evaluation as ev
    return ev


@contextmanager
def offline():
    from unittest.mock import patch
    connect=socket.socket.connect
    def block(sock,address):
        if sock.family in (socket.AF_INET,socket.AF_INET6):raise AssertionError('external sockets forbidden')
        return connect(sock,address)
    with patch.object(socket.socket,'connect',block),patch.object(socket,'create_connection',side_effect=AssertionError('external sockets forbidden')):yield


def environment():
    import platform
    from importlib.metadata import version
    return dict(os=platform.platform(),python=sys.version,executable=sys.executable,
        libraries={p:version(p) for p in ('numpy','scikit-learn','catboost','sqlalchemy','fastmcp')},
        numerical_threads={k:os.environ[k] for k in THREAD_ENV},quantile='nearest rank ceil(p*n), for both p50 and p95')


def write_summary(output,result):
    ev=evaluation();output=Path(output)
    paths=[Path(__file__),HERE/'evaluation.py',HERE.with_name('local_guards_v4')/'runtime.py',
           HERE.with_name('local_guards_v4')/'guard.py',HERE.with_name('local_guards_v4')/'store.py',
           HERE.with_name('local_guards_v4')/'tests/test_runtime.py']
    paths += [ROOT/'finbot/finbot'/n for n in ('agents/base.py','agents/chat.py','agents/orchestrator.py','agents/runner.py','probe/v4.py')]
    result['source_sha256']={str(p.resolve()):ev.digest(p) for p in paths}
    result['reproduction_argv']=sys.argv
    ev.write_json(output/'summary.json',result)
    ev.write_json(output/'artifact-hashes.json',{p.name:ev.digest(p) for p in sorted(output.iterdir()) if p.is_file()})


def selected_methods(freeze,names=None):
    ev=evaluation();manifest=ev.verify_freeze(freeze)
    selected=[m for m in manifest['methods'] if not names or m['name'] in names]
    if names and {m['name'] for m in selected}!=set(names):raise ValueError('unknown selected method')
    return manifest,selected


def stratified_sample(rows,metadata,contract,limit=128):
    ev=evaluation();bins=defaultdict(list);rng=random.Random(17)
    for row in rows:
        if ev.eligible(row,contract):bins[(ev.obj(row)['checkpoint'],metadata[row['prefix_id']].get('family','unspecified'))].append(row)
    for key in sorted(bins):bins[key].sort(key=lambda r:r['prefix_id']);rng.shuffle(bins[key])
    sample=[]
    while bins and len(sample)<limit:
        for key in sorted(list(bins)):
            sample.append(bins[key].pop())
            if not bins[key]:del bins[key]
            if len(sample)==limit:break
    return sample


def single(freeze,observations,metadata,output,repeats=5,limit=128,methods=None):
    ev=evaluation();manifest,selected=selected_methods(freeze,methods);meta=ev.keyed(metadata)
    ev.validate_join(observations,meta);rows=list(ev.read_lines(observations))
    samples={c:stratified_sample(rows,meta,c,limit) for c in ev.CONTRACTS}
    configs=[dict(kind='rule',contract=c,name='rule_'+c) for c in ev.CONTRACTS]+selected
    rng=random.Random(17);summaries=defaultdict(lambda:defaultdict(list))
    with offline(),ev.Shards(output) as sink:
        for repeat in range(repeats):
            order=list(configs);rng.shuffle(order)
            for config in order:
                is_rule=config.get('kind')=='rule';candidate=ev.Rule(config['contract']) if is_rule else ev.Frozen(freeze,config,manifest)
                states=list(samples[config['contract']]);rng.shuffle(states)
                for variant in (['rule'] if is_rule else ['raw','gated']):
                    name=config['name'] if is_rule else config['name']+'__'+variant
                    for row in states:
                        start=time.perf_counter_ns();r=candidate(row) if is_rule else candidate.one(row,variant);elapsed=(time.perf_counter_ns()-start)/1e6
                        record=dict(method=name,contract=config['contract'],repeat=repeat,prefix_id=row['prefix_id'],variant=variant,elapsed_ms=elapsed,decision=r['decision'],checked=r['checked'],timing=r.get('timing',{}))
                        # Separate component measurement on this same individual
                        # state. These diagnostic timings are not subtracted from
                        # end-to-end wall time and never batch-amortized.
                        if not is_rule:
                            start=time.perf_counter_ns();f=ev.features(row,config['feature_mode']);feature_ms=(time.perf_counter_ns()-start)/1e6
                            start=time.perf_counter_ns();ps=ev.probabilities(candidate.model,ev.FeatureBatch([f],config['feature_mode']));proba_ms=(time.perf_counter_ns()-start)/1e6
                            if ps[0]!=r['probabilities']:raise AssertionError('FeatureBatch pipeline differs from full single-state pipeline')
                            record['component_diagnostic']=dict(feature_ms=feature_ms,precomputed_pipeline_ms=proba_ms)
                        sink.write(config['contract'],name,record)
                        summaries[name]['single_call'].append(elapsed)
                        for k,v in r.get('timing',{}).items():
                            if v is not None:summaries[name][k].append(v)
        result=dict(kind='individual inference, applicable states only',environment=environment(),repeats=repeats,
            input_identity=ev.input_identity(observations,metadata),freeze_sha256=ev.digest(Path(freeze)/'freeze-manifest.json'),
            sample_ids={c:[r['prefix_id'] for r in rs] for c,rs in samples.items()},
            summary={name:{k:ev.stats(v) for k,v in groups.items()} for name,groups in summaries.items()},
            limitations=['Raw mode is diagnostic only.','Components are additional individual calls, not additive decompositions.','No eligibility/no-check time in applicable distribution.'])
    result['raw_files']=sink.files;write_summary(output,result)


def cold_worker(freeze,method,observation):
    began=time.perf_counter_ns();ev=evaluation()
    manifest=json.loads((Path(freeze)/'freeze-manifest.json').read_text());entry=next(m for m in manifest['methods'] if m['name']==method)
    before=time.perf_counter_ns();candidate=ev.Frozen(freeze,entry,manifest);loaded=time.perf_counter_ns()
    row=json.loads(Path(observation).read_text());r=candidate.one(row,'gated');ready=time.perf_counter_ns()
    record=dict(kind='first_response',method=method,decision=r['decision'],checked=r['checked'],
        worker_import_load_first_response_ms=(ready-began)/1e6,verified_model_load_ms=(loaded-before)/1e6,
        first_applicable_call_ms=(ready-loaded)/1e6,
        model_file_bytes=(Path(freeze)/entry['model_file']).stat().st_size,
        peak_process_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024))
    print(json.dumps(record),flush=True)


def load(freeze,observations,metadata,output,methods=None):
    ev=evaluation();_,selected=selected_methods(freeze,methods);meta=ev.keyed(metadata);ev.validate_join(observations,meta)
    first={}
    for row in ev.read_lines(observations):
        for contract in ev.CONTRACTS:
            if contract not in first and ev.eligible(row,contract):first[contract]=row
        if len(first)==3:break
    import tempfile
    raw=[]
    with tempfile.TemporaryDirectory(prefix='finbot-cold-') as td,offline(),ev.Shards(output) as sink:
        for entry in selected:
            if entry['contract'] not in first:raise ValueError('no applicable cold-start state')
            path=Path(td)/(entry['contract']+'.json');path.write_text(ev.canonical(first[entry['contract']]))
            start=time.perf_counter_ns()
            process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'cold-worker','--freeze',str(Path(freeze).resolve()),'--method',entry['name'],'--observation',str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=os.environ.copy())
            line=process.stdout.readline();available=time.perf_counter_ns()
            if not line:
                _,err=process.communicate();raise RuntimeError('cold worker produced no response: '+err[-2000:])
            r=json.loads(line);remaining,err=process.communicate();ended=time.perf_counter_ns()
            if process.returncode or remaining.strip():raise RuntimeError('cold worker failure: '+err[-2000:])
            r.update(parent_first_response_available_ms=(available-start)/1e6,parent_process_exit_ms=(ended-start)/1e6,response_to_exit_ms=(ended-available)/1e6)
            raw.append(r);sink.write(entry['contract'],entry['name'],r)
    write_summary(output,dict(environment=environment(),raw=raw,raw_files=sink.files,
        observations_sha256=ev.digest(observations),freeze_sha256=ev.digest(Path(freeze)/'freeze-manifest.json'),
        caveats=['One fresh worker per model, not a stable tail estimate.','Filesystem is warm; imports/runtime/verification included.','RSS is whole Python/dependency process, not model size.','Parent first-response availability precedes process teardown.']))


def delegation_context(checkpoint,invocation):
    if checkpoint!='P2' or not invocation:return {}
    agent,name,_,observation=invocation
    if not str(name).startswith('delegate_to_'):return {}
    parent=getattr(agent,'workflow_id',None) or getattr(agent,'_workflow_id',None)
    call=(observation.get('context') or {}).get('call_id')
    result={}
    if isinstance(parent,str) and parent:result['parent_workflow_id']=parent
    if isinstance(call,str) and call:result['call_id']=call
    return result


def native_imports():
    # Insert this checkout before the old fixture module can import an editable
    # FinBot installation from another checkout. Fail if already contaminated.
    sys.path.insert(0,str(ROOT/'finbot'))
    import importlib
    result={}
    expected=(ROOT/'finbot/finbot').resolve()
    for name in ('finbot.agents.base','finbot.agents.chat','finbot.agents.orchestrator'):
        module=importlib.import_module(name);path=Path(module.__file__).resolve()
        if not path.is_relative_to(expected):raise AssertionError('wrong FinBot checkout: '+str(path))
        result[name]=str(path)
    return result


def native_trial(candidate,name,contract,variant='gated',enriched=True,fixture='positive'):
    import asyncio
    from unittest.mock import patch
    from experiments.local_guards_v4.tests import test_runtime as nt
    import experiments.local_guards_v4.runtime as rm
    from starlette.background import BackgroundTasks
    ev=evaluation();provenance=native_imports()
    case=nt.NativeRuntimeTests('test_safe_full_native_workflow');case.setUp()
    Runtime=nt.Runtime;original_snapshot=Runtime.snapshot;original_check=Runtime.check;original_invoke=Runtime.invoke
    checks=[];verdicts=[];invocations=[];observations=[];linkages=[];timings=defaultdict(list)
    try:
        case.runtime.fixture.pop('fraud_review_completed');case.runtime.profile='B' if contract=='B' else 'A'
        def bookkeeping():
            with nt.db_session() as db:reference=db.query(nt.PaymentTransaction).one().transfer_id
            return [nt.tool('process_payment',invoice_id=3,payment_method='bank_transfer',payment_reference=reference,agent_notes='paid')]
        case.script({'orchestrator_agent':[[nt.tool('delegate_to_fraud',vendor_id=2,task_description='review')],
            [nt.tool('delegate_to_invoice',invoice_id=3,task_description='review')],
            [nt.tool('delegate_to_payments',invoice_id=3,task_description='pay')],[nt.done()]],
            'fraud_agent':[[nt.tool('get_invoice_details',invoice_id=3),nt.tool('get_vendor_risk_profile',vendor_id=2)],[nt.done()]],
            'invoice_agent':[[nt.tool('update_invoice_status',invoice_id=3,status='approved',agent_notes='reviewed')],[nt.done()]],
            'payments_agent':[[nt.tool('finstripe__create_transfer',vendor_account='account',amount=101. if fixture=='amount_mismatch' else 100.,invoice_reference='fixture',vendor_id=2,invoice_id=3)],bookkeeping,[nt.done()]]},mcp=True)
        def snapshot(runtime,checkpoint,agent,tool,arguments,**extra):
            additions=delegation_context(checkpoint,rm._INVOKING.get()) if enriched else {}
            extra.update(additions)
            if additions:linkages.append(dict(checkpoint=checkpoint,**additions))
            result=original_snapshot(runtime,checkpoint,agent,tool,arguments,**extra)
            observations.append(result);return result
        def guard(o,_profile):
            start=time.perf_counter_ns()
            r=candidate({'observation':o}) if isinstance(candidate,ev.Rule) else candidate.one({'observation':o},variant)
            wall=(time.perf_counter_ns()-start)/1e6
            verdicts.append(dict(checkpoint=o['checkpoint'],tool=o['proposal'].get('tool'),decision=r['decision'],checked=r['checked'],stop=r['stop'],reasons=r.get('reasons',[]),gate_reasons=r.get('gate_reasons',[]),candidate_wall_ms=wall))
            for k,v in r.get('timing',{}).items():
                if v is not None:timings[k].append(v)
            return dict(r,evidence=[],timing_ms=wall)
        def check(runtime,*args,**kwargs):
            start=time.perf_counter_ns()
            try:return original_check(runtime,*args,**kwargs)
            finally:checks.append((time.perf_counter_ns()-start)/1e6)
        async def invoke(runtime,agent,tool,arguments,execute):
            invocations.append(dict(tool=tool,actor=rm.technical_actor(agent)))
            return await original_invoke(runtime,agent,tool,arguments,execute)
        async def chain():
            background=BackgroundTasks();chat=nt.CoPilotAssistant(case.session,background)
            # Actual chat admission, captured child runtime, background execution,
            # native delegations, native tools and MCP transfer are all traversed.
            with case.runtime.agent_scope(chat,{'vendor_id':2,'invoice_id':3}) if candidate else nullcontext():
                response=await chat._execute_tool('start_workflow',dict(description='benchmark fixture',vendor_id=2,invoice_id=3))
                if 'started' not in response:raise AssertionError(response)
            await background()
        status='completed';stopped=None
        with patch.object(Runtime,'snapshot',snapshot),patch.object(Runtime,'check',check),patch.object(Runtime,'invoke',invoke),patch.object(rm,'guard',guard):
            start=time.perf_counter_ns()
            try:asyncio.run(chain())
            except nt.v4.V4Stop as error:status='stopped';stopped=error.decision
            elapsed=(time.perf_counter_ns()-start)/1e6
        with nt.db_session() as db:payments=db.query(nt.PaymentTransaction).count();invoice_status=db.get(nt.Invoice,3).status
        if status=='completed' and (payments!=1 or invoice_status!='paid'):raise AssertionError((payments,invoice_status))
        if status=='stopped' and payments!=0:raise AssertionError('stopped fixture had a payment')
        if candidate is None or isinstance(candidate,ev.Rule):
            if fixture=='positive' and status!='completed':raise AssertionError('positive native control stopped: '+str(stopped))
            if fixture=='amount_mismatch' and (status!='stopped' or stopped['decision']!='BLOCK'):raise AssertionError('negative native fixture not blocked')
        proof_gate_diagnostic=[]
        if isinstance(candidate,ev.Rule):
            proof_gate_diagnostic=[dict(checkpoint=o['checkpoint'],tool=o['proposal'].get('tool'),**ev.mandatory_proof_gate({'observation':o},contract)) for o in observations if ev.eligible({'observation':o},contract)]
            if enriched and fixture=='positive' and any(not g['allow'] for g in proof_gate_diagnostic):raise AssertionError('positive native adapter lacks required evidence')
        return dict(method=name,contract=contract,variant=variant,fixture=fixture,adapter='trusted_parent_linkage' if enriched else 'original_v4_snapshot',
            status=status,elapsed_ms=elapsed,check_ms=checks,verdicts=verdicts,observations=observations,
            payments=payments,invoice_status=invoice_status,model_stub_calls=len(case.calls),intercepted_tools=invocations,
            stop=stopped,linkage_enrichment=linkages,component_timings=dict(timings),proof_gate_diagnostic=proof_gate_diagnostic,import_provenance=provenance,
            declared_fixture_contract=dict(case.runtime.fixture),external_api_calls=0)
    finally:case.stack.close();case.directory.cleanup()


def native_summary(rows):
    ev=evaluation();groups=defaultdict(list)
    for row in rows:groups[row['method']].append(row)
    return {name:dict(completed=sum(r['status']=='completed' for r in rs),stopped=sum(r['status']=='stopped' for r in rs),
        completed_chain=ev.stats([r['elapsed_ms'] for r in rs if r['status']=='completed']),
        stopped_chain=ev.stats([r['elapsed_ms'] for r in rs if r['status']=='stopped']),
        full_Runtime_check=ev.stats([v for r in rs for v in r['check_ms']]),
        components={k:ev.stats([v for r in rs for v in r.get('component_timings',{}).get(k,[])]) for k in {k for r in rs for k in r.get('component_timings',{})}}) for name,rs in groups.items()}


def native(freeze,output,repeats=5,methods=None,smoke=False):
    ev=evaluation();manifest,selected=selected_methods(freeze,methods)
    if smoke and not methods:
        selected=[m for m in selected if m['feature_mode']=='new' and m['source']=='mixed' and m['family']=='logistic' and m['seed']==17]
    configs=[dict(name='profile_off',contract='B',kind='off',variant='off')]
    configs += [dict(name='rule_'+c,contract=c,kind='rule',variant='rule') for c in ev.CONTRACTS]
    configs += [dict(m,name=m['name']+'__'+variant,model_name=m['name'],kind='model',variant=variant) for m in selected for variant in ('raw','gated')]
    rows=[];rng=random.Random(29)
    with offline(),ev.Shards(output) as sink:
        for repeat in range(1 if smoke else repeats):
            order=list(configs);rng.shuffle(order)
            for c in order:
                candidate=None if c['kind']=='off' else ev.Rule(c['contract']) if c['kind']=='rule' else ev.Frozen(freeze,next(m for m in selected if m['name']==c['model_name']),manifest)
                trial=native_trial(candidate,c['name'],c['contract'],c['variant']);trial['repeat']=repeat
                sink.write(c['contract'],c['name'],trial);rows.append({k:v for k,v in trial.items() if k not in ('observations','verdicts','intercepted_tools')})
                print('native',repeat,c['name'],trial['status'],trial['payments'],flush=True)
        # Retain original observation behavior, and one explicit negative path.
        for contract,enriched,fixture in [('A',False,'positive'),('B',False,'positive'),('B',True,'amount_mismatch')]:
            name='diagnostic_rule_'+contract+('_old_observation' if not enriched else '_amount_mismatch')
            trial=native_trial(ev.Rule(contract),name,contract,'rule',enriched,fixture);trial['repeat']=0
            sink.write(contract,name,trial);rows.append({k:v for k,v in trial.items() if k not in ('observations','verdicts','intercepted_tools')})
    summary=dict(kind='bounded_smoke_not72_model_benchmark' if smoke else 'native scripted full-chain benchmark',environment=environment(),
        freeze_sha256=ev.digest(Path(freeze)/'freeze-manifest.json'),summary=native_summary(rows),raw_files=sink.files,
        smoke_rows=rows if smoke else None,
        limitations=['Scripted local clients, no adaptive realLLM/production latency or cost evidence.',
            'Full Runtime.check includes sidecar source reads/writes even for payment-only candidate.',
            'Benchmark-only P2 parent derives from actual invoking source workflow; call_id reuses actual delegation call before proof construction, identically for rules and ML.',
            'Old shared-owner runtime retained; old-observation rule diagnostics included.',
            'Declared USD ledger and initial no-HOLD fixture; fraud completion only actual native reads plus completion.',
            'Raw classifier mode diagnostic only, isolated disposable DBs.',
            'STOP and completed chain distributions are separate; STOP is not speedup.'])
    write_summary(output,summary)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for command in ('single','load','native','smoke','cold-worker'):
        p=sub.add_parser(command);p.add_argument('--freeze',required=True)
        if command=='cold-worker':p.add_argument('--method',required=True);p.add_argument('--observation',required=True);continue
        p.add_argument('--output',required=True);p.add_argument('--methods',nargs='+')
        if command in ('single','load'):p.add_argument('--observations',required=True);p.add_argument('--metadata',required=True)
        if command in ('single','native'):p.add_argument('--repeats',type=int,default=5)
        if command=='single':p.add_argument('--limit',type=int,default=128)
    args=vars(parser.parse_args());command=args.pop('command')
    with offline():
        if command=='smoke':native(**args,smoke=True)
        else:globals()[command.replace('-','_')](**args)

if __name__=='__main__':main()
