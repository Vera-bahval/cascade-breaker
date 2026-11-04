"""Prepare only from sealed pre-action packets, no labels or outcomes."""
from collections import Counter
from pathlib import Path
import json
from .profile import prepare,METHODS
from experiments.local_guards_adapter_repair.evidence import pair_events
from experiments.local_guards_final_replay import early
from experiments.local_guards_archive_comparison.methods import _result
from experiments.local_guards_adapter_repair.inventory import ROOT,rows,sha,write_json
from experiments.local_guards_adapter_repair.prepare import preparation_fence,writer
from experiments.local_guards_archive_comparison.collector import digest
HERE=Path(__file__).resolve().parent
EXP=HERE.parent


def review_events():
    inventory_path=EXP/'local_guards_adapter_repair/inventory.json'
    episodes=json.loads(inventory_path.read_text())['early_episodes']
    registry=EXP/'local_guards_archive_comparison/data/collector-manifest.json'
    result={};sources={str(p.relative_to(ROOT)):sha(p) for p in (inventory_path,registry)}
    for ep,journal,initial,member in early.raw_episodes(list(episodes.values()),ROOT.parent/'finbot-four-model-report'):
        events=early.legacy_events(journal) if initial is not None else early.native_events(journal)
        selected=[]
        for frame,event in pair_events(events)[0]:
            if not frame or frame['tool']!='delegate_to_fraud':continue
            value=_result(event.get('tool_result'))
            if not isinstance(value,dict):continue
            # Retain only actual scoped callback signatures/status, no summaries/outcomes.
            before={k:v for k,v in frame['event'].items() if k in ('event_seq','hook_kind','tool_name','tool_arguments','source_event_kind','call_id','tool_call_id','namespace','session_id','workflow_id','parent_workflow_id')}
            before['hook_kind']='before_tool'
            after={k:v for k,v in event.items() if k in ('event_seq','hook_kind','tool_name','tool_arguments','source_event_kind','call_id','tool_call_id','namespace','session_id','workflow_id','parent_workflow_id')}
            after['tool_result']={k:value[k] for k in ('task_status','status','success','error','is_error') if k in value}
            selected.append((before,after))
        result[ep['episode_id']]=selected
    return result,sources


def run():
    counts=Counter();sources={};out=HERE/'inputs.jsonl.gz'
    if out.exists():raise FileExistsError(out)
    paths=[('legacy176',EXP/'local_guards_legacy176/prepared-inputs.jsonl.gz'),('p4',EXP/'local_guards_adapter_repair/inputs/p4-inputs.jsonl.gz')]
    paths.extend(('early',p) for p in sorted((EXP/'local_guards_adapter_repair/inputs').glob('early-inputs-*.jsonl.gz')))
    with preparation_fence(),writer(out) as emit:
        reviews,raw_sources=review_events();sources.update(raw_sources)
        for dataset,path in paths:
            sources[str(path.relative_to(ROOT))]=sha(path)
            for row in rows(path):
                if dataset=='legacy176' and row['mode']!='full' or dataset=='p4' and row['mode'] not in ('common','expanded'):continue
                if dataset=='early':
                    cut=row['bundle']['event_seq']
                    row['fraud_events']=sorted([e for before,after in reviews[row['episode_id']] if after['event_seq']<cut for e in (before,after)],key=lambda e:e['event_seq'])
                for method in METHODS if dataset!='early' else ('v4.3_archive',):
                    payload=prepare(row,method)
                    record={k:row[k] for k in ('prefix_id','episode_id','case_id','mode','action_boundary') if k in row}
                    record.update(dataset=dataset,method=method,payload=payload,input_sha256=digest(payload),source_sha256=sources[str(path.relative_to(ROOT))])
                    emit(record);counts[dataset+'/'+row['mode']+'/'+method]+=1
    write_json(HERE/'input-manifest.json',dict(base='f4008520be82006fc5b56aa88506565594ca2ca9',code={n:sha(HERE/n) for n in ('profile.py','prepare.py','CONTRACT.md','test_profile.py')},sources=sources,counts=counts,inputs_sha256=sha(out),label_reads=0,model_calls=0))
    print(dict(counts))

if __name__=='__main__':run()
