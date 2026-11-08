"""Prediction-independent group union and fixed seed-17 archive partition."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
from collector import HERE, canonical, digest, read_jsonl, write_jsonl, file_hash

MECHANISMS = ('HOLD','amountbounds','recipient','materialchange','access','delegation','SystemUtils','repeat')
VARIANTS = r'(?:base|placebo|cfo|manager|urgent|nocheck|no-check|control|attack)'


def normalize_text(text):
    return re.sub(r'\s+',' ',str(text or '')).strip().casefold()


def lineage_keys(row):
    s=row.get('scenario') or {}
    keys=[]
    for field in ('pair','base','base_id','parent_id','original_id','lineage'):
        if s.get(field) is not None:keys.append(('explicit_'+field,str(s[field])))
    sid=str(s.get('id') or '')
    stripped=re.sub(r'-r\d+$','',sid)
    match=re.fullmatch(r'(.+?)-'+VARIANTS+r'(?:-.+)?',stripped,re.I)
    if match:keys.append(('variant_base',match[1]))
    text=normalize_text(s.get('desc',s.get('description')))
    if text:keys.append(('exact_normalized_description',text))
    # Same exact scenario identity across executors/repeats is additional evidence;
    # no amount, executor, result or old fingerprint is used as a split key.
    if stripped:keys.append(('scenario_id',stripped))
    return keys


def assign_groups(rows):
    parent=list(range(len(rows)))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    receipts=[];seen={}
    for i,row in enumerate(rows):
        for kind,key in lineage_keys(row):
            # Explicit pair/base and derived variant base must share a namespace.
            key_type='base_lineage' if kind.startswith('explicit_') or kind=='variant_base' else kind
            lookup=(key_type,key)
            if lookup in seen:
                j=seen[lookup];a,b=find(i),find(j)
                if a!=b:
                    parent[max(a,b)]=min(a,b)
                    receipts.append(dict(left=rows[j]['episode_id'],right=row['episode_id'],kind=kind,key_sha256=digest(key)))
            else:seen[lookup]=i
    members=defaultdict(list)
    for i,row in enumerate(rows):members[find(i)].append(row['episode_id'])
    ids={k:'group/'+digest(sorted(v))[:24] for k,v in members.items()}
    return [dict(row,group_id=ids[find(i)]) for i,row in enumerate(rows)],receipts


def mechanisms(row):
    s=row.get('scenario') or {}
    text=normalize_text(s.get('desc',s.get('description')))
    tools=set(row.get('observed_tool_names') or [])
    tags=set()
    if re.search(r'\b(hold|pause|reject|escalat\w*)\b',text):tags.add('HOLD')
    try:
        amount=float(s.get('amount'))
        if amount<=0 or amount>10000 or amount in (1000,5000,10000,50000):tags.add('amountbounds')
    except (ValueError,TypeError):pass
    if re.search(r'\b(bank|account|recipient|routing|wire|beneficiary)\b',text):tags.add('recipient')
    if re.search(r'\b(updat\w*|chang\w*|edit\w*|modif\w*)\b',text):tags.add('materialchange')
    if re.search(r'\b(namespace|other vendor|access|admin|permission)\b',text):tags.add('access')
    if any(t.startswith('delegate_to_') for t in tools):tags.add('delegation')
    if 'systemutils__execute_script' in tools or 'systemutils' in text:tags.add('SystemUtils')
    if (row.get('repeat') or 1)>1:tags.add('repeat')
    return tags


def select_splits(rows,seed=17):
    by=defaultdict(list)
    for row in rows:by[row['group_id']].append(row)
    groups=sorted(by)
    rng=random.Random(seed)
    strata=defaultdict(list)
    for group,values in by.items():
        # Mixed-origin groups are indivisible. Their full origin/version set forms
        # the stratum instead of arbitrarily assigning the first executor's source.
        stratum=canonical(sorted({(r.get('source_origin') or 'unknown',bool(r.get('verified_source_version',r.get('source_version')))) for r in values}))
        strata[stratum].append(group)
    target=math.ceil(len(groups)*.20)
    allocation={s:math.floor(len(v)*target/len(groups)) for s,v in strata.items()}
    remainders=sorted(strata,key=lambda s:(-(len(strata[s])*target/len(groups)-allocation[s]),digest([seed,s])))
    for s in remainders[:target-sum(allocation.values())]:allocation[s]+=1
    representative=set()
    for s in sorted(strata):
        values=sorted(strata[s]);rng.shuffle(values);representative.update(values[:allocation[s]])
    remaining=[g for g in groups if g not in representative]
    tags={g:set().union(*(mechanisms(r) for r in by[g])) for g in groups}
    challenge_target=min(len(remaining),math.ceil(len(groups)*.10))
    challenge=set();coverage=Counter()
    # Fixed mechanism round-robin, seeded deterministic tie order; no labels/results.
    tie={g:digest([seed,'challenge',g]) for g in remaining}
    while len(challenge)<challenge_target:
        candidates=[g for g in remaining if g not in challenge]
        needed=sorted(MECHANISMS,key=lambda tag:(coverage[tag],MECHANISMS.index(tag)))
        tag=next((t for t in needed if any(t in tags[g] for g in candidates)),None)
        eligible=[g for g in candidates if tag is None or tag in tags[g]]
        chosen=min(eligible,key=lambda g:(-sum(1/(1+coverage[t]) for t in tags[g]),tie[g]))
        challenge.add(chosen);coverage.update(tags[chosen])
    development=[g for g in groups if g not in representative|challenge]
    rng=random.Random(seed);rng.shuffle(development)
    cal=set(development[:math.ceil(len(development)*.25)])
    partition={g:'REPRESENTATIVE' if g in representative else 'CHALLENGE' if g in challenge else 'CAL' if g in cal else 'TRAIN' for g in groups}
    result=[]
    for row in rows:
        part=partition[row['group_id']]
        split='HOLDOUT_LUNA' if row.get('executor')=='luna' and part in ('TRAIN','CAL') else part
        result.append(dict(row,split=split,group_partition=part,mechanism_tags=sorted(mechanisms(row))))
    manifest=dict(seed=seed,selection_inputs='initial scenario/lineage, source origin/version availability, observed tool names/repeats only; no labels or new predictions',representative_fraction='ceil(20% all groups), proportional stratum allocation',challenge_fraction='ceil(10% all groups), selected from remaining; fixed predeclared mechanism coverage',development_fraction='remaining groups 75/25 TRAIN/CAL; all Luna rows excluded both',representative_groups=sorted(representative),challenge_groups=sorted(challenge),cal_groups=sorted(cal),train_groups=sorted(set(development)-cal),strata={s:dict(groups=len(v),representative=allocation[s]) for s,v in sorted(strata.items())},challenge_mechanism_coverage=dict(coverage),group_sizes={g:len(by[g]) for g in groups},group_mechanisms={g:sorted(tags[g]) for g in groups},split_episodes=dict(Counter(r['split'] for r in result)))
    return result,manifest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=HERE/'data');args=parser.parse_args()
    episodes=read_jsonl(args.data/'episodes.jsonl.gz')
    grouped,receipts=assign_groups(episodes);assigned,manifest=select_splits(grouped)
    lookup={e['episode_id']:e for e in assigned}
    metadata=read_jsonl(args.data/'metadata.jsonl.gz')
    for row in metadata:
        e=lookup[row['episode_id']]
        row.update({k:e[k] for k in ('group_id','split','group_partition','mechanism_tags')})
    write_jsonl(args.data/'split-episodes.jsonl.gz',assigned)
    write_jsonl(args.data/'split-metadata.jsonl.gz',metadata)
    write_jsonl(args.data/'group-lineage-receipts.jsonl.gz',receipts)
    source_labels=[]
    for e in assigned:
        s=e.get('scenario') or {}
        source_labels.append({k:e.get(k) for k in ('episode_id','source_intent','source_requires_stop')}|dict(scenario_truth=s.get('truth')))
    write_jsonl(args.data/'source-labels-unverified.jsonl.gz',source_labels)
    metadata_by={r['prefix_id']:r for r in metadata}
    package_counts=Counter()
    # Selected evaluation predictor rows remain in custodian data only.
    package_rows={split:[] for split in ('TRAIN','CAL')}
    for row in read_jsonl(args.data/'historical/observations.jsonl.gz'):
        split=metadata_by[row['prefix_id']]['split']
        if split in package_rows:
            package_rows[split].append(row);package_counts[split]+=1
    for split,rows in package_rows.items():
        dest=HERE/'packages'/split;dest.mkdir(parents=True,exist_ok=True)
        write_jsonl(dest/'observations.jsonl.gz',rows)
        selected_ids={r['prefix_id'] for r in rows}
        # Metadata is a join-only sidecar, never fed to predictors. Keep old source
        # labels in a separate explicit file and omit the old target entirely.
        safe=[]
        for meta in metadata:
            if meta['prefix_id'] in selected_ids:
                safe.append({k:v for k,v in meta.items() if k not in ('source_intent','source_requires_stop','source_attempt_harm','continuation_harm')})
        write_jsonl(dest/'metadata.jsonl.gz',safe)
        ids={x['episode_id'] for x in safe}
        write_jsonl(dest/'source-labels-unverified.jsonl.gz',[x for x in source_labels if x['episode_id'] in ids])
        for name in ('POLICY.md','policy.json','schema.json'):shutil.copyfile(HERE/name,dest/name)
    raw_reads=json.loads((HERE/'provenance/collector-read-log.json').read_text())
    read_by_hash=defaultdict(list)
    for item in raw_reads:
        read_by_hash[item['sha256']].append(item['source']+('::'+item['member'] if item.get('member') else ''))
    source_inventory=json.loads((HERE.parent/'local_guards_v4/data/source-inventory.json').read_text())['records']
    aliases=[dict(sha256=item['sha256'],git_blob=item.get('git_blob'),locations=item['locations'],matched_read_sources=read_by_hash[item['sha256']],reason='byte_identical_raw_source_alias_not_an_additional_episode') for item in source_inventory if item['sha256'] in read_by_hash and (item.get('native_hook_episodes') or item.get('legacy_probe_episodes') or item.get('status')=='native_journal_candidate')]
    write_jsonl(args.data/'source-alias-receipts.jsonl.gz',aliases)
    manifest['source_alias_receipts']=len(aliases)
    manifest.update(observations=dict(package_counts),registry_episodes=len(episodes),groups=len(set(e['group_id'] for e in assigned)),lineage_edges=len(receipts),source_hashes={name:file_hash(args.data/name) for name in ('episodes.jsonl.gz','historical/observations.jsonl.gz')})
    (args.data/'split-manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:manifest[k] for k in ('seed','groups','registry_episodes','split_episodes','observations','lineage_edges')},indent=2))

if __name__=='__main__':main()
