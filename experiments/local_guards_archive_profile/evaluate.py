"""Score sealed archive-profile answers and reuse saved model/cost controls."""
from collections import Counter,defaultdict
import json
from statistics import mean
from .prepare import HERE,EXP
from experiments.local_guards_adapter_repair.inventory import rows,sha,write_json
from experiments.local_guards_repaired_evaluation.evaluate import source_labels,summarize,Intervals
from experiments.local_guards_repaired_evaluation.cascade_accounting import one
from experiments.local_guards_final_replay.early_score import first_stop
from experiments.local_guards_legacy176.evaluate import metrics,intervals
from experiments.local_guards_legacy176.timing import stats,clock


def run():
    freeze=json.loads((HERE/'prediction-freeze.json').read_text())
    assert freeze['predictions_sha256']==sha(HERE/'predictions.jsonl.gz')
    assert freeze['input_manifest_sha256']==sha(HERE/'input-manifest.json')
    expected={(r['dataset'],r['mode'],r['method'],r['prefix_id']):r for r in rows(HERE/'inputs.jsonl.gz')}
    vectors=defaultdict(dict);details={};early=defaultdict(list)
    for r in rows(HERE/'predictions.jsonl.gz'):
        key=r['dataset'],r['mode'],r['method'];pid=r['prefix_id'];assert pid not in vectors[key]
        e=expected[*key,pid];assert e['input_sha256']==r['input_sha256']
        assert (r['checkpoint'],r['event_seq'])==(e['payload']['checkpoint'],e['payload']['event_seq'])
        vectors[key][pid]=r['result']['decision'];details[*key,pid]=r
        if key[0]=='early':early[key[1]].append(dict(r,decision=r['result']['decision']))
    assert len(expected)==sum(map(len,vectors.values()))==39872
    labels=source_labels();saved={r['prefix_id']:r for r in rows(EXP/'local_guards_repaired_evaluation/results/saved-deepseek.jsonl.gz')}
    original={r['prefix_id']:r for r in rows(EXP/'local_guards_adapter_repair/inputs/p4-inputs.jsonl.gz') if r['mode']=='common'}
    assert set(labels)==set(saved)==set(original)
    assert all(original[k]['query_id']==saved[k]['query_id'] for k in labels)
    old=json.loads((EXP/'local_guards_repaired_evaluation/results/p4-summary.json').read_text())
    ci=Intervals(labels,{k:r['decision'] for k,r in saved.items()});p4={};transitions={}
    prior=defaultdict(dict)
    for r in rows(EXP/'local_guards_repaired_evaluation/results/p4-decisions.jsonl.gz'):
        if r['config'] in ('v3|rule|A','v4.3|rule|A'):prior[r['config'],r['mode']][r['prefix_id']]=r['decision']
    for (dataset,mode,method),decisions in vectors.items():
        if dataset!='p4':continue
        result=summarize([labels[k]['label'] for k in labels],[decisions[k] for k in labels]);result['intervals']=ci.evaluate(decisions)
        p4.setdefault(method,{})[mode]=result
        family='v3' if method=='v3_archive' else 'v4.3'
        transitions[method+'/'+mode]=dict(Counter(prior[family+'|rule|A',mode][k]+' -> '+decisions[k] for k in labels))
    legacy_labels={r['prefix_id']:r for r in rows(EXP/'local_guards_legacy176/labels/scoring.jsonl.gz')}
    oldlegacy={r['prefix_id']:r['result']['decision'] for r in rows(EXP/'local_guards_legacy176/predictions.jsonl.gz') if r['mode']=='full' and r['method']=='v2'}
    legacy={}
    for method in ('v3_archive','v4.3_archive'):
        values=vectors['legacy176','full',method]
        legacy[method]=dict(metrics(legacy_labels,values),intervals=intervals(legacy_labels,values,oldlegacy),
            transitions_vs_v2=dict(Counter(oldlegacy[k]+' -> '+values[k] for k in legacy_labels)))
    # Ready-source packet acquisition+projection+guard; initial producer timing remains separate.
    bench=defaultdict(list)
    for r in rows(HERE/'benchmark.jsonl.gz'):bench[r['dataset'],r['method'],r['prefix_id']].append(r)
    costs={};latency={}
    for key,data in bench.items():
        assert len(data)==30
        costs[key]=mean(r['working_ms'] for r in data)
    for dataset,method in sorted({k[:2] for k in costs}):
        data=[r for k,rs in bench.items() if k[:2]==(dataset,method) for r in rs]
        latency[dataset+'/'+method]={f:dict(n=len(data),mean_ms=mean(r[f] for r in data),p50_ms=stats([r[f] for r in data])['median_s'],p95_ms=stats([r[f] for r in data])['p95_s']) for f in ('guard_ms','state_ms','projection_ms','working_ms','diagnostics_ms')}
    cascades={}
    sample=json.loads((EXP/'local_guards_repaired_evaluation/benchmark/latency.json').read_text())['sampled_prefixes']
    for method in ('v3_archive','v4.3_archive'):
        values=vectors['p4','common',method]
        times={k:costs['p4',method,k] for k in sample}
        cascades[method]={mode:one(labels,values,saved,times,mode) for mode in ('local','block_then_llm','decisive_then_llm')}
    cascade_baseline=one(labels,{k:'UNKNOWN' for k in labels},saved,{k:0 for k in sample},'llm')
    initial_builder=defaultdict(list)
    for r in rows(EXP/'local_guards_legacy176/benchmark.jsonl.gz'):
        if r['method']=='v4.3':initial_builder[r['prefix_id']].append(r['evidence_ms'])
    clocks={r['prefix_id']:clock(r) for r in rows(EXP/'local_guards_legacy176/timing-sources.jsonl.gz')}
    full_time={}
    for method in ('v3_archive','v4.3_archive'):
        data=[]
        for pid,d in vectors['legacy176','full',method].items():
            extra=(costs['legacy176',method,pid]+mean(initial_builder[pid]))/1000
            c=clocks[pid];stop=d!='ALLOW'
            data.append(dict(prefix_id=pid,decision=d,stopped=stop,time_s=(c['stop_s'] if stop else c['complete_s'])+extra,
                lower_s=(c['stop_lower_s'] if stop else c['complete_lower_s'])+extra,added_s=extra,baseline_s=c['complete_s']))
        full_time[method]=dict(terminal=stats([r['time_s'] for r in data]),
            completed=stats([r['time_s'] for r in data if not r['stopped']]),stopped=stats([r['time_s'] for r in data if r['stopped']]),
            paired_completed_overhead=stats([r['added_s'] for r in data if not r['stopped']]),rows=data)
    early_labels=json.loads((EXP/'local_guards_final_replay/results/early/early-consensus.json').read_text())
    selection=json.loads((EXP/'local_guards_final_replay/early-data/id-map.private.json').read_text())
    selected={r['prefix_id']:r for r in selection};episodes={r['episode_id']:r for r in rows(EXP/'local_guards_final_replay/early-data/early-events.jsonl.gz')}
    early_result={}
    for mode,data in early.items():
        chosen={r['prefix_id']:r for r in data if r['prefix_id'] in selected};assert len(chosen)==128
        summary=summarize([{'action_label':early_labels[selected[k]['case_id']]['label']} for k in chosen],[r['decision'] for r in chosen.values()])
        by_episode=defaultdict(list)
        for r in data:by_episode[r['episode_id']].append(r)
        stops=[];counts=Counter()
        for eid in episodes:
            reached,stop=first_stop(by_episode[eid],stop_unknown=True);counts['reached_points']+=len(reached)
            counts['no_points']+=not reached
            if stop:counts['stopped_episodes']+=1;stops.append({k:stop[k] for k in ('episode_id','prefix_id','checkpoint','event_seq','decision')})
            else:counts['no_stop']+=1
        early_result[mode]=dict(sample=summary,points=Counter(r['decision'] for r in data),sequential=counts,first_stops=stops)
    write_json(HERE/'summary.json',dict(legacy176=legacy,p4=p4,p4_transitions=transitions,early=early_result,
        latency=latency,cascades=cascades,cascade_baseline=cascade_baseline,full_time=full_time,
        prediction_freeze_sha256=sha(HERE/'prediction-freeze.json'),label_sources={
            'legacy176':sha(EXP/'local_guards_legacy176/labels/scoring.jsonl.gz'),
            'p4':sha(EXP/'local_guards_archive_annotation/consensus-freeze.json'),
            'early':sha(EXP/'local_guards_final_replay/results/early/early-consensus.json')},new_model_calls=0))
    print(json.dumps(dict(legacy176=legacy,p4=p4,early={m:r['sample'] for m,r in early_result.items()}),ensure_ascii=False))

if __name__=='__main__':run()
