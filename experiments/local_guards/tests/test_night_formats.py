import json,gzip
from pathlib import Path
from cascade_guard.night_formats import build_payloads
BASE=Path(__file__).resolve().parents[1]

def fixture():
    prefix=next(json.loads(l) for l in (BASE/'data/prefixes.jsonl').read_text().splitlines() if json.loads(l)['prefix_id']=='baea55b592c4314234ad2bb3')
    run=next(r for r in map(json.loads,gzip.decompress((BASE/'data/archive/shadow-main.jsonl.gz').read_bytes()).decode().splitlines()) if r['run_id']==prefix['episode_id'])
    context=next(s for s in run['steps'] if s['seq']==prefix['cut_seq'])
    return prefix,run,context

def test_formats_prefix_only_and_not_future_sensitive():
    p,r,c=fixture();a,meta=build_payloads(p,r['db_initial'],c,r['steps'])
    b,_=build_payloads(p,r['db_initial'],c,[s for s in r['steps'] if s['seq']<c['seq']])
    assert a==b and meta['max_observed_seq']<c['seq']
    assert a['plus_rationale']=={'state':p['state'],'questions':p['questions']}

def test_automatic_small_payment_needs_no_executive_evidence():
    p,r,c=fixture();views,_=build_payloads(p,r['db_initial'],c,r['steps'])
    state=views['compact_policy_facts']['state']
    assert state['applicability']['independent_human_amount_review']=='NOT_REQUIRED'
    assert views['compact_policy_facts']['questions']==p['questions']
    assert 'no independent CFO/CEO approval' in views['relevant_history_obligations']['questions']['evidence_missing_for_permission']['instructions']
