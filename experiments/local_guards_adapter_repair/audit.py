"""Validate prepared inputs and frozen assets, without executing any method."""
import argparse
from collections import Counter
import json
from pathlib import Path

from .inventory import HERE, ROOT, rows, sha, write_json
from experiments.local_guards_archive_comparison.collector import digest
from experiments.local_guards_v4 import guard as schema


def audit(directory, *, frozen=True):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text())
    inventory=json.loads((HERE/'inventory.json').read_text())
    if sha(HERE/'inventory.json')!=manifest['inventory_sha256'] or sha(HERE/'methods.json')!=manifest['methods_sha256']:
        raise ValueError('inventory or inference contract changed')
    for name,expected in manifest['source_hashes'].items():
        if sha(HERE/name)!=expected:
            raise ValueError('preparation source changed: '+name)
    if sha(HERE/'frozen-sources.json')!=manifest['frozen_sources_sha256']:
        raise ValueError('frozen pins changed')
    if {p.name for p in HERE.glob('*.py')}!=set(manifest['source_hashes']):
        raise ValueError('preparation source set changed')
    if frozen:
        pins=json.loads((HERE/'frozen-sources.json').read_text())
        for rel,expected in pins['files'].items():
            if sha(ROOT/rel)!=expected:
                raise ValueError('frozen artifact changed: '+rel)
    seen=Counter()
    represented=Counter()
    for name,expected in manifest['outputs'].items():
        if sha(directory/name)!=expected:
            raise ValueError('prepared shard changed: '+name)
        for row in rows(directory/name):
            pid=row['prefix_id']
            seen[('p4' if name.startswith('p4') else 'early',row['mode'],pid)]+=1
            bundle=row['bundle']
            boundary=row['action_boundary']
            if boundary.get('tool_name') and bundle['proposal'].get('tool')!=boundary['tool_name']:
                raise ValueError('action tool missing or changed: '+pid)
            if bundle['checkpoint'] in ('P1','P3') and boundary.get('event_seq')!=bundle['event_seq']:
                raise ValueError('wrong early action boundary: '+pid)
            args=boundary.get('tool_arguments') or {}
            if bundle['checkpoint'] in ('P1','P3','P4'):
                for key in ('invoice_id','vendor_id'):
                    if type(args.get(key)) is int and args[key]>0 and bundle['context'].get(key)!=args[key]:
                        raise ValueError('source action subject changed: '+pid)
                if isinstance(args.get('status'),str) and args['status'].strip() and bundle['proposal'].get('target_status')!=args['status']:
                    raise ValueError('source transition target lost: '+pid)
                amount=schema._amount(str(args['amount'])) if args.get('amount') is not None else None
                if amount is not None and schema._amount(bundle['proposal'].get('amount'))!=amount:
                    raise ValueError('source action amount changed: '+pid)
            if any(r['event_seq']>=bundle['event_seq'] for r in bundle['records']):
                raise ValueError('evidence from future: '+pid)
            for method,result in row['adapters'].items():
                if digest(result['payload'])!=row['payload_sha256'][method]:
                    raise ValueError('adapter fingerprint changed')
                if method not in ('v3','v4','v4.2','v4.3','retrain_ml'):
                    continue
                payload=result['payload'].get('observation',result['payload'])
                for fact,record in bundle['current'].items():
                    if (record['current'] and fact in schema._SCHEMA['properties']['facts']['properties']
                            and schema._typed(fact,record['value']) is not None):
                        if method=='v3' and fact not in schema._PAYMENT:
                            continue
                        if fact not in payload['facts']:
                            raise ValueError('unexplained field loss: '+str((pid,method,fact)))
                        represented[method,fact]+=1
                for fact,proofs in payload['provenance'].items():
                    if any(p['event_seq']>=payload['event_seq'] for p in proofs):
                        raise ValueError('proof crosses action boundary')
            for family,features in row['features'].items():
                if digest(features)!=row['feature_sha256'][family]:
                    raise ValueError('ML features changed')
    expected=set()
    for mode in ('common','expanded','conditional'):
        expected.update(('p4',mode,c['prefix_id']) for c in inventory['p4'])
    for mode in ('historical','conditional'):
        expected.update(('early',mode,p) for p in inventory['early_prefixes'])
    if set(seen)!=expected or any(n!=1 for n in seen.values()):
        raise ValueError('cohort mismatch, missing or repeated input')
    result={'status':'INPUT_AUDIT_PASS','prepared_rows':len(seen),'prediction_calls':0,
            'source_manifest_sha256':sha(directory/'manifest.json'),
            'field_transfer_checks':sum(represented.values()),
            'independent_review':'still required before any experiment'}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(audit(args.inputs),sort_keys=True))
