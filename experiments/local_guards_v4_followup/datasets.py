"""Build OPEN regression/conditional datasets; labels never guide conversions."""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
V3=HERE.with_name('local_guards_v3');V4=HERE.with_name('local_guards_v4')


def rows(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as h:
        for line in h:
            if line.strip():yield json.loads(line)


def write_rows(path,values):
    with Path(path).open('xb') as raw:
        with gzip.GzipFile(fileobj=raw,filename='',mode='wb',mtime=0) as h:
            for r in values:h.write((json.dumps(r,sort_keys=True,separators=(',',':'))+'\n').encode())


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_file(path,value):
    with Path(path).open('x') as h:json.dump(value,h,indent=2);h.write('\n')


def old_oracle():
    p=V4/'prepare_data.py';spec=importlib.util.spec_from_file_location('followup_frozen_custodian',p)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def payment_projection(row):
    from experiments.local_guards_v4.evaluate import baseline_observation
    return baseline_observation(row)


def label(row, *, known_payment=None,known41=None):
    from .oracle42 import adjudicate
    from .replay import project_v41
    custodian=old_oracle_cached
    old=project_v41(row['observation']);base=payment_projection(row)
    narrow=deepcopy(base);narrow['prefix_id']=row['prefix_id'];narrow['facts']={k:base.get('facts',{}).get(k) for k in custodian.old.FACTS}
    narrow['provenance']={k:base.get('provenance',{}).get(k,[]) for k in custodian.old.FACTS}
    payment=known_payment or custodian.old.action_gold(narrow)['decision']
    req41=known41 if known41 is not None else custodian.oracle(old,narrow)
    if old['checkpoint']=='P4' and old['proposal'].get('tool')=='finstripe__create_transfer':
        req41=deepcopy(req41);req41['A08']={'ALLOW':'satisfied','BLOCK':'violated','UNKNOWN':'unknown'}[payment]
    judged=adjudicate(row['observation'],'B')
    return {'prefix_id':row['prefix_id'],'requirements_41':req41,'requirements_42':judged['requirements'],
            'payment':payment,'malformed_41':False,'malformed_42':judged.get('malformed',False),
            'declared_target_42':judged['decision']}


old_oracle_cached=old_oracle()


def build(kind,output):
    from .replay import payment320_variant,adapt_v41_fixture,archive_variant,ArchiveReplayRegistry
    from .normalize import normalize,normalization_version
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    observations=[];metadata=[];labels=[];episodes=[];outcomes=[]
    assumptions_count=Counter();sources=[]
    if kind=='old320':
        source=V3/'closed-test';sources=[source/(n+'.jsonl') for n in ('observations','metadata','gold-actions')]
        meta={r['prefix_id']:r for r in rows(sources[1])};gold={r['prefix_id']:r for r in rows(sources[2])}
        for original in rows(sources[0]):
            wrapped=payment320_variant(original);pid=original['prefix_id'];wrapped['prefix_id']=pid
            observations.append(wrapped);metadata.append(meta[pid]);labels.append(label(wrapped,known_payment=gold[pid]['decision']))
    elif kind=='old400':
        source=V4/'closed';sources=[source/(n+'.jsonl.gz') for n in ('observations','metadata','gold-actions')]
        meta={r['prefix_id']:r for r in rows(sources[1])};gold={r['prefix_id']:r for r in rows(sources[2])}
        for original in rows(sources[0]):
            wrapped=adapt_v41_fixture(original);pid=original['prefix_id'];wrapped['prefix_id']=pid
            observations.append(wrapped);metadata.append(meta[pid]);labels.append(label(wrapped,known41=gold[pid]['requirements']))
    else:
        # Conditional source tables/outcomes remain frozen; no outcome is used by conversion.
        mode,portal=kind.split('_',1) if '_' in kind else (kind,'vendor')
        source=V4/'data';sources=[source/(n+'.jsonl.gz') for n in ('observations','metadata','episodes','gold-outcomes')]
        meta={r['prefix_id']:r for r in rows(sources[1])}
        registry=ArchiveReplayRegistry() if mode=='technical' else None
        for original in rows(sources[0]):
            pid=original['prefix_id'];wrapped=archive_variant(original,meta[pid],mode,portal,registry=registry);wrapped['prefix_id']=pid
            observations.append(wrapped);metadata.append(meta[pid]);labels.append(label(wrapped))
        episodes=list(rows(sources[2]));outcomes=list(rows(sources[3]))
    for r in observations:
        assumptions_count.update(a['field'].split('.')[0] for a in r.get('assumptions',[]))
    if not episodes:
        by_episode={}
        for m in metadata:
            eid=m.get('episode_id',m['prefix_id']);by_episode.setdefault(eid,dict(episode_id=eid,group_id=m.get('group_id',eid),cohort=kind,executor='synthetic'))
        episodes=list(by_episode.values())
    write_rows(output/'observations.jsonl.gz',observations);write_rows(output/'metadata.jsonl.gz',metadata)
    write_rows(output/'gold-actions.jsonl.gz',labels);write_rows(output/'episodes.jsonl.gz',episodes)
    write_rows(output/'gold-outcomes.jsonl.gz',outcomes)
    normalized=Counter(normalize(r['observation']) for r in observations)
    json_file(output/'manifest.json',{'dataset':kind,'kind':'OPEN_regression' if kind.startswith('old') else 'OPEN_conditional_archive',
        'rows':len(observations),'episodes':len(episodes),'normalization_version':normalization_version,
        'normalized_unique':len(normalized),'duplicate_groups':sum(v>1 for v in normalized.values()),
        'assumption_fields':dict(assumptions_count),'source_hashes':{str(p.relative_to(ROOT)):digest(p) for p in sources},
        'producer_hashes':{str(p.relative_to(ROOT)):digest(p) for p in [HERE/'datasets.py',HERE/'replay.py',HERE/'normalize.py',HERE/'oracle42.py']},
        'output_hashes':{p.name:digest(p) for p in sorted(output.glob('*.gz'))}})
    print(json.dumps({'dataset':kind,'rows':len(observations),'episodes':len(episodes),'unique':len(normalized)}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',choices=['old320','old400','strict','session_vendor','session_admin','technical_vendor','technical_admin'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.dataset,a.output)


if __name__=='__main__':main()
