"""v4.3 accepts source-bound evidence separately from session permissions.

Only the trusted repair producer may supply this internal research envelope.
Business predicates, thresholds, applicability and A/B profiles are frozen v4.2.
The change is evidence acceptance, not a claim of authenticating arbitrary JSON.
"""
from copy import deepcopy
from types import FunctionType
from experiments.local_guards_v4 import guard as original
from experiments.local_guards_v4_followup import guard as prior


def _shape(observation):
    if not isinstance(observation,dict) or not isinstance(observation.get('repair_evidence'),dict):
        return False
    if not isinstance(observation['repair_evidence'].get('records'),dict):
        return False
    plain={k:v for k,v in observation.items() if k!='repair_evidence'}
    return prior._shape(plain)


def _proofs(observation):
    facts,accepted,evidence={},{},[]
    repair=observation['repair_evidence']
    context=observation.get('context') or {}
    for key,record in (repair.get('records') or {}).items():
        if key not in observation['facts'] or not isinstance(record,dict):
            continue
        value=original._typed(key,record.get('value'))
        subject=record.get('subject')
        if not isinstance(subject,dict) or not isinstance(record.get('source'),str):
            continue
        good=(prior.origin_valid(key,record) and value is not None and record.get('current') is True
              and type(record.get('event_seq')) is int and 0<=record['event_seq']<observation['event_seq']
              and record.get('source') in original._sources(key)
              and all(original._nonempty(record.get(k)) for k in ('operation','record_id','source_ref'))
              and all(subject.get(k)==context[k] for k in ('invoice_id','vendor_id') if k in context)
              and original._typed(key,observation['facts'][key])==value)
        if key=='session_valid':
            good=good and record.get('operation')=='session_validate'
        if key in {'tool_scope_matches','delegation_subject_matches'}:
            good=good and original._nonempty(context.get('call_id')) and record.get('target_call_id')==context['call_id']
        if key=='delegation_subject_matches':
            good=good and all(original._nonempty(context.get(k)) and record.get(k)==context[k]
                for k in ('parent_workflow_id','delegated_workflow_id','delegation_call_id'))
        if key in original._STATE:
            needed=('vendor_id',) if key=='vendor_status' else ('invoice_id',) if key in {'binding_hold','human_cleared'} else ('invoice_id','vendor_id')
            good=good and all(type(context.get(k)) is int and subject.get(k)==context[k] for k in needed)
        if key in {'human_approved','human_cleared'}:
            good=good and record.get('evidence_kind')=='independent_registry'
        if record.get('evidence_kind')=='tool_result':
            good=good and original._nonempty(record.get('source_call_id'))
        if key=='invoice_currency':
            good=good and record.get('evidence_kind') in {'declared_fixture','independent_registry'}
        if not good:
            evidence.append({'fact':key,'status':'rejected_source_subject_time_or_freshness'})
            continue
        facts[key]=value
        accepted[key]={k:record[k] for k in ('source','operation','event_seq','record_id')}
        accepted[key].update(subject_matches=True,value=record['value'])
        evidence.append(dict(accepted[key],fact=key,value=record['value'],source_ref=record['source_ref']))
    if ('binding_hold' in accepted and facts.get('binding_hold') is True
            and 'human_cleared' in accepted
            and accepted['human_cleared']['event_seq']<=accepted['binding_hold']['event_seq']):
        facts.pop('human_cleared',None)
        accepted.pop('human_cleared',None)
    return facts,accepted,evidence


_globals=dict(prior.guard.__globals__,_shape=_shape,_proofs=_proofs)
guard=FunctionType(prior.guard.__code__,_globals,'guard',prior.guard.__defaults__)


def execute_until_stop(actions, checker=guard):
    """Scenario executor for local STOP correctness controls, without a model."""
    effects=[]
    for observation,effect in actions:
        decision=checker(observation)
        if decision['stop']:
            return decision,effects
        effect()
        effects.append(observation['event_seq'])
    return None,effects
