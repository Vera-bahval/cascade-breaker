"""Causal source evidence, independent of labels, guard decisions and agent names.

The caller must admit the source packet. JSON source labels alone authenticate
nothing. Replay coordinates identify evidence, never authorise business actions.
"""
from copy import deepcopy
from decimal import Decimal
from experiments.local_guards_v4 import guard as contract

from experiments.local_guards_final_replay import projection as prior
from experiments.local_guards_archive_comparison.collector import digest, parse_result

MUTABLE = {'invoice_amount', 'invoice_status', 'vendor_status', 'account',
           'invoice_vendor_matches', 'fraud_review_completed', 'prior_completed_transfers'}
READS = prior.INVOICE_READ | prior.VENDOR_READ
WRITES = prior.INVOICE_WRITE | prior.VENDOR_WRITE
WRITE_FIELDS={name:set() for name in WRITES}
WRITE_FIELDS.update(update_invoice_status={'invoice_status'},process_payment={'invoice_status'},
                    update_vendor_status={'vendor_status'})
KNOWN_NATIVE={tool for role in contract._REGISTRY['actor_matrix'].values() for tool in role['native']} | WRITES | READS
KNOWN_MCP={tool for name,tools in contract._REGISTRY['mcp_tool_registry'].items() if name!='systemutils' for tool in tools}


def pair_events(events):
    """Keep callbacks, model proposals and completed legacy records distinct.

    The producer must admit the source format; a tag in arbitrary JSON is not
    an execution attestation. Derived proposal links never become beforehooks.
    """
    pending, pairs, proposals = [], [], []
    legacy=any(e.get('source_event_kind') in {'tool','llm','recorded_model_proposal'} for e in events)
    batch=None
    def compatible(before,after):
        if (before.get('tool_name')!=after.get('tool_name')
                or digest(before.get('tool_arguments') or {})!=digest(after.get('tool_arguments') or {})):
            return False
        fields=('namespace',*prior.CALL_IDENTITIES,'tool_call_id','call_id','tool_source')
        first=before.get('tool_call_id') or before.get('call_id')
        second=after.get('tool_call_id') or after.get('call_id')
        if any(e.get('tool_call_id') and e.get('call_id') and e['tool_call_id']!=e['call_id'] for e in (before,after)):
            return False
        return (not first or not second or first==second) and all(
            before.get(k) is None or after.get(k) is None or before[k]==after[k] for k in fields)
    for index, event in enumerate(events):
        kind = event.get('hook_kind')
        if kind=='after_model' or kind=='before_model' and event.get('source_event_kind')=='llm':
            batch=index
        if event.get('tool_name')=='complete_task':
            # Modern terminal sentinel may have no callback. Legacy traces
            # record its return; neither representation closes its delegate.
            if kind=='after_tool' and legacy:
                pairs.append(({'event':event,'index':index,'parent':None,'tool':'complete_task',
                               'legacy_executed':True},event))
            continue
        if kind == 'before_tool':
            frame={'event':event,'index':index,'parent':pending[-1]['index'] if pending else None,
                   'tool':event.get('tool_name')}
            if event.get('source_event_kind')=='recorded_model_proposal':
                proposals.append(dict(frame,batch=batch))
            else:
                pending.append(frame)
        elif kind == 'after_tool':
            if pending and compatible(pending[-1]['event'],event) and prior._matches(pending[-1]['event'], event):
                pairs.append((pending.pop(), event))
            elif legacy and (not pending or pending[-1]['tool'].startswith('delegate_to_')
                    and event.get('tool_name')!=pending[-1]['tool']
                    and not str(event.get('tool_name') or '').startswith('delegate_to_')):
                batch_proposals=[p for p in proposals if p['batch']==batch]
                candidates=[p for p in batch_proposals if compatible(p['event'],event)]
                frame={'event':event,'index':index,'parent':None,
                       'tool':event.get('tool_name'),'legacy_executed':True}
                unique=len(candidates)==1
                if unique:
                    proposal=candidates[0];proposals.remove(proposal)
                    frame['proposal_event_seq']=proposal['event']['event_seq']
                    frame['proposal_link_kind']='derived_unique_structural_match'
                # A completed legacy tool step, or a unique source-recorded
                # proposal/result, may belong to one active actual delegate.
                own_ids_consistent=not (event.get('tool_call_id') and event.get('call_id')
                                        and event['tool_call_id']!=event['call_id'])
                if (unique or event.get('source_event_kind')=='tool' and not batch_proposals) and own_ids_consistent and len(pending)==1:
                    parent=pending[0]
                    first,second=parent['event'],event
                    conflict=any(first.get(k) is not None and second.get(k) is not None and first[k]!=second[k]
                                 for k in ('namespace','session_id'))
                    if first.get('workflow_id') and second.get('workflow_id') not in (None,first['workflow_id']):
                        conflict=conflict or second.get('parent_workflow_id')!=first['workflow_id']
                    if first.get('workflow_id') and second.get('parent_workflow_id'):
                        conflict=conflict or second['parent_workflow_id']!=first['workflow_id']
                    same_parent=not unique or proposal['parent']==parent['index']
                    if not conflict and same_parent:frame['parent']=parent['index']
                pairs.append((frame,event))
            else:
                pairs.append((None, event))
    return pairs, pending


def build_evidence(row, source=None):
    source = source or {}
    row = deepcopy(row)
    cut = row['event_seq']
    events = row.get('raw_context', {}).get('events', [])
    if any(type(e.get('event_seq')) is not int or not 0 <= e['event_seq'] < cut for e in events):
        raise ValueError('future_or_invalid_event')
    if any(a['event_seq'] > b['event_seq'] for a,b in zip(events, events[1:])):
        raise ValueError('unordered_events')
    _, modern, coordinates = prior.project(row, {}, conditional=False)
    context = modern['context']
    context.pop('technical_actor', None)
    context.pop('delegated_actor', None)
    coordinates=[r for r in coordinates if r.get('field') in {'proposal','proposal.currency',
        'context.invoice_id','context.vendor_id','context.session_id','context.workflow_id',
        'context.parent_workflow_id','context.delegation_call_id','context.delegation_succeeded'}]
    initial = deepcopy(row.get('raw_context', {}).get('initial_state') or {})
    target = {k: context.get(k) for k in ('invoice_id','vendor_id')}
    bundle = {'checkpoint': modern['checkpoint'], 'event_seq': cut,
              'proposal': modern['proposal'], 'context': context, 'initial': initial,
              'current': {}, 'baseline': {}, 'versions': {}, 'version_events': [], 'records': [], 'rejected': [], 'invalidations': [],
              'coordinates': coordinates, 'raw_input': row,
              'source': deepcopy(source), 'complete_prefix':
                  row.get('observation',{}).get('context',{}).get('prefix_complete') is True}
    binding=source.get('runner_binding') or {}
    for field in ('namespace','user_id','origin_portal','current_vendor_id'):
        if binding.get(field) is not None and field not in context:
            context[field]=binding[field]
            coordinates.append({'field':'context.'+field,'status':'derived',
                'reason':'verified_constructor_property_not_authentication',
                'source_ref':binding.get('session_source_ref')})
    if 'attachment_file_ids' not in context and isinstance(binding.get('root_attachment_file_ids'),list):
        context['attachment_file_ids']=deepcopy(binding['root_attachment_file_ids'])
    current, baseline = bundle['current'], bundle['baseline']
    run_ref = source.get('source_instance') or source.get('source_ref') or row.get('raw_context',{}).get('source_ref') or 'packet/'+digest(row)[:24]
    pairs, pending = pair_events(events)
    if bundle['checkpoint']=='P2':
        returned=(row.get('anchor') or {}).get('return_event') or {}
        return_seq=returned.get('event_seq',cut-1)
        matches=[(frame,event) for frame,event in pairs if frame and event['event_seq']==return_seq
                 and frame['tool'].startswith('delegate_to_')]
        if len(matches)==1:
            frame,event=matches[0]
            bundle['proposal']={'tool':frame['tool']}
            for key in target:
                if key in (frame['event'].get('tool_arguments') or {}):
                    target[key]=prior._id(frame['event']['tool_arguments'][key])
                    if target[key] is not None:
                        context[key]=target[key]
            for key in prior.CALL_IDENTITIES:
                if prior._text(frame['event'].get(key)):
                    context[key]=frame['event'][key]
            value=parse_result(event.get('tool_result'))
            if isinstance(value,dict):
                status=value.get('task_status')
                if status in {'success','failed','error'} or value.get('error'):
                    context['delegation_succeeded']=status=='success' and prior._result(event) is not None
            context['delegation_call_id']=(frame['event'].get('tool_call_id') or frame['event'].get('call_id')
                or 'delegation/'+digest([run_ref,frame['event']['event_seq'],frame['tool']])[:24])
    if any(frame is None for frame,_ in pairs):
        bundle['complete_prefix']=False
    model_open=False
    for event in events:
        if event.get('source_event_kind')=='llm':
            # One completed legacy request/response record, not an open hook.
            continue
        if event.get('hook_kind')=='before_model':
            if model_open:
                bundle['complete_prefix']=False
            model_open=True
        elif event.get('hook_kind')=='after_model':
            if not model_open:
                bundle['complete_prefix']=False
            model_open=False
    complete_ledger = isinstance(initial.get('transactions'), list)
    transfers = set()
    transfer_receipts=[]
    hold_events = []

    def store(key, value, seq, ref, operation, *, origin='observed', raw=None, call=None, evidence_kind='tool_result'):
        record = {'fact':key, 'value':value, 'event_seq':seq, 'source_ref':ref,
                  'operation':operation, 'origin':origin, 'source':
                  'initial_fixture' if evidence_kind=='declared_fixture' else 'native_tool',
                  'evidence_kind':evidence_kind, 'subject':dict(target), 'current':True,
                  'record_id':'evidence/'+digest([run_ref,ref,seq,key,value])[:24]}
        if call is not None:
            record['source_call_id'] = call
            record['call_identity_kind']='observed_or_derived_occurrence_not_authentication'
        if raw:
            record['native_version'] = prior._version(raw)
            record['observed_namespace'] = raw.get('namespace')
        bundle['records'].append(record)
        previous=current.get(key)
        if previous and previous['event_seq']==seq and previous['value']!=value:
            record.update(current=False,invalidated_at=seq,invalidated_reason='same_coordinate_conflict')
        current[key] = record
        if key in ('invoice_amount','account') and key not in baseline:
            baseline[key] = record
        return record

    def invalidate_versions(kinds,reason,seq):
        for kind in kinds:
            if kind in bundle['versions']:
                bundle['versions'][kind]=dict(bundle['versions'][kind],current=False,
                    invalidated_reason=reason,invalidated_at=seq)

    def invalidate(keys, reason, seq):
        bundle['invalidations'].append({'fields':sorted(keys),'reason':reason,'event_seq':seq})
        kinds=[]
        if {'invoice_amount','invoice_status','invoice_vendor_matches'}.intersection(keys):
            kinds.append('invoice')
        if {'vendor_status','account'}.intersection(keys):
            kinds.append('vendor')
        invalidate_versions(kinds,reason,seq)
        for key in keys:
            if key in current:
                current[key] = dict(current[key], current=False, invalidated_at=seq, invalidated_reason=reason)

    def observe(kind, value, args, seq, ref, name, **kwargs):
        key=kind+'_id'
        if not prior._subject(value,args,key,target[key]):
            bundle['rejected'].append({'source_ref':ref,'event_seq':seq,'reason':'subject_mismatch','kind':kind})
            return False
        namespace = (initial.get(kind) or {}).get('namespace')
        if namespace and value.get('namespace') not in (None,namespace):
            bundle['rejected'].append({'source_ref':ref,'event_seq':seq,'reason':'namespace_mismatch','kind':kind})
            invalidate({'invoice_amount','invoice_status','invoice_vendor_matches'} if kind=='invoice' else {'vendor_status','account'},'namespace_conflict',seq)
            return False
        version=prior._version(value)
        if version:
            event={'kind':kind,'value':version,'event_seq':seq,'source_ref':ref,'current':True}
            bundle['versions'][kind]=event
            bundle['version_events'].append(event)
        elif 'version' in value or 'updated_at' in value:
            invalidate_versions([kind],'invalid_native_version',seq)
        record_start=len(bundle['records'])
        fields = {'amount':'invoice_amount','status':'invoice_status'} if kind=='invoice' else {'status':'vendor_status','bank_account_number':'account'}
        if kind=='invoice' and 'vendor_id' in value:
            store('invoice_vendor_matches',value['vendor_id']==target['vendor_id'],seq,ref,name,raw=value,**kwargs)
            if value['vendor_id'] != target['vendor_id']:
                return False
            fields.update({'vendor_status':'vendor_status','vendor_bank_account_number':'account'})
        for field, fact in fields.items():
            if field in value:
                parsed=prior._amount(value[field]) if fact=='invoice_amount' else prior._text(value[field])
                record=store(fact,parsed,seq,ref,name,raw=value,**kwargs)
                if fact=='account':
                    record['explicit_absence']=value[field] is None or isinstance(value[field],str) and not value[field].strip()
        for record in bundle['records'][record_start:]:
            if prior._version(value):
                record['native_versions']={kind+'_version':prior._version(value)}
        return True

    seed_ref=source.get('fixture_ref') or run_ref+'/initial_state'
    for kind in ('invoice','vendor'):
        if initial.get(kind):
            observe(kind,initial[kind],{},0,seed_ref,'captured_initial_state',evidence_kind='declared_fixture',origin=source.get('initial_state_origin','observed'))
    for txn in initial.get('transactions',[]) if complete_ledger else []:
        if not isinstance(txn,dict) or type(txn.get('invoice_id')) is not int:
            complete_ledger=False
        elif txn['invoice_id']==target['invoice_id']:
            if txn.get('status')=='completed' and prior._text(txn.get('transfer_id')):
                transfers.add(txn['transfer_id'])
                if (txn.get('vendor_id',(initial.get('invoice') or {}).get('vendor_id'))
                        ==target['vendor_id']):
                    transfer_receipts.append({'transfer_id':txn['transfer_id'],
                        'event_seq':0,'source_ref':seed_ref,'evidence_kind':'declared_fixture'})
            elif txn.get('status') not in ('failed','rejected','pending'):
                complete_ledger=False
    for frame, event in pairs:
        name=event.get('tool_name') or ''
        if name=='complete_task':
            continue
        seq=event['event_seq']
        ref=prior._event_ref(event,run_ref)
        args=event.get('tool_arguments') or {}
        value=prior._result(event)
        if name in WRITES:
            kind='invoice' if name in prior.INVOICE_WRITE else 'vendor'
            if args.get(kind+'_id') in (None,target[kind+'_id']):
                invalidate_versions([kind],'native_write_without_new_version',seq)
        if name.startswith('systemutils__') or name not in KNOWN_NATIVE|KNOWN_MCP:
            invalidate(MUTABLE,'opaque_write',seq)
            complete_ledger=False
            continue
        if not frame:
            if name in WRITES:
                invalidate(MUTABLE,'unpaired_mutation',seq)
            if name=='finstripe__create_transfer':
                complete_ledger=False
            bundle['rejected'].append({'source_ref':ref,'event_seq':seq,'reason':'unpaired_result'})
            continue
        call_id=frame['event'].get('tool_call_id') or frame['event'].get('call_id')
        call_id=call_id or 'recorded-occurrence/'+digest([run_ref,frame['event']['event_seq'],frame['tool']])[:24]
        if value is None:
            if name in WRITES and name not in {'flag_invoice_for_review','update_invoice_agent_notes','update_payment_agent_notes','update_vendor_agent_notes','update_fraud_agent_notes'}:
                invalidate(MUTABLE,'failed_mutation_effect_unconfirmed',seq)
            bundle['rejected'].append({'source_ref':ref,'event_seq':seq,'reason':'failed_or_malformed_result'})
            if name=='finstripe__create_transfer':
                complete_ledger=False
            continue
        if name=='finstripe__create_transfer':
            txn=value.get('transfer') or value
            if (args.get('invoice_id')==target['invoice_id'] and args.get('vendor_id')==target['vendor_id']
                    and txn.get('invoice_id',target['invoice_id'])==target['invoice_id']
                    and txn.get('vendor_id',target['vendor_id'])==target['vendor_id']
                    and txn.get('status')=='completed' and prior._text(txn.get('transfer_id'))):
                transfers.add(txn['transfer_id'])
                transfer_receipts.append({'transfer_id':txn['transfer_id'],'event_seq':seq,
                    'source_ref':ref,'source_call_id':call_id,'evidence_kind':'tool_result'})
            elif txn.get('status') not in ('failed','rejected'):
                complete_ledger=False
            continue
        if event.get('tool_source') != 'native':
            continue
        if name in WRITES:
            keys=WRITE_FIELDS[name]
            # Notes and flags do not mutate the amount/account contract.
            if name not in {'flag_invoice_for_review','update_invoice_agent_notes','update_payment_agent_notes',
                            'update_vendor_agent_notes','update_fraud_agent_notes'}:
                invalidate(keys,'state_mutation',seq)
        valid=False
        if name in prior.INVOICE_READ | prior.INVOICE_WRITE:
            valid=observe('invoice',value,args,seq,ref,name,call=call_id)
        elif name in prior.VENDOR_READ | prior.VENDOR_WRITE:
            valid=observe('vendor',value,args,seq,ref,name,call=call_id)
        if (valid and name=='flag_invoice_for_review'
                and (value.get('flagged') is True or 'flagged' not in value and value.get('status') in contract._REGISTRY['native_enums']['invoice_status'])
                and value.get('recommended_action') in ('hold','escalate','reject')):
            hold=store('binding_hold',True,seq,ref,name,call=call_id)
            hold['recommended_action']=value['recommended_action']
            hold_events.append(hold)
            store('fraud_review_completed',True,seq,ref,name,call=call_id)
        if name=='delegate_to_fraud' and value.get('task_status')=='success':
            # Completion is the successful delegated call; never its textual reasoning.
            nested=[(f,e) for f,e in pairs if f and f.get('parent')==frame['index']
                    and prior._result(e) is not None]
            invoice_read=any(e.get('tool_name') in prior.INVOICE_READ and
                             (e.get('tool_arguments') or {}).get('invoice_id')==target['invoice_id']
                             and prior._subject(prior._result(e),e.get('tool_arguments') or {},'invoice_id',target['invoice_id'])
                             and prior._result(e).get('vendor_id',target['vendor_id'])==target['vendor_id'] for _,e in nested)
            vendor_read=any(e.get('tool_name')=='get_vendor_risk_profile' and
                            (e.get('tool_arguments') or {}).get('vendor_id')==target['vendor_id']
                            and prior._subject(prior._result(e),e.get('tool_arguments') or {},'vendor_id',target['vendor_id']) for _,e in nested)
            if invoice_read and vendor_read and args.get('vendor_id')==target['vendor_id']:
                store('fraud_review_completed',True,seq,ref,name,origin='derived',call=call_id)
    for frame in pending:
        if frame['event'].get('source_event_kind')=='recorded_model_proposal':
            continue
        name=frame['tool'] or ''
        if name.startswith('systemutils__') or name not in KNOWN_NATIVE|KNOWN_MCP:
            invalidate(MUTABLE,'unresolved_mutation',frame['event']['event_seq'])
        if name in WRITES:
            kind='invoice' if name in prior.INVOICE_WRITE else 'vendor'
            invalidate_versions([kind],'unresolved_mutation',frame['event']['event_seq'])
            invalidate(WRITE_FIELDS[name],'unresolved_mutation',frame['event']['event_seq'])
        if name=='finstripe__create_transfer':
            complete_ledger=False
    if transfers or complete_ledger:
        if transfer_receipts:
            latest=max(transfer_receipts,key=lambda r:r['event_seq'])
            aggregate=store('prior_completed_transfers',len(transfers),latest['event_seq'],latest['source_ref'],
                  'count_confirmed_transfer_receipts',origin='derived',call=latest.get('source_call_id'),
                  evidence_kind=latest['evidence_kind'])
        else:
            aggregate=store('prior_completed_transfers',len(transfers),0,seed_ref,
                  'captured_initial_history_with_causal_prefix',origin='derived',evidence_kind='declared_fixture')
        aggregate['derived_from']=[seed_ref,*[r['source_ref'] for r in transfer_receipts]]
    reference=context.get('payment_reference')
    matches=[r for r in transfer_receipts if reference is not None and r['transfer_id']==reference]
    if matches:
        receipt=max(matches,key=lambda r:r['event_seq'])
        record=store('payment_reference_matches_transfer',True,receipt['event_seq'],receipt['source_ref'],
            'join_payment_reference_to_confirmed_receipt',origin='derived',
            call=receipt.get('source_call_id'),evidence_kind=receipt['evidence_kind'])
        record['derived_from']=[receipt['source_ref']]
    if not bundle['complete_prefix']:
        invalidate(MUTABLE,'incomplete_prefix',cut-1)
    if transfers and 'prior_completed_transfers' in current:
        current['prior_completed_transfers']=dict(current['prior_completed_transfers'],current=True,count_kind='observed_lower_bound')
    technical=source.get('technical_observation')
    if technical:
        context.update(deepcopy(technical['context']))
        for key,value in technical['facts'].items():
            if key not in {'session_valid','tool_scope_matches','invoice_in_scope','vendor_in_scope',
                           'invoice_vendor_matches','attachments_in_scope','delegation_subject_matches'}:
                continue
            proof=technical['provenance'][key][0]
            record=store(key,value,proof['event_seq'],proof['record_id'],proof['operation'],
                         origin='replay',evidence_kind=proof['evidence_kind'],call=proof.get('source_call_id'))
            record['source']=proof['source']
            record['target_call_id']=proof.get('call_id')
            for field in ('parent_workflow_id','delegated_workflow_id','delegation_call_id'):
                if field in proof:
                    record[field]=proof[field]
            if proof.get('snapshot_id'):
                record['snapshot_id']=proof['snapshot_id']
    bundle['hold_events']=hold_events
    for record in hold_events:
        current['binding_hold']=record
    # Verified code-to-callable bindings are supplied by the source auditor.
    # A free-form agent_name, including an allowlisted name, never enters this path.
    actor_proof=source.get('actor_proof')
    if bundle['complete_prefix'] and actor_proof and actor_proof.get('event_seq')==cut and actor_proof.get('source_hash') and actor_proof.get('callable'):
        if actor_proof.get('actor') in prior.ACTORS:
            context['technical_actor']=actor_proof['actor']
            bundle['actor_proof']=deepcopy(actor_proof)
    child=source.get('delegation_proof')
    if (bundle['complete_prefix'] and child and child.get('event_seq')==cut
            and child.get('source_hash') and child.get('callable')
            and child.get('actor') in prior.ACTORS):
        context['delegated_actor']=child['actor']
        bundle['delegation_proof']=deepcopy(child)
    bundle['history_complete']=complete_ledger
    bundle['input_sha256']=digest(row)
    return bundle
