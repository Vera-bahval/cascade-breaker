"""New pre-effect scope from frozen point origin only; keep old extended results."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import json
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from experiments.local_guards_archive_comparison import evaluation as base, cascade_evaluation as cascade


def selfcheck():
    def view(name, checkpoint, kind):
        return dict(case_id=name,prefix_id=name,input=dict(checkpoint=checkpoint,event_seq=1,
            raw_context={'proposed_action': {'source_event_kind': kind}}))
    rows=[view('actual','P4','before_tool_hook'),view('proposal','P4','recorded_model_proposal'),
          view('p2','P2_afterFraud','recorded_model_proposal'),view('outside','P4',None)]
    scope=origin_scope(rows,{'actual','proposal','p2'})
    assert scope['kept_case_ids']==['actual','p2']
    assert scope['removed_case_ids']==['proposal']
    assert scope['p2_case_ids']==['p2']
    assert scope['actual_p4_case_ids']==['actual']
    try:
        origin_scope([view('bad','P4',None)],{'bad'})
    except ValueError:
        pass
    else:
        raise AssertionError('unclassified P4 origin must not become actual')
    with tempfile.TemporaryDirectory() as tmp:
        source=Path(tmp)/'source.gz';output=Path(tmp)/'subset.gz'
        payload=[dict(case_id='actual',method='first'),dict(case_id='proposal',method='first'),
                 dict(case_id='proposal',method='other'),dict(case_id='p2',method='other')]
        base.write_rows(source,payload)
        result=filter_excluding(source,output,{'proposal'})
        assert list(base.read_rows(output))==[payload[0],payload[3]]
        assert result['removed_rows']==2
    print('origin-only P4 refinement and complete P2 retention selfchecks PASS')


def origin_scope(views,representative_cases):
    seen=set();p2=set();actual=set();removed=[]
    for wrapper in views:
        case=wrapper['case_id']
        if case not in representative_cases:
            continue
        if case in seen:
            raise ValueError('duplicate frozen view case')
        seen.add(case)
        point=wrapper['input'];checkpoint=point['checkpoint']
        if checkpoint=='P4':
            kind=(point.get('raw_context') or {}).get('proposed_action',{}).get('source_event_kind')
            if kind=='before_tool_hook':actual.add(case)
            elif kind=='recorded_model_proposal':
                removed.append(dict(case_id=case,prefix_id=wrapper['prefix_id'],event_seq=point['event_seq'],
                    checkpoint=checkpoint,source_event_kind=kind,
                    pointer='/input/raw_context/proposed_action/source_event_kind'))
            else:
                raise ValueError('P4 source event kind unavailable or unsupported')
        elif checkpoint=='P2_afterFraud':p2.add(case)
        else:raise ValueError('unexpected selected checkpoint')
    if seen!=representative_cases:
        raise ValueError('selected representative case missing frozen view')
    removed_ids={row['case_id'] for row in removed}
    return {'kept_case_ids':sorted(seen-removed_ids),'removed_case_ids':sorted(removed_ids),
            'removed_case_receipts':sorted(removed,key=lambda row:row['case_id']),
            'actual_p4_case_ids':sorted(actual),'p2_case_ids':sorted(p2)}


def filter_excluding(source,output,removed_cases):
    counts={'input_rows':0,'kept_rows':0,'removed_rows':0};kept=set();removed=set();prefixes=set()
    def rows():
        for row in base.read_rows(source):
            counts['input_rows']+=1
            if row['case_id'] in removed_cases:
                counts['removed_rows']+=1;removed.add(row['case_id']);continue
            counts['kept_rows']+=1;kept.add(row['case_id']);prefixes.add(row.get('prefix_id',row['case_id']))
            yield row
    base.write_rows(output,rows())
    return {**counts,'case_ids':sorted(kept),'prefix_ids':sorted(prefixes),'removed_case_ids':sorted(removed),
            'sha256':base.digest(output)}


def prepare(experiment):
    E=Path(experiment).resolve();R=E/'results'
    parent_path=R/'cascade-representative-freeze.json';parent=cascade.verify_freeze(parent_path)
    parent_input_path=R/'strata/representative/input-manifest.json'
    parent_input=json.loads(parent_input_path.read_text())
    representative_cases=set(parent_input['outputs']['predictions']['case_ids'])
    view_freeze_path=R/'evaluation-freeze.json';view_freeze=json.loads(view_freeze_path.read_text())
    view=view_freeze['inputs']['common']
    cascade._check(view['path'],view['sha256'],'frozen historical view')
    scope=origin_scope(base.read_rows(view['path']),representative_cases)
    if len(scope['actual_p4_case_ids'])!=542 or len(scope['removed_case_ids'])!=5:
        raise ValueError('approved origin-only542actual/5proposal scope mismatch')
    source_sha=base.digest(Path(__file__))
    preserved_paths=[E/'evaluation.py',E/'cascade_evaluation.py',E/'stratify.py',
        R/'cascade-evaluation-freeze.json',R/'cascade-representative-freeze.json',R/'cascade-challenge-freeze.json',
        R/'cascade-strata-comparison.json',R/'cascade-strata-comparison.md']
    for name in ('cascade-evaluation','cascade-representative','cascade-challenge'):
        preserved_paths.extend(sorted((R/name).glob('*')))
    preserved={str(path):base.digest(path) for path in preserved_paths if path.is_file()}
    directory=R/'strata/representative-actual-hook';directory.mkdir(parents=True,exist_ok=False)
    predictions=directory/'predictions.jsonl.gz';answers=directory/'deepseek.jsonl.gz'
    removed=set(scope['removed_case_ids'])
    pred_report=filter_excluding(parent['inputs']['predictions']['path'],predictions,removed)
    answer_source=R/'strata/representative/deepseek.jsonl.gz'
    cascade._check(answer_source,parent_input['outputs']['deepseek']['sha256'],'representative answers')
    answer_report=filter_excluding(answer_source,answers,removed)
    if pred_report['case_ids']!=scope['kept_case_ids'] or answer_report['case_ids']!=scope['kept_case_ids']:
        raise ValueError('point-origin filter did not preserve exact same served case scope')
    if pred_report['removed_case_ids']!=scope['removed_case_ids'] or answer_report['removed_case_ids']!=scope['removed_case_ids']:
        raise ValueError('predictions/answers removed cases differ from source-origin scope')
    metadata=base.unique(base.read_rows(parent['inputs']['metadata']['path']),'prefix_id')
    episodes=list(base.read_rows(parent['inputs']['episodes']['path']));episode_ids={row['episode_id'] for row in episodes}
    if len(episodes)!=754 or len(episode_ids)!=754:raise ValueError('complete representative754episode universe required')
    reached={metadata[prefix]['episode_id'] for prefix in pred_report['prefix_ids']}
    p4_reached={metadata[prefix]['episode_id'] for prefix in pred_report['prefix_ids'] if metadata[prefix]['checkpoint']=='P4'}
    manifest={'version':'representative-actual-hook-1','created_at':datetime.now(timezone.utc).isoformat(),
        'selection':'existing REPRESENTATIVE split, then exclude ONLY P4 recorded_model_proposal; keep every P2 and all754episodes',
        'no_method_gold_or_outcome_selection':True,'stratifier_sha256':source_sha,
        'parent_freeze':{'path':str(parent_path),'sha256':base.digest(parent_path)},
        'parent_input_manifest':{'path':str(parent_input_path),'sha256':base.digest(parent_input_path)},
        'frozen_view':view,'view_freeze':{'path':str(view_freeze_path),'sha256':base.digest(view_freeze_path)},
        'scope':scope,'outputs':{'predictions':{'path':str(predictions),**pred_report},'answers':{'path':str(answers),**answer_report}},
        'complete_episode_universe':parent['inputs']['episodes'],'episode_ids':sorted(episode_ids),
        'no_p4_episode_ids_after_refinement':sorted(episode_ids-p4_reached),
        'no_cut_episode_ids_after_refinement':sorted(episode_ids-reached),
        'all_p2_retained':set(scope['p2_case_ids'])<=set(pred_report['case_ids']),
        'all754episodes_retained':True,'preserved_extended_files':preserved}
    manifest_path=directory/'input-manifest.json';base.write_json(manifest_path,manifest)
    bindings={key:item['path'] for key,item in parent['inputs'].items()}
    bindings.update(predictions=str(predictions),actual_hook_manifest=str(manifest_path))
    freeze_path=R/'cascade-representative-actual-freeze.json'
    cascade.freeze(parent['cascade_manifest']['path'],freeze_path,bindings)
    for path,expected in preserved.items():cascade._check(path,expected,'preserved extended result/source')
    if base.digest(Path(__file__))!=source_sha:raise ValueError('actual-hook stratifier changed during preparation')
    return {'freeze':str(freeze_path),'answers':str(answers),'answers_sha256':answer_report['sha256'],
            'output_dir':str(R/'cascade-representative-actual'),'input_manifest':str(manifest_path),
            'retained_cases':len(scope['kept_case_ids']),'actual_p4_cases':len(scope['actual_p4_case_ids']),
            'removed_p4_proposals':len(removed),'retained_p2_cases':len(scope['p2_case_ids']),
            'episodes':len(episode_ids),'no_p4_episodes':len(episode_ids-p4_reached),'no_cut_episodes':len(episode_ids-reached)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--selfcheck',action='store_true')
    parser.add_argument('--experiment',default=str(HERE));args=parser.parse_args()
    if args.selfcheck:selfcheck()
    else:print(json.dumps(prepare(args.experiment),indent=2))


if __name__=='__main__':main()
