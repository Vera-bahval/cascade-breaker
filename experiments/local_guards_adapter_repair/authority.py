"""Read verified callable/class bindings without importing the FinBot runtime."""
import ast
from hashlib import sha256
from pathlib import Path

from .evidence import pair_events

CLASSES={'OrchestratorAgent':'orchestrator','VendorOnboardingAgent':'onboarding',
         'InvoiceAgent':'invoice','FraudComplianceAgent':'fraud',
         'PaymentsAgent':'payments','CommunicationAgent':'communication'}


def code_authority(runner, orchestrator, expected):
    payloads={'runner':runner,'orchestrator':orchestrator}
    if any(sha256(data).hexdigest()!=expected[key] for key,data in payloads.items()):
        raise ValueError('callable source hash mismatch')
    functions={}
    for fn in ast.walk(ast.parse(runner)):
        if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):
            roles={CLASSES[kw.value.id] for call in ast.walk(fn) if isinstance(call,ast.Call)
                   for kw in call.keywords if kw.arg=='agent_class' and isinstance(kw.value,ast.Name)
                   and kw.value.id in CLASSES}
            if len(roles)==1:
                functions[fn.name]=roles.pop()
    delegations={}
    for fn in ast.walk(ast.parse(orchestrator)):
        if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)) and fn.name.startswith('delegate_to_'):
            called={call.func.id for call in ast.walk(fn) if isinstance(call,ast.Call)
                    and isinstance(call.func,ast.Name) and call.func.id in functions}
            if len(called)==1:
                name=called.pop()
                delegations[fn.name]={'callable':name,'actor':functions[name]}
    return {'functions':functions,'delegations':delegations,'source_hashes':dict(expected)}


def actor_at(row, authority):
    """Root callable is admitted only by a separately verified launcher binding."""
    events=row['raw_context']['events']
    pairs,pending=pair_events(events)
    frames={f['index']:f for f,_ in pairs if f}
    frames.update({f['index']:f for f in pending})
    roles={}
    for index,frame in sorted(frames.items()):
        parent=frame['parent']
        role=(None if frame.get('legacy_executed') else authority['functions'].get('run_orchestrator_agent')) if parent is None else roles.get(parent)
        roles[index]=role
        if parent is not None and frames[parent]['tool'] in authority['delegations']:
            if roles.get(parent)=='orchestrator':
                roles[index]=authority['delegations'][frames[parent]['tool']]['actor']
    active=pending[-1] if pending else None
    cp=row['checkpoint']
    child=None
    if cp in ('P2','P2_afterFraud'):
        matched=[(f,e) for f,e in pairs if f and f['tool'].startswith('delegate_to_')
                 and e['event_seq']==((row.get('anchor') or {}).get('return_event') or {}).get('event_seq',row['event_seq']-1)]
        if len(matched)==1:
            active=matched[0][0]
            mapping=authority['delegations'].get(active['tool'])
            if mapping and roles.get(active['index'])=='orchestrator':
                child=dict(mapping,event_seq=row['event_seq'],source_hash=authority['source_hashes']['runner'],
                           source_event_seq=active['event']['event_seq'])
    if active:
        role=roles.get(active['index'])
        delegated=authority['delegations'].get(active['tool'])
        if cp not in ('P2','P2_afterFraud') and delegated and role=='orchestrator':
            role=delegated['actor']
    else:
        role=authority['functions'].get('run_orchestrator_agent')
    if not role:
        return None
    return {'actor':role,'event_seq':row['event_seq'],'delegated':child,
            'callable':authority.get('root_callable','run_orchestrator_agent') if role=='orchestrator' else next((name for name,actor in authority['functions'].items() if actor==role),'unresolved'),'source_hash':authority['source_hashes']['runner'],
            'source_hashes':authority['source_hashes'],
            'lineage':[{'event_seq':f['event']['event_seq'],'tool':f['tool']}
                       for f in pending if f['tool'].startswith('delegate_to_')]}
