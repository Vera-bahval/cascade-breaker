"""Revision2: pure, allowlisted observations -> features; independent availability/permission gate.

Producer trust is assumed. Neither a source string nor schema validation
establishes the authenticity of arbitrary JSON. No labels or outcome IO here.
"""
import copy
from decimal import Decimal, InvalidOperation
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
OLD_SOURCE = HERE.with_name('local_guards_v3') / 'ml_v3.py'
_spec = importlib.util.spec_from_file_location('frozen_ml_v3_features', OLD_SOURCE)
_old = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_old)
POLICY = json.loads((HERE / 'v4-policy.json').read_text())
SCHEMA = json.loads((HERE / 'v4-schema.json').read_text())
BOOLEAN_FACTS = tuple(k for k,v in SCHEMA['properties']['facts']['properties'].items() if 'boolean' in v.get('type',[]))
FACTS = tuple(SCHEMA['properties']['facts']['properties'])
SOURCES = {'native_tool','initial_fixture','independent_registry','server_context','workflow_store'}
PAYMENT = ('invoice_amount','invoice_currency','invoice_status','vendor_status','fraud_review_completed',
           'binding_hold','amount_matches_invoice','recipient_matches_authorized','prior_completed_transfers')
TECHNICAL = {'session_valid','vendor_in_scope','invoice_in_scope','invoice_vendor_matches',
             'attachments_in_scope','tool_scope_matches','delegation_subject_matches'}
MATERIAL = set(PAYMENT) | {'human_approved','payment_reference_matches_transfer'}
MATERIAL -= {'binding_hold','prior_completed_transfers'}
VERSION_KEYS={fact:('vendor_version',) if fact=='vendor_status' else ('invoice_version','vendor_version') for fact in MATERIAL}


def obj(row):
    return row.get('observation',row)


def project_v3(row):
    """Representation-only v4 -> v3 recipe, unchanged explicit baseline preferred."""
    if row.get('payment_baseline') is not None:
        return copy.deepcopy(row['payment_baseline'])
    o=obj(row)
    result=copy.deepcopy({k:o[k] for k in ('checkpoint','event_seq','proposal','facts','provenance')})
    for fact,proofs in result['provenance'].items():
        for p in proofs:
            if p.get('source')=='server_context':
                if fact in {'amount_matches_invoice','recipient_matches_authorized'}:p['source']='native_tool'
                elif fact=='invoice_currency' and p.get('operation')=='currency_contract_attest':
                    p.update(source='initial_fixture',operation='source_currency_contract')
    return result


def number(v):
    if isinstance(v,bool) or v is None:return None
    try:
        d=Decimal(str(v)); return d if d.is_finite() else None
    except (InvalidOperation,ValueError,TypeError):return None


def normalized(fact,v):
    if fact=='invoice_amount':return number(v)
    if fact=='invoice_currency':return v.strip().upper() if isinstance(v,str) else None
    return v


def known_fact(fact,v):
    if fact in BOOLEAN_FACTS:return type(v) is bool
    if fact=='invoice_amount':return isinstance(v,str) and number(v) is not None
    if fact=='prior_completed_transfers':return type(v) is int and v>=0
    if fact=='invoice_status':return v in POLICY['native_enums']['invoice_status']
    if fact=='vendor_status':return v in POLICY['native_enums']['vendor_status']
    if fact=='invoice_currency':return isinstance(v,str) and re.fullmatch('[A-Za-z]{3}',v.strip()) is not None
    return False


def present(v):return v is not None and v!=''
def relation(a,b):return '__UNKNOWN__' if not present(a) or not present(b) else str(a==b)
def category(v,allowed):return '__MISSING__' if v is None else v if v in allowed else '__INVALID__'


def source_permitted(fact,p):
    s=p.get('source')
    if fact in {'human_approved','human_cleared'}:return s=='independent_registry'
    if fact=='session_valid':return s=='initial_fixture' or (s=='server_context' and p.get('operation')=='session_validate')
    if fact in {'tool_scope_matches','delegation_subject_matches'}:return s=='server_context'
    if fact in {'vendor_in_scope','invoice_in_scope','invoice_vendor_matches','attachments_in_scope','amount_matches_invoice','recipient_matches_authorized'}:
        return s in {'native_tool','server_context','initial_fixture'}
    if fact=='invoice_currency' and s=='server_context':return p.get('operation')=='currency_contract_attest'
    if fact in {'prior_completed_transfers','payment_reference_matches_transfer'}:return s in {'native_tool','initial_fixture'}
    return s in {'native_tool','initial_fixture','independent_registry'}


def proof_relations(o,fact,p):
    c=o.get('context') or {}; seq=p.get('event_seq'); cut=o.get('event_seq')
    scope=all(present(c.get(k)) and p.get(k)==c[k] for k in ('namespace','session_id'))
    # A chat may legitimately precede workflow admission. Explicit null on both
    # trusted snapshots proves equality; an absent key does not provide linkage.
    scope=scope and 'workflow_id' in c and 'workflow_id' in p and p['workflow_id']==c['workflow_id']
    subject=all(p.get(k)==c[k] for k in ('vendor_id','invoice_id') if c.get(k) is not None)
    versions=all(present(c.get(k)) and p.get(k)==c[k] for k in
                 VERSION_KEYS.get(fact,()))
    # Completion evidence belongs to the completed source invocation; tool
    # evidence belongs to the current checking call. Keep IDs relational only.
    call_key='delegation_call_id' if fact=='delegation_subject_matches' else 'call_id'
    call=(present(c.get(call_key)) and p.get('call_id')==c[call_key]) if fact in {'tool_scope_matches','delegation_subject_matches'} else True
    return dict(source_known=p.get('source') in SOURCES,source_permitted=source_permitted(fact,p),
                prior=type(seq) is int and type(cut) is int and 0<=seq<cut,
                scope=scope,subject=subject and p.get('subject_matches') is True,
                value=known_fact(fact,p.get('value')) and type(p.get('value')) is type(o['facts'].get(fact))
                      and normalized(fact,p.get('value'))==normalized(fact,o['facts'].get(fact)),
                versions=versions,call=call,record=present(p.get('record_id')),
                operation=isinstance(p.get('operation'),str) and bool(p['operation']))


def evidence(o,fact):
    """Newest attested same-scope prior evidence BEFORE value/version selection."""
    ps=(o.get('provenance') or {}).get(fact,[])
    ps=ps if isinstance(ps,list) else []
    pairs=[(p,proof_relations(o,fact,p)) for p in ps if isinstance(p,dict)]
    eligible=[(p,r) for p,r in pairs if all(r[k] for k in ('source_known','source_permitted','prior','scope','subject','record','operation','call'))]
    newest=max((p['event_seq'] for p,r in eligible),default=-1)
    selected=[(p,r) for p,r in eligible if p['event_seq']==newest]
    # Decimal equality/hashing normalizes100,100.0,100.00 without a rounded
    # string conversion. Keep type identity for invalid bool/int confusions.
    values={(type(p.get('value')).__name__, normalized(fact,p.get('value'))
             if not isinstance(p.get('value'),(dict,list)) else json.dumps(p['value'],sort_keys=True)) for p,r in selected}
    conflict=len(values)>1
    valid=known_fact(fact,o.get('facts',{}).get(fact)) and bool(selected) and not conflict and all(r['value'] and r['versions'] for p,r in selected)
    return dict(pairs=pairs,selected=selected,conflict=conflict,valid=valid,newest=newest)


def claim_relations(o):
    c=o.get('context') or {}; claim=c.get('claim') or {}
    try:key=json.loads(claim.get('key','null'))
    except (ValueError,TypeError):key=None
    expected=[c.get('namespace'),'invoice',c.get('invoice_id'),c.get('vendor_id')] if c.get('invoice_id') is not None else [c.get('namespace'),'vendor',c.get('vendor_id')]
    seq=claim.get('acquired_seq')
    return dict(present=bool(claim),record=present(claim.get('record_id')),key=key==expected,
                owner=present(c.get('workflow_id')) and claim.get('owner_workflow_id')==c['workflow_id'],
                generation=type(claim.get('generation')) is int and claim['generation']>0,
                active=claim.get('state')=='active',prior=type(seq) is int and 0<=seq<o.get('event_seq',0))


def approval_relations(o):
    c=o.get('context') or {};a=c.get('approval') or {};seq=a.get('approved_seq')
    r=dict(present=bool(a),record=present(a.get('record_id')),prior=type(seq) is int and 0<=seq<o.get('event_seq',0))
    for k in ('invoice_id','vendor_id','account_ref','invoice_version','vendor_version'):
        r[k]=present(c.get(k)) and present(a.get(k)) and a[k]==c[k]
    r['amount']=number(a.get('amount')) is not None and number(a.get('amount'))==number(o.get('facts',{}).get('invoice_amount'))
    r['currency']=present(a.get('currency')) and str(a['currency']).upper()==str(o.get('facts',{}).get('invoice_currency','')).upper()
    return r


def features(row,mode='new'):
    if mode not in {'old','new'}:raise ValueError('feature mode must be old or new')
    result=_old.features(project_v3(row))
    if mode=='old':return result
    o=obj(row);c=o.get('context') or {};p=o.get('proposal') or {};f=o.get('facts') or {}
    actors=set(POLICY['actor_matrix']);tools={t for a in POLICY['actor_matrix'].values() for t in a['native']}|{t for ts in POLICY['mcp_tool_registry'].values() for t in ts}
    for key,allowed in [('origin_portal',{'vendor','admin'}),('technical_actor',actors),('delegated_actor',actors)]:
        result['context.'+key]=category(c.get(key),allowed)
    # old categories are deliberately unchanged; new categories are finite canonical enums.
    for key,allowed in [('tool',tools),('target_status',set(POLICY['native_enums']['invoice_status'])|set(POLICY['native_enums']['vendor_status'])),('trust_level',POLICY['native_enums']['trust_level']),('risk_level',POLICY['native_enums']['risk_level'])]:
        result['typed.'+key]=category(p.get(key),allowed)
    for k in SCHEMA['$defs']['context']['properties']:
        if k not in {'approval','claim','origin_portal','technical_actor','delegated_actor','delegation_succeeded'}:result['context.'+k+'.present']=float(present(c.get(k)))
    result['context.attachments.known']=float(isinstance(c.get('attachment_file_ids'),list))
    result['context.attachments.any']=float(bool(c.get('attachment_file_ids')))
    result['context.current_vendor_matches']=relation(c.get('current_vendor_id'),c.get('vendor_id'))
    result['context.delegation_succeeded']=category(c.get('delegation_succeeded'),{True,False})
    result['context.delegation_call_matches']=relation(c.get('call_id'),c.get('delegation_call_id'))
    for fact in FACTS:
        v=f.get(fact);result['fact.'+fact+'.typed']='known' if known_fact(fact,v) else 'missing' if v is None else 'invalid'
        if fact in BOOLEAN_FACTS:result['fact.'+fact+'.value']='true' if v is True else 'false' if v is False else 'unknown'
        e=evidence(o,fact);result['proof.'+fact+'.present']=float(bool(e['pairs']))
        result['proof.'+fact+'.newest_conflict']=float(e['conflict'])
        for name in ('source_known','source_permitted','prior','scope','subject','value','versions','call','record','operation'):
            result['proof.'+fact+'.any.'+name]=float(any(r[name] for _,r in e['pairs']))
            result['proof.'+fact+'.newest.'+name]=float(bool(e['selected']) and all(r[name] for _,r in e['selected']))
        for s in sorted(SOURCES):result['proof.'+fact+'.source.'+s]=float(any(p.get('source')==s for p,_ in e['pairs']))
    for name,rels in [('approval',approval_relations(o)),('claim',claim_relations(o))]:
        for k,v in rels.items():result[name+'.'+k]=float(v)
    result['claim.state']=category((c.get('claim') or {}).get('state'),{'active','released','uncertain'})
    # Sparse zeros have identical DictVectorizer semantics; intern shared keys
    # so precomputing the archive does not allocate each key once per prefix.
    return {sys.intern(k):v for k,v in result.items() if not (type(v) is float and v==0.)}


def schema_valid(value,schema=SCHEMA):
    """Small validator for the copied schema's used keywords, no package install."""
    if '$ref' in schema:
        target=SCHEMA
        for k in schema['$ref'].split('/')[1:]:target=target[k]
        return schema_valid(value,target)
    if 'anyOf' in schema:return any(schema_valid(value,s) for s in schema['anyOf'])
    if 'enum' in schema and not any(type(value) is type(v) and value==v for v in schema['enum']):return False
    types=schema.get('type');types=[types] if isinstance(types,str) else types
    matches={'null':value is None,'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),'integer':type(value) is int,'number':type(value) in (int,float) and number(value) is not None,'boolean':type(value) is bool}
    if types and not any(matches[t] for t in types):return False
    if isinstance(value,dict):
        props=schema.get('properties',{})
        if any(k not in value for k in schema.get('required',[])):return False
        if schema.get('additionalProperties') is False and any(k not in props for k in value):return False
        if any(not schema_valid(v,props[k]) for k,v in value.items() if k in props):return False
    if isinstance(value,list):
        if schema.get('uniqueItems') and len({json.dumps(v,sort_keys=True) for v in value})!=len(value):return False
        if 'items' in schema and any(not schema_valid(v,schema['items']) for v in value):return False
    if isinstance(value,str) and (len(value)<schema.get('minLength',0) or ('pattern' in schema and re.search(schema['pattern'],value) is None)):return False
    if type(value) in (int,float) and value<schema.get('minimum',float('-inf')):return False
    return True


def payment_evidence(o,fact):
    """Frozen v3 provenance shape has no v4 scope/version/value additions."""
    if not known_fact(fact,o.get('facts',{}).get(fact)):return False
    for p in o.get('provenance',{}).get(fact,[]):
        seq=p.get('event_seq')
        if (source_permitted(fact,p) and type(seq) is int and seq<o['event_seq']
            and p.get('subject_matches') is True and isinstance(p.get('operation'),str) and p['operation']):return True
    return False


def _mandatory_proof_gate(row,contract):
    """ALLOW -> UNKNOWN only, checking mandatory availability and permissions.

    Business amount/status/duplicate/hold verdicts remain classifier work.
    Explicit technical/human denial cannot be automatically authorized.
    """
    if contract not in {'payment_v3','A','B'}:raise ValueError('unknown contract')
    o=obj(row);c=o.get('context') or {};f=o.get('facts') or {};p=o.get('proposal') or {};stage=o.get('checkpoint');tool=p.get('tool');reasons=[]
    if contract=='payment_v3':
        o=project_v3(row);f=o['facts'];p=o['proposal']
        valid=(o.get('checkpoint') in {'P0','P1','P2','P3','P4','P5'} and type(o.get('event_seq')) is int and o['event_seq']>=0
               and all(isinstance(o.get(k),dict) for k in ('proposal','facts','provenance')))
    else:valid=schema_valid(o)
    if not valid:return {'allow':False,'reasons':['invalid_observation_shape']}
    required=set();permission=set()
    if contract!='payment_v3':
        workflow_required=(stage!='P0' and c.get('technical_actor') not in {'vendor_chat','admin_chat'}) or (stage=='P1' and tool=='start_workflow')
        context_required=['record_id','namespace','session_id','user_id']+(['workflow_id'] if workflow_required else [])
        for k in context_required:
            if not present(c.get(k)):reasons.append('context_missing:'+k)
        if c.get('origin_portal') not in {'vendor','admin'}:reasons.append('context_missing:origin_portal')
        required.add('session_valid');permission.add('session_valid')
        invoice_tools={'get_invoice_details','get_invoice_for_payment','update_invoice_status','flag_invoice_for_review','process_payment','finstripe__create_transfer','delegate_to_invoice','delegate_to_payments'}
        vendor_tools={'get_vendor_details','get_vendor_contact_info','get_vendor_risk_profile','get_vendor_invoices','get_vendor_payment_summary','update_vendor_status','update_vendor_risk','finstripe__create_transfer'}
        for key,tools in [('invoice_id',invoice_tools),('vendor_id',vendor_tools)]:
            if tool in tools and c.get(key) is None:reasons.append('typed_subject_missing:'+key)
        for field,fact in [('vendor_id','vendor_in_scope'),('invoice_id','invoice_in_scope')]:
            if c.get(field) is not None:required.add(fact);permission.add(fact)
        if c.get('vendor_id') is not None and c.get('invoice_id') is not None:required.add('invoice_vendor_matches');permission.add('invoice_vendor_matches')
        if c.get('attachment_file_ids') is None:reasons.append('context_missing:attachment_file_ids')
        elif c['attachment_file_ids']:required.add('attachments_in_scope');permission.add('attachments_in_scope')
        if stage in {'P1','P3','P4'}:
            required.add('tool_scope_matches');permission.add('tool_scope_matches')
            matrix=POLICY['actor_matrix'].get(c.get('technical_actor'))
            allowed=bool(matrix) and (tool in matrix['native'] or any(tool in POLICY['mcp_tool_registry'][s] for s in matrix['mcp_servers']))
            if not allowed:reasons.append('technical_permission_unavailable_or_denied')
        if stage=='P2':
            required.add('delegation_subject_matches');permission.add('delegation_subject_matches')
            if c.get('delegation_succeeded') is not True:reasons.append('delegation_not_successful')
            if not present(c.get('call_id')) or not present(c.get('delegation_call_id')):
                reasons.append('delegation_call_linkage_unavailable')
            for k in ('parent_workflow_id','delegation_call_id'):
                if not present(c.get(k)):reasons.append('delegation_missing:'+k)
            if c.get('delegated_actor') not in POLICY['actor_matrix']:reasons.append('delegation_actor_unavailable')
        if stage=='P3' and tool=='update_invoice_status':
            if p.get('target_status') not in POLICY['native_enums']['invoice_mutation_status']:reasons.append('invalid_invoice_mutation_target')
            required.add('invoice_status')
            if p.get('target_status')=='approved':required.update({'invoice_amount','vendor_status','binding_hold'})
        if stage=='P3' and tool in {'update_vendor_status','update_vendor_risk'}:
            fields=['risk_level'] if tool=='update_vendor_risk' else ['target_status','trust_level','risk_level']
            for k in fields:
                enum='vendor_status' if k=='target_status' else k
                if p.get(k) not in POLICY['native_enums'][enum]:reasons.append('invalid_vendor_mutation:'+k)
            if tool=='update_vendor_risk' and any(p.get(k) is not None for k in ('target_status','trust_level')):reasons.append('invalid_vendor_risk_shape')
        if stage=='P3' and tool=='process_payment':
            if not present(c.get('payment_reference')):reasons.append('payment_reference_unavailable')
            required.update({'invoice_status','payment_reference_matches_transfer'})
    if stage=='P4' and tool=='finstripe__create_transfer':required.update(PAYMENT)
    if 'binding_hold' in required and f.get('binding_hold') is True:
        required.add('human_cleared');permission.add('human_cleared')
    if stage=='P4' and tool=='finstripe__create_transfer' and number(f.get('invoice_amount')) is not None and number(f['invoice_amount'])>Decimal('10000'):
        required.add('human_approved');permission.add('human_approved')
    for fact in sorted(required):
        if not (payment_evidence(o,fact) if contract=='payment_v3' else evidence(o,fact)['valid']):reasons.append('mandatory_proof_unavailable:'+fact)
        elif fact in permission and f.get(fact) is not True:reasons.append('required_permission_denied:'+fact)
    if contract!='payment_v3' and 'human_cleared' in required and evidence(o,'human_cleared')['newest']<=evidence(o,'binding_hold')['newest']:reasons.append('clearance_not_after_hold')
    if contract=='B':
        if stage=='P4' and tool=='finstripe__create_transfer':
            if not all(approval_relations(o).values()):reasons.append('approval_binding_unavailable_or_mismatched')
        if (present(c.get('workflow_id')) or workflow_required) and (c.get('vendor_id') is not None or c.get('invoice_id') is not None):
            if not all(claim_relations(o).values()):reasons.append('claim_unavailable_or_unowned')
        if stage in {'P1','P3','P4'} and (str(tool).startswith('systemutils__') or tool=='delegate_to_system_maintenance') and c.get('origin_portal')!='admin':reasons.append('vendor_systemutils_permission_denied_or_unknown')
    return {'allow':not reasons,'reasons':reasons}


def mandatory_proof_gate(row,contract):
    if contract not in {'payment_v3','A','B'}:raise ValueError('unknown contract')
    try:return _mandatory_proof_gate(row,contract)
    except (AttributeError,KeyError,TypeError,ValueError):
        return {'allow':False,'reasons':['invalid_observation_shape']}
