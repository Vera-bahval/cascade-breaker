"""Read-only checks of source identity, sealed answers, counts and time arithmetic."""
from collections import Counter,defaultdict
import json,subprocess
from .prepare import HERE,ROOT,EXP
from experiments.local_guards_adapter_repair.inventory import rows,sha
from experiments.local_guards_archive_comparison.collector import digest


def run():
    m=json.loads((HERE/'input-manifest.json').read_text());f=json.loads((HERE/'prediction-freeze.json').read_text())
    assert m['inputs_sha256']==sha(HERE/'inputs.jsonl.gz')
    assert f['input_manifest_sha256']==sha(HERE/'input-manifest.json')
    assert f['predictions_sha256']==sha(HERE/'predictions.jsonl.gz')
    assert f['code_sha256']==sha(HERE/'execute.py')
    for name,h in m['code'].items():assert sha(HERE/name)==h
    for name,h in m['sources'].items():assert sha(ROOT/name)==h
    key=lambda r:(r['dataset'],r['mode'],r['method'],r['prefix_id'])
    inputs={key(r):r for r in rows(HERE/'inputs.jsonl.gz')};assert len(inputs)==39872
    seen=set();counts=Counter();vectors=defaultdict(dict)
    for r in rows(HERE/'predictions.jsonl.gz'):
        k=key(r);assert k not in seen;seen.add(k);expected=inputs[k]
        assert r['input_sha256']==expected['input_sha256']==digest(expected['payload'])
        assert r['result']['decision'] in ('ALLOW','BLOCK','UNKNOWN')
        vectors[k[:3]][k[3]]=r['result']['decision']
        counts['/'.join(k[:3])]+=1
    assert seen==set(inputs) and counts==m['counts']==f['counts']
    bench=json.loads((HERE/'benchmark-receipt.json').read_text())
    assert sha(HERE/'benchmark.jsonl.gz')==bench['sha256'];assert bench['count']==43080
    reps=Counter()
    for r in rows(HERE/'benchmark.jsonl.gz'):
        reps[r['dataset'],r['method'],r['prefix_id']]+=1
        assert abs(r['working_ms']-r['state_ms']-r['projection_ms']-r['guard_ms'])<1e-8
    assert set(reps.values())=={30} and len(reps)==1436
    s=json.loads((HERE/'summary.json').read_text())
    for method,v in s['legacy176'].items():
        assert v['n']==176 and v['safe']==93 and v['positive']==83
        assert v['correct']==v['tp']+v['allow']-v['wrong_allow']
        t=s['full_time'][method]
        assert t['terminal']['n']==176 and t['completed']['n']+t['stopped']['n']==176
        assert t['completed']['n']==v['allow']
        for r in t['rows']:
            assert r['lower_s']<=r['time_s'] and r['added_s']>=0
            if not r['stopped']:assert abs(r['time_s']-r['baseline_s']-r['added_s'])<1e-10
    for method,modes in s['p4'].items():
        for mode,r in modes.items():
            assert r['n']==542
            assert r['correct']+r['wrong_allow']+r['wrong_block']+r['insufficient_allow']+r['insufficient_block']+r['unknown']==542
        for mode,r in s['cascades'][method].items():
            assert r['safe_n']==7 and r['bad_n']==238 and r['legit_n']==160
            if mode=='local':assert r['llm_calls']==0
    for mode,r in s['early'].items():
        assert sum(r['points'].values())==18676 and r['sample']['n']==128
        assert r['sequential']['no_stop']+r['sequential']['stopped_episodes']==754
    # No frozen rule/model/data changes; old release manifests only update report hash.
    changed=subprocess.check_output(['git','diff','f4008520','--name-only'],cwd=ROOT,text=True).splitlines()
    allowed=('experiments/local_guards_archive_profile/','experiments/NO_LLM_REPORT.md',
             'experiments/local_guards_legacy176/release-manifest.json','experiments/local_guards_repaired_evaluation/release-manifest.json')
    assert all(any(p.startswith(a) for a in allowed) for p in changed),changed
    print('ARCHIVE_PROFILE_AUDIT_PASS',len(seen),'predictions',sum(reps.values()),'timings')

if __name__=='__main__':run()
