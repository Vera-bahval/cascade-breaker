"""Pure v4 guard. Inputs must be snapshots from the trusted adapter/fixture producer.

JSON shape and attester labels cannot authenticate arbitrary caller-created input.
Only unchanged pure function definitions are loaded from v3; its policy is not read.
"""
import ast
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter

_ROOT = Path(__file__).resolve().parent
_REGISTRY = json.loads((_ROOT / 'policy.json').read_text())
_SCHEMA = json.loads((_ROOT / 'schema.json').read_text())
_V3_PATH = _ROOT.parent / 'local_guards_v3' / 'rules_v3.py'
_tree = ast.parse(_V3_PATH.read_text(), filename=str(_V3_PATH))
_v3 = {'Decimal': Decimal, 'InvalidOperation': InvalidOperation,
       'perf_counter': perf_counter, '_DEFAULT_POLICY': _REGISTRY['payment_policy']}
for _node in _tree.body:
    if isinstance(_node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in
            {'_BOOLEAN_FACTS','_STRING_FACTS','_PAYMENT_FACTS'} for t in _node.targets):
        exec(compile(ast.Module(body=[_node], type_ignores=[]), str(_V3_PATH),'exec'), _v3)
    elif isinstance(_node, ast.FunctionDef):
        exec(compile(ast.Module(body=[_node], type_ignores=[]), str(_V3_PATH),'exec'), _v3)

_BOOL = {k for k in _SCHEMA['properties']['facts']['properties'] if k not in
         {'invoice_amount','invoice_currency','invoice_status','vendor_status','prior_completed_transfers'}}
_PAYMENT = set(_v3['_PAYMENT_FACTS']) | {'human_approved','human_cleared'}
_SCOPE = ('namespace','session_id','workflow_id')
_STATE = _PAYMENT | {'payment_reference_matches_transfer'}
_DECIMAL = re.compile(r'^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$')


def _amount(value):
    if not isinstance(value,str) or not _DECIMAL.fullmatch(value): return None
    try: result=Decimal(value)
    except InvalidOperation: return None
    return result if result.is_finite() else None


def _nonempty(value): return isinstance(value,str) and bool(value.strip())
def _integer(value,minimum=0): return type(value) is int and value >= minimum


def _typed(key,value):
    if value is None: return None
    if key in _BOOL: return value if type(value) is bool else None
    if key == 'invoice_amount': return _amount(value)
    if key == 'prior_completed_transfers': return value if _integer(value) else None
    if key == 'invoice_currency':
        return value.strip().upper() if _nonempty(value) and re.fullmatch('[A-Za-z]{3}',value.strip()) else None
    if key in {'invoice_status','vendor_status'}:
        return value if value in _REGISTRY['native_enums'][key] else None
    return None


def _record_shape(value,kind):
    if value is None: return True
    spec=_SCHEMA['$defs'][kind]
    if not isinstance(value,dict) or set(value) != set(spec['required']): return False
    for key,item in value.items():
        if key in {'invoice_id','vendor_id','generation'}:
            if not _integer(item,1): return False
        elif key in {'approved_seq','acquired_seq'}:
            if not _integer(item): return False
        elif key=='state':
            if not isinstance(item,str) or item not in {'active','released','uncertain'}: return False
        elif key=='amount':
            if _amount(item) is None: return False
        elif key=='currency':
            if not isinstance(item,str) or not re.fullmatch('[A-Z]{3}',item): return False
        elif not _nonempty(item): return False
    return True


def _shape(obj):
    if not isinstance(obj,dict) or set(obj)-set(_SCHEMA['properties']): return False
    if not set(_SCHEMA['required']) <= set(obj): return False
    if 'schema_version' in obj and (type(obj['schema_version']) is not int or obj['schema_version'] != 4): return False
    if not isinstance(obj['checkpoint'],str) or obj['checkpoint'] not in {'P0','P1','P2','P3','P4','P5'} or not _integer(obj['event_seq']): return False
    for section in ('proposal','facts','provenance'):
        if not isinstance(obj[section],dict) or set(obj[section])-set(_SCHEMA['properties'][section]['properties']): return False
    for key,value in obj['proposal'].items():
        if value is not None and (not _nonempty(value) or key=='amount' and _amount(value) is None): return False
    for key,value in obj['facts'].items():
        # Native enums are semantic evidence checks, not malformed JSON shape.
        if value is None: continue
        if key in _BOOL and type(value) is not bool: return False
        if key=='prior_completed_transfers' and not _integer(value): return False
        if key=='invoice_amount' and _amount(value) is None: return False
        if key in {'invoice_status','vendor_status','invoice_currency'} and not _nonempty(value): return False
    proof_fields=set(_SCHEMA['$defs']['proof']['properties'])
    for records in obj['provenance'].values():
        if not isinstance(records,list): return False
        for proof in records:
            if not isinstance(proof,dict) or set(proof)-proof_fields: return False
            # Invalid proof values are rejected locally, without hiding other violations.
    ctx=obj.get('context')
    if ctx is None: return True
    if not isinstance(ctx,dict) or set(ctx)-set(_SCHEMA['$defs']['context']['properties']): return False
    for key,value in ctx.items():
        if value is None: continue
        if key in {'approval','claim'}:
            if not _record_shape(value,'approval_binding' if key=='approval' else 'workflow_claim'): return False
        elif key in {'vendor_id','invoice_id','current_vendor_id'}:
            if not _integer(value,1): return False
        elif key=='attachment_file_ids':
            if not isinstance(value,list) or any(not _integer(v,1) for v in value) or len(set(value))!=len(value): return False
        elif key=='delegation_succeeded':
            if type(value) is not bool: return False
        elif not _nonempty(value): return False
    return True


def _sources(key):
    if key in {'human_approved','human_cleared'}: return {'independent_registry'}
    if key=='session_valid': return {'server_context','initial_fixture'}
    if key in {'tool_scope_matches','delegation_subject_matches'}: return {'server_context'}
    if key in {'vendor_in_scope','invoice_in_scope','invoice_vendor_matches','attachments_in_scope',
               'amount_matches_invoice','recipient_matches_authorized'}:
        return {'server_context','native_tool','initial_fixture'}
    if key in {'prior_completed_transfers','payment_reference_matches_transfer'}:
        return {'native_tool','initial_fixture'}
    return {'native_tool','initial_fixture','independent_registry'}


def _proofs(obj):
    """Select latest same-scope attestation BEFORE claimed-value/version filtering."""
    ctx=obj.get('context') or {}; values={}; accepted={}; diagnostics=[]
    for key in _SCHEMA['properties']['facts']['properties']:
        eligible=[]
        for proof in obj['provenance'].get(key,[]):
            good=(isinstance(proof.get('source'),str) and proof.get('source') in _sources(key) and _integer(proof.get('event_seq'))
                  and proof['event_seq'] < obj['event_seq'] and proof.get('subject_matches') is True
                  and _nonempty(proof.get('operation')) and _nonempty(proof.get('record_id'))
                  and 'value' in proof and all(k in proof and proof[k]==ctx.get(k) for k in _SCOPE)
                  and _nonempty(ctx.get('namespace')) and _nonempty(ctx.get('session_id')))
            if key=='session_valid': good=good and proof.get('operation')=='session_validate'
            subjects=()
            if key not in {'session_valid'}:
                subjects=tuple(k for k in ('vendor_id','invoice_id') if ctx.get(k) is not None)
            good=good and all(k in proof and _integer(proof[k],1) and proof[k]==ctx[k] for k in subjects)
            if key in _STATE:
                needed=('vendor_id',) if key=='vendor_status' else ('invoice_id','vendor_id')
                good=good and all(_integer(ctx.get(k),1) for k in needed)
            if key in {'tool_scope_matches','delegation_subject_matches'}:
                good=good and _nonempty(ctx.get('call_id')) and proof.get('call_id')==ctx['call_id']
            if good: eligible.append(proof)
            else: diagnostics.append({'fact':key,'status':'rejected_proof','checkpoint':obj['checkpoint']})
        if not eligible: continue
        latest=max(p['event_seq'] for p in eligible)
        newest=[p for p in eligible if p['event_seq']==latest]
        normalized=[_typed(key,p['value']) for p in newest]
        value=_typed(key,obj['facts'].get(key))
        versions=tuple(k for k in ('invoice_version','vendor_version')
                       if ctx.get('invoice_id' if k=='invoice_version' else 'vendor_id') is not None) if key in _STATE else ()
        valid=(value is not None and all(v is not None and type(v) is type(value) and v==value for v in normalized)
               and all(_nonempty(ctx.get(k)) and all(p.get(k)==ctx[k] for p in newest) for k in versions))
        if not valid:
            diagnostics.append({'fact':key,'status':'latest_unbound_conflicting_or_stale',
                                'checkpoint':obj['checkpoint'],'event_seq':latest})
            continue
        values[key]=value; accepted[key]=newest[0]
    if (values.get('binding_hold') is True and 'human_cleared' in accepted
        and accepted['human_cleared']['event_seq'] <= accepted['binding_hold']['event_seq']):
        values.pop('human_cleared',None); accepted.pop('human_cleared',None)
    evidence=[{'fact':k,'value':str(v) if isinstance(v,Decimal) else v,
               'record_id':accepted[k]['record_id'],'event_seq':accepted[k]['event_seq'],
               'source':accepted[k]['source'],'checkpoint':obj['checkpoint']}
              for k,v in values.items()]
    return values,accepted,evidence+diagnostics


def _selection(policy):
    if policy is None: policy={'profile':'A'}
    if isinstance(policy,str): policy={'profile':policy}
    if not isinstance(policy,dict): return None
    profile=policy.get('profile','A')
    if not isinstance(profile,str) or profile not in _REGISTRY['profiles']: return None
    # Full immutable registry may be passed; overrides of contract controls are not accepted.
    for key in set(policy)-{'profile','enabled_requirements'}:
        if key not in _REGISTRY or policy[key]!=_REGISTRY[key]: return None
    enabled=policy.get('enabled_requirements',_REGISTRY['profiles'][profile])
    if not isinstance(enabled,list) or any(not isinstance(k,str) or k not in _REGISTRY['profiles'][profile] for k in enabled): return None
    return set(enabled)


def guard(observation,policy=None):
    """A/B profile string or immutable registry plus profile/enabled_requirements.

    A is the default. Ablations may enable only predeclared IDs from that profile.
    """
    started=perf_counter(); requirements=[]; reasons=[]; evidence=[]
    p5=isinstance(observation,dict) and observation.get('checkpoint')=='P5'
    enabled=_selection(policy)
    def result(decision):
        return dict(decision=decision,reasons=list(dict.fromkeys(reasons)),evidence=evidence,
                    timing_ms=max(0.,(perf_counter()-started)*1000),stop=decision!='ALLOW' and not p5,
                    requirements=requirements)
    if enabled is None or not _shape(observation):
        reasons.append('missing_or_invalid:policy' if enabled is None else 'missing_or_invalid:observation')
        return result('UNKNOWN')
    obj=observation; cp=obj['checkpoint']; ctx=obj.get('context') or {}; prop=obj['proposal']; tool=prop.get('tool')
    facts,proofs,evidence=_proofs(obj)
    def truth(name):
        return 'unknown' if name not in facts else 'satisfied' if facts[name] is True else 'violated'
    def combine(states):
        return 'violated' if 'violated' in states else 'unknown' if 'unknown' in states else 'satisfied'
    def required(*names): return combine([truth(k) for k in names])
    def known_equal(key,value):
        return 'unknown' if key not in facts else 'satisfied' if facts[key]==value else 'violated'
    def actor(expected):
        current=ctx.get('technical_actor')
        return 'unknown' if current not in _REGISTRY['actor_matrix'] else 'satisfied' if current==expected else 'violated'
    def legacy():
        projection={'checkpoint':cp,'event_seq':obj['event_seq'],'proposal':dict(prop),'facts':{},'provenance':{}}
        for key in _PAYMENT & facts.keys():
            value=facts[key]; projection['facts'][key]=str(value) if isinstance(value,Decimal) else value
            proof=dict(proofs[key]); proof['source']='native_tool' if proof['source']=='server_context' else proof['source']
            projection['provenance'][key]=[proof]
        raw=_v3['guard'](projection,_REGISTRY['payment_policy'])
        if raw['decision']!='ALLOW': reasons.extend(raw['reasons'])
        return {'ALLOW':'satisfied','BLOCK':'violated','UNKNOWN':'unknown'}[raw['decision']]
    for rule in _REGISTRY['requirements']:
        rid=rule['id']; state='not_applicable'
        if rid not in enabled or cp not in rule['checkpoints']:
            requirements.append({'id':rid,'state':state}); continue
        if rid=='A01':
            state=combine([truth('session_valid'), 'satisfied' if all(_nonempty(ctx.get(k)) for k in
                ('record_id','session_id','user_id','namespace')) and ctx.get('origin_portal') in {'vendor','admin'} else 'unknown'])
        elif rid=='A02':
            names=[]
            if not obj.get('context'): state='unknown'
            else:
                if ctx.get('vendor_id') is not None: names.append('vendor_in_scope')
                if ctx.get('invoice_id') is not None: names.append('invoice_in_scope')
                if ctx.get('vendor_id') is not None and ctx.get('invoice_id') is not None: names.append('invoice_vendor_matches')
                if ctx.get('attachment_file_ids'): names.append('attachments_in_scope')
                state=required(*names) if names else 'not_applicable'
                invoice_tools={'get_invoice_details','get_invoice_for_payment','update_invoice_status',
                               'flag_invoice_for_review','process_payment'}
                vendor_tools={'get_vendor_details','get_vendor_invoices','get_vendor_payment_summary',
                              'get_vendor_contact_info','get_vendor_compliance_docs','get_vendor_activity_report',
                              'get_vendor_risk_profile','update_vendor_status','update_vendor_risk'}
                if (ctx.get('attachment_file_ids') is None
                    or tool in invoice_tools and ctx.get('invoice_id') is None
                    or tool in vendor_tools and ctx.get('vendor_id') is None):
                    state=combine([state,'unknown'])
        elif rid=='A03':
            matrix=_REGISTRY['actor_matrix'].get(ctx.get('technical_actor'))
            if not matrix or not tool: permitted='unknown'
            else:
                mcp=next((server for server,tools in _REGISTRY['mcp_tool_registry'].items() if tool in tools),None)
                permitted='satisfied' if tool in matrix['native'] or mcp in matrix['mcp_servers'] else 'violated'
            state=combine([permitted,truth('tool_scope_matches')])
        elif rid=='A04':
            complete=ctx.get('delegation_succeeded')
            state=combine([truth('delegation_subject_matches'),
                'unknown' if complete is None else 'satisfied' if complete else 'violated',
                'satisfied' if ctx.get('delegated_actor') in {'onboarding','invoice','fraud','payments','communication'}
                and _nonempty(ctx.get('delegation_call_id')) and _nonempty(ctx.get('workflow_id')) else 'unknown'])
        elif rid=='A05' and tool=='update_invoice_status':
            states=[actor('invoice')]
            target=prop.get('target_status')
            states.append('unknown' if target is None else 'satisfied' if target in _REGISTRY['native_enums']['invoice_mutation_status'] else 'violated')
            states.append('unknown' if 'invoice_status' not in facts else 'violated' if facts['invoice_status'] in {'approved','rejected','paid'} else 'satisfied')
            if target=='approved':
                amount=facts.get('invoice_amount')
                states.extend(['unknown' if amount is None else 'satisfied' if 0<amount<=Decimal(_REGISTRY['payment_policy']['maximum_invoice_amount']) else 'violated',known_equal('vendor_status','active')])
                states.append('unknown' if 'binding_hold' not in facts else 'satisfied' if facts['binding_hold'] is False else truth('human_cleared'))
            state=combine(states)
        elif rid=='A06' and tool in {'update_vendor_status','update_vendor_risk'}:
            states=[actor('onboarding' if tool=='update_vendor_status' else 'fraud')]
            fields={'target_status':'vendor_status','trust_level':'trust_level','risk_level':'risk_level'} if tool=='update_vendor_status' else {'risk_level':'risk_level'}
            for key,enum in fields.items():
                states.append('unknown' if prop.get(key) is None else 'satisfied' if prop[key] in _REGISTRY['native_enums'][enum] else 'violated')
            if tool=='update_vendor_risk' and any(prop.get(k) is not None for k in ('target_status','trust_level')): states.append('violated')
            state=combine(states)
        elif rid=='A07' and tool=='process_payment':
            state=combine([actor('payments'),known_equal('invoice_status','approved'),truth('payment_reference_matches_transfer'),
                           'satisfied' if _nonempty(ctx.get('payment_reference')) else 'unknown',
                           'violated' if prop.get('target_status') is not None else 'satisfied'])
        elif rid=='A08' and tool=='finstripe__create_transfer': state=legacy()
        elif rid=='A09' and ((cp=='P2' and tool=='delegate_to_fraud') or (cp=='P3' and tool=='update_invoice_status')): state=legacy()
        elif rid=='B01' and tool=='finstripe__create_transfer':
            binding=ctx.get('approval'); keys=('invoice_id','vendor_id','account_ref','invoice_version','vendor_version')
            if not binding or any(ctx.get(k) is None for k in keys) or _amount(prop.get('amount')) is None or not _nonempty(prop.get('currency')): state='unknown'
            else:
                valid=all(binding[k]==ctx[k] for k in keys) and _amount(binding['amount'])==_amount(prop['amount']) and binding['currency']==prop['currency'].strip().upper() and binding['approved_seq']<obj['event_seq']
                state='satisfied' if valid else 'violated'
        elif rid=='B02':
            if _nonempty(ctx.get('workflow_id')):
                claim=ctx.get('claim')
                if not claim: state='unknown'
                else:
                    key=[ctx.get('namespace'),'invoice',ctx.get('invoice_id'),ctx.get('vendor_id')] if ctx.get('invoice_id') is not None else [ctx.get('namespace'),'vendor',ctx.get('vendor_id')]
                    try: matches=json.loads(claim['key']) in (key,[ctx.get('namespace'),'vendor',ctx.get('vendor_id')])
                    except (ValueError,TypeError): matches=False
                    state='satisfied' if (matches and claim['owner_workflow_id']==ctx['workflow_id'] and claim['state']=='active' and claim['acquired_seq']<obj['event_seq']) else 'violated'
            elif (tool=='start_workflow' or cp=='P4' or ctx.get('technical_actor') in
                  {'orchestrator','onboarding','invoice','fraud','payments','communication'}): state='unknown'
        elif rid=='B03' and (tool=='delegate_to_system_maintenance' or tool in _REGISTRY['mcp_tool_registry']['systemutils']):
            state='unknown' if ctx.get('origin_portal') not in {'vendor','admin'} else 'violated' if ctx['origin_portal']=='vendor' else 'satisfied'
        requirements.append({'id':rid,'state':state})
        if state in {'violated','unknown'}: reasons.append(rid+':'+state)
    for entry in evidence:
        entry['requirement_ids']=[r['id'] for r in _REGISTRY['requirements'] if entry.get('fact') in r['facts']]
    if p5:
        legacy(); reasons.append('post_payment_detection_only'); return result('UNKNOWN')
    states=[r['state'] for r in requirements]
    decision='BLOCK' if 'violated' in states else 'UNKNOWN' if 'unknown' in states else 'ALLOW'
    if decision=='ALLOW': reasons.append('payment_obligations_observed' if cp=='P4' else 'provisional_early_allow')
    return result(decision)
