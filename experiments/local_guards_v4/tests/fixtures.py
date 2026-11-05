"""Declared synthetic producer; no archive or model-authored provenance."""
from copy import deepcopy


def observation(checkpoint='P0', tool=None, actor='invoice', **facts):
    context = dict(record_id='snapshot', session_id='session', user_id='user',
                   namespace='ns', workflow_id='work', parent_workflow_id=None,
                   origin_portal='admin', technical_actor=actor, vendor_id=2,
                   invoice_id=3, current_vendor_id=2, attachment_file_ids=[],
                   call_id='call', invoice_version='i1', vendor_version='v1',
                   account_ref='opaque', payment_reference='transfer')
    obj = dict(schema_version=4, checkpoint=checkpoint, event_seq=10,
               proposal={}, facts={}, provenance={}, context=context)
    if tool:
        obj['proposal']['tool'] = tool
    for name, value in dict(session_valid=True, vendor_in_scope=True,
                            invoice_in_scope=True, invoice_vendor_matches=True,
                            tool_scope_matches=True, **facts).items():
        put(obj, name, value)
    return obj


def put(obj, key, value, seq=2, **changes):
    source = ('independent_registry' if key in {'human_approved','human_cleared'}
              else 'server_context' if key in {'session_valid','tool_scope_matches',
                   'delegation_subject_matches'} else 'initial_fixture')
    proof = {name: obj['context'].get(name) for name in
             ('namespace','session_id','workflow_id','vendor_id','invoice_id',
              'invoice_version','vendor_version','call_id')}
    proof.update(source=source, operation='session_validate' if key == 'session_valid'
                 else 'synthetic_structured_read', event_seq=seq,
                 subject_matches=True, record_id='proof-'+key, value=value)
    proof.update(changes)
    obj['facts'][key] = value
    obj['provenance'].setdefault(key, []).append(proof)
    return obj


def payment():
    obj = observation('P4', 'finstripe__create_transfer', 'payments')
    obj['proposal'].update(amount='12000', currency='usd')
    for key, value in dict(invoice_amount='12000', invoice_currency='USD',
        invoice_status='approved', vendor_status='active', fraud_review_completed=True,
        binding_hold=False, amount_matches_invoice=True, recipient_matches_authorized=True,
        human_approved=True, prior_completed_transfers=0).items():
        put(obj,key,value)
    return obj
