"""Predeclared numeric/categorical features over the common observation schema.

No outcome, family, correctness verdict, textual attack identifier, or old derived
state is an input. Missing fields stay missing. Pairwise equality is an observable
relationship, never an inferred permission or policy verdict.
"""
from __future__ import annotations
import math
from .v2_inputs import SHAPES, ARGUMENTS, LIST_SLOTS

NUMERIC={'amount','version','expected_version','expected_vendor_version','invoice_version','vendor_version','limit_major','rate'}
BOOLEAN={'review_completed','flagged_for_review','human_cleared','signature_verified','exactly_once_keys','enforce_expected_versions','transfer_amount_matches_invoice','recipient_matches_authorized_account','completed_transfer_exists','approved','hold_cleared','raw_proposed_amount_equals_recorded_invoice_amount','raw_account_text_equal','source_reported_completed_transfer_exists','source_reported_hold_cleared'}
IDENTITY={'tenant_id','vendor_id','invoice_id','registry_id','receipt_id','idempotency_key','request_key','request_fingerprint'}
STATUS=('completed','pending','failed','processing','success','unknown','posted','reserved','released','reversed')
KINDS=('debit','credit','refund','settlement','authorization')


def numeric(value):
    if value is None:return None
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (TypeError,ValueError):return None


def tabular_features(common):
    observations=common['observations'];result={};objects={}
    def add_object(path,value,fields):
        value=value if isinstance(value,dict) else {}
        objects[path]=value
        for key in fields:
            v=value.get(key)
            if key in IDENTITY:
                result[path+'.'+key+'.observed']=None if v is None else 1.
            elif key in NUMERIC or key in BOOLEAN:result[path+'.'+key]=numeric(v)
            elif key not in ('arguments','description','description_writer'):
                result[path+'.'+key]=None if v is None else str(v)
    for slot,fields in SHAPES.items():
        value=observations.get(slot)
        if slot in LIST_SLOTS:
            items=value if isinstance(value,list) else None
            result[slot+'.count']=None if items is None else float(len(items))
            for status in STATUS:
                result[slot+'.status.'+status+'.count']=None if items is None else float(sum(str(r.get('status','unknown')).lower()==status for r in items))
            for kind in KINDS:
                result[slot+'.kind.'+kind+'.count']=None if items is None else float(sum(str(r.get('kind','')).lower()==kind for r in items))
            invoice=observations.get('invoice') or {}
            for identity in ('tenant_id','vendor_id','invoice_id'):
                reference=invoice.get(identity)
                result[slot+'.'+identity+'.same_invoice.count']=None if items is None or reference is None else float(sum(r.get(identity)==reference for r in items if r.get(identity) is not None))
                result[slot+'.'+identity+'.unknown.count']=None if items is None else float(sum(r.get(identity) is None for r in items))
            amounts=[numeric(r.get('amount')) for r in items or []]
            valid=[a for a in amounts if a is not None]
            for stat in ('sum','min','max'):
                result[slot+'.amount.'+stat]=None if items is None or len(valid)!=len(amounts) else (sum(valid) if stat=='sum' else (min(valid) if stat=='min' and valid else max(valid) if valid else 0.))
            completed=None if items is None else [r for r in items if str(r.get('status','')).lower()=='completed']
            paid=[numeric(r.get('amount')) for r in completed or []]
            result[slot+'.completed.amount.sum']=None if completed is None or any(a is None for a in paid) else sum(paid)
        else:add_object(slot,value,fields)
    proposal=observations.get('proposal') or {}
    add_object('proposal.arguments',proposal.get('arguments'),ARGUMENTS)
    # All exact relationships have fixed positions, independent of observed values.
    for left,right in (('invoice','proposal.arguments'),('vendor','proposal.arguments'),('invoice','vendor'),('validation','invoice'),('validation','vendor')):
        a,b=objects[left],objects[right]
        for key in ('tenant_id','vendor_id','invoice_id','currency','unit','bank_account','version'):
            x,y=a.get(key),b.get(key)
            result[f'relation.{left}.{right}.{key}.equal']=None if x is None or y is None else float(x==y)
    invoice=objects['invoice'];action=objects['proposal.arguments']
    original,proposed=numeric(invoice.get('amount')),numeric(action.get('amount'))
    result['amount.proposed_minus_original']=None if original is None or proposed is None else proposed-original
    result['amount.proposed_over_original']=None if original in (None,0) or proposed is None else proposed/original
    for boundary in (5000,10000,50000):result[f'amount.distance_{boundary}']=None if proposed is None else proposed-boundary
    result['history.observed_event_count']=float(len(common.get('history',[])))
    return result


def feature_types():
    # Generate every position without relying on values of any experiment case.
    from .v2_inputs import SLOTS
    dummy={'observations':{k:None for k in SLOTS},'history':[]}
    values=tabular_features(dummy);result={}
    for k in values:
        tail=k.rsplit('.',1)[-1]
        result[k]='numeric' if (tail in NUMERIC or tail in BOOLEAN or tail in ('count','observed','sum','min','max','equal') or k.startswith(('amount.','history.'))) else 'categorical'
    return result
