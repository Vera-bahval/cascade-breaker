"""Representation adapters. These functions never invoke guards or classifiers."""
from copy import deepcopy
from experiments.local_guards_final_replay import p4
from experiments.local_guards_v4 import guard as frozen
from experiments.local_guards_v4_followup.replay import project_v41

METHODS = ('v1','v2','v3','v4','v4.2','v4.3','native','native_core','archive_ml','retrain_ml','v3_ml')


def archive_view(bundle):
    """Keep the frozen interchange and repair its evidence, not its features."""
    row=deepcopy(bundle['raw_input'])
    obs=row['observation']
    facts=obs.setdefault('facts',{})
    provenance=obs.setdefault('provenance',{})
    statuses=row.setdefault('evidence_status',{})
    mapping={'invoice_amount':'invoice_amount','invoice_status':'invoice_status',
             'vendor_status':'vendor_status','account':'vendor_account_token',
             'prior_completed_transfers':'prior_completed_transfers_observed'}
    for source,key in mapping.items():
        record=bundle['current'].get(source)
        if record is None:
            continue
        if not record['current'] or record['value'] is None:
            facts[key]=None
            provenance[key]=[]
            statuses[key]='unknown'
            continue
        facts[key]=record['value']
        status='instrumented' if record['origin']=='replay' else record['origin']
        provenance[key]=[{'field':key,'value':record['value'],'subject':record['subject'],
            'source_ref':record['source_ref'],'event_seq':record['event_seq'],'status':status,
            'kind':'declared_instrumentation' if record['origin']=='replay' else 'historical'}]
        statuses[key]=status
    if bundle.get('hold_events'):
        hold=bundle['hold_events'][-1]
        key='fraud_recommendation'
        facts[key]=hold['recommended_action']
        provenance[key]=[{'field':key,'value':facts[key],'subject':hold['subject'],
            'source_ref':hold['source_ref'],'event_seq':hold['event_seq'],'status':'observed','kind':'historical'}]
        statuses[key]='observed'
    # Preserve the old definitions of risk, text and history features, but do
    # not carry stale material observations past an opaque or broken prefix.
    material={'invoice_number','invoice_vendor_id','vendor_bank_details_present','vendor_trust_level',
              'vendor_risk_level','vendor_industry','vendor_total_invoices','vendor_invoice_history'}
    uncertain=[r['event_seq'] for r in bundle['invalidations'] if r['reason'] in
               {'opaque_write','unpaired_mutation','unresolved_mutation','incomplete_prefix'}]
    if uncertain:
        latest=max(uncertain)
        for key in material:
            observed=max((p['event_seq'] for p in provenance.get(key,[]) if type(p.get('event_seq')) is int),default=-1)
            if observed<=latest:
                facts[key]=None
                provenance[key]=[]
                statuses[key]='unknown'
    return row


def adapt(bundle, method):
    if method not in METHODS:
        raise ValueError('unknown method: '+method)
    if method in ('v1','v2'):
        state, prior, issues=p4.legacy_prefix(archive_view(bundle))
        return {'payload':{'state':state,'prior':prior},'applicable':not issues,
                'coverage':{'missing_legacy_operands':issues},'method':method}
    if method in ('native','native_core','archive_ml'):
        # This is the frozen archive interchange contract, not v4's fact schema.
        return {'payload':archive_view(bundle),'applicable':True,'method':method,
                'coverage':{'representation':'original_archive_interchange',
                            'ledger_sha256':bundle['input_sha256'],
                            **{key:{'representation':'typed_recommendation_and_raw_event' if key=='binding_hold' else
                                'archive_fact' if key in {'invoice_amount','invoice_status','vendor_status','account','prior_completed_transfers'} else
                                'raw_event_or_frozen_contract_unsupported', 'source_ref':record['source_ref']}
                               for key,record in bundle['current'].items()}}}
    if method=='v3_ml':
        from experiments.local_guards_v3 import prepare_data as original_text
        from .evidence import pair_events
        from experiments.local_guards_archive_comparison.collector import parse_result
        state=original_text.initial_state(bundle['initial'],bundle['raw_input'].get('raw_context',{}).get('initial_fixture'))
        state['invoice_id']=str(bundle['context']['invoice_id']) if bundle['context'].get('invoice_id') is not None else None
        state['vendor_id']=str(bundle['context']['vendor_id']) if bundle['context'].get('vendor_id') is not None else None
        for frame,event in pair_events(bundle['raw_input']['raw_context'].get('events',[]))[0]:
            if frame is None:
                continue
            tool=event.get('tool_name') or ''
            value=parse_result(event.get('tool_result'))
            original_text.consume_native(state,tool,event.get('tool_arguments') or {},value,event['event_seq'],source=event.get('tool_source'))
            if tool.startswith('delegate_to_') and isinstance(value,dict):
                state['agent']=str(value.get('task_summary') or '')
        payload=adapt(bundle,'v3')['payload']
        payload['untrusted_text']={'invoice':state['text'],'agent':state['agent']}
        return {'payload':payload,'applicable':True,'method':method,
                'coverage':{'text_recipe':'frozen prepare_data initial_state/consume_native and paired delegation summary'}}
    context=deepcopy(bundle['context'])
    # Context and proof versions have different origins. Never transplant the
    # version of another row or a later read into an earlier source proof.
    for kind in ('invoice','vendor'):
        context.pop(kind+'_version',None)
        version=bundle.get('versions',{}).get(kind)
        if version and version['current']:
            context[kind+'_version']=version['value']
    payload={'schema_version':4,'checkpoint':bundle['checkpoint'],'event_seq':bundle['event_seq'],
             'proposal':deepcopy(bundle['proposal']),'context':context,'facts':{},'provenance':{}}
    coverage={}
    requirements=frozen._REGISTRY['requirements']
    records=deepcopy(bundle['current'])
    if method=='v3' and bundle['baseline'].get('invoice_amount'):
        records['invoice_amount']=deepcopy(bundle['baseline']['invoice_amount'])
    for key,operand,proposed in (
        ('amount_matches_invoice','invoice_amount',payload['proposal'].get('amount')),
        ('recipient_matches_authorized','account',
         (bundle['raw_input'].get('raw_context',{}).get('proposed_action',{}).get('tool_arguments') or {}).get('vendor_account'))):
        # The old v3 compares with the earliest attributable amount/account.
        record=(bundle['baseline'] if method=='v3' else bundle['current']).get(operand)
        if (record and record.get('current') and proposed is not None
                and (record['value'] is not None or operand=='account' and method!='v3' and record.get('explicit_absence'))):
            value=(frozen._amount(record['value'])==frozen._amount(str(proposed))) if operand=='invoice_amount' else record['value']==proposed
            records[key]=dict(record,fact=key,value=value,origin='derived')
    for key in frozen._SCHEMA['properties']['facts']['properties']:
        record=records.get(key)
        if not record:
            coverage[key]={'status':'source_absent'}
            continue
        if not record['current']:
            coverage[key]={'status':'observed_but_stale','source_ref':record['source_ref'],
                           'reason':record['invalidated_reason']}
            continue
        value=record['value']
        if frozen._typed(key,value) is None:
            coverage[key]={'status':'observed_invalid_value','source_ref':record['source_ref']}
            continue
        payload['facts'][key]=value
        proof={k:record[k] for k in ('source','operation','event_seq','record_id','value')}
        proof.update(subject_matches=True)
        proof.update({k:v for k,v in context.items() if k in (
            'namespace','session_id','workflow_id','invoice_id','vendor_id','call_id')})
        proof.update(record.get('native_versions') or {})
        proof['evidence_kind']=record['evidence_kind']
        if record.get('source_call_id'):
            proof['source_call_id']=record['source_call_id']
        if record['evidence_kind']=='server_snapshot' and record.get('snapshot_id'):
            proof['snapshot_id']=record['snapshot_id']
        payload['provenance'][key]=[proof]
        gaps=[]
        if method in {'v4','v4.2','retrain_ml'}:
            gaps=[k for k in frozen._SCOPE if not frozen._nonempty(context.get(k))]
            if key in frozen._MATERIAL:
                gaps.extend(k for k in ('invoice_version','vendor_version')
                            if context.get('invoice_id' if k=='invoice_version' else 'vendor_id') is not None and (not context.get(k) or proof.get(k)!=context[k]))
        coverage[key]={'status':'represented','source_ref':record['source_ref'],
                       'frozen_contract_missing':gaps}
    if method=='v3':
        payload={k:payload[k] for k in ('checkpoint','event_seq','proposal','facts','provenance')}
        allowed=set(frozen._PAYMENT)
        payload['facts']={k:v for k,v in payload['facts'].items() if k in allowed}
        payload['provenance']={k:v for k,v in payload['provenance'].items() if k in allowed}
    elif method=='v4':
        payload=project_v41(payload)
    elif method=='v4.3':
        payload['repair_evidence']={'records':records,'source_input_sha256':bundle['input_sha256'],
                                    'actor_proof':bundle.get('actor_proof')}
    if method=='retrain_ml':
        payload={'observation':payload,'payment_baseline':adapt(bundle,'v3')['payload']}
    for key,item in coverage.items():
        item['requirements_at_checkpoint']=[r['id'] for r in requirements
            if key in r['facts'] and bundle['checkpoint'] in r['checkpoints']]
    return {'payload':payload,'applicable':True,'coverage':coverage,'method':method}
