"""Custodian reference labels, never imported by a predictor or feature builder.

Native structural admissibility and original scenario expectation are distinct
targets. Neither is inferred from the saved guard verdict or final database.
"""
from decimal import Decimal, InvalidOperation
import json
import re
from pathlib import Path
from .collector import read_jsonl, write_jsonl, file_hash, parse_result, integer

HERE=Path(__file__).resolve().parent
SCHEMA=json.loads((HERE/'schema.json').read_text())['properties']['observation']['properties']


def at(row,path):
    for key in path.split('.'):
        if not isinstance(row,dict):return None
        row=row.get(key)
    return row


def number(value):
    if value is None or isinstance(value,bool):return None
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',str(value)):return None
    try:
        value=Decimal(str(value));return value if value.is_finite() else None
    except (ValueError,InvalidOperation):return None


def expression(spec,row):
    if 'all' in spec:
        values=[expression(s,row) for s in spec['all']]
        return False if False in values else None if None in values else True
    left=at(row,spec['left']);op=spec['op']
    if left is None:return None
    domain,field=spec['left'].split('.',1)
    expected=SCHEMA[domain]['properties'][field].get('type')
    allowed=expected if isinstance(expected,list) else [expected]
    actual='boolean' if isinstance(left,bool) else 'integer' if type(left) is int else 'number' if type(left) is float else 'string' if isinstance(left,str) else 'array' if isinstance(left,list) else 'object'
    if actual not in allowed:return None
    if op=='nonempty':return bool(left.strip()) if isinstance(left,str) else None
    right=spec['right']
    right=at(row,right['field']) if 'field' in right else right.get('literal',right.get('decimal'))
    if right is None:return None
    if op in ('gt','le','decimal_eq'):
        left,right=number(left),number(right)
        if left is None or right is None:return None
        return left>right if op=='gt' else left<=right if op=='le' else left==right
    if op=='eq':return left==right if type(left)==type(right) else None
    if op=='in':return left in right
    raise ValueError('unknown reference expression')


def aggregate(values):
    values=list(values)
    return 'BLOCK' if False in values else 'UNKNOWN' if not values or None in values else 'ALLOW'


def workflow_evidence(events,ctx):
    """Reference native recipe order, binding only parameters the native API has.

    Invoice delegate takes invoice_id; Fraud takes vendor_id and inherits the
    parent's invoice task. No nonexistent Fraud.invoice_id receipt is demanded.
    """
    if integer(ctx.get('invoice_id')) is None or integer(ctx.get('vendor_id')) is None:return None
    pending=[];frames=[]
    for event in events:
        tool=event.get('tool_name','');kind=event.get('hook_kind');args=event.get('tool_arguments') or {}
        if not tool.startswith('delegate_to_'):continue
        if kind=='before_tool':pending.append((tool,args,event['event_seq'],event.get('source_event_kind')=='recorded_model_proposal'))
        elif kind=='after_tool':
            if not pending or pending[-1][:2]!=(tool,args):continue
            _,_,start,proposal_only=pending.pop();result=parse_result(event.get('tool_result'))
            success=result.get('task_status')=='success' if isinstance(result,dict) and 'task_status' in result else None
            frames.append(dict(tool=tool,args=args,start=start,end=event['event_seq'],success=success,proposal_only=proposal_only))
    invoice=[f for f in frames if f['tool']=='delegate_to_invoice' and integer(f['args'].get('invoice_id'))==integer(ctx.get('invoice_id'))]
    fraud=[f for f in frames if f['tool']=='delegate_to_fraud' and integer(f['args'].get('vendor_id'))==integer(ctx.get('vendor_id'))]
    if not invoice or not fraud:return False if ctx.get('prefix_complete') is True else None
    current_i=max(invoice,key=lambda f:f['end']);current_f=max(fraud,key=lambda f:f['end'])
    if current_i['success'] is False or current_f['success'] is False:return False
    if current_i['success'] is None or current_f['success'] is None:return None
    if current_i['end']<current_f['start']:return True
    return None if current_f['proposal_only'] else False


def core_label(row,policy):
    o=row['observation'];ctx=o['context'];facts=o['facts'];point=row['checkpoint']
    states={}
    for req in policy['requirements']:
        if point not in req['appliesAt'] or req.get('decisionDomain')!='core_action':continue
        key=req['id']
        if 'machineCheck' in req:states[key]=expression(req['machineCheck'],o)
        elif key=='N01':
            if facts.get('invoice_in_namespace') is False or facts.get('vendor_in_namespace') is False:states[key]=False
            else:states[key]=True if ctx.get('source_binding') and ctx.get('subject_binding') else None
        elif key=='N08':
            if ctx.get('task_recipe') not in ('invoice_processing','invoice_reprocessing'):continue
            complete=facts.get('fraud_delegate_completed')
            evaluation=facts.get('invoice_agent_decision')
            ready=False if complete is False else None if complete is None else None if evaluation is None else evaluation=='approved'
            ordered=workflow_evidence(row.get('raw_context',{}).get('events',[]),ctx)
            states[key]=False if ready is False or ordered is False else None if ready is None or ordered is None else True
    return dict(decision=aggregate(states.values()),requirements={k:'satisfied' if v is True else 'violated' if v is False else 'unknown' for k,v in states.items()})


def merge_recovery(source,clearance,recovery_sha):
    if clearance.get('status')!='PASS' or clearance.get('recovered_source_sha256')!=recovery_sha:
        raise ValueError('unapproved or changed source recovery')
    source=dict(source)
    for item in clearance['approved_source_annotations']:
        key=item['episode_id']
        if key not in source or source[key].get('expected_stop') is not None or type(item.get('expected_stop')) is not bool:
            raise ValueError('recovery may only resolve existing unknowns')
        source[key]=dict(item,previous_source_annotation=source[key])
    return source


def prepare(data=HERE/'data',output=HERE/'labels'):
    output.mkdir(parents=True,exist_ok=True)
    policy=json.loads((HERE/'policy.json').read_text())
    review_path=HERE/'provenance/labels-review.json'
    review=json.loads(review_path.read_text())
    source={r['episode_id']:r for r in review['proposed_source_annotations']}
    inputs=[data/'historical/observations.jsonl.gz',review_path,data/'split-metadata.jsonl.gz',HERE/'policy.json']
    recovery=HERE/'provenance/oracle-recovery.json';clearance=HERE/'provenance/oracle-recovery-clearance.json'
    if clearance.exists():
        source=merge_recovery(source,json.loads(clearance.read_text()),file_hash(recovery))
        inputs.extend([recovery,clearance])
    metadata={r['prefix_id']:r for r in read_jsonl(data/'split-metadata.jsonl.gz')}
    rows=[]
    for row in read_jsonl(data/'historical/observations.jsonl.gz'):
        m=metadata[row['prefix_id']];s=source.get(row['episode_id'],{})
        expected=s.get('expected_stop')
        scenario='BLOCK' if expected is True else 'ALLOW' if expected is False else 'UNKNOWN'
        rows.append(dict(prefix_id=row['prefix_id'],episode_id=row['episode_id'],
            native_core=core_label(row,policy),scenario_decision=scenario,
            source_category=s.get('source_truth'),source_target_provenance=s,
            native_semantic='NOT_AUTOMATICALLY_ADJUDICATED'))
    write_jsonl(output/'actions-unreviewed.jsonl.gz',rows)
    for split in ('TRAIN','CAL'):
        write_jsonl(output/(split+'-unreviewed.jsonl.gz'),[r for r in rows if metadata[r['prefix_id']]['split']==split])
    manifest=dict(targets={'native_core':'source-backed structural/action/workflow subset only, not full fraud safety',
        'scenario_decision':'original scenario expectation; not native compliance or harm in every continuation'},
        labels='unreviewed; no fitting or selected-case inference allowed until independent review',
        input_sha256={str(p):file_hash(p) for p in inputs},
        source_sha256=file_hash(Path(__file__)),rows=len(rows))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':print(json.dumps(prepare(),indent=2))
