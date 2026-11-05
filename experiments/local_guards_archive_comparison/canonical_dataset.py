"""Rebuild the technical mode from published historical rows and tiny patches."""
import argparse
import copy
import json
from itertools import zip_longest
from pathlib import Path
from .collector import file_hash, write_jsonl
from .evaluation import read_rows

HERE=Path(__file__).resolve().parent
FIELDS=('call_id','parent_workflow_id','source_binding')


def apply_technical(row,patch):
    if row['prefix_id']!=patch['prefix_id'] or set(patch)!={'prefix_id','context','provenance','evidence_status'}:
        raise ValueError('wrong technical patch identity/shape')
    if set(patch['context'])!=set(FIELDS) or any(set(patch[k])!={'context.'+f for f in FIELDS} for k in ('provenance','evidence_status')):
        raise ValueError('patch may only contain the three declared technical fields')
    result=copy.deepcopy(row)
    result['observation']['context'].update(patch['context'])
    result['observation']['provenance'].update(patch['provenance'])
    result['evidence_status'].update(patch['evidence_status'])
    return result


def extract():
    h=HERE/'data/historical/observations.jsonl.gz';i=HERE/'data/instrumented/observations.jsonl.gz'
    p=HERE/'data/technical-context-patches.jsonl.gz';count=0
    def rows():
        nonlocal count
        for old,new in zip_longest(read_rows(h),read_rows(i)):
            if old is None or new is None:raise ValueError('mode population mismatch')
            patch={'prefix_id':new['prefix_id'],'context':{f:new['observation']['context'][f] for f in FIELDS},
                'provenance':{'context.'+f:new['observation']['provenance']['context.'+f] for f in FIELDS},
                'evidence_status':{'context.'+f:new['evidence_status']['context.'+f] for f in FIELDS}}
            if apply_technical(old,patch)!=new:raise ValueError('nontechnical mode difference')
            count+=1;yield patch
    write_jsonl(p,rows())
    manifest={'rows':count,'historical_sha256':file_hash(h),'instrumented_sha256':file_hash(i),
              'patches_sha256':file_hash(p),'source_sha256':file_hash(Path(__file__))}
    (HERE/'data/technical-context-patches.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def restore():
    data=HERE/'data';m=json.loads((data/'technical-context-patches.manifest.json').read_text())
    h=data/'historical/observations.jsonl.gz';p=data/'technical-context-patches.jsonl.gz';i=data/'instrumented/observations.jsonl.gz'
    if file_hash(h)!=m['historical_sha256'] or file_hash(p)!=m['patches_sha256']:raise ValueError('canonical inputs changed')
    if i.exists():
        if file_hash(i)!=m['instrumented_sha256']:raise ValueError('existing technical mode changed')
        return m
    def rows():
        for row,patch in zip_longest(read_rows(h),read_rows(p)):
            if row is None or patch is None:raise ValueError('patch population mismatch')
            yield apply_technical(row,patch)
    write_jsonl(i,rows())
    if file_hash(i)!=m['instrumented_sha256']:raise ValueError('technical reconstruction mismatch')
    return m


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--extract-patches',action='store_true')
    args=parser.parse_args();print(json.dumps(extract() if args.extract_patches else restore(),indent=2))
