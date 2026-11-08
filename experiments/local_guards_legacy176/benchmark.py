"""30 shuffled repetitions on exact176; isolated replay storage, no model calls."""
import json
from pathlib import Path
from random import Random
import sqlite3
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from .prepare import HERE,prepare_one
from .run import CONFIGS,admitted,checker,decision
from experiments.local_guards_adapter_repair.adapters import adapt
from experiments.local_guards_adapter_repair.inventory import rows,sha,write_json
from experiments.local_guards_adapter_repair.prepare import writer,preparation_fence
from experiments.local_guards_archive_comparison.collector import digest


def canonical_result(value,key=''):
    if isinstance(value,dict):return {k:canonical_result(v,k) for k,v in value.items()}
    if isinstance(value,list):
        items=[canonical_result(v) for v in value]
        return sorted(items,key=lambda x:json.dumps(x,sort_keys=True)) if key=='evidence' else items
    return value


def benchmark():
    admitted();out=HERE/'benchmark.jsonl.gz'
    if out.exists():raise FileExistsError(out)
    cases={c['prefix_id']:c for c in rows(HERE/'source-prefixes.jsonl.gz')}
    expected={r['prefix_id']:r for r in rows(HERE/'prepared-inputs.jsonl.gz') if r['mode']=='full'}
    frozen={(r['prefix_id'],r['method']):r['result'] for r in rows(HERE/'predictions.jsonl.gz') if r['mode']=='full'}
    fns={c['name']:checker(c) for c in CONFIGS};rng=Random(17);checks=0;count=0
    with TemporaryDirectory(prefix='finbot-legacy176-') as directory:
        db=sqlite3.connect(str(Path(directory)/'replay.sqlite'))
        db.execute('CREATE TABLE cases (prefix TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        for pid,c in cases.items():
            lite={k:c[k] for k in ('prefix_id','episode_id','cut_seq','source','source_sha256','run')}
            db.execute('INSERT INTO cases VALUES (?,?)',(pid,json.dumps(lite)))
        db.commit()
        with preparation_fence(),writer(out) as emit:
            for rep in range(30):
                ids=list(cases);rng.shuffle(ids)
                for pid in ids:
                    t=perf_counter_ns();case=json.loads(db.execute('SELECT payload FROM cases WHERE prefix=?',(pid,)).fetchone()[0]);state_ms=(perf_counter_ns()-t)/1e6
                    t=perf_counter_ns();bundle=prepare_one(case,only='__bundle__',verify_legacy=False);common_ms=(perf_counter_ns()-t)/1e6
                    configs=list(CONFIGS);rng.shuffle(configs)
                    for config in configs:
                        family=config['family'];name=config['name'];evidence_ms=common_ms if family not in (None,'v1','v2') else 0
                        t=perf_counter_ns()
                        adapted=(prepare_one(case,only=family,verify_legacy=False) if family in ('v1','v2') else adapt(bundle,family)) if family else {'payload':{},'applicable':True}
                        adapter_ms=(perf_counter_ns()-t)/1e6
                        t=perf_counter_ns();result=decision(fns[name],adapted['payload']);decision_ms=(perf_counter_ns()-t)/1e6
                        diagnostic_start=perf_counter_ns()
                        if family:assert digest(adapted['payload'])==expected[pid]['payload_sha256'][family],(pid,name)
                        assert canonical_result(result)==canonical_result(frozen[pid,name]),(pid,name)
                        checks+=1
                        diagnostics_ms=(perf_counter_ns()-diagnostic_start)/1e6
                        fetch_ms=state_ms if family else 0
                        emit(dict(prefix_id=pid,method=name,rep=rep,state_ms=fetch_ms,evidence_ms=evidence_ms,
                            adapter_ms=adapter_ms,decision_ms=decision_ms,diagnostics_ms=diagnostics_ms,
                            working_ms=fetch_ms+evidence_ms+adapter_ms+decision_ms))
                        count+=1
                if rep%5==4:print(json.dumps({'repetitions':rep+1}),flush=True)
        db.close()
    write_json(HERE/'benchmark-receipt.json',dict(records=count,single_bulk_equalities=checks,repetitions=30,
        scope='isolated SQLite archived-prefix read + evidence builder + selected adapter + guard; excludes output/hash diagnostics; replay implementation, not measured production integration',
        source_sha256=sha(Path(__file__)),output_sha256=sha(out),input_manifest_sha256=sha(HERE/'input-manifest.json'),new_model_calls=0))

if __name__=='__main__':benchmark()
