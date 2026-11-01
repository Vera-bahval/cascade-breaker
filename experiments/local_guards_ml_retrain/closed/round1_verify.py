"""Embargoed focused author correction check; own files and authorized review only."""
from pathlib import Path
import json,gzip,hashlib,runpy
b=Path(__file__).resolve().parent.parent;old=b/'closed/pre-round1'
H=lambda d:hashlib.sha256(d).hexdigest()
J=lambda p:[json.loads(x) for x in gzip.decompress(p.read_bytes()).splitlines()]
obs=J(b/'closed/observations.jsonl.gz');og=J(old/'gold-actions.jsonl.gz');ng=J(b/'closed/gold-actions.jsonl.gz');om=J(old/'metadata.jsonl.gz');nm=J(b/'closed/metadata.jsonl.gz')
assert (b/'closed/observations.jsonl.gz').read_bytes()==(old/'observations.jsonl.gz').read_bytes()
expected_states={f'closed-state-{i:04d}' for i in (506,536,566,596)}
changed=[];slotchanges=[]
for a,z in zip(og,ng):
    assert a['prefix_id']==z['prefix_id']
    if a!=z:
        changed.append(a['prefix_id']);assert a['prefix_id'] in expected_states
        for k in ('payment_v3','A','B'):
            if a['labels'][k]!=z['labels'][k]:slotchanges.append({'prefix_id':a['prefix_id'],'contract':k,'before':a['labels'][k],'after':z['labels'][k]})
assert set(changed)==expected_states and len(slotchanges)==8
assert all(x['contract'] in ('A','B') and x['before']=='UNKNOWN' and x['after']=='ALLOW' for x in slotchanges)
meta_changes=[]
for a,z in zip(om,nm):
    if a!=z:
        copy=dict(a);copy.pop('policy_ambiguity');assert copy==z;meta_changes.append(a['prefix_id'])
assert len(meta_changes)==2
# This is the independent test author's source, not target guard/oracle/evaluation code.
g=runpy.run_path(str(b/'closed_author.py'),run_name='closed_author_regeneration_check')
assert g['rows']==obs and g['gold']==ng
for meta,row in zip(g['metas'],g['rows']):
    tool=row['observation'].get('proposal',{}).get('tool')
    if meta['family']=='state_transitions' and ((tool=='update_vendor_status' and meta['counterfactual_variant'] in (6,7)) or (tool=='update_vendor_risk' and meta['counterfactual_variant']==6)):
        meta['policy_ambiguity']='Missing mandatory native enum argument is interpreted UNKNOWN rather than a known invalid enum; reviewer adjudication required.'
    if meta['family']=='delegation_provenance' and meta['counterfactual_variant'] in (3,5,6,7):
        meta['policy_ambiguity']='Successful-completion/parent/call prose applied; registry does not exhaustively enumerate linkage fields.'
assert g['metas']==nm
rp=b/'closed-review.json';rb=rp.read_bytes();review=json.loads(rb)
adjudications=next(v for v in review.values() if isinstance(v,list) and len(v)==1200 and isinstance(v[0],dict) and 'independent' in v[0])
expected={r['prefix_id']:r['independent'] for r in adjudications}
assert all(r['labels']==expected[r['prefix_id']] for r in ng)
assert len(obs)==len(ng)==len(nm)==1200
assert len({x['episode_id'] for x in nm})==1200 and len({x['group_id'] for x in nm})==120
assert all(a[k]==z[k] for a,z in zip(om,nm) for k in ('group_id','episode_id','family','split','checkpoint','source'))
# Preserve intermediate receipts before incorporating this explicit focused review read.
lp=b/'closed-author-read-log.json';lb=lp.read_bytes();(b/'closed/round1-before-focused-read-log.json').write_bytes(lb)
log=json.loads(lb);log['reads'].append({'path':str(rp),'sha256':H(rb),'uses':['focused all-slot comparison against authorized independent policy adjudications after four-state correction']})
log['round1_focused_own_reads']=[{'path':str(p),'sha256':H(p.read_bytes()),'uses':['exact original/final diff, independent author-source regeneration and integrity check']} for p in [b/'closed_author.py',Path(__file__),b/'closed/observations.jsonl.gz',b/'closed/gold-actions.jsonl.gz',b/'closed/metadata.jsonl.gz',old/'gold-actions.jsonl.gz',old/'metadata.jsonl.gz']]
log['round1_failed_focused_check']='First focused byte-diff assertion found unnecessary rationale wording changes at unchanged checkpoints, before additional review reads or receipt writes. The intermediate authored draft is preserved in closed/round1-focused-draft; unchanged-cut rationale bytes were restored and focused check repeated.'
lp.write_text(json.dumps(log,indent=2)+'\n')
mp=b/'closed/manifest.json';mb=mp.read_bytes();(b/'closed/round1-before-focused-manifest.json').write_bytes(mb)
m=json.loads(mb);m['read_log_sha256']=H(lp.read_bytes());m['pre_prediction_review_correction']={'round':1,'original_test_seal_parent_reference':'ad77387','original_observations_sha256':H((old/'observations.jsonl.gz').read_bytes()),'original_gold_sha256':H((old/'gold-actions.jsonl.gz').read_bytes()),'label_slots_changed':8,'gold_states_changed':4,'metadata_annotations_changed':2,'observations_unchanged':True,'groups_splits_episodes_unchanged':True}
mp.write_bytes(g['canon'](m)+b'\n')
paths={'observations.jsonl.gz':b/'closed/observations.jsonl.gz','metadata.jsonl.gz':b/'closed/metadata.jsonl.gz','gold-actions.jsonl.gz':b/'closed/gold-actions.jsonl.gz','manifest.json':mp,'../closed_author.py':b/'closed_author.py','../closed-author-report.md':b/'closed-author-report.md','../closed-author-read-log.json':lp}
checks={'observations_identical':True,'gold_change_states_exact':4,'gold_change_slots_exact':8,'payment_baseline_labels_unchanged':True,'metadata_changes_only_removed_two_inaccurate_ambiguity_fields':True,'identifiers_splits_groups_episodes_unchanged':True,'source_regenerated_observations_gold_metadata_exact':True,'independent_policy_review_all_slots_match':True,'rows':1200,'families':10,'groups':120,'episodes':1200,'target_outputs_accessed':False}
receipt={'stage':'pre-prediction independent review correction round 1','original_test_seal_parent_reference':'ad77387','review_inputs':{'closed-review.md':'ac5097d62609489fb0e8ed953d9797103c98aa63949e3f7d651fe29979ddcdf4','closed-review.json':H(rb)},'original_hashes':{name:H((old/Path(name).name).read_bytes()) for name in paths},'final_hashes':{name:H(p.read_bytes()) for name,p in paths.items()},'label_changes':slotchanges,'metadata_annotation_changes':meta_changes,'focused_checks':checks}
cp=b/'closed/round1-correction.json';cp.write_text(json.dumps(receipt,indent=2)+'\n')
handoff={'status':'DONE','count':1200,'families':10,'per_family':120,'episodes':1200,'groups':120,'round':1,'source_read_compliance':True,'os_isolation_claim':False,'observations_unchanged':True,'groups_splits_episodes_unchanged':True,'metadata_wording_only_changed':True,'files':receipt['final_hashes']|{'round1-correction.json':H(cp.read_bytes()),'round1_verify.py':H(Path(__file__).read_bytes())}}
(b/'closed/handoff-label-blind.json').write_text(json.dumps(handoff,indent=2)+'\n')
print(json.dumps(handoff))
