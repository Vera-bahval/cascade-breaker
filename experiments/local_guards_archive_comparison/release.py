"""Custodian-only release of normalized TRAIN/CAL; never used by predictors."""
import hashlib
import json
from pathlib import Path
from .collector import read_jsonl, write_jsonl, file_hash

HERE=Path(__file__).resolve().parent


def prepare():
    metadata={r['prefix_id']:r for r in read_jsonl(HERE/'data/split-metadata.jsonl.gz')}
    labels={r['prefix_id']:r for r in read_jsonl(HERE/'labels/actions-unreviewed.jsonl.gz')}
    views=read_jsonl(HERE/'views/historical.jsonl.gz')
    out=HERE/'packages/release';out.mkdir(parents=True,exist_ok=True)
    manifest={'sources':{},'outputs':{},'population':{}}
    for split in ('TRAIN','CAL'):
        rows=[];targets=[];meta=[]
        for v in views:
            key=v['prefix_id'];m=metadata[key]
            if m['split']!=split:continue
            if v['split']!=split or m['executor']=='luna':raise RuntimeError('release split mismatch')
            episode='episode/'+hashlib.sha256(m['episode_id'].encode()).hexdigest()[:24]
            rows.append(dict(v['input'],prefix_id=key,episode_id=episode))
            targets.append(dict(prefix_id=key,scenario_decision=labels[key]['scenario_decision'],
                                native_core=labels[key]['native_core']['decision']))
            meta.append(dict(prefix_id=key,episode_id=episode,base_group_id=m['group_id']))
        manifest['population'][split]={'states':len(rows),'episodes':len({r['episode_id'] for r in rows}),
                                      'groups':len({r['base_group_id'] for r in meta})}
        for name,values in (('rows',rows),('labels',targets),('meta',meta)):
            path=out/(split+'-'+name+'.jsonl.gz');write_jsonl(path,values)
            manifest['outputs'][str(path.relative_to(Path.cwd()))]=file_hash(path)
    for name in ('views/historical.jsonl.gz','views/manifest.json','labels/manifest.json',
                 'labels/actions-unreviewed.jsonl.gz','provenance/labels-clearance.json',
                 'provenance/collector-clearance.json','data/split-metadata.jsonl.gz','release.py'):
        path=HERE/name
        manifest['sources'][str(path.relative_to(Path.cwd()))]=file_hash(path)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':print(json.dumps(prepare(),indent=2))
