"""Offline inference and shuffled timings, never fits or calls models."""
from collections import Counter,defaultdict
from pathlib import Path
import json,random,sqlite3,subprocess,tempfile
from time import perf_counter_ns
from .prepare import HERE,EXP,ROOT
from .profile import prepare,guard
from experiments.local_guards_adapter_repair.inventory import rows,sha,write_json
from experiments.local_guards_adapter_repair.prepare import writer,preparation_fence
from experiments.local_guards_archive_comparison.collector import digest


def admitted():
    approval=json.loads((HERE/'approval.json').read_text());m=json.loads((HERE/'input-manifest.json').read_text())
    assert approval['status']=='APPROVED' and approval['input_manifest_sha256']==sha(HERE/'input-manifest.json')
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==approval['reviewed_commit']
    assert sha(HERE/'inputs.jsonl.gz')==m['inputs_sha256']
    for name,h in m['code'].items():assert sha(HERE/name)==h
    for name,h in m['sources'].items():assert sha(ROOT/name)==h
    return m


def run():
    admitted();out=HERE/'predictions.jsonl.gz';counts=Counter()
    if out.exists():raise FileExistsError(out)
    with preparation_fence(),writer(out) as emit:
        for row in rows(HERE/'inputs.jsonl.gz'):
            assert digest(row['payload'])==row['input_sha256']
            result=guard(row['payload'])
            emit(dict(**{k:v for k,v in row.items() if k!='payload'},result=result))
            counts[row['dataset']+'/'+row['mode']+'/'+row['method']]+=1
    write_json(HERE/'prediction-freeze.json',dict(input_manifest_sha256=sha(HERE/'input-manifest.json'),
        approval_sha256=sha(HERE/'approval.json'),predictions_sha256=sha(out),code_sha256=sha(Path(__file__)),
        counts=counts,label_reads=0,new_model_calls=0))
    print('FROZEN',dict(counts))


def benchmark():
    admitted();out=HERE/'benchmark.jsonl.gz'
    if out.exists():raise FileExistsError(out)
    expected={(r['dataset'],r['prefix_id'],r['method']):r for r in rows(HERE/'inputs.jsonl.gz') if r['mode'] in ('common','full') and r['dataset']!='early'}
    frozen={(r['dataset'],r['prefix_id'],r['method']):r['result'] for r in rows(HERE/'predictions.jsonl.gz') if r['mode'] in ('common','full') and r['dataset']!='early'}
    cases={}
    for dataset,path in [('legacy176',EXP/'local_guards_legacy176/prepared-inputs.jsonl.gz'),('p4',EXP/'local_guards_adapter_repair/inputs/p4-inputs.jsonl.gz')]:
        for r in rows(path):
            if r['mode'] not in ('common','full'):continue
            cases[dataset,r['prefix_id']]={'bundle':r['bundle'],'adapters':{'native':r['adapters']['native']}}
    rng=random.Random(17);count=0
    with tempfile.TemporaryDirectory(prefix='finbot-archive-profile-') as directory:
        db=sqlite3.connect(str(Path(directory)/'state.sqlite'))
        db.execute('CREATE TABLE packets (id TEXT PRIMARY KEY, packet TEXT)')
        for key,case in cases.items():db.execute('INSERT INTO packets VALUES (?,?)',(json.dumps(key),json.dumps(case)))
        db.commit()
        with preparation_fence(),writer(out) as emit:
            for rep in range(30):
                keys=list(cases);rng.shuffle(keys)
                for dataset,pid in keys:
                    t=perf_counter_ns();row=json.loads(db.execute('SELECT packet FROM packets WHERE id=?',(json.dumps((dataset,pid)),)).fetchone()[0]);state_ms=(perf_counter_ns()-t)/1e6
                    methods=['v3_archive','v4.3_archive'];rng.shuffle(methods)
                    for method in methods:
                        t=perf_counter_ns();payload=prepare(row,method);projection_ms=(perf_counter_ns()-t)/1e6
                        t=perf_counter_ns();result=guard(payload);guard_ms=(perf_counter_ns()-t)/1e6
                        t=perf_counter_ns();assert digest(payload)==expected[dataset,pid,method]['input_sha256'];assert result==frozen[dataset,pid,method]
                        diagnostics_ms=(perf_counter_ns()-t)/1e6
                        emit(dict(dataset=dataset,prefix_id=pid,method=method,rep=rep,state_ms=state_ms,projection_ms=projection_ms,
                            guard_ms=guard_ms,diagnostics_ms=diagnostics_ms,working_ms=state_ms+projection_ms+guard_ms))
                        count+=1
                if rep%10==9:print('benchmark',rep+1,flush=True)
        db.close()
    write_json(HERE/'benchmark-receipt.json',dict(count=count,repetitions=30,sha256=sha(out),code_sha256=sha(Path(__file__)),
        source_scope='read reconstructed packet + archive projection + guard; excludes initial common evidence reconstruction and diagnostics',new_model_calls=0))

if __name__=='__main__':
    import sys
    benchmark() if '--benchmark' in sys.argv else run()
