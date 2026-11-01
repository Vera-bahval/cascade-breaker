"""Prespecified point-kind restriction: factual pre-tool P4, no proposal bounds."""
from collections import Counter,defaultdict
import json
from pathlib import Path
from .evaluation import read_rows,action_metrics,episode_records,outcome_metrics,_quantile,digest

HERE=Path(__file__).resolve().parent


def run():
    cases={r['case_id'] for r in read_rows(HERE/'views/historical.jsonl.gz') if r['split']=='REPRESENTATIVE'
           and r['input']['checkpoint']=='P4' and r['input']['raw_context'].get('proposed_action',{}).get('source_event_kind')=='before_tool_hook'}
    metadata={r['prefix_id']:r for r in read_rows(HERE/'data/evaluation-metadata.jsonl.gz')}
    gold={r['prefix_id']:r for r in read_rows(HERE/'labels/actions-unreviewed.jsonl.gz')}
    outcomes=list(read_rows(HERE/'labels/canonical-outcomes.jsonl.gz'));by=defaultdict(list)
    for path in (HERE/'results/historical-local.jsonl.gz',HERE/'results/deepseek-historical.jsonl.gz'):
        for r in read_rows(path):
            if r['case_id'] in cases:by[r['method']+'|'+r['placement']].append({**r,**metadata[r['prefix_id']],**gold[r['prefix_id']]})
    reference={r['case_id']:r['decision'] for r in by['deepseek|both']};methods={}
    for name,rows in sorted(by.items()):
        if len(rows)!=len(cases):raise ValueError('actual-hook prediction population mismatch')
        methods[name]={'source':action_metrics(rows),'formal':action_metrics(rows,'native_core'),
            'outcomes':outcome_metrics(episode_records(rows,placement='p4'),outcomes,outcomes),
            'agreement_with_deepseek':sum(r['decision']==reference[r['case_id']] for r in rows),
            'recorded_decision_ms':{'p50':_quantile([r['decision_ms'] for r in rows],.5),'p95':_quantile([r['decision_ms'] for r in rows],.95)}}
    result={'selection':'REPRESENTATIVE P4 and source_event_kind==before_tool_hook only; no outcome/prediction-based selection',
        'cases':len(cases),'case_ids':sorted(cases),'methods':methods,
        'sources':{str(HERE/p):digest(HERE/p) for p in ['views/historical.jsonl.gz','data/evaluation-metadata.jsonl.gz',
             'labels/actions-unreviewed.jsonl.gz','results/historical-local.jsonl.gz','results/deepseek-historical.jsonl.gz']}}
    output=HERE/'results/representative-actual-hook-metrics.json';output.write_text(json.dumps(result,indent=2)+'\n')
    # Preserve all58 exploratory annotations; report their actual-hook subset separately.
    consensus=list(read_rows(HERE/'adjudication/consensus.jsonl.gz'));sample=[];excluded=[]
    for r in consensus:
        p=HERE/'adjudication/inputs'/(r['annotation_id']+'.json');kind=json.loads(p.read_text())['input']['raw_context']['proposed_action']['source_event_kind']
        (sample if kind=='before_tool_hook' else excluded).append(r)
    subset={'cases':len(sample),'excluded_proposal_bounds':[r['annotation_id'] for r in excluded],
        'reference_counts':dict(Counter(r['decision'] for r in sample)),
        'material_unknown':sum(r['status']=='AGREED' and r['decision']=='UNKNOWN' for r in sample),
        'disagreement':sum(r['status']=='DISAGREEMENT' for r in sample),
        'raw_agreement':sum(r['status']=='AGREED' for r in sample),'methods':{}}
    refs={r['case_id']:r for r in sample}
    all_ratings=json.loads((HERE/'adjudication/summary.json').read_text())
    for name in all_ratings['metrics']:
        counts=Counter()
        for r in by[name]:
            if r['case_id'] not in refs:continue
            ref=refs[r['case_id']];p=r['decision'];counts['cases']+=1;counts['method_unknown']+=p=='UNKNOWN'
            if ref['status']=='DISAGREEMENT':counts['reference_disagreement']+=1
            elif ref['decision']=='UNKNOWN':counts['allow_with_unresolved_evidence']+=p=='ALLOW'
            else:
                counts['correct_defined']+=p==ref['decision'] and p!='UNKNOWN'
                counts['allow_against_known_block']+=p=='ALLOW' and ref['decision']=='BLOCK'
                counts['block_against_known_allow']+=p=='BLOCK' and ref['decision']=='ALLOW'
        subset['methods'][name]=dict(counts)
    (HERE/'adjudication/actual-hook-summary.json').write_text(json.dumps(subset,indent=2)+'\n')
    return result,subset


if __name__=='__main__':
    result,subset=run();print(json.dumps({'cases':result['cases'],'actual_annotations':subset['cases'],
        'native_agreement':result['methods']['native|both']['agreement_with_deepseek'],
        'deepseek_latency':result['methods']['deepseek|both']['recorded_decision_ms']},indent=2))
