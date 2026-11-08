"""Evaluate sealed deterministic decisions against unchanged old labels."""
from collections import Counter,defaultdict
import json
from pathlib import Path
import numpy as np

from .prepare import HERE
from .timing import clock,stats
from experiments.local_guards_adapter_repair.inventory import rows,sha,write_json
from experiments.local_guards_adapter_repair.prepare import writer


def metrics(labels,decisions):
    assert set(labels)==set(decisions)
    c=Counter(n=len(labels),positive=sum(r['label']==1 for r in labels.values()),safe=sum(r['label']==0 for r in labels.values()))
    for pid,r in labels.items():
        d=decisions[pid];gold='BLOCK' if r['label'] else 'ALLOW'
        c['allow']+=d=='ALLOW';c['block']+=d=='BLOCK';c['unknown']+=d=='UNKNOWN';c['unavailable']+=d not in ('ALLOW','BLOCK','UNKNOWN')
        c['tp']+=r['label']==1 and d=='BLOCK';c['wrong_allow']+=r['label']==1 and d=='ALLOW'
        c['false_block']+=r['label']==0 and d=='BLOCK';c['safe_stop']+=r['label']==0 and d!='ALLOW'
        c['correct']+=d==gold
    assert sum(c[k] for k in ('allow','block','unknown','unavailable'))==len(labels)
    return dict(c)


def intervals(labels,decisions,reference):
    groups=sorted({r['group_id'] for r in labels.values()});idx={g:i for i,g in enumerate(groups)}
    vectors=np.zeros((len(groups),7))
    for pid,r in labels.items():
        d=decisions[pid];ref=reference[pid];gold='BLOCK' if r['label'] else 'ALLOW'
        vectors[idx[r['group_id']]]+=np.array([1,r['label']==0,r['label']==1,d==gold,
            r['label']==0 and d=='BLOCK',r['label']==0 and d!='ALLOW',int(d==gold)-int(ref==gold)])
    rng=np.random.default_rng(17);draws=rng.multinomial(len(groups),np.full(len(groups),1/len(groups)),size=2000)@vectors
    ratio=lambda a,b:np.divide(draws[:,a],draws[:,b],out=np.full(len(draws),np.nan),where=draws[:,b]>0)
    ci=lambda values:np.nanquantile(values,[.025,.975]).tolist()
    return dict(groups=len(groups),draws=2000,seed=17,correct_ci95=ci(ratio(3,0)),fpr_block_ci95=ci(ratio(4,1)),
        safe_stop_ci95=ci(ratio(5,1)),paired_correct_difference_vs_v2_ci95=ci(ratio(6,0)))


def run():
    freeze=json.loads((HERE/'prediction-freeze.json').read_text())
    assert sha(HERE/'predictions.jsonl.gz')==freeze['predictions_sha256']
    assert sha(HERE/'input-manifest.json')==freeze['input_manifest_sha256']
    labels={r['prefix_id']:r for r in rows(HERE/'labels/scoring.jsonl.gz')}
    vectors=defaultdict(dict);details={};errors=[]
    for r in rows(HERE/'predictions.jsonl.gz'):
        key=(r['method'],r['mode']);pid=r['prefix_id'];assert pid not in vectors[key]
        d=r['result'].get('decision') or r['result'].get('availability','ADAPTER_UNAVAILABLE')
        vectors[key][pid]=d;details[key,pid]=r
        if r['result'].get('execution_error'):errors.append(r)
    controls=list(rows(HERE/'saved-controls.jsonl.gz'))
    for r in controls:
        key=r['method'],'saved';pid=r['prefix_id'];assert pid not in vectors[key]
        vectors[key][pid]=r['decision'];details[key,pid]=r
    reference=vectors['v2','full'];summary={};regressions=[]
    for (name,mode),values in vectors.items():
        m=metrics(labels,values);m['intervals']=intervals(labels,values,reference)
        m['paired_v1_ci95']=intervals(labels,values,vectors['v1','full'])['paired_correct_difference_vs_v2_ci95']
        m['relative_v2']=dict(Counter(reference[pid]+' -> '+values[pid] for pid in labels))
        m['relative_v1']=dict(Counter(vectors['v1','full'][pid]+' -> '+values[pid] for pid in labels))
        summary.setdefault(name,{})[mode]=m
        if mode=='full':
            for pid in labels:
                gold='BLOCK' if labels[pid]['label'] else 'ALLOW'
                if reference[pid]==gold and values[pid]!=gold:
                    r=details[(name,mode),pid]
                    regressions.append(dict(method=name,prefix_id=pid,episode_id=labels[pid]['episode_id'],gold=gold,
                        v2=reference[pid],decision=values[pid],reasons=r['result'].get('reasons',[]),evidence=r['result'].get('evidence',[])))
    assert summary['v1']['full']['tp']==78 and summary['v1']['full']['false_block']==0
    assert summary['v2']['full']['tp']==83 and summary['v2']['full']['false_block']==0
    write_json(HERE/'quality.json',dict(labels=Counter(r['label'] for r in labels.values()),methods=summary,execution_errors=errors,
        source_labels_sha256=sha(HERE/'labels/scoring.jsonl.gz'),prediction_freeze_sha256=sha(HERE/'prediction-freeze.json')))
    with writer(HERE/'regressions.jsonl.gz') as emit:
        for r in regressions:emit(r)
    timings={r['prefix_id']:r for r in rows(HERE/'timing-sources.jsonl.gz')};clocks={p:clock(r) for p,r in timings.items()}
    bench=defaultdict(list)
    for r in rows(HERE/'benchmark.jsonl.gz'):bench[r['method'],r['prefix_id']].append(r)
    local_cost={};components={}
    for key,rs in bench.items():
        assert len(rs)==30
        local_cost[key]=sum(r['working_ms'] for r in rs)/30
        components[str(key)]={k:dict(mean_ms=float(np.mean([r[k] for r in rs])),median_ms=float(np.median([r[k] for r in rs])),p95_ms=float(np.quantile([r[k] for r in rs],.95))) for k in ('state_ms','evidence_ms','adapter_ms','decision_ms','diagnostics_ms','working_ms')}
    control_rows={(r['method'],r['prefix_id']):r for r in controls}
    timing_methods={}
    for (name,mode),values in vectors.items():
        if mode not in ('full','saved'):continue
        data=[]
        for pid,d in values.items():
            if mode=='full':cost=local_cost.get((name,pid));overhead='measured replay acquisition+adapter+guard'
            else:cost=control_rows[name,pid].get('source_ms');overhead=control_rows[name,pid]['head_timing']
            if cost is None:continue
            c=clocks[pid];stop=d!='ALLOW'
            terminal=c['stop_s'] if stop else c['complete_s'];lower=c['stop_lower_s'] if stop else c['complete_lower_s']
            completed=not stop and timings[pid]['orchestrator_status']=='success' and not timings[pid]['error']
            data.append(dict(prefix_id=pid,decision=d,stopped=stop,archived_completed=completed,
                time_s=terminal+cost/1000,lower_s=lower+cost/1000,added_s=cost/1000,
                same_episode_baseline_s=c['complete_s'],clock_rounding_bound_s=c['rounding_bound_s'],timing_scope=overhead))
        completions=[r for r in data if r['archived_completed']];stops=[r for r in data if r['stopped']]
        timing_methods[name]=dict(n=len(data),missing=176-len(data),terminal=stats([r['time_s'] for r in data]),
            completed=stats([r['time_s'] for r in completions]),stopped=stats([r['time_s'] for r in stops]),
            paired_completed_baseline=stats([r['same_episode_baseline_s'] for r in completions]),
            paired_completed_overhead=stats([r['time_s']-r['same_episode_baseline_s'] for r in completions]),
            terminal_lower=stats([r['lower_s'] for r in data]),rows=data,
            completeness='local replay measured' if mode=='full' else 'model-source only; missing client/render and possible trained head; lower estimate')
    baseline=dict(observed=stats([r['wall_s'] for r in timings.values()]),clean=stats([c['complete_s'] for c in clocks.values()]),
        clean_lower=stats([c['complete_lower_s'] for c in clocks.values()]),
        sum_pauses_s=sum(c['pause_ms'] for c in clocks.values())/1000,checks=sum(c['checks'] for c in clocks.values()))
    assert baseline['checks']==2343 and abs(baseline['sum_pauses_s']-2910.5895)<1e-7
    assert abs(sum(c['complete_s'] for c in clocks.values())-5546.6005)<1e-7
    write_json(HERE/'full-time.json',dict(baseline=baseline,methods=timing_methods,clocks=clocks,
        components=components,benchmark_sha256=sha(HERE/'benchmark.jsonl.gz'),timing_source_sha256=sha(HERE/'timing-sources.jsonl.gz'),
        scope='per-episode archived execution without old shadow waits plus new checker cost; STOP truncates prefix; no adaptive model rerun'))
    print(json.dumps({name:{mode:{k:r[k] for k in ('tp','false_block','safe_stop','wrong_allow','unknown','correct')} for mode,r in modes.items()} for name,modes in summary.items()}))

if __name__=='__main__':run()
