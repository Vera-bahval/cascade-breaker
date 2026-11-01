"""Execute frozen faulty variants independently; record crashes, never repair them.

The original batch CLI aborts if any mutant crashes on malformed proof. This
label-free supplement preserves all mutant functions and records each exception.
Only incorrect defined verdicts, not crashes, count toward sensitivity success.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
from .evaluate import read_rows, write_rows, write_json, digest, routing_envelope, verify_manifest
from .mutations import configurations, mutate_guard


def run(observations, metadata, manifest, output):
    verify_manifest(manifest)
    if Path(output).exists() or Path(str(output)+'.receipt.json').exists():
        raise ValueError('output already exists')
    obs, meta = read_rows(observations), {r['prefix_id']:r for r in read_rows(metadata)}
    predictions=[]
    for config in configurations('B'):
        subject=mutate_guard(config['mutation'])
        for row in obs:
            route=routing_envelope(row,meta[row['prefix_id']])
            try:
                result=subject(row['observation'],'B')
                value=dict(decision=result['decision'],reasons=result['reasons'],error=None)
            except Exception as exc:
                value=dict(decision=None,reasons=[],error=type(exc).__name__)
            predictions.append(dict(prefix_id=row['prefix_id'],method=config['name'],
                                    mutation=config['mutation'],**route,**value))
    verify_manifest(manifest)
    write_rows(output,predictions)
    inputs=[Path(observations),Path(metadata),Path(manifest),Path(__file__)]
    write_json(str(output)+'.receipt.json',dict(created_at=datetime.now(timezone.utc).isoformat(),
        inputs={str(p):digest(p) for p in inputs},predictions_sha256=digest(output),
        rows=len(predictions),gold_opened=False,functions_unchanged=True,
        crash_is_not_sensitivity_success=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('observations','metadata','manifest','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.observations,a.metadata,a.manifest,a.output)
