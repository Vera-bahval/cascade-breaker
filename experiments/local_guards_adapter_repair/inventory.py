"""Custodial identity/source extraction and byte hashing. No labels are parsed."""
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
EXP=HERE.parent
BASE='5f947a38193f65ffcc1f55c29c75e35be7678461'
META_KEYS=('episode_id','executor','source','source_sha256','member','raw_hash','raw_events',
           'fixture_ref','verified_source_version','prefix_id','source_event_index')


def rows(path):
    with gzip.open(path,'rt') as stream:
        for line in stream:
            yield json.loads(line)


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n')


def freeze():
    annotation=EXP/'local_guards_archive_annotation'
    archive=EXP/'local_guards_archive_comparison'
    early=EXP/'local_guards_final_replay/early-data'
    cases=json.loads((annotation/'custodian_manifest.json').read_text())['cases']
    ids={c['prefix_id'] for c in cases}
    metadata={r['prefix_id']:{k:r[k] for k in META_KEYS if k in r}
              for r in rows(archive/'data/metadata.jsonl.gz') if r['prefix_id'] in ids}
    early_ids=[r['episode_id'] for r in rows(early/'early-events.jsonl.gz')]
    eps={r['episode_id']:{k:r[k] for k in META_KEYS if k in r}
         for r in rows(archive/'data/episodes.jsonl.gz') if r['episode_id'] in set(early_ids)}
    early_inputs=list(rows(early/'early-inputs.jsonl.gz'))
    selection=json.loads((early/'id-map.private.json').read_text())
    selected_ids=[r['prefix_id'] for r in selection]
    assert len(cases)==542 and len(ids)==542 and set(metadata)==ids
    assert len(eps)==754 and len(early_inputs)==18676 and len(selected_ids)==128
    inventory={'base':BASE,'p4':[{'case_id':c['case_id'],'annotation_id':c['annotation_id'],
                 'prefix_id':c['prefix_id'],'input_sha256':c['input_sha256'],
                 'metadata':metadata[c['prefix_id']]} for c in cases],
               'early_episodes':eps,'early_prefixes':[r['prefix_id'] for r in early_inputs],
               'early_selected_prefixes':selected_ids}
    write_json(HERE/'inventory.json',inventory)
    families=('local_guards_v3','local_guards_v4','local_guards_v4_followup',
              'local_guards_ml_retrain','local_guards_archive_comparison','local_guards_archive_annotation',
              'local_guards_final_replay')
    tracked=subprocess.check_output(['git','ls-files','--',*[str((EXP/f).relative_to(ROOT)) for f in families]],cwd=ROOT,text=True).splitlines()
    # Hash frozen artifacts, including labels and predictions, without decoding
    # them. Their content is excluded from the preparation input allowlist.
    pins={p:sha(ROOT/p) for p in tracked if (ROOT/p).is_file()}
    write_json(HERE/'frozen-sources.json',{'base':BASE,'files':pins,
               'inventory_sha256':sha(HERE/'inventory.json')})
    print(json.dumps({'p4':len(ids),'early_episodes':len(eps),'early_actions':len(early_inputs),
                      'selected_actions':len(selected_ids),'frozen_files':len(pins)}),flush=True)


if __name__=='__main__':
    freeze()
