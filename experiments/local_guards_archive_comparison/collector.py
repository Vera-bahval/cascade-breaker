"""Archive-only collector. Predictor facts come from initial fixtures and pre-cut events.

No inference client or previous detector is imported. Archive members are read in place;
no tar member is extracted to the filesystem. Final databases are evaluator-only.
"""
from __future__ import annotations
import argparse
import ast
import copy
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import tarfile
import subprocess

HERE = Path(__file__).resolve().parent
RAW_ROOT = Path('/Users/proskurin-dmi/Documents/hw-itmo/cascades/research/finbot-four-model-report')
LEGACY_ROOT = Path('/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/data/archive')
SCHEMA = json.loads((HERE / 'schema.json').read_text())
FIELDS = SCHEMA['properties']['observation']['properties']
NATIVE_REVISION = 'a7f6964fbc60da807e2544d826a5b4e20eb0c5dc'
INVOICE_TOOLS = {'get_invoice_details', 'get_invoice_for_payment', 'update_invoice_status', 'update_invoice_agent_notes', 'flag_invoice_for_review', 'process_payment', 'update_payment_agent_notes'}
VENDOR_TOOLS = {'get_vendor_details', 'get_vendor_risk_profile', 'get_vendor_contact_info', 'update_vendor_status', 'update_vendor_risk', 'update_vendor_agent_notes', 'update_fraud_agent_notes'}


def canonical(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def decimal(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        n = Decimal(str(x))
        return format(n.normalize(), 'f') if n.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def integer(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        return int(x) if str(int(x)) == str(x) else None
    except (TypeError, ValueError):
        return None


def parse_result(x):
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except (ValueError, TypeError):
            try:
                x = ast.literal_eval(x)
            except (ValueError, SyntaxError, TypeError, RecursionError):
                return None
    def clean(v):
        if v is None or isinstance(v, (str, bool, int)):
            return v
        if isinstance(v, float) and math.isfinite(v):
            return v
        if isinstance(v, (tuple, list)):
            return [clean(y) for y in v]
        if isinstance(v, dict) and all(isinstance(k, str) for k in v):
            return {k: clean(y) for k, y in v.items()}
        raise ValueError()
    try:
        return clean(x)
    except (ValueError, RecursionError):
        return None


def token(x):
    return 'account/' + digest(str(x))[:24] if x is not None else None


def source_event(source_ref, line, pointer=''):
    return f'{source_ref}#L{line}{pointer}'


def evidence(ref, seq, field, value, subject, *, status='observed', kind='historical', derived_from=None, note=None, call_id=None):
    result = dict(source_ref=ref, event_seq=seq, status=status, kind=kind, subject=subject, field=field, value=value)
    if derived_from:
        result['derived_from'] = derived_from
    if note:
        result['note'] = note
    if call_id:
        result['source_call_id'] = call_id
    return result


def compact_event(row, seq):
    """Remove envelope/provider/boilerplate only. Never truncate source content."""
    keep = ('hook_kind', 'tool_name', 'tool_source', 'tool_arguments', 'tool_result', 'user_message', 'model_output', 'request_tools', 'source_event_kind')
    result = {k: row[k] for k in keep if row.get(k) is not None}
    result['event_seq'] = seq
    return result


def collect_hooks(rows, *, episode_id, source_ref, initial=None, fixture=None, source_version=None, namespace=None, root_task=None, fixture_ref=None, source_revision_ref=None):
    facts = {k: None for k in FIELDS['facts']['properties']}
    provenance = {k: [] for k in facts}
    context = {k: None for k in FIELDS['context']['properties']}
    context['source_refs'] = [source_ref]
    context['source_binding'] = 'captured_raw_prefix'
    context['native_revision'] = source_version
    context['native_policy_hash'] = file_hash(HERE / 'policy.json')
    context['namespace_token'] = namespace
    initial = copy.deepcopy(initial or {})
    fixture = copy.deepcopy(fixture or {})
    invoice = initial.get('invoice') or {}
    vendor = initial.get('vendor') or {}
    iid = integer(invoice.get('id'))
    vid = integer(vendor.get('id', invoice.get('vendor_id')))
    root_message = root_task or next((r.get('user_message') for r in rows if r.get('user_message')), '')
    for name, current in [('invoice_id', iid), ('vendor_id', vid)]:
        m = re.search(r'\b' + name + r'\s*[:=]\s*(\d+)', root_message or '')
        if current is None and m:
            if name == 'invoice_id': iid = int(m[1])
            else: vid = int(m[1])
    context.update(invoice_id=iid, vendor_id=vid, current_vendor_id=vid)
    if 'new invoice' in (root_message or '').lower() or 're-process' in (root_message or '').lower():
        context['task_recipe'] = 'invoice_processing'
    context['workflow_id'] = next((r.get('workflow_id') for r in rows if r.get('workflow_id')), None)
    raw = {'initial_fixture': {k: v for k, v in fixture.items() if k in ('amount','desc','description','due_date_offset_days')}, 'initial_state': initial, 'events': []}
    untrusted = []
    subject = lambda: {'invoice_id': iid, 'vendor_id': vid}

    def put(key, value, ref, seq, *, status='observed', inputs=None, note=None):
        if value is None:
            return
        facts[key] = value
        provenance[key] = [evidence(ref, seq, key, value, subject(), status=status,
            kind='deterministic_reconstruction' if status == 'derived' else 'historical', derived_from=inputs, note=note)]

    def clear(key, ref, seq, note):
        facts[key]=None
        provenance[key]=[evidence(ref,seq,key,None,subject(),status='unknown',kind='unknown',note=note)]

    def append_history(key, value, ref, seq):
        prior = facts[key] or []
        put(key, prior + [dict(source_ref=ref, event_seq=seq, **value)], ref, seq, status='derived', inputs=list(dict.fromkeys([x['source_ref'] for x in prior]+[ref])))

    def ingest(tool, args, result, ref, seq, actor, native=True):
        nonlocal iid, vid
        value = parse_result(result)
        if not isinstance(value, dict) or value.get('error') or value.get('updated') is False or not native:
            return
        if tool in INVOICE_TOOLS:
            actual = integer(value.get('invoice_id', value.get('id', args.get('invoice_id'))))
            requested = integer(args.get('invoice_id'))
            if iid is None and actual is not None:
                iid = actual
                context['invoice_id'] = iid
            if actual != iid or (requested is not None and requested != iid):
                return
            if namespace is not None and value.get('namespace') is not None and value['namespace']!=namespace:
                put('invoice_in_namespace',False,ref,seq,status='derived',inputs=[ref],note='Foreign namespace result not used as current invoice state.')
                return
            new_vendor = integer(value.get('vendor_id'))
            if new_vendor is not None:
                if vid is not None and vid != new_vendor:
                    # The latest invoice relationship changes the relevant vendor;
                    # do not retain a previous vendor's bank/status as current.
                    for key in facts:
                        if key.startswith('vendor_'):
                            facts[key], provenance[key] = None, []
                vid = new_vendor
                context.update(vendor_id=vid)
                put('invoice_vendor_id', vid, ref, seq)
            for field, native_field in [('invoice_amount','amount'),('invoice_status','status'),('invoice_number','invoice_number')]:
                if native_field in value:
                    parsed=decimal(value[native_field]) if native_field == 'amount' else value[native_field]
                    if parsed is None:clear(field,ref,seq,'Latest native field is null or invalid; older value not retained.')
                    else:put(field,parsed,ref,seq)
            if value.get('vendor_status') is not None:
                put('vendor_status',value['vendor_status'],ref,seq)
            if value.get('vendor_bank_account_number') is not None:
                put('vendor_account_token',token(value['vendor_bank_account_number']),ref,seq,status='derived',inputs=[ref])
                put('vendor_bank_details_present',bool(value['vendor_bank_account_number']),ref,seq,status='derived',inputs=[ref])
            actual_ns = value.get('namespace')
            if actual_ns is not None and namespace is not None:
                put('invoice_in_namespace', actual_ns == namespace, ref, seq,status='derived',inputs=[ref])
            if tool == 'flag_invoice_for_review':
                rec = args.get('recommended_action', value.get('recommended_action'))
                put('fraud_recommendation', rec, ref, seq)
                append_history('fraud_review_history', {'tool':tool,'arguments':args,'result':value,'actor':actor},ref,seq)
            if tool in {'update_invoice_status','update_invoice_agent_notes'} and actor in ('invoice','invoice_agent'):
                put('invoice_agent_decision',value.get('status',args.get('status')),ref,seq)
                append_history('invoice_review_history',{'tool':tool,'arguments':args,'result':value,'actor':actor},ref,seq)
        if tool in VENDOR_TOOLS:
            actual = integer(value.get('vendor_id', value.get('id',args.get('vendor_id'))))
            if vid is None or actual != vid or (args.get('vendor_id') is not None and integer(args['vendor_id']) != vid):
                return
            if namespace is not None and value.get('namespace') is not None and value['namespace']!=namespace:
                put('vendor_in_namespace',False,ref,seq,status='derived',inputs=[ref],note='Foreign namespace result not used as current vendor state.')
                return
            for field,native_field in [('vendor_status','status'),('vendor_trust_level','trust_level'),('vendor_risk_level','risk_level'),('vendor_industry','industry'),('vendor_total_invoices','total_invoices')]:
                if native_field in value:
                    if value[native_field] is None:clear(field,ref,seq,'Latest native field explicitly null.')
                    else:put(field,value[native_field],ref,seq)
            if 'bank_account_number' in value:
                if value['bank_account_number'] is None:clear('vendor_account_token',ref,seq,'Latest native bank account explicitly absent.')
                else:put('vendor_account_token',token(value['bank_account_number']),ref,seq,status='derived',inputs=[ref])
                put('vendor_bank_details_present',bool(value['bank_account_number']),ref,seq,status='derived',inputs=[ref])
            if value.get('namespace') is not None and namespace is not None:
                put('vendor_in_namespace', value['namespace']==namespace,ref,seq,status='derived',inputs=[ref])
            if tool == 'update_fraud_agent_notes':
                append_history('fraud_review_history',{'tool':tool,'arguments':args,'result':value,'actor':actor},ref,seq)
        if tool == 'get_vendor_invoices' and integer(args.get('vendor_id')) == vid:
            history = value.get('invoices')
            put('vendor_total_invoices',value.get('total_invoices'),ref,seq)
            if isinstance(history,list):
                for i,v in enumerate(history):
                    if isinstance(v,dict) and integer(v.get('invoice_id',v.get('id'))) == iid:
                        ingest('get_invoice_details',{'invoice_id':iid},v,ref+f'/invoices/{i}',seq,actor,native)
                put('vendor_invoice_history',[dict(source_ref=ref,event_seq=seq,**v) for v in history if isinstance(v,dict)],ref,seq)
        if tool == 'finstripe__create_transfer' and integer(args.get('invoice_id')) == iid and value.get('status') == 'completed':
            history = facts['transfer_history'] or []
            transfer_id=value.get('transfer_id',value.get('id'))
            if not any(x.get('result',{}).get('transfer_id',x.get('result',{}).get('id')) == transfer_id for x in history):
                append_history('transfer_history',{'arguments':args,'result':value},ref,seq)
                put('prior_completed_transfers_observed',len(facts['transfer_history']),ref,seq,status='derived',inputs=[ref],note='Observed count; not a complete-zero-history assertion.')

    initial_ref = fixture_ref or source_ref + '#/db_initial'
    if invoice:
        ingest('get_invoice_details',{'invoice_id':iid},dict(invoice,invoice_id=iid),initial_ref,0,'initial')
    if vendor:
        ingest('get_vendor_details',{'vendor_id':vid},dict(vendor,vendor_id=vid),initial_ref,0,'initial')
    if not invoice and fixture.get('amount') is not None:
        put('invoice_amount',decimal(fixture['amount']),initial_ref,0)
    if initial.get('transactions') is not None:
        # Full initial collection, if captured. Later opaque writes invalidate it.
        transactions=initial['transactions']
        put('transfer_history',[dict(source_ref=initial_ref,event_seq=0,result=x) for x in transactions],initial_ref,0)
        put('prior_completed_transfers_observed',sum(x.get('status')=='completed' for x in transactions),initial_ref,0,status='derived',inputs=[initial_ref])
    description=invoice.get('description',fixture.get('desc',fixture.get('description')))
    if description is not None:
        untrusted.append(dict(source_ref=initial_ref,text=str(description),role='invoice_description'))
    pending=[]
    stack=['orchestrator']
    journal_ok=bool(rows and rows[0].get('hook_kind')=='before_model')
    outputs=[]
    linkage=[]
    model_pending=0

    def emit(point, seq, tool, args, ref, line, completed=None, frame=None):
        obs=dict(proposal={k:None for k in FIELDS['proposal']['properties']}, facts=copy.deepcopy(facts), provenance=copy.deepcopy(provenance), context=copy.deepcopy(context),untrusted_text=copy.deepcopy(untrusted))
        boundary_actor=(frame['actor'] if frame else None) if point=='P2_afterFraud' else stack[-1]
        obs['context'].update(actor=boundary_actor,prefix_complete=journal_ok,call_id=frame['ref'] if frame else ref,subject_binding='root_task_and_causally_paired_tool_arguments')
        if point=='P2_afterFraud':
            obs['context']['delegated_actor']='fraud'
            obs['facts']['fraud_delegate_completed']=completed
            obs['provenance']['fraud_delegate_completed']=[]
            if completed is not None:
                obs['provenance']['fraud_delegate_completed']=[evidence(ref,seq,'fraud_delegate_completed',completed,subject(),status='derived',kind='deterministic_reconstruction',derived_from=[frame['ref'],ref])]
        p=obs['proposal']
        p.update(tool=tool,amount=decimal(args.get('amount')),currency=args.get('currency'),payment_method=args.get('payment_method'),invoice_reference=args.get('invoice_reference',args.get('reference')),vendor_account_token=token(args.get('vendor_account',args.get('bank_account'))),target_status=args.get('status'),payment_reference=args.get('payment_reference'),invoice_id=integer(args.get('invoice_id')),vendor_id=integer(args.get('vendor_id')))
        if tool=='finstripe__create_transfer' and p['currency'] is None and source_version == NATIVE_REVISION:
            p['currency']='usd'
            obs['provenance']['proposal.currency']=[evidence('git:'+NATIVE_REVISION+':finstripe:create_transfer:currency-default',seq,'proposal.currency','usd',subject(),status='derived',kind='deterministic_reconstruction',derived_from=[ref],note='Callable default only, not invoice currency or USD-only policy.')]
        if point=='P4' and obs['facts']['fraud_delegate_completed'] is None and journal_ok and context['task_recipe']=='invoice_processing':
            obs['facts']['fraud_delegate_completed']=False
            obs['provenance']['fraud_delegate_completed']=[evidence(ref,seq,'fraud_delegate_completed',False,subject(),status='derived',kind='deterministic_reconstruction',derived_from=[source_ref+'#L1',ref],note='No paired successful same-subject Fraud delegation in complete observed prefix.')]
        proposal_derived=bool(rows[line-1].get('_derived_before_tool'))
        for k,v in p.items():
            if not obs['provenance'].get('proposal.'+k):
                obs['provenance']['proposal.'+k]=[evidence(ref,seq,'proposal.'+k,v,subject(),status=('derived' if proposal_derived else 'observed') if v is not None else 'unknown',kind=('deterministic_reconstruction' if proposal_derived else 'historical') if v is not None else 'unknown',derived_from=[ref] if proposal_derived else None,note='Proposed tool call from recorded model output; no fabricated historical callback.' if proposal_derived else None)]
        for k,v in obs['facts'].items():
            if not obs['provenance'].get(k):
                obs['provenance'][k]=[evidence(ref,seq,k,v,subject(),status='unknown',kind='unknown',note='Unavailable at cut; absence is not a false fact.')]
        for k,v in obs['context'].items():
            key='context.'+k
            origin_ref=source_revision_ref if k=='native_revision' and source_revision_ref else ref
            status_context='unknown' if v is None else 'derived' if k in ('actor','prefix_complete','subject_binding','task_recipe','invoice_id','vendor_id','current_vendor_id','native_policy_hash') else 'observed'
            obs['provenance'][key]=[evidence(origin_ref,seq,key,v,subject(),status=status_context,kind='unknown' if status_context=='unknown' else 'deterministic_reconstruction' if status_context=='derived' else 'historical',derived_from=[source_ref+'#L1',ref] if status_context=='derived' else None)]
        status={k:(obs['provenance'][k][-1]['status'] if obs['provenance'].get(k) else 'unknown') for k in obs['facts']}
        status.update({'proposal.'+k:obs['provenance']['proposal.'+k][-1]['status'] for k in p})
        status.update({'context.'+k:obs['provenance']['context.'+k][-1]['status'] for k in obs['context']})
        join_seq=rows[line-1].get('_original_hash_seq',seq)
        prefix_id=hashlib.sha256(f'{episode_id}/{join_seq}/{tool}'.encode()).hexdigest()[:28]
        raw_at_cut=copy.deepcopy(raw)
        if point=='P4':raw_at_cut['proposed_action']={'tool_name':tool,'tool_arguments':copy.deepcopy(args),'event_seq':seq,'source_ref':ref,'origin_kind':'deterministic_reconstruction' if proposal_derived else 'historical','source_event_kind':'recorded_model_proposal' if proposal_derived else 'before_tool_hook'}
        outputs.append(dict(prefix_id=prefix_id,episode_id=episode_id,checkpoint=point,event_seq=seq,observation=obs,raw_context=raw_at_cut,evidence_status=status,mode='reconstructed_state'))
        linkage.append(dict(prefix_id=prefix_id,source_ref=ref,source_event_index=rows[line-1].get('_source_line',line),task_admission_ref=source_ref+'#L1',call_source_ref=frame['ref'] if frame else ref,actor_stack=list(stack),paired_return=point=='P2_afterFraud' and frame is not None))

    for line,row in enumerate(rows,1):
        seq=row.get('_event_seq',line*2)
        ref=source_ref+row['_source_pointer'] if row.get('_source_pointer') else source_event(source_ref,row.get('_source_line',line))
        kind=row.get('hook_kind');tool=str(row.get('tool_name') or '');args=row.get('tool_arguments') or {}
        if not isinstance(args,dict): args={}
        if kind=='before_model':
            if model_pending:journal_ok=False
            model_pending+=1
        elif kind=='after_model':
            if model_pending!=1:journal_ok=False
            model_pending=max(0,model_pending-1)
        if kind=='before_tool' and tool=='finstripe__create_transfer':
            # Proposal is present; the call and its eventual result are excluded.
            emit('P4',seq,tool,args,ref,line)
        if kind in ('before_model','after_model','before_tool','after_tool'):
            schemas=row.get('request_tool_schemas')
            if schemas is not None:
                captured=raw.setdefault('captured_callable_schemas',[])
                schema_hash=digest(schemas)
                if not any(x['sha256']==schema_hash for x in captured):
                    captured.append(dict(event_seq=seq,source_ref=ref,sha256=schema_hash,schemas=copy.deepcopy(schemas)))
            item=compact_event(row,seq)
            # Identical message copies are references, not silently discarded text.
            if item.get('user_message') is not None:
                previous=next((x for x in raw['events'] if x.get('user_message')==item['user_message']),None)
                if previous is not None:
                    item.pop('user_message');item['user_message_same_as_event_seq']=previous['event_seq']
            raw['events'].append(item)
        if kind=='before_tool':
            if tool!='complete_task':
                pending.append(dict(tool=tool,args=args,ref=ref,invoice_id=integer(args.get('invoice_id',iid)),vendor_id=integer(args.get('vendor_id',vid)),actor=stack[-1],session_id=row.get('session_id'),workflow_id=row.get('workflow_id'),batch_ref=row.get('_legacy_batch_ref'),source_call_id=row.get('_source_call_id',row.get('tool_call_id',row.get('call_id')))))
            if tool.startswith('delegate_to_'):
                stack.append(tool.removeprefix('delegate_to_'))
        elif kind=='after_tool':
            return_call_id=row.get('_source_call_id',row.get('tool_call_id',row.get('call_id')))
            return_actor=str(row.get('agent_name') or '').removesuffix('_agent') or None
            def matches(candidate):
                return (candidate['tool']==tool and canonical(candidate['args'])==canonical(args)
                    and all(candidate.get(k) is None or row.get(k) is None or candidate[k]==row[k] for k in ('session_id','workflow_id'))
                    and (return_actor is None or candidate['actor']==return_actor)
                    and (return_call_id is None or candidate.get('source_call_id')==return_call_id))
            pair_index=None
            for index in range(len(pending)-1,-1,-1):
                candidate=pending[index]
                if not matches(candidate):continue
                batch=candidate.get('batch_ref')
                if batch is not None:
                    # A saved model batch is a proposal set, not parallel dispatch.
                    # Actual return order supplies state chronology. Missing IDs
                    # require a unique exact call within this recorded batch.
                    matching=[p for p in pending if p.get('batch_ref')==batch and matches(p)]
                    if len(matching)!=1:continue
                if index==len(pending)-1 or (batch is not None and not tool.startswith('delegate_to_')
                    and all(p.get('batch_ref')==batch and not p['tool'].startswith('delegate_to_') for p in pending[index:])):
                    pair_index=index;break
            paired=pair_index is not None
            frame=pending.pop(pair_index) if paired else None
            if not paired and tool!='complete_task': journal_ok=False
            value=parse_result(row.get('tool_result'))
            if tool.startswith('delegate_to_'):
                target=tool.removeprefix('delegate_to_')
                if isinstance(value,dict):
                    history='fraud_review_history' if target=='fraud' else 'invoice_review_history' if target=='invoice' else None
                    if history and frame and frame['invoice_id']==iid and frame['vendor_id']==vid:
                        append_history(history,{'tool':tool,'arguments':args,'result':value,'actor':target},ref,seq)
                if target=='fraud':
                    completed=None
                    if frame and frame['invoice_id']==iid and frame['vendor_id']==vid and isinstance(value,dict):
                        status=value.get('task_status')
                        completed=True if status=='success' else False if status in ('failed','error') or value.get('error') else None
                        put('fraud_delegate_completed',completed,ref,seq,status='derived',inputs=[frame['ref'],ref])
                    emit('P2_afterFraud',seq+1,tool,args,ref,line,completed,frame)
                if len(stack)>1 and stack[-1]==target: stack.pop()
            else:
                if paired:
                    ingest(tool,args,value,ref,seq,row.get('agent_name') or stack[-1],row.get('tool_source','native')=='native' or tool=='finstripe__create_transfer')
                if paired and tool=='systemutils__execute_script':
                    journal_ok=False
                    for k in facts:
                        if k.startswith(('invoice_','vendor_','prior_completed','transfer_history')):
                            facts[k],provenance[k]=None,[]
        # Failed native calls remain in raw context, never become state.
    return outputs,linkage


def legacy_events(run):
    """Normalize old shadow events without verifier decisions or future snapshots.

    Use guard_context as the exact callback cut where present; otherwise a saved
    model tool call records its proposed native invocation before the result.
    """
    result=[]
    root_task=None
    steps=sorted(run.get('steps',[]),key=lambda x:x['seq'])
    for index,step in enumerate(steps):
        seq=step['seq'];kind=step['kind']
        if kind=='llm' and not str(step.get('agent','')).startswith('verifier'):
            messages=[m.get('content') for m in step.get('messages',[]) if m.get('role')=='user']
            if root_task is None and messages:root_task=messages[0]
            result.append(dict(hook_kind='before_model',user_message='\n\n'.join(str(m) for m in messages),request_tools=step.get('tools'),request_tool_schemas=run.get('tool_defs',{}).get(step.get('tools_sha')),_event_seq=seq*2,_source_line=seq))
            output=step.get('output') or {}
            result.append(dict(hook_kind='after_model',model_output=output,_event_seq=seq*2+1,_source_line=seq))
            for call_index,call in enumerate(output.get('tool_calls',[]) if isinstance(output,dict) else []):
                tool=call.get('name');args=call.get('arguments') or {}
                upcoming=[]
                for later in steps[index+1:]:
                    if later['kind']=='tool' and later.get('name')==tool:break
                    if later['kind']=='guard_context':upcoming.append(later)
                has_callback=any((x.get('payload') or {}).get('tool')==tool and canonical((x.get('payload') or {}).get('arguments') or {})==canonical(args) for x in upcoming)
                if not has_callback:
                    result.append(dict(hook_kind='before_tool',tool_name=tool,tool_arguments=args,_event_seq=seq*2+1,_source_line=seq,_original_hash_seq=seq*2+1,_derived_before_tool=True,_source_pointer=f'/steps/{index}/output/tool_calls/{call_index}',_legacy_batch_ref=f'/steps/{index}/output',_source_call_id=call.get('call_id',call.get('id')),source_event_kind='recorded_model_proposal'))
        elif kind=='guard_context':
            payload=step.get('payload') or {};tool=payload.get('tool')
            if tool:
                result.append(dict(hook_kind='before_tool',tool_name=tool,tool_arguments=payload.get('arguments') or {},_event_seq=seq*2+1,_source_line=seq,_original_hash_seq=seq*2+1))
        elif kind=='tool':
            original_hash_seq=None
            if step.get('name')=='delegate_to_fraud':
                follow=next((x for x in steps[index+1:] if x['kind'] in ('guard_context','tool')),None)
                if follow and follow.get('point')=='P2.fraud_agent':original_hash_seq=follow['seq']*2+1
            result.append(dict(hook_kind='after_tool',tool_name=step.get('name'),tool_arguments=step.get('arguments') or {},tool_result=step.get('output') if not step.get('error') else {'error':step['error']},tool_source=step.get('source','native'),agent_name=step.get('agent'),_source_call_id=step.get('call_id',step.get('tool_call_id')),_event_seq=seq*2,_source_line=seq,**({'_original_hash_seq':original_hash_seq} if original_hash_seq is not None else {})))
    index_by_seq={step['seq']:i for i,step in enumerate(steps)}
    for row in result:
        row.setdefault('_source_pointer','/steps/'+str(index_by_seq[row['_source_line']] ))
    return result,root_task


def read_jsonl(path):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt') as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as base:
        with gzip.GzipFile(filename='',mode='wb',fileobj=base,mtime=0,compresslevel=1) as z:
            for row in rows: z.write((canonical(row)+'\n').encode())


def resolve_source(source):
    p=Path(source)
    candidates=[p] if p.is_absolute() else [RAW_ROOT/p]
    if p.name=='shadow-main.jsonl.gz':candidates.append(LEGACY_ROOT/p.name)
    # Additional verified raw roots can be supplied explicitly, not guessed from cwd.
    candidates.extend(root/p.name for root in EXTRA_ROOTS)
    return next((x.resolve() for x in candidates if x.is_file()),None)


EXTRA_ROOTS=[]


def tar_members(path,read_log):
    wanted={}
    with tarfile.open(path,'r:gz') as t:
        for member in t:
            name=member.name
            if not member.isfile():continue
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError('Unsafe archive member: '+name)
            relevant=(name.endswith(('.hooks.jsonl','/hooks.jsonl','/job.json','/scenarios.json')) or bool(re.search(r'/scenarios_[^/]+\.json$',name)))
            if relevant:
                data=t.extractfile(member).read();wanted[name]=data
                read_log.append(dict(source=str(path),member=name,sha256=hashlib.sha256(data).hexdigest(),role='raw_prefix_or_initial_scenario'))
    return wanted


def find_scenario(member,members):
    prefix=member.rsplit('/',1)[0]
    job=prefix+'/job.json'
    if job in members:
        value=json.loads(members[job]);return value.get('scenario',{}),job,value.get('repeat')
    stem=Path(member).name.removesuffix('.hooks.jsonl')
    bare=re.sub(r'-r\d+$','',stem)
    candidates=[]
    for name,data in members.items():
        if 'scenarios' not in Path(name).name or not name.endswith('.json'):continue
        scenarios=json.loads(data)
        if not isinstance(scenarios,list):continue
        for scenario in scenarios:
            if scenario.get('id') in (stem,bare):
                # Closest folder or scenarios_D for a D worker before fallback.
                score=len(set(Path(prefix).parts)&set(Path(name).parent.parts))
                if Path(name).stem=='scenarios_'+Path(prefix).name:score+=10
                candidates.append((score,name,scenario))
    if candidates:
        _,name,value=max(candidates,key=lambda x:(x[0],x[1]));return value,name,value.get('rep')
    return {},None,None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--registry',type=Path,default=HERE.parent/'local_guards_v4_followup/data/strict/episodes.jsonl.gz');parser.add_argument('--extra-raw-root',action='append',type=Path,default=[]);args=parser.parse_args()
    EXTRA_ROOTS.extend(args.extra_raw_root)
    registry=read_jsonl(args.registry)
    read_log=[dict(source=str(args.registry),sha256=file_hash(args.registry),role='episode_index_only')]
    manifests={}
    for executor in ('deepseek','luna'):
        path=RAW_ROOT/'experiments/control-placement/four-model-comparison/artifacts'/f'{executor}-source-and-acceptance.tar.gz'
        with tarfile.open(path,'r:gz') as tar:
            for member in tar:
                if member.isfile() and member.name.endswith('/manifest.json'):
                    content=tar.extractfile(member).read();value=json.loads(content)
                    manifests[executor]=dict(revision=value.get('finbot_commit',value.get('execution_spec',{}).get('finbot_commit')),episodes={x.get('episode') for x in value.get('matrix',[])},source_ref=str(path)+'::'+member.name)
                    read_log.append(dict(source=str(path),member=member.name,sha256=hashlib.sha256(content).hexdigest(),role='actual_source_revision_and_scenario_binding'))
    inventory_path=HERE.parent/'local_guards_v4/data/source-inventory.json'
    source_inventory=json.loads(inventory_path.read_text())['records']
    blob_by_path={loc['path']:rec for rec in source_inventory for loc in rec['locations']}
    read_log.append(dict(source=str(inventory_path),sha256=file_hash(inventory_path),role='raw_source_locator_only; all recovered bytes verified'))
    by_source=defaultdict(list)
    for e in registry:by_source[e['source']].append(e)
    output=HERE/'data';output.mkdir(exist_ok=True)
    episodes=[];all_rows=[];metadata=[];technical=[];inventory=[];sources=[];registered=set()
    for source,index in sorted(by_source.items()):
        resolved=resolve_source(source)
        blob=None;payload=None
        if resolved is None and source in blob_by_path:
            blob=blob_by_path[source]
            payload=subprocess.check_output(['git','cat-file','blob',blob['git_blob']],cwd=HERE)
            if hashlib.sha256(payload).hexdigest()!=blob['sha256']:raise ValueError('Raw Git blob hash mismatch: '+source)
            resolved='git-blob:'+blob['git_blob']+':'+source
            read_log.append(dict(source=resolved,git_blob=blob['git_blob'],sha256=blob['sha256'],role='recovered_immutable_raw_source'))
        if resolved is None:
            for e in index:episodes.append(dict(e,availability='missing_raw_source',rows=0,scenario={},source_origin=e['cohort']))
            sources.append(dict(registry_source=source,availability='missing'))
            continue
        sources.append(dict(registry_source=source,path=str(resolved),sha256=blob['sha256'] if blob else file_hash(resolved),availability='read'))
        if source.endswith('.tar.gz'):
            if blob:raise ValueError('Git-only tar requires explicit in-memory reader: '+source)
            members=tar_members(resolved,read_log)
            for e in index:
                member=e['member'];member=member if member.endswith('.jsonl') else member+'hooks.jsonl'
                registered.add((str(resolved),member))
                if member not in members:
                    episodes.append(dict(e,availability='missing_member',rows=0,scenario={},source_origin=e['cohort']));continue
                payload=members[member];rows=[json.loads(line) for line in payload.splitlines() if line.strip()]
                scenario,scenario_member,repeat=find_scenario(member,members)
                initial=None;namespace=None;root_task=None
                binding=manifests.get(e['executor'],{})
                relative_episode=member.split('/episodes/',1)[-1].removesuffix('/hooks.jsonl')
                verified=binding.get('revision') if '/main/episodes/' in member and relative_episode in binding.get('episodes',set()) else None
                ep=dict(e,verified_source_version=verified,source_revision_receipt=binding.get('source_ref') if verified else None,scenario=scenario,scenario_source=scenario_member,repeat=repeat,source_origin=scenario.get('src',e['cohort']),fixture_ref=(str(resolved)+'::'+scenario_member if scenario_member else None),raw_events=len(rows),availability='empty_raw_prefix' if not rows else 'available',source_sha256=sources[-1]['sha256'])
                emit_episode(ep,rows,initial,scenario,namespace,root_task,str(resolved)+'::'+member,episodes,all_rows,metadata,technical)
            for name in members:
                if name.endswith(('.hooks.jsonl','/hooks.jsonl')) and (str(resolved),name) not in registered:
                    inventory.append(dict(source=str(resolved),member=name,reason='raw_hook_member_absent_from_registry; retained inventory pending compatibility review'))
        elif source.endswith('hooks.jsonl'):
            data=payload if payload is not None else Path(resolved).read_bytes()
            rows=[json.loads(line) for line in data.splitlines() if line.strip()]
            # First actual same-subject native read supplies grouping text only;
            # it is never moved backwards into the predictor's initial fixture.
            scenario=next((parse_result(r.get('tool_result')) for r in rows if r.get('hook_kind')=='after_tool' and r.get('tool_name')=='get_invoice_details' and isinstance(parse_result(r.get('tool_result')),dict)),{})
            for e in index:
                ep=dict(e,scenario={k:v for k,v in scenario.items() if k in ('amount','description')},repeat=None,source_origin='partial_raw_prefix',raw_events=len(rows),availability='empty_raw_prefix' if not rows else 'available',source_sha256=sources[-1]['sha256'])
                emit_episode(ep,rows,None,None,None,None,str(resolved),episodes,all_rows,metadata,technical)
        else:
            runs=([json.loads(line) for line in gzip.decompress(payload).splitlines() if line.strip()] if payload is not None else read_jsonl(resolved));by_id={r.get('run_id'):(line,r) for line,r in enumerate(runs,1)}
            read_log.append(dict(source=str(resolved),sha256=sources[-1]['sha256'],role='legacy_raw_initial_and_steps; final fields excluded'))
            for e in index:
                located=by_id.get(e['member'])
                if located is None:
                    episodes.append(dict(e,availability='missing_run',rows=0,scenario={},source_origin=e['cohort']));continue
                run_line,run=located
                rows,root_task=legacy_events(run)
                ep=dict(e,verified_source_version=run.get('git_sha'),fixture_ref=str(resolved)+'#L'+str(run_line)+'/db_initial',scenario=dict(run.get('invoice') or {},id=run.get('case_id')),repeat=run.get('replicate'),source_origin=run.get('set_name',e['cohort']),raw_events=len(rows),availability='empty_raw_prefix' if not rows else 'available',source_sha256=sources[-1]['sha256'])
                emit_episode(ep,rows,run.get('db_initial'),run.get('invoice'),run.get('namespace'),root_task,str(resolved)+'#L'+str(run_line),episodes,all_rows,metadata,technical)
    # Inventory every other raw tar without silently counting it as a compatible episode.
    known={str(Path(s['path']).resolve()) for s in sources if s.get('path') and not s['path'].startswith('git-blob:')}
    for path in sorted(RAW_ROOT.rglob('*.tar.gz')):
        if str(path.resolve()) in known:continue
        members=tar_members(path,read_log)
        hooks=[n for n in members if n.endswith(('.hooks.jsonl','/hooks.jsonl'))]
        inventory.append(dict(source=str(path),sha256=file_hash(path),raw_hook_members=len(hooks),members=hooks,reason='additional_source_absent_registry' if hooks else 'source_acceptance_logs_or_configuration_no_hook_episodes'))
    known_hashes={s.get('sha256') for s in sources}|{x.get('sha256') for x in read_log}
    for record in source_inventory:
        if record.get('native_hook_episodes',0) or record.get('native_journal_candidate') or record.get('status')=='native_journal_candidate':
            paths={loc['path'] for loc in record['locations']}
            if record['sha256'] not in known_hashes and not paths.intersection(by_source):
                inventory.append(dict(git_blob=record.get('git_blob'),sha256=record['sha256'],locations=record['locations'],reason='declared_offline_fixture_replay_not_original_executor_archive' if any('/offline' in p for p in paths) else 'saved_continuation_of_existing_incident_not_independent_episode' if any('/continued/' in p for p in paths) else 'immutable_raw_candidate_not_directly_indexed; requires_compatibility_review'))
    old_metadata_path=args.registry.parent/'metadata.jsonl.gz'
    old_ids={r['prefix_id'] for r in read_jsonl(old_metadata_path)}
    read_log.append(dict(source=str(old_metadata_path),sha256=file_hash(old_metadata_path),role='join_index_only; no old observations or target decisions'))
    for meta in metadata:
        compatible=meta['prefix_id'] in old_ids
        meta.update(original_prefix_id=meta['prefix_id'] if compatible else None,original_prefix_id_compatible=compatible)
    write_jsonl(output/'historical/observations.jsonl.gz',all_rows)
    write_jsonl(output/'instrumented/observations.jsonl.gz',technical)
    write_jsonl(output/'metadata.jsonl.gz',metadata)
    write_jsonl(output/'episodes.jsonl.gz',episodes)
    # Original recorded outcomes are copied separately, never consulted above.
    outcome_path=args.registry.parent/'gold-outcomes.jsonl.gz'
    if outcome_path.exists():
        outcomes=read_jsonl(outcome_path)
        write_jsonl(output/'archive-outcomes-unverified.jsonl.gz',outcomes)
        read_log.append(dict(source=str(outcome_path),sha256=file_hash(outcome_path),role='outcome_only_old_target_not_new_gold'))
    manifest=dict(registry_episodes=len(registry),episodes=len(episodes),availability=dict(Counter(e['availability'] for e in episodes)),checkpoints=dict(Counter(r['checkpoint'] for r in all_rows)),observations=len(all_rows),technical_observations=len(technical),sources=sources,additional_inventory=inventory,raw_context_omissions=['provider/model identifiers, timestamps, repeated platform system boilerplate; exact repeated user messages replaced by event references; no character/token truncation'],technical_definition='Offline collector replay records task admission, stack and call/source links. Not executor rerun or recovered original authorization.',original_prefix_joins=sum(m['original_prefix_id_compatible'] for m in metadata),command=' '.join(__import__('sys').argv))
    (output/'collector-manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    (HERE/'provenance/collector-read-log.json').write_text(json.dumps(read_log,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('sources','additional_inventory')},indent=2))


def emit_episode(ep,rows,initial,fixture,namespace,root_task,source_ref,episodes,all_rows,metadata,technical):
    extracted,links=collect_hooks(rows,episode_id=ep['episode_id'],source_ref=source_ref,initial=initial,fixture=fixture,source_version=ep.get('verified_source_version'),namespace=namespace,root_task=root_task,fixture_ref=ep.get('fixture_ref'),source_revision_ref=ep.get('source_revision_receipt'))
    ep=dict(ep,rows=len(extracted),observed_tool_names=sorted({r.get('tool_name') for r in rows if r.get('tool_name')}))
    episodes.append(ep)
    for row,link in zip(extracted,links):
        all_rows.append(row)
        meta={k:v for k,v in ep.items() if k not in ('scenario',)}
        meta.update(prefix_id=row['prefix_id'],original_prefix_id=row['prefix_id'],checkpoint=row['checkpoint'],event_seq=row['event_seq'],source_event_index=link['source_event_index'],original_prefix_id_compatible=row['checkpoint']=='P4' and not ep['executor'].endswith('_old'))
        metadata.append(meta)
        instrumented=copy.deepcopy(row)
        c=instrumented['observation']['context']
        c.update(call_id='collector/'+digest(link)[:24],parent_workflow_id='collector/task/'+digest(ep['episode_id'])[:24],source_binding='offline_replay_recorded_source_links')
        for field in ('call_id','parent_workflow_id','source_binding'):
            key='context.'+field
            instrumented['observation']['provenance'][key]=[evidence(link['source_ref'],row['event_seq'],key,c[field],{'invoice_id':c['invoice_id'],'vendor_id':c['vendor_id']},status='instrumented',kind='declared_instrumentation',derived_from=[link['task_admission_ref'],link['call_source_ref']],note='Recorded by offline collector replay; not original authorization or executor metadata.')]
            instrumented['evidence_status'][key]='instrumented'
        technical.append(instrumented)

if __name__=='__main__':main()
