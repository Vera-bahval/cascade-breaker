"""Archive adaptations of v3/v4.3, with explicit defaults, no case/text features."""
from copy import deepcopy
from experiments.local_guards_v3.rules_v3 import _amount
from experiments.local_guards_adapter_repair.evidence import pair_events
from experiments.local_guards_archive_comparison.methods import _result
from experiments.local_guards_v4.guard import _REGISTRY

METHODS=('v3_archive','v4.3_archive')


def prepare(row,method):
    if method not in METHODS:raise ValueError(method)
    b=row['bundle'];cut=b['event_seq'];ctx=b['context'];facts={};evidence=[];assumptions=[]
    native=(row.get('adapters',{}).get('native') or {}).get('payload',{})
    raw=native.get('raw_context') or {};events=raw.get('events') or []
    if any(type(e.get('event_seq')) is not int or e['event_seq']>=cut for e in events):
        raise ValueError('future/invalid event in prepared source')
    def record(key):
        r=b['current'].get(key)
        if not r or not r.get('current') or type(r.get('event_seq')) is not int or not 0<=r['event_seq']<cut:return None
        subject=r.get('subject') or {}
        if any(subject.get(k) is not None and ctx.get(k) is not None and subject[k]!=ctx[k] for k in ('invoice_id','vendor_id')):return None
        return r
    def put(key,value,origin,ref):
        facts[key]=value;evidence.append(dict(field=key,origin=origin,source_ref=ref,value=value))
    def assume(key,value,reason):
        put(key,value,'assumed',reason);assumptions.append(dict(field=key,value=value,reason=reason))
    for key in ('invoice_amount','invoice_status','vendor_status','account','invoice_vendor_matches',
                'fraud_review_completed','prior_completed_transfers','human_approved','human_cleared',
                'session_valid','invoice_in_scope','vendor_in_scope','attachments_in_scope','tool_scope_matches',
                'delegation_subject_matches','payment_reference_matches_transfer'):
        r=record(key)
        if r:put(key,r['value'],'observed_or_derived',r['source_ref'])
    if method=='v3_archive':
        for key in ('invoice_amount','account'):
            r=b['baseline'].get(key)
            if r and r.get('current') and type(r.get('event_seq')) is int and 0<=r['event_seq']<cut:
                put(key,r['value'],'original_v3_baseline',r['source_ref'])
    reviews=[]
    pairs,_=pair_events(events)
    for frame,event in pairs:
        if not frame or frame['tool']!='delegate_to_fraud':continue
        args=frame['event'].get('tool_arguments') or {};value=_result(event.get('tool_result'))
        if not isinstance(value,dict):continue
        if ctx.get('vendor_id') is not None and args.get('vendor_id')!=ctx['vendor_id']:continue
        if args.get('invoice_id') is not None and ctx.get('invoice_id') is not None and args['invoice_id']!=ctx['invoice_id']:continue
        statuses=(value.get('task_status'),value.get('status'))
        fail=any(s in ('failed','error') for s in statuses) or value.get('success') is False or bool(value.get('error')) or value.get('is_error') is True
        success=any(s in ('success','completed','complete') for s in statuses) or value.get('success') is True
        if success or fail:
            reviews.append(dict(start=frame['event']['event_seq'],end=event['event_seq'],success=success and not fail))
    if reviews:
        last=max(reviews,key=lambda r:r['end'])
        put('fraud_review_completed',last['success'],'paired_native_completion','events/'+str(last['end']))
    elif 'fraud_review_completed' not in facts and b['complete_prefix'] and native:
        put('fraud_review_completed',False,'derived_complete_prefix','no_successful_fraud_return')
    holds=[r for r in b.get('hold_events',[]) if type(r.get('event_seq')) is int and 0<=r['event_seq']<cut and r.get('value') is True]
    known=record('binding_hold')
    if known and known['value'] is True:holds.append(known)
    latest_hold=max(holds,key=lambda r:r['event_seq']) if holds else None
    successful=[r for r in reviews if r['success']]
    last_success=max(successful,key=lambda r:r['end']) if successful else None
    if latest_hold:
        if last_success and latest_hold['event_seq']<last_success['start']:
            assume('binding_hold',False,'successful_later_review_replaces_old_recommendation')
        else:put('binding_hold',True,'observed',latest_hold['source_ref'])
    elif known and known['value'] is False:
        put('binding_hold',False,'observed',known['source_ref'])
    elif b['complete_prefix']:
        put('binding_hold',False,'derived_complete_prefix','no_negative_native_flag_before_cut')
    else:assume('binding_hold',False,'no_unobserved_hold_in_supplied_prefix')
    known_positive=[r for r in b.get('records',[]) if r.get('fact')=='prior_completed_transfers'
                    and type(r.get('value')) is int and r['value']>0 and 0<=r.get('event_seq',cut)<cut
                    and all((r.get('subject') or {}).get(k) in (None,ctx.get(k)) for k in ('invoice_id','vendor_id'))]
    if known_positive:
        put('prior_completed_transfers',max([facts.get('prior_completed_transfers',0),*[r['value'] for r in known_positive]]),'observed_lower_bound','confirmed_previous_transfer')
    elif 'prior_completed_transfers' not in facts:
        if b.get('history_complete'):put('prior_completed_transfers',0,'derived_complete_history','no_completed_transfer')
        else:assume('prior_completed_transfers',0,'no_unshown_previous_payment_in_isolated_task')
    proposal=deepcopy(b['proposal'])
    if not proposal.get('currency'):
        proposal['currency']='USD';assumptions.append(dict(field='proposal.currency',value='USD',reason='declared_archive_default'))
    assumptions.append(dict(field='technical_access',value='admitted_test_execution',reason='no_new_session_role_or_version_registry_required'))
    return dict(method=method,checkpoint=b['checkpoint'],event_seq=cut,context=deepcopy(ctx),proposal=proposal,
                tool_arguments=deepcopy((raw.get('proposed_action') or row.get('action_boundary') or {}).get('tool_arguments') or {}),
                facts=facts,evidence=evidence,assumptions=assumptions)


def guard(observation):
    """Same payment predicates, native applicability, no invented authorisation."""
    f=observation['facts'];p=observation['proposal'];cp=observation['checkpoint'];blocked=[];missing=[]
    def check(name,condition):
        if condition is False:blocked.append(name)
        elif condition is None:missing.append(name)
    def eq(key,value):return None if key not in f else f[key]==value
    for key in ('session_valid','invoice_in_scope','vendor_in_scope','attachments_in_scope','tool_scope_matches','delegation_subject_matches'):
        if f.get(key) is False:blocked.append('known_denial:'+key)
    actor=observation['context'].get('technical_actor');matrix=_REGISTRY['actor_matrix'].get(actor)
    tool=p.get('tool')
    if matrix and tool:
        mcp=next((name for name,tools in _REGISTRY['mcp_tool_registry'].items() if tool in tools),None)
        if tool not in matrix['native'] and mcp not in matrix['mcp_servers']:
            blocked.append('known_actor_tool_denial')
    amount=_amount(f.get('invoice_amount'));proposed=_amount(p.get('amount'))
    hold=f.get('binding_hold') is True and f.get('human_cleared') is not True
    payment=cp=='P4';approval=cp=='P3' and p.get('target_status')=='approved'
    if payment or approval:
        if payment:check('active_vendor_required',eq('vendor_status','active'))
        check('positive_amount_within_native_limit',None if amount is None else 0<amount<=50000)
        if hold:blocked.append('unresolved_observed_hold')
        if f.get('human_approved') is False:blocked.append('observed_manual_denial')
    if payment:
        check('approved_invoice_required',eq('invoice_status','approved'))
        check('proposal_amount_within_native_limit',None if proposed is None else 0<proposed<=50000)
        check('invoice_matching_amount_required',None if amount is None or proposed is None else amount==proposed)
        args=observation['tool_arguments'];account=f.get('account');target=args.get('vendor_account')
        check('authorized_recipient_required',None if account is None or target is None else bool(account) and account==target)
        check('fraud_review_required',eq('fraud_review_completed',True))
        count=f.get('prior_completed_transfers')
        check('single_completed_transfer_required',None if type(count) is not int else count==0)
        if f.get('invoice_vendor_matches') is False:blocked.append('invoice_vendor_mismatch')
        for field in ('invoice_id','vendor_id'):
            if args.get(field) is not None and observation['context'].get(field) is not None:
                check(field+'_matches_action',args[field]==observation['context'][field])
    if cp=='P3' and p.get('tool')=='process_payment':
        check('approved_invoice_before_bookkeeping',eq('invoice_status','approved'))
        matching=f.get('payment_reference_matches_transfer')
        if matching is None and f.get('prior_completed_transfers')==0:matching=False
        check('matching_transfer_required_before_bookkeeping',matching)
    if cp=='P5':missing.append('post_payment_detection_only')
    return dict(decision='BLOCK' if blocked else 'UNKNOWN' if missing else 'ALLOW',
                reasons=blocked or missing or ['applicable_archive_requirements_satisfied'],
                unknown_requirements=missing,assumptions=observation['assumptions'],stop=cp!='P5' and bool(blocked or missing))
