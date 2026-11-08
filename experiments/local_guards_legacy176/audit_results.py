"""Reconcile saved artifacts and original labels, without rerunning inference."""
from collections import Counter,defaultdict
import gzip
import json
import subprocess

from .prepare import HERE,ROOT,OLD,PUBLISHED
from .audit_inputs import audit as audit_inputs
from .evaluate import metrics
from .timing import clock,stats
from experiments.local_guards_adapter_repair.inventory import rows,sha,write_json


def audit():
    input_audit=audit_inputs()
    source=json.loads((HERE/'source-manifest.json').read_text())
    for path,h in source['sources'].items():assert sha(path)==h,path
    labels=list(rows(HERE/'labels/scoring.jsonl.gz'))
    published=subprocess.check_output(['git','show',source['published_revision']+':experiments/local_guards/results/guard-v2/archive-p4-labels.jsonl'],cwd=ROOT)
    assert labels==[json.loads(x) for x in published.splitlines()]
    labelmap={r['prefix_id']:r for r in labels}
    assert len(labelmap)==176 and Counter(r['label'] for r in labels)=={0:93,1:83}
    cases={(r['mode'],r['prefix_id']):r for r in rows(HERE/'prepared-inputs.jsonl.gz')}
    freeze=json.loads((HERE/'prediction-freeze.json').read_text())
    assert freeze['predictions_sha256']==sha(HERE/'predictions.jsonl.gz')
    assert freeze['runner_sha256']==sha(HERE/'run.py')
    assert freeze['approval_sha256']==sha(HERE/'approval.json')
    families={c['name']:c['family'] for c in freeze['configs']};vectors=defaultdict(dict)
    for r in rows(HERE/'predictions.jsonl.gz'):
        c=cases[r['mode'],r['prefix_id']];lab=labelmap[r['prefix_id']]
        assert r['episode_id']==c['episode_id']==lab['episode_id']
        assert r['cut_seq']==c['cut_seq']==lab['cut_seq']
        assert r['input_sha256']==c['payload_sha256'].get(families[r['method']])
        assert r['prefix_id'] not in vectors[r['method'],r['mode']]
        assert not r['result'].get('execution_error')
        vectors[r['method'],r['mode']][r['prefix_id']]=r['result'].get('decision') or r['result']['availability']
    assert len(vectors)==22 and sum(map(len,vectors.values()))==3872
    saved=json.loads((HERE/'saved-controls-manifest.json').read_text())
    assert saved['output_sha256']==sha(HERE/'saved-controls.jsonl.gz')
    assert saved['code_sha256']==sha(HERE/'saved_controls.py')
    for path,h in saved['files'].items():assert sha(path)==h
    for r in rows(HERE/'saved-controls.jsonl.gz'):
        assert r['prefix_id'] in labelmap and r['prefix_id'] not in vectors[r['method'],'saved']
        vectors[r['method'],'saved'][r['prefix_id']]=r['decision']
    quality=json.loads((HERE/'quality.json').read_text())
    for (method,mode),values in vectors.items():
        actual=metrics(labelmap,values)
        for key,v in actual.items():assert quality['methods'][method][mode][key]==v,(method,key)
    bench=json.loads((HERE/'benchmark-receipt.json').read_text())
    assert bench['output_sha256']==sha(HERE/'benchmark.jsonl.gz')
    assert bench['source_sha256']==sha(HERE/'benchmark.py')
    repeats=Counter((r['method'],r['prefix_id']) for r in rows(HERE/'benchmark.jsonl.gz'))
    assert len(repeats)==1936 and set(repeats.values())=={30}
    times=json.loads((HERE/'full-time.json').read_text())
    records={r['prefix_id']:r for r in rows(HERE/'timing-sources.jsonl.gz')}
    raw={r['run_id']:r for r in rows(OLD/'data/archive/shadow-main.jsonl.gz')}
    time_fields=('seq','kind','point','family','context_seq','t_ms','pause_ms','t_start_ms','duration_ms','source','name','verifier','latency_ms','cost_usd','tokens_in','tokens_out')
    for pid,r in records.items():
        original=raw[r['episode_id']]
        assert r['wall_s']==original['wall_s'] and r['source_git_sha']==original['git_sha']
        assert r['steps']==[{k:s[k] for k in time_fields if k in s} for s in original['steps']]
    runtime=subprocess.check_output(['git','show','08b7b900cf48c3344dfbc039223a4b1e258e193f:finbot/finbot/probe/guards/runtime.py'],cwd=ROOT)
    import hashlib
    assert hashlib.sha256(runtime).hexdigest()=='df376da90125afdd461f67bf7dac9ad0a780bdf43d87d4e7a884b5e3124ef22e'
    clocks={pid:clock(r) for pid,r in records.items()}
    assert len(clocks)==176
    assert all(abs(c['pause_sum_ms']-c['pause_ms'])<1e-7 for c in clocks.values())
    assert times['baseline']['observed']==stats([r['wall_s'] for r in records.values()])
    assert times['baseline']['clean']==stats([c['complete_s'] for c in clocks.values()])
    for method,t in times['methods'].items():
        decisions=vectors[method,'full'] if (method,'full') in vectors else vectors[method,'saved']
        assert t['n']==176 and t['completed']['n']+t['stopped']['n']==176
        assert t['completed']['n']==sum(d=='ALLOW' for d in decisions.values())
        assert t['terminal']==stats([r['time_s'] for r in t['rows']])
        for r in t['rows']:
            c=clocks[r['prefix_id']];stop=decisions[r['prefix_id']]!='ALLOW'
            assert r['stopped']==stop
            assert abs(r['time_s']-(c['stop_s'] if stop else c['complete_s'])-r['added_s'])<1e-10
            assert r['lower_s']<=r['time_s']
    outcomes_path=OLD/'data/outcomes.jsonl';prefixes_path=OLD/'data/prefixes.jsonl'
    outcomes={r['episode_id']:r for r in map(json.loads,outcomes_path.read_text().splitlines())}
    prefixes=defaultdict(list)
    for r in map(json.loads,prefixes_path.read_text().splitlines()):prefixes[r['episode_id']].append(r)
    selected={r['episode_id'] for r in labels};exclusions=[]
    for eid,o in outcomes.items():
        if eid in selected:continue
        reached=any(r['control_point']=='P4.finstripe__create_transfer' for r in prefixes[eid])
        reason='ambiguous_original_target' if reached and o['legacy_ambiguous'] else 'did_not_reach_P4' if not reached else 'UNEXPLAINED'
        exclusions.append(dict(episode_id=eid,reason=reason,reached_P4=reached,original_ambiguity=o['legacy_ambiguous']))
    assert Counter(r['reason'] for r in exclusions)=={'did_not_reach_P4':38,'ambiguous_original_target':20}
    write_json(HERE/'exclusion-details.json',dict(counts=Counter(r['reason'] for r in exclusions),rows=exclusions,
        sources={str(p):sha(p) for p in (outcomes_path,prefixes_path)}))
    strict=Counter();legacy=Counter()
    for r in labels:
        o=outcomes[r['episode_id']]
        assert bool(r['label'])==o['strict_harm']
        if r['label']:
            strict.update(o['strict_harm_reasons']);legacy[o['legacy_harm']]+=1
    result=dict(status='PASS',input_audit=input_audit,prediction_rows=3872,benchmark_rows=58080,
        episodes=176,groups=len({r['group_id'] for r in labels}),labels=Counter(r['label'] for r in labels),
        original_target='strict_harm at frozen P4; 39 also legacy_harm, 44 strict-only; not 83 independently semantic attacks',
        positive_strict_reasons=strict,positive_legacy_harm=legacy,exclusions=Counter(r['reason'] for r in exclusions),
        labels_sha256=sha(HERE/'labels/scoring.jsonl.gz'),quality_sha256=sha(HERE/'quality.json'),
        time_sha256=sha(HERE/'full-time.json'),new_model_calls=0)
    write_json(HERE/'result-audit.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='input_audit'},ensure_ascii=False))
    return result


if __name__=='__main__':audit()
