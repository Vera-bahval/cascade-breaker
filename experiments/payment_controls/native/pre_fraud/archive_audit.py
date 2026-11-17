"""Read-only historical PRE-Fraud inventory; no provider or current campaign imports."""
import argparse
import json,gzip,hashlib,sys
from pathlib import Path
from collections import Counter,defaultdict

ROOT=Path(__file__).resolve().parents[4]
cli=argparse.ArgumentParser(description=__doc__)
cli.add_argument('--raw-root',type=Path,default=ROOT.parent/'finbot-four-model-report')
cli.add_argument('--output',type=Path,default=Path(__file__).with_name('archive_summary.json'))
audit_options=cli.parse_args()
sys.path.insert(0,str(ROOT))
from experiments.local_guards_final_replay import early
from experiments.local_guards_archive_comparison.collector import parse_result

EXP=ROOT/'experiments'
inv=json.loads((EXP/'local_guards_adapter_repair/inventory.json').read_text())['early_episodes']
points=list(early.read_rows(EXP/'local_guards_final_replay/early-data/early-inputs.jsonl.gz'))
point_index={r['prefix_id']:r for r in points}
selected=json.loads((EXP/'local_guards_final_replay/early-data/id-map.private.json').read_text())
consensus=json.loads((EXP/'local_guards_final_replay/results/early/early-consensus.json').read_text())
split={r['episode_id']:r for r in early.read_rows(EXP/'local_guards_archive_comparison/data/split-episodes.jsonl.gz')}
reach={r['episode_id']:r['reach_status'] for r in early.read_rows(EXP/'local_guards_final_replay/early-data/early-events.jsonl.gz')}
groups=defaultdict(Counter)
counts=Counter()
features=defaultdict(Counter)
selection=Counter()
pre={}
raw_pre=set()
all_tool=Counter()
source_versions=Counter()
success=lambda v:not(isinstance(v,dict) and (v.get('error') or v.get('success') is False))

def dictionaries(v):
    if isinstance(v,dict):
        yield v
        for child in v.values():yield from dictionaries(child)
    elif isinstance(v,list):
        for child in v:yield from dictionaries(child)

for ep,journal,initial,member in early.raw_episodes(list(inv.values()),audit_options.raw_root):
    eid=ep['episode_id'];legacy=initial is not None
    events=early.legacy_events(journal) if legacy else early.native_events(journal)
    anchors=early.index_anchors(eid,events,legacy)
    firsts=sorted(((pid,a) for pid,a in anchors.items() if a['checkpoint']=='P1' and a['tool']=='delegate_to_fraud'),key=lambda x:x[1]['event_seq'])
    scope='legacy_injected' if legacy else 'native'
    if not legacy:
        source=split[eid]
        source_versions['verified' if source.get('verified_source_version') else 'declared_only' if source.get('source_version') else 'no_version']+=1
    counts['episodes_'+scope]+=1
    if not firsts:
        counts['no_pre_boundary_'+scope]+=1
        if any(e.get('tool_name')=='delegate_to_fraud' and e['hook_kind']=='after_tool' for e in events):counts['return_without_pre_'+scope]+=1
        continue
    raw_pre.add(eid)
    counts['all_pre_boundaries_'+scope]+=len(firsts)
    pid,a=firsts[0]
    counts['episodes_with_pre_'+scope]+=1
    if pid not in point_index:
        counts['first_pre_not_saved_'+scope]+=1
        continue
    cut=a['event_seq'];before=[e for e in events if e['event_seq']<cut]
    assert not any(e.get('tool_name')=='delegate_to_fraud' and e['hook_kind']=='after_tool' for e in before)
    args=a['event'].get('tool_arguments') or {}
    explicit_iid=args.get('invoice_id');vid=args.get('vendor_id')
    invoice_candidates={e.get('tool_arguments',{}).get('invoice_id') for e in before if e.get('tool_name') in ('get_invoice_details','get_invoice_for_payment','update_invoice_status') and e.get('tool_arguments',{}).get('invoice_id') is not None}
    iid=explicit_iid if explicit_iid is not None else next(iter(invoice_candidates)) if len(invoice_candidates)==1 else None
    record=dict(episode_id=eid,prefix_id=pid,cut=cut,scope=scope,group_id=split[eid]['group_id'],reach=reach[eid],executor=ep['executor'])
    pre[pid]=record
    counts['saved_first_pre_'+scope]+=1
    groups[scope][split[eid]['group_id']]+=1
    selection[scope+'|reach|'+reach[eid]]+=1
    selection[scope+'|executor|'+ep['executor']]+=1
    f=features[scope]
    f['n']+=1
    f['invoice_argument_bound']+=explicit_iid is not None
    f['invoice_target_bound_from_prior_unique_read']+=iid is not None
    f['invoice_target_ambiguous']+=iid is None
    record['invoice_id']=iid
    f['vendor_argument_bound']+=vid is not None
    invoice=[];vendor=[];history=[];risk=[];prior_money=[];paid_target=[];accounts=[];notes=[]
    for e in before:
        if e['hook_kind']!='after_tool':continue
        tool=e.get('tool_name');p=e.get('tool_arguments') or {};v=parse_result(e.get('tool_result'))
        if v is None or not success(v):continue
        all_tool[scope+'|'+str(tool)]+=1
        if tool in ('get_invoice_details','get_invoice_for_payment','update_invoice_status') and iid is not None and p.get('invoice_id')==iid and isinstance(v,dict):
            invoice.append((e,v))
            if v.get('status')=='paid':paid_target.append(e)
        if tool=='get_vendor_details' and vid is not None and p.get('vendor_id')==vid and isinstance(v,dict):
            vendor.append((e,v))
            if v.get('bank_account_number') is not None:accounts.append(v['bank_account_number'])
            if v.get('agent_notes'):notes.append(str(v['agent_notes']))
        if tool=='get_vendor_invoices' and vid is not None and p.get('vendor_id')==vid:
            history.append((e,v))
        if tool=='get_vendor_risk_profile' and vid is not None and p.get('vendor_id')==vid:risk.append((e,v))
        if tool=='finstripe__create_transfer' and iid is not None and p.get('invoice_id')==iid and isinstance(v,dict) and v.get('status')=='completed':prior_money.append(e)
    f['invoice_read_or_status_result']+=bool(invoice)
    f['invoice_amount']+=any('amount' in v and v['amount'] is not None for _,v in invoice)
    f['invoice_description']+=any(bool(v.get('description')) for _,v in invoice)
    f['invoice_number']+=any(bool(v.get('invoice_number')) for _,v in invoice)
    f['invoice_status']+=any(v.get('status') is not None for _,v in invoice)
    if invoice:f['invoice_status_value|'+str(invoice[-1][1].get('status'))]+=1
    f['vendor_details_read']+=bool(vendor)
    for key in ('status','trust_level','risk_level','services','bank_account_number','bank_account_holder_name'):
        f['vendor_'+key]+=any(v.get(key) is not None for _,v in vendor)
    f['vendor_notes_nonempty']+=bool(notes)
    f['history_read']+=bool(history)
    f['risk_profile_read']+=bool(risk)
    histories=[v for _,v in history]
    hitems=[d for v in histories for d in dictionaries(v) if 'amount' in d and 'status' in d]
    f['historical_invoice_rows_observed']+=bool(hitems)
    f['historical_paid_rows_observed']+=any(d.get('status')=='paid' and d.get('id')!=iid for d in hitems)
    f['target_paid_status_observed']+=bool(paid_target) or any(d.get('status')=='paid' and d.get('id')==iid for d in hitems)
    f['target_completed_transfer_observed']+=bool(prior_money)
    f['two_different_registered_accounts_observed']+=len(set(map(str,accounts)))>1
    import re
    f['bank_change_mention_only']+=any(re.search(r'bank.{0,40}chang|chang.{0,40}bank|new.{0,12}account',text,re.I) for text in notes)
    f['prior_fraud_return']+=any(e.get('tool_name')=='delegate_to_fraud' and e['hook_kind']=='after_tool' for e in before)
    # Later observations are counted as missing-at-PRE diagnostics only, never inputs.
    later=[e for e in events if e['event_seq']>cut and e['hook_kind']=='after_tool']
    f['history_first_seen_only_after_pre']+=(not history and any(e.get('tool_name')=='get_vendor_invoices' and parse_result(e.get('tool_result')) is not None and success(parse_result(e.get('tool_result'))) and (e.get('tool_arguments') or {}).get('vendor_id')==vid for e in later))
    record['read_tools_before_pre']=dict(Counter(e.get('tool_name') for e in before if e['hook_kind']=='after_tool'))

matches=[]
for row in selected:
    if row['prefix_id'] in pre:
        matches.append(dict(case_id=row['case_id'],label=consensus[row['case_id']]['label'],**pre[row['prefix_id']]))

# The saved adapter's pre-cut projection can carry initial-fixture facts even when no agent read them.
bundle_counts=defaultdict(Counter)
bundle_origins=defaultdict(Counter)
seen=set()
for path in sorted((EXP/'local_guards_adapter_repair/inputs').glob('early-inputs-*.jsonl.gz')):
    for row in early.read_rows(path):
        pid=row['prefix_id']
        if pid not in pre or row['mode']!='historical':continue
        assert pid not in seen;seen.add(pid)
        scope=pre[pid]['scope'];b=row['bundle'];c=b['current'];cut=b['event_seq']
        bundle_counts[scope]['n']+=1
        for field in ('invoice_amount','invoice_status','vendor_status','account','vendor_trust_level','vendor_risk_level','vendor_invoice_history','prior_completed_transfers','binding_hold'):
            r=c.get(field)
            if r and r.get('current') and isinstance(r.get('event_seq'),int) and r['event_seq']<cut:
                bundle_counts[scope][field]+=1
                bundle_origins[scope+'|'+field][str(r.get('source_ref','')).split('/coordinate/')[0]]+=1
                if field=='prior_completed_transfers':bundle_counts[scope]['prior_transfer_value|'+str(r.get('value'))]+=1
        bundle_counts[scope]['complete_prefix']+=bool(b.get('complete_prefix'))
        bundle_counts[scope]['history_complete']+=bool(b.get('history_complete'))

assert len(seen)==len(pre)==739
assert len(inv)==754 and len(points)==18676 and len(selected)==128
assert sum(groups['native'].values())==691 and len(groups['native'])==49
assert not matches
prior_origin_classes=Counter()
for ref,count in bundle_origins['native|prior_completed_transfers'].items():
    key=('deepseek_main_setup' if 'deepseek-main-batch-' in ref else
         'luna_main_setup' if 'luna-main-batch-' in ref else
         'deepseek_pilot_setup' if 'deepseek-additional-attempts' in ref else 'unclassified')
    prior_origin_classes[key]+=count
assert prior_origin_classes=={'deepseek_main_setup':46,'luna_main_setup':46,'deepseek_pilot_setup':2}
result=dict(counts=dict(counts),point_counts=dict(Counter(r['checkpoint'] for r in points)),
    unique_groups={k:len(v) for k,v in groups.items()},features={k:dict(v) for k,v in features.items()},
    coverage=dict(selection),successful_tool_counts_before_pre=dict(all_tool),early_128_exact_pre_matches=matches,
    early_128_matched_labels=dict(Counter(r['label'] for r in matches)),
    projection_fields={k:dict(v) for k,v in bundle_counts.items()},
    selected_pre_group_count=len({r['group_id'] for r in matches}),
    prior_transfer_setup_origin_classes=dict(prior_origin_classes),source_version_coverage=dict(source_versions),
    overall_128_labels=dict(Counter(row['label'] for row in consensus.values())),
    provider_calls=0,current_campaign_inputs_or_outcomes_read=False,excluded_closed_51=True,
    audit_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    adapter_inputs_sha256={path.name:hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((EXP/'local_guards_adapter_repair/inputs').glob('early-inputs-*.jsonl.gz'))},
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
        EXP/'local_guards_adapter_repair/inventory.json',EXP/'local_guards_final_replay/early-data/early-inputs.jsonl.gz',
        EXP/'local_guards_final_replay/early-data/id-map.private.json',EXP/'local_guards_final_replay/results/early/early-consensus.json',
        EXP/'local_guards_archive_comparison/data/split-episodes.jsonl.gz',EXP/'local_guards_archive_comparison/data/collector-manifest.json',
        EXP/'local_guards_final_replay/early.py']})
audit_options.output.parent.mkdir(parents=True,exist_ok=True)
audit_options.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
