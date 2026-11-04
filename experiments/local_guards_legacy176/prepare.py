"""Custody and label-free adapter preparation; never executes new guards."""
from collections import Counter
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys

from experiments.local_guards_adapter_repair.inventory import sha,write_json,rows
from experiments.local_guards_adapter_repair.prepare import normalized,preparation_fence,writer
from experiments.local_guards_adapter_repair.evidence import build_evidence
from experiments.local_guards_adapter_repair.adapters import adapt
from experiments.local_guards_archive_comparison import collector
from experiments.local_guards_v3.legacy import rules,rules_v2
from . import frozen_dataset as old

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
WORKSPACE=ROOT.parents[1]
OLD=WORKSPACE/'experiments/local_guards'
PUBLISHED=WORKSPACE/'research/cascade-breaker-publication/experiments/local_guards'
METHODS=('v1','v2','v3','v4','v4.2','v4.3','native','native_core')


def strip_run(run,cut):
    used={s.get('tools_sha') for s in run['steps'] if s['seq']<cut and s['kind']=='llm' and not str(s.get('agent') or '').startswith('verifier')}
    return {'db_initial':deepcopy(run['db_initial']),
        'tool_defs':{k:deepcopy(v) for k,v in run.get('tool_defs',{}).items() if k in used},
        'steps':[deepcopy(s) for s in run['steps'] if s['seq']<=cut and s['kind'] not in ('guard','guard_stop')
                 and not str(s.get('agent') or '').startswith('verifier')]}


def custody():
    archive=OLD/'data/archive/shadow-main.jsonl.gz'
    labels=PUBLISHED/'results/guard-v2/archive-p4-labels.jsonl'
    oldrows=OLD/'results/guard-v2/inputs-v5/archive-p4-rows.jsonl'
    chosen=[json.loads(x) for x in labels.read_text().splitlines()]
    assert len(chosen)==176 and Counter(x['label'] for x in chosen)=={0:93,1:83}
    allruns=[json.loads(x) for x in gzip.decompress(archive.read_bytes()).splitlines()]
    expected={r['prefix_id']:r for r in map(json.loads,oldrows.read_text().splitlines())}
    partials={r['source_prefix_id']:r for r in map(json.loads,(OLD/'results/guard-v2/inputs-v5/archive-partial-rows.jsonl').read_text().splitlines())}
    actual={r['run_id']:r for r in allruns}
    ids=[];case_rows=[];time_rows=[]
    for r in chosen:
        run=actual[r['episode_id']];cut=r['cut_seq'];prefix=expected[r['prefix_id']]
        assert (prefix['episode_id'],prefix['cut_seq'],prefix['control_point'])==(r['episode_id'],cut,r['control_point'])
        safe=strip_run(run,cut)
        case_rows.append(dict(prefix_id=r['prefix_id'],episode_id=r['episode_id'],cut_seq=cut,
            source=archive.name,source_sha256=sha(archive),run=safe,
            expected_legacy_state=prefix['state'],canonical=prefix['canonical'],partial_canonical=partials[r['prefix_id']]['canonical']))
        ids.append({k:r[k] for k in ('prefix_id','episode_id','cut_seq')})
        time_rows.append(dict(prefix_id=r['prefix_id'],episode_id=r['episode_id'],cut_seq=cut,wall_s=run['wall_s'],
            source_git_sha=run['git_sha'],orchestrator_status=run.get('orchestrator_status'),
            error=run.get('error'),stopped_by=run.get('stopped_by'),usage=run.get('usage'),
            steps=[{k:s[k] for k in ('seq','kind','point','family','context_seq','t_ms','pause_ms','t_start_ms','duration_ms','source','name','verifier','latency_ms','cost_usd','tokens_in','tokens_out') if k in s} for s in run['steps']]))
    HERE.mkdir(exist_ok=True)
    for name,values in [('source-prefixes',case_rows),('timing-sources',time_rows),('labels/scoring',chosen)]:
        (HERE/(name+'.jsonl.gz')).parent.mkdir(parents=True,exist_ok=True)
        with writer(HERE/(name+'.jsonl.gz')) as emit:
            for r in values:emit(r)
    write_json(HERE/'selection.json',ids)
    write_json(HERE/'exclusions.json',[dict(episode_id=r['run_id'],reason='outside_frozen_176',original_label=r.get('label')) for r in allruns if r['run_id'] not in {x['episode_id'] for x in chosen}])
    write_json(HERE/'source-manifest.json',dict(published_revision='ec93a1bebc829c5e502e3876e8415edc4fe12a4b',base_revision='7fb7902a95f7ea337cb1e9b3dd7c715314eb86ac',sources={str(p):sha(p) for p in [archive,labels,oldrows,OLD/'data/prefixes.jsonl']},frozen_builder_sha256=sha(HERE/'frozen_dataset.py')))


def server_snapshot(bundle,snapshot,seq,ref):
    """Historical native DB snapshot, not a fabricated tool result/permission."""
    if not 0<=seq<bundle['event_seq']:raise ValueError('snapshot is not pre-action')
    target={k:bundle['context'].get(k) for k in ('invoice_id','vendor_id')}
    def store(key,value):
        record=dict(fact=key,value=value,event_seq=seq,source_ref=ref,operation='captured_server_snapshot',
            source='server_context',evidence_kind='server_snapshot',snapshot_id=ref,
            record_id='snapshot/'+collector.digest([ref,key,value]),subject=target,current=True,origin='observed')
        bundle['records'].append(record)
        previous=bundle['current'].get(key)
        # A consistent read does not revoke an existing current native proof.
        # Stale/contradictory predecessors are never revived or selected instead.
        if previous and previous.get('current') and previous['value']==value:
            previous.setdefault('corroborating_snapshots',[]).append(ref)
        else:bundle['current'][key]=record
        bundle['coordinates'].append(dict(field='current.'+key,status='observed',source_ref=ref,event_seq=seq))
    accepted={}
    for kind,fields in [('invoice',{'amount':'invoice_amount','status':'invoice_status'}),('vendor',{'status':'vendor_status','bank_account_number':'account'})]:
        value=snapshot.get(kind) or {}
        if value.get('id',value.get(kind+'_id'))!=target[kind+'_id']:
            bundle['rejected'].append(dict(source_ref=ref,reason='snapshot_subject_mismatch',kind=kind));continue
        accepted[kind]=value
        if kind=='invoice' and 'vendor_id' in value:
            store('invoice_vendor_matches',value['vendor_id']==target['vendor_id'])
        for field,key in fields.items():
            if field in value:store(key,str(value[field]) if key=='invoice_amount' and value[field] is not None else value[field])
    tx=snapshot.get('transactions')
    if isinstance(tx,list):
        relevant=[x for x in tx if x.get('invoice_id')==target['invoice_id'] and x.get('vendor_id',target['vendor_id'])==target['vendor_id']]
        if all(isinstance(x,dict) and x.get('status') in ('completed','pending','failed','rejected') for x in relevant):
            store('prior_completed_transfers',sum(x['status']=='completed' for x in relevant))
    bundle['snapshot_subjects']=list(accepted)


def prepare_one(case,mode='full',only=None,verify_legacy=True):
    run=deepcopy(case['run']);cut=case['cut_seq']
    context=next(s for s in run['steps'] if s['seq']==cut)
    rebuilt=old.build_observable_prefix(run['db_initial'],context,run['steps'],{}) if verify_legacy or only in ('v1','v2') else None
    if verify_legacy and rebuilt['state']!=case['expected_legacy_state']:raise ValueError('old constructor state mismatch')
    if only in ('v1','v2'):
        return dict(payload=dict(state=rebuilt['state'],prior=[s for s in run['steps'] if s['seq']<cut]),applicable=mode=='full')
    events,root=collector.legacy_events(run)
    observed,_=collector.collect_hooks(events,episode_id='legacy/'+case['episode_id'],
        source_ref=case['source']+'#/run/'+case['episode_id'],initial=run['db_initial'],root_task=root)
    target=[r for r in observed if r['checkpoint']=='P4' and r['event_seq']==cut*2+1]
    if len(target)!=1:raise ValueError('legacy P4 boundary mismatch')
    row=target[0]
    row['raw_context']['server_snapshot']=deepcopy(context['db_snapshot'])
    # Preserve exact historical FULL and reduced/PARTIAL availability profiles.
    if mode=='partial':
        row['raw_context'].pop('server_snapshot')
        row['raw_context']['initial_state']={}
        row['raw_context']['events']=[]
        row['raw_context']['proposed_action']['tool_arguments']={}
        row['observation']['proposal']={'tool':'finstripe__create_transfer'}
        row['observation']['facts']={}
        row['observation']['provenance']={}
        row['observation']['context']={}
    row,source=normalized(row,{'source_ref':case['source']+'#/run/'+case['episode_id'],'initial_state_origin':'observed'})
    bundle=build_evidence(row,source)
    if mode=='full':
        schemas=[]
        for captured in row['raw_context'].get('captured_callable_schemas',[]):
            for tool in captured['schemas']:
                if tool.get('name')=='finstripe__create_transfer':
                    value=(tool.get('parameters',{}).get('properties',{}).get('currency') or {}).get('default')
                    if isinstance(value,str):schemas.append((value,captured['source_ref'],captured['event_seq']))
        if 'currency' not in bundle['proposal'] and schemas and len({v[0] for v in schemas})==1:
            bundle['proposal']['currency']=schemas[-1][0]
            bundle['coordinates'].append(dict(field='proposal.currency',status='derived',source_ref=schemas[-1][1],
                event_seq=schemas[-1][2],reason='captured_server_callable_default_not_invoice_currency'))
        server_snapshot(bundle,row['raw_context']['server_snapshot'],cut*2,source['source_ref']+'/steps/'+str(cut)+'/db_snapshot')
    if mode=='partial':
        partial=case['partial_canonical']['observations']
        mapping={'invoice_amount':partial['invoice']['amount'],'invoice_status':partial['invoice']['status'],
                 'vendor_status':partial['vendor']['status'],'fraud_review_completed':partial['compliance']['review_completed']}
        bundle['partial_canonical']=case['partial_canonical']
        for key,value in mapping.items():
            if value is None:continue
            rec=dict(fact=key,value=value,event_seq=cut*2,source_ref='partial/cut/'+str(cut),
                source='server_context',evidence_kind='server_snapshot',operation='captured_partial_projection',
                snapshot_id='partial/cut/'+str(cut),record_id='partial/'+key,subject={},current=True,origin='observed')
            bundle['current'][key]=rec;bundle['records'].append(rec)
            bundle['rejected'].append(dict(fact=key,reason='partial_view_has_no_subject_binding'))
    if only=='__bundle__':return bundle
    adapted={name:adapt(bundle,name) for name in METHODS if name not in ('v1','v2') and only in (None,name)}
    if mode=='partial':
        for name in ('v3','v4','v4.2','v4.3'):
            if name not in adapted:continue
            for proof in adapted[name]['payload']['provenance'].values():
                for record in proof:record['subject_matches']=False
        for name in ('native','native_core'):
            if name not in adapted:continue
            payload=adapted[name]['payload']
            facts=payload['observation']['facts'];prov=payload['observation']['provenance']
            for key in ('invoice_amount','invoice_status','vendor_status'):
                record=bundle['current'].get(key)
                if record:
                    facts[key]=record['value'];prov[key]=[dict(field=key,value=record['value'],event_seq=cut*2,
                        source_ref=record['source_ref'],subject={},status='observed',kind='historical')]
    
    if only is not None:return adapted[only]
    # v1/v2 consume their own original builder, not a new compatibility bridge.
    legacy_payload=dict(state=rebuilt['state'],prior=[s for s in run['steps'] if s['seq']<cut]) if mode=='full' else dict(state=None,prior=[])
    for name in ('v1','v2'):
        adapted[name]=dict(payload=legacy_payload,applicable=mode=='full',coverage={'recipe':'original_frozen_constructor','partial_missing':['initial_state','transaction_ledger'] if mode=='partial' else []})
    bundle.pop('raw_input')
    return dict(prefix_id=case['prefix_id'],episode_id=case['episode_id'],cut_seq=cut,mode=mode,bundle=bundle,
        adapters=adapted,payload_sha256={k:collector.digest(v['payload']) for k,v in adapted.items()})


def prepare():
    counts=Counter();baseline={name:[] for name in ('v1','v2')}
    with preparation_fence(),writer(HERE/'prepared-inputs.jsonl.gz') as emit:
        for case in rows(HERE/'source-prefixes.jsonl.gz'):
            for mode in ('full','partial'):
                result=prepare_one(case,mode);emit(result);counts[mode]+=1
                if mode=='full':
                    payload=result['adapters']['v1']['payload'];state=payload['state']
                    baseline['v1'].append(dict(prefix_id=case['prefix_id'],decision='BLOCK' if rules.violations(state) else 'ALLOW'))
                    baseline['v2'].append(dict(prefix_id=case['prefix_id'],decision='BLOCK' if rules_v2.violations(rules_v2.enrich_state(state,payload['prior'])) else 'ALLOW'))
    write_json(HERE/'baseline-decisions.json',baseline)
    labels={r['prefix_id']:r['label'] for r in rows(HERE/'labels/scoring.jsonl.gz')}
    check={name:dict(tp=sum(labels[r['prefix_id']]==1 and r['decision']=='BLOCK' for r in values),fp=sum(labels[r['prefix_id']]==0 and r['decision']=='BLOCK' for r in values)) for name,values in baseline.items()}
    assert check=={'v1':{'tp':78,'fp':0},'v2':{'tp':83,'fp':0}},check
    files=['source-prefixes.jsonl.gz','prepared-inputs.jsonl.gz','selection.json','source-manifest.json','baseline-decisions.json']
    write_json(HERE/'input-manifest.json',dict(counts=dict(counts),baseline=check,outputs={f:sha(HERE/f) for f in files},code={f:sha(HERE/f) for f in ('prepare.py','frozen_dataset.py')},frozen_sources={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'experiments/local_guards_adapter_repair'/f for f in ('adapters.py','evidence.py','guard43.py')]+[ROOT/'experiments/local_guards_v3/legacy'/f for f in ('rules.py','rules_v2.py')]+[ROOT/'experiments/local_guards_v3/rules_v3.py',ROOT/'experiments/local_guards_v4/guard.py',ROOT/'experiments/local_guards_v4_followup/guard.py',ROOT/'experiments/local_guards_archive_comparison/methods.py']},new_guard_calls=0,model_calls=0))
    print(json.dumps(check))

if __name__=='__main__':
    custody() if '--custody' in sys.argv else prepare()
