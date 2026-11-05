"""Portable API-free verification; optionally recompute every frozen local verdict."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from . import canonical_dataset, views, release, evaluation as base
from .collector import file_hash
from .eliza import query_identity

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def rebase_paths(value,old_root,new_root):
    if isinstance(value,dict):return {rebase_paths(k,old_root,new_root):rebase_paths(v,old_root,new_root) for k,v in value.items()}
    if isinstance(value,list):return [rebase_paths(v,old_root,new_root) for v in value]
    if isinstance(value,str) and (value==old_root or value.startswith(old_root+'/')):
        return str(new_root)+value[len(old_root):]
    return value


def document_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def verify(local_predictions=False):
    os.chdir(ROOT)
    original_path=HERE/'results/evaluation-freeze.json'
    original=json.loads(original_path.read_text())
    old_root=original['inputs']['common']['path'].split('/experiments/')[0]
    frozen=rebase_paths(original,old_root,ROOT)
    # Verify executable sources before deserialization or projection generation.
    for p,h in frozen['sources'].items():
        if file_hash(Path(p))!=h:raise ValueError('source changed: '+p)
    canonical_dataset.restore()
    scratch=HERE/'.runtime';scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='verify-',dir=scratch) as tmp:
        tmp=Path(tmp);projected=tmp/'views';views.prepare(output=projected)
        # Original manifest bytes stay untouched. Only ignored caches are copied.
        for mode,name in [('historical','common'),('instrumented','instrumented')]:
            p=projected/(mode+'.jsonl.gz')
            if file_hash(p)!=original['inputs'][name]['sha256']:raise ValueError('projection changed')
            target=HERE/'views'/p.name;target.parent.mkdir(exist_ok=True)
            if not target.exists():shutil.copyfile(p,target)
        release.prepare()
        base.verify_freeze(frozen)
        from .cascade_evaluation import verify_cascade_manifest
        verify_cascade_manifest(HERE/'results/cascade-freeze-manifest.json')
        context={}; selected=set()
        for mode in ('historical','instrumented'):
            for row in base.read_rows(projected/(mode+'.jsonl.gz')):
                context[row['case_id']]=document_hash(row['input'])
                if row['split'] in ('REPRESENTATIVE','CHALLENGE'):selected.add(row['case_id'])
        inference=json.loads((HERE/'inference/freeze.json').read_text())
        if set(inference['selected_case_ids'])!=selected:raise ValueError('selected population changed')
        packets=set()
        for row in base.read_rows(HERE/'inference/inputs.jsonl.gz'):
            case=row['case_id']
            if case not in selected or case in packets or row['split'] not in ('REPRESENTATIVE','CHALLENGE'):
                raise ValueError('duplicate, unselected or training inference input')
            if document_hash(views.unpack_view(row['input']))!=context[case]:raise ValueError('frozen inference information mismatch')
            packets.add(case)
        if packets!=selected:raise ValueError('incomplete frozen inference population')
        run=HERE/'results/eliza-run';config=json.loads((HERE/'eliza-config.json').read_text());prompt=(HERE/'guard_prompt.txt').read_text()
        requests=set()
        for row in base.read_rows(run/'requests.jsonl.gz'):
            body=row['request'];identity=row['query_id']
            if row['case_id'] not in selected:raise ValueError('paid query outside selected groups')
            if identity in requests or query_identity(body)!=identity:raise ValueError('duplicate or altered paid query')
            requests.add(identity)
            if body['messages'][0]!={'role':'system','content':prompt}:raise ValueError('paid prompt changed')
            if any(body[k]!=config[k] for k in ('model','temperature','max_tokens','thinking','reasoning_effort')):raise ValueError('paid configuration changed')
            packet=json.loads(body['messages'][1]['content'])
            if document_hash(views.unpack_view(packet))!=context[row['case_id']]:raise ValueError('LLM/local information mismatch')
        responses={r['query_id'] for r in base.read_rows(run/'responses.jsonl.gz')}
        if responses!=requests or len(requests)!=3100:raise ValueError('incomplete paid request/response population')
        result={'sources_verified':True,'shared_contexts':len(context),'paid_queries':len(requests),'identical_expanded_information':True,
                'local_recomputed':local_predictions,'new_api_calls':0,'selected_inputs':len(packets),
                'verifier_sha256':file_hash(Path(__file__)),'local_predictions':{}}
        for mode,name in [('historical','common'),('instrumented','instrumented')]:
            old=HERE/f'results/{mode}-local.jsonl.gz';receipt=json.loads(Path(str(old)+'.receipt.json').read_text())
            if receipt['predictions_sha256']!=file_hash(old) or receipt['freeze_sha256']!=file_hash(original_path):raise ValueError('prediction receipt changed')
            if not local_predictions:continue
            from itertools import zip_longest
            count=0
            for expected,actual in zip_longest(base.read_rows(old),base.local_predictions(base.read_rows(projected/(mode+'.jsonl.gz')),frozen)):
                if expected is None or actual is None:raise ValueError('local prediction population changed')
                for key in ('case_id','method','placement','decision','raw_decision','calibrated_decision','gated_decision','probabilities','adapter_applicable'):
                    if expected.get(key)!=actual.get(key):raise ValueError('local prediction changed: '+str((key,expected.get('case_id'),expected.get('method'))))
                count+=1
            result['local_predictions'][mode]={'records':count,'mismatches':0}
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--local-predictions',action='store_true');p.add_argument('--receipt',type=Path)
    args=p.parse_args();result=verify(args.local_predictions)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True,exist_ok=True);args.receipt.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
