"""Label-blind canonical routing/episode records for open one-state fixtures.

Never repairs the observation body. The old400 metadata lacks an ordering value
for one deliberately boolean cut; its independent one-state episode gets route 0.
"""
from pathlib import Path
import argparse
from .evaluate import read_rows, write_rows, write_json, digest


def build(source, output):
    source, output = Path(source), Path(output)
    observations = read_rows(source / 'observations.jsonl.gz')
    metadata = read_rows(source / 'metadata.jsonl.gz')
    by_id = {r['prefix_id']: r['observation'] for r in observations}
    episodes, changed = {}, []
    for row in metadata:
        body = by_id[row['prefix_id']]
        seq = body.get('event_seq')
        if type(seq) is not int or seq < 0:
            row['event_seq'] = 0
            row['routing_assumption'] = 'sole-state ordering only; invalid body unchanged'
            changed.append(row['prefix_id'])
        eid = row.get('episode_id', row['prefix_id'])
        if eid in episodes:
            raise ValueError('only independent one-state fixtures are supported')
        episodes[eid] = dict(episode_id=eid, group_id=row.get('group_id', eid),
                            **{k:row[k] for k in ('cohort','executor','split') if k in row})
    output.mkdir(parents=True, exist_ok=False)
    write_rows(output/'metadata.jsonl.gz', metadata)
    write_rows(output/'episodes.jsonl.gz', list(episodes.values()))
    write_json(output/'manifest.json', dict(
        source_hashes={n:digest(source/n) for n in ('observations.jsonl.gz','metadata.jsonl.gz')},
        source_code_sha256=digest(Path(__file__)), gold_read=False, body_unchanged=True,
        routing_assumptions=changed, episodes=len(episodes),
        output_hashes={p.name:digest(p) for p in output.glob('*.gz')}))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();build(args.source,args.output)
