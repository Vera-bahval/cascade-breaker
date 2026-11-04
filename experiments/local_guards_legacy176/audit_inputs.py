"""Read-only structural checks, no guard/model predictions or scoring labels."""
from collections import Counter
import json
from .prepare import HERE,ROOT
from experiments.local_guards_adapter_repair.inventory import rows,sha


def audit():
    manifest=json.loads((HERE/'input-manifest.json').read_text())
    for name,h in manifest['outputs'].items():assert sha(HERE/name)==h,name
    for name,h in manifest['code'].items():assert sha(HERE/name)==h,name
    for name,h in manifest['frozen_sources'].items():assert sha(ROOT/name)==h,name
    counts=Counter();ids=set();facts=Counter();records=0
    sources={c['prefix_id']:c for c in rows(HERE/'source-prefixes.jsonl.gz')}
    for c in sources.values():
        assert 'db_final' not in c['run'] and 'label' not in c['run']
        assert all(s['seq']<=c['cut_seq'] and s['kind'] not in ('guard','guard_stop') for s in c['run']['steps'])
    for r in rows(HERE/'prepared-inputs.jsonl.gz'):
        key=r['mode'],r['prefix_id'];assert key not in ids;ids.add(key)
        counts[r['mode']]+=1;b=r['bundle'];assert b['event_seq']==2*r['cut_seq']+1
        assert b['proposal']['tool']=='finstripe__create_transfer'
        assert all(p['event_seq']<b['event_seq'] for p in b['records'])
        assert all('source_call_id' not in p for p in b['records'] if p['evidence_kind']=='server_snapshot')
        for method,a in r['adapters'].items():
            from experiments.local_guards_archive_comparison.collector import digest
            assert digest(a['payload'])==r['payload_sha256'][method]
        for fact,value in b['current'].items():facts[r['mode']+':'+fact+':'+value['source']]+=1
        records+=len(b['records'])
        if r['mode']=='full':
            assert r['adapters']['v1']['payload']['state']==sources[r['prefix_id']]['expected_legacy_state']
            assert r['adapters']['v1']['applicable'] and r['adapters']['v2']['applicable']
        else:
            assert not r['adapters']['v1']['applicable']
            assert not b['initial']
            for method in ('v3','v4.3'):
                assert not r['adapters'][method]['payload']['proposal'].get('amount')
    assert counts=={'full':176,'partial':176}
    return dict(status='INPUT_AUDIT_PASS',counts=dict(counts),records=records,fact_sources=dict(facts),input_manifest_sha256=sha(HERE/'input-manifest.json'))

if __name__=='__main__':print(json.dumps(audit(),sort_keys=True))
