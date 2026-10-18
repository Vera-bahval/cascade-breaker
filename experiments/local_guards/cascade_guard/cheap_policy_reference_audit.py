"""Cached 4B selection audit and separately named legacy B selector diagnostic."""
import json
import time
from pathlib import Path
from collections import defaultdict
from . import cheap_eval as e
from . import cheap_reference as ref
from . import cheap_policy_reference as p


def run(base,root):
    output=root/'selection-diagnostic';output.mkdir(parents=True,exist_ok=True)
    if (output/'metrics.json').exists():raise ValueError('Do not overwrite selection diagnostic')
    rows,outcomes,records,schemas,alloc=p.inputs(base)
    source=root/'predictions.jsonl'
    files=[Path(__file__),source,root/'cached-fits.jsonl',root/'fit-input-freeze.json',
           base/'results/cheap-guards/matched-reference/predictions.jsonl']
    freeze={'post_hoc':True,'phase':'FROZEN_BEFORE_BLEGACY_METRICS','created_at':time.time(),
        'source_files':[{'path':str(path),'sha256':e.digest(path)} for path in files],'record_files':[],
        'definition':'Blegacy: select standalone format with inner standalone criterion; OR selected component with rules after selection. B2 separately chooses format using final wrapped inner metrics.',
        'new_inference_calls':0,'new_fit_calls':0,'old_A_selected_reproduction':'legacy nextafter thresholds and unchanged selection_rank/source costs'}
    e.dump(output/'input-freeze.json',freeze)
    flags,rule_times=e.rule_flags(rows,base/'data/archive/shadow-main.jsonl.gz')
    row_lookup={r['prefix_id']:r for r in rows};out_lookup={o['episode_id']:o for o in outcomes}
    alloc_lookup={(a['seed'],a['outer_fold']):a for a in alloc}
    choices=defaultdict(list)
    for f in e.read_jsonl(root/'cached-fits.jsonl'):
        seed,fold,head,fmt=(f[k] for k in ('seed','outer_fold','head','format'))
        a=alloc_lookup[seed,fold];trainout=[out_lookup[i] for i in a['train_episode_ids']]
        ir=[row_lookup[x['prefix_id']] for x in f['inner']];ip=[x['score'] for x in f['inner']]
        test=[row_lookup[x['prefix_id']] for x in f['outer']];op=[x['score'] for x in f['outer']]
        cfg=ref.config(head,fmt)
        for wrapper in ref.WRAPPERS:
            threshold,cal,_=e.select_threshold(ir,ip,trainout,flags[wrapper])
            rank=e.selection_rank(cfg,cal,e.reconstructed_latency(ir,cfg[1],records))
            pp=e.prediction_records(test,op,threshold,flags[wrapper],seed,fold,
                f'{head}:train_selected_format:{wrapper}',head!='scalar',False)
            choices[seed,fold,head,wrapper].append((rank,fmt,pp))
    original={(r['seed'],r['outer_fold'],r['arm'],r['prefix_id']):r
        for r in e.read_jsonl(base/'results/cheap-guards/matched-reference/predictions.jsonl')
        if 'train_selected_format' in r['arm']}
    checked=0;different=[]
    for cc in choices.values():
        _,fmt,pp=min(cc,key=lambda t:t[0])
        for r in pp:
            old=original[r['seed'],r['outer_fold'],r['arm'],r['prefix_id']]
            if any(r[k]!=old[k] for k in ('probability','scalar_risk','threshold','block','unknown','rule_stop')) or fmt!=old['selected_format']:
                different.append({k:r[k] for k in ('seed','outer_fold','arm','prefix_id')})
            checked+=1
    audit={'checked_selected_predictions':checked,'expected_selected_predictions':3168,
           'difference_count':len(different),'differences':different}
    e.dump(output/'legacy-selected-reproduction.json',audit)
    if different:raise ValueError('Legacy selected format replay differs')
    predictions=[]
    for r in e.read_jsonl(source):
        if r['policy']!='B_independent' or not r['arm'].endswith('train_selected_format:none'):continue
        head=r['arm'].split(':')[0]
        for wrapper in e.WRAPPERS:
            record=dict(r,arm=f'{head}:train_selected_format_standalone_then_wrap:{wrapper}',
                        selection_variant='Blegacy_standalone_format_selection_then_wrap',
                        rule_stop=flags[wrapper].get(r['prefix_id'],False))
            record['block']=bool(r['block'] or record['rule_stop'])
            e.attach_guard_timing([record],[row_lookup[r['prefix_id']]],('B4_'+r['selected_format'],),
                records,{r['prefix_id']:r['decision_model_ms']},rule_times[wrapper])
            predictions.append(record)
    groups=defaultdict(list)
    for r in predictions:groups[r['seed'],r['arm']].append(r)
    aggregates=[]
    for (seed,arm),rr in groups.items():
        m=e.counts(outcomes,e.decisions_from_records(rr))
        m.update(seed=seed,policy='B_independent',arm=arm,post_hoc=True,
                 selection_variant='Blegacy_standalone_format_selection_then_wrap',prefixes=len(rr),complete=len(rr)==176)
        if rr[0]['learned_component']:m.update(e.probability_metrics(rows,rr))
        aggregates.append(m)
    e.verify_frozen(freeze)
    e.jsonl(output/'predictions.jsonl',predictions);e.dump(output/'metrics.json',{'aggregates':aggregates})
    e.dump(output/'manifest.json',dict(freeze,status='COMPLETE',output_files=[{'path':str(output/name),'sha256':e.digest(output/name)}
        for name in ('input-freeze.json','predictions.jsonl','metrics.json','legacy-selected-reproduction.json')]))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',type=Path,default=Path('experiments/local_guards'))
    args=parser.parse_args();base=args.base.resolve();run(base,base/'results/policy-comparison/matched-reference')
