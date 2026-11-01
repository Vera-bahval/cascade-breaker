"""Join paid unique-query receipts to served cases, without filling missing replies."""
import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from .evaluation import digest, read_rows, write_rows, write_json, verify_freeze

HERE=Path(__file__).resolve().parent


def normalize(mode,output):
    frozen=HERE/'results/evaluation-freeze.json';verify_freeze(frozen)
    run=HERE/'results/eliza-run'
    responses={r['query_id']:r for r in read_rows(run/'responses.jsonl.gz')}
    metadata={r['prefix_id']:r for r in read_rows(HERE/'data/evaluation-metadata.jsonl.gz')}
    with closing(sqlite3.connect(run/'ledger.sqlite')) as db:
        ledger={r[0]:r[1:] for r in db.execute('SELECT id,cost,status FROM requests')}
    for key,r in responses.items():
        if key not in ledger or ledger[key][1]!='complete' or abs(ledger[key][0]-r['cost_usd'])>1e-12:
            raise ValueError('response/actual-charge ledger mismatch')
    mapped={r['case_id']:r['query_id'] for r in read_rows(run/'case-mapping.jsonl.gz')}
    rows=[]
    for case,key in sorted(mapped.items()):
        if not case.startswith(mode+'/') or key not in responses:continue
        prefix=case.split('/',1)[1];m=metadata[prefix];r=responses[key]
        rows.append(dict(case_id=case,prefix_id=prefix,split=m['split'],checkpoint=m['checkpoint'],event_seq=m['event_seq'],
            method='deepseek',placement='both',decision=r['decision'],decision_ms=r['latency_s']*1000,
            timing_scope='actual individual Eliza HTTP request while up to8 requests concurrent',
            query_id=key,charge_usd=r['cost_usd'],charge_source='actual_eliza_response.cost',status='RESPONSE',
            usage=r['usage'],parsed=r['parsed']))
    write_rows(output,rows)
    receipt=dict(freeze_sha256=digest(frozen),predictions_sha256=digest(output),mode=mode,
        served_states=len(rows),unique_queries=len({r['query_id'] for r in rows}),
        missing_reply_policy='NOT_MEASURED, never method UNKNOWN',
        sources={str(p):digest(p) for p in [Path(__file__),run/'responses.jsonl.gz',run/'case-mapping.jsonl.gz',
            run/'ledger.sqlite',HERE/'data/evaluation-metadata.jsonl.gz',HERE/'inference/freeze.json']})
    write_json(str(output)+'.receipt.json',receipt)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['historical','instrumented'],required=True)
    p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(normalize(a.mode,a.output),indent=2))
