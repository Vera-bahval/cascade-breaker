"""Measure store operations for explicit trusted retry reconciliation, offline."""
import argparse
import json
from pathlib import Path
import tempfile
from time import perf_counter
from .store import EvidenceStore, ClaimConflict
from .latency_followup import offline
from . import evaluate as ev


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();raw=[]
    with offline():
        for repeat in range(30):
            with tempfile.TemporaryDirectory() as td:
                s=EvidenceStore(Path(td)/'claims.sqlite')
                start=perf_counter();s.acquire_claim('ns',2,3,'failed',1)
                acquired=(perf_counter()-start)*1000
                start=perf_counter();s.release_claim('failed',False)
                uncertain=(perf_counter()-start)*1000
                start=perf_counter()
                try:s.acquire_claim('ns',2,3,'retry',2)
                except ClaimConflict:pass
                else:raise AssertionError('uncertain claim allowed a new owner')
                rejected=(perf_counter()-start)*1000
                start=perf_counter();s.release_claim('failed',True)
                released=(perf_counter()-start)*1000
                start=perf_counter();s.acquire_claim('ns',2,3,'retry',3)
                retry=(perf_counter()-start)*1000
                assert s.claim('retry')['state']=='active'
                raw.append({'repeat':repeat,'initial_acquire_ms':acquired,'mark_uncertain_ms':uncertain,
                            'reject_uncertain_ms':rejected,'trusted_release_ms':released,'retry_acquire_ms':retry})
    ev.write_json(args.output,{'source_sha256':ev.digest(Path(__file__)),'raw':raw,
        'new_inference_api_calls':0,'reconciliation':'explicit trusted release; no real business reconciliation is timed'})
    print(json.dumps({'measured_recovery_cycles':len(raw),'output':str(args.output)}))


if __name__=='__main__':main()
