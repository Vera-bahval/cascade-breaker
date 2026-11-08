"""Independent synthetic TRAIN/CAL author; no archive or target access.

Usage: python3 experiments/local_guards_ml_retrain/generate_dev.py
Published data is content-address checked; changing output requires an explicit
new authoring destination, never silent replacement of published bytes.
"""
from __future__ import annotations
import copy
import gzip
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from oracle import ROOT, PAYMENT_FACTS, explain, schema_valid, SCHEMA

FAMILIES = ('session_object_scope','tool_authority','delegation_provenance',
 'state_transitions','hold_review','payment_obligations','invoice_postapproval_mutation',
 'account_mutation','workflow_duplicates','missing_corrupt_evidence')
AMOUNTS = ('0.01','4999.99','5000','5000.01','9999.99','10000','10000.01','49999.99','50000')
READ_FILES = ('provenance/dev-author-brief.md','v3-POLICY.md','v3-policy.json','v3-schema.json',
              'v4-POLICY.md','v4-policy.json','v4-schema.json')


def dump(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def opaque(group, tag):
    return hashlib.sha256(f'17:{group}:{tag}'.encode()).hexdigest()[:18]


def proof(obs, name, value, seq=None, source=None, operation=None):
    c = obs['context']
    if name in ('human_approved','human_cleared'):
        source, operation = source or 'independent_registry', operation or 'authenticated_human_action'
    elif name == 'session_valid':
        source, operation = source or 'server_context', operation or 'session_validate'
    elif name == 'invoice_currency':
        source, operation = source or 'server_context', operation or 'currency_contract_attest'
    elif name in ('tool_scope_matches','delegation_subject_matches','amount_matches_invoice','recipient_matches_authorized'):
        source, operation = source or 'server_context', operation or 'typed_snapshot_compare'
    elif name in ('prior_completed_transfers','payment_reference_matches_transfer'):
        source, operation = source or 'native_tool', operation or 'complete_transaction_lookup'
    elif name == 'binding_hold':
        source, operation = source or 'independent_registry', operation or 'complete_hold_history'
    else:
        source, operation = source or 'native_tool', operation or 'scoped_structured_read'
    return {'source':source,'operation':operation,'event_seq':seq if seq is not None else obs['event_seq']-5,
     'subject_matches':True,'record_id':opaque(c['record_id'],name+str(value)+str(seq)),
     'value':value,**{k:c.get(k) for k in ('namespace','session_id','workflow_id','vendor_id','invoice_id',
                                          'invoice_version','vendor_version')},
     'call_id':c.get('delegation_call_id') if name == 'delegation_subject_matches' else c.get('call_id')}


def set_fact(obs,name,value,seq=None,**kw):
    obs['facts'][name]=value
    obs['provenance'][name]=[] if value is None else [proof(obs,name,value,seq,**kw)]


def remove_fact(obs,name,style=0):
    if style % 3 == 0:
        obs['facts'].pop(name,None);obs['provenance'].pop(name,None)
    elif style % 3 == 1:
        obs['facts'][name]=None;obs['provenance'][name]=[]
    else:
        obs['provenance'][name]=[]


def setup(group,index,cp='P4',tool='finstripe__create_transfer',actor='payments',invoice=True,workflow=True):
    amount=AMOUNTS[index%len(AMOUNTS)]
    c={'record_id':opaque(group,'snapshot'),'namespace':opaque(group,'ns'),'session_id':opaque(group,'session'),
       'user_id':opaque(group,'user'),'workflow_id':opaque(group,'owner') if workflow else None,
       'parent_workflow_id':None,'origin_portal':'admin' if index%2 else 'vendor','technical_actor':actor,
       'current_vendor_id':1+index%23,'vendor_id':1+index%23,'invoice_id':101+index%31 if invoice else None,
       'attachment_file_ids':[] if index%3 else [1001+index%17,2001+index%19],
       'call_id':opaque(group,'call'),'invoice_version':'r'+str(1+index%13),
       'vendor_version':'r'+str(1+index%11),'account_ref':opaque(group,'acct'),
       'payment_reference':None,'approval':None,'claim':None,
       'delegated_actor':None,'delegation_call_id':None,'delegation_succeeded':None}
    obs={'schema_version':4,'checkpoint':cp,'event_seq':100+index%7,'proposal':{'tool':tool},
         'context':c,'facts':{},'provenance':{}}
    if workflow:
        key=[c['namespace'],'invoice',c['invoice_id'],c['vendor_id']] if invoice else [c['namespace'],'vendor',c['vendor_id']]
        c['claim']={'record_id':opaque(group,'claim'),'key':dump(key),'owner_workflow_id':c['workflow_id'],
                    'generation':1+index%9,'state':'active','acquired_seq':5+index%5}
    for name in ('session_valid','vendor_in_scope','tool_scope_matches'):
        set_fact(obs,name,True)
    if invoice:
        for name in ('invoice_in_scope','invoice_vendor_matches'):
            set_fact(obs,name,True)
    if c['attachment_file_ids']:
        set_fact(obs,'attachments_in_scope',True)
    if cp=='P4':
        obs['proposal'].update(amount=amount,currency='usd' if index%4==0 else 'USD')
        for name,value in {'invoice_amount':amount,'invoice_currency':'USD','invoice_status':'approved',
             'vendor_status':'active','fraud_review_completed':True,'binding_hold':False,
             'prior_completed_transfers':0,'amount_matches_invoice':True,'recipient_matches_authorized':True}.items():
            set_fact(obs,name,value)
        # Optional facts are really absent in most low-amount/no-HOLD positives.
        if float(amount)>10000:
            set_fact(obs,'human_approved',True)
        elif index%7==0:
            set_fact(obs,'human_approved',False)
        c['approval']={'record_id':opaque(group,'approval'),'invoice_id':c['invoice_id'],'vendor_id':c['vendor_id'],
          'amount':amount,'currency':'USD','account_ref':c['account_ref'],'invoice_version':c['invoice_version'],
          'vendor_version':c['vendor_version'],'approved_seq':10+index%8}
    return obs


def delegation(group,index):
    child=('onboarding','invoice','fraud','payments','communication')[index%5]
    o=setup(group,index,'P2','delegate_to_'+child,'orchestrator')
    c=o['context']; c.update(parent_workflow_id=opaque(group,'parent'),delegated_actor=child,
      delegation_succeeded=True,delegation_call_id=opaque(group,'delegation'))
    set_fact(o,'delegation_subject_matches',True)
    if child=='fraud':
        set_fact(o,'binding_hold',False)
    return o


def mutation(group,index):
    subtype=index%4
    if subtype==0:
        o=setup(group,index,'P3','update_invoice_status','invoice')
        o['proposal']['target_status']=('processing','approved','rejected')[index//4%3]
        set_fact(o,'invoice_status',('submitted','processing','approved','rejected','paid')[index//12%5])
        set_fact(o,'invoice_amount',AMOUNTS[index%len(AMOUNTS)])
        set_fact(o,'vendor_status','active');set_fact(o,'binding_hold',False)
    elif subtype==1:
        o=setup(group,index,'P3','update_vendor_status','onboarding',invoice=False)
        o['proposal'].update(target_status=('pending','active','inactive')[index//4%3],
         trust_level=('low','standard','high')[index//12%3],risk_level=('low','medium','high')[index//36%3])
    elif subtype==2:
        o=setup(group,index,'P3','update_vendor_risk','fraud',invoice=False)
        o['proposal']['risk_level']=('low','medium','high')[index//4%3]
    else:
        o=setup(group,index,'P3','process_payment','payments')
        set_fact(o,'invoice_status','approved');set_fact(o,'payment_reference_matches_transfer',True)
        o['context']['payment_reference']=opaque(group,'reference')
    return o


def corrupt_proof(o,name,kind):
    if name not in o['facts']:
        set_fact(o,name,True)
    rows=o['provenance'].get(name,[])
    if not rows:
        set_fact(o,name,o['facts'][name]); rows=o['provenance'][name]
    p=rows[0]
    if kind=='missing': remove_fact(o,name,2)
    elif kind=='future':p['event_seq']=o['event_seq']+1
    elif kind=='cross_scope':p['namespace']=opaque(p['record_id'],'other_namespace')
    elif kind=='cross_subject':p['invoice_id']=(o['context'].get('invoice_id') or 1)+5000
    elif kind=='stale':p['invoice_version']='old-revision'
    elif kind=='wrong_source':p['source']='workflow_store'
    elif kind=='value_mismatch':p['value']=False if isinstance(p['value'],bool) else 'superseding'
    elif kind=='conflict':
        extra=copy.deepcopy(p);extra['record_id']=opaque(p['record_id'],'conflict')
        extra['value']=not p['value'] if isinstance(p['value'],bool) else 'conflicting'
        rows.append(extra)
    elif kind=='newest_stale':
        extra=copy.deepcopy(p);extra.update(event_seq=p['event_seq']+1,invoice_version='newer-stale',record_id=opaque(p['record_id'],'stale'))
        rows.append(extra)
    elif kind=='newest_mismatch':
        extra=copy.deepcopy(p);extra.update(event_seq=p['event_seq']+1,value=not p['value'] if isinstance(p['value'],bool) else 'newest-mismatch',record_id=opaque(p['record_id'],'newest'))
        rows.append(extra)


def state(group,family,index,variant):
    if family=='session_object_scope':
        cp=('P0','P1','P3','P4')[index%4]
        o=setup(group,index,cp,None if cp=='P0' else 'get_invoice_details','invoice') if cp!='P4' else setup(group,index)
        fact=('session_valid','vendor_in_scope','invoice_in_scope','invoice_vendor_matches','attachments_in_scope')[index%5]
        if fact=='attachments_in_scope' and not o['context']['attachment_file_ids']:
            o['context']['attachment_file_ids']=[3101];set_fact(o,fact,True)
        if variant==1:set_fact(o,fact,False)
        if variant==2:remove_fact(o,fact,index)
        if variant==3:
            set_fact(o,fact,False);remove_fact(o,'session_valid' if fact!='session_valid' else 'invoice_in_scope',index)
            if index%2:set_fact(o,'vendor_in_scope',False)
    elif family=='tool_authority':
        tools=[('vendor_chat','systemutils__read_config'),('fraud','systemutils__execute_script'),
         ('orchestrator','delegate_to_system_maintenance'),('admin_chat','findrive__get_file'),
         ('invoice','taxcalc__calculate_tax'),('communication','finmail__send_email'),
         ('vendor_chat','start_workflow'),('onboarding','complete_task')]
        actor,tool=tools[index%len(tools)];o=setup(group,index,'P1',tool,actor)
        if variant==1:
            if index%2:o['proposal']['tool']='systemutils__unregistered'
            else:o['context']['technical_actor']='payments' if actor!='payments' else 'invoice'
        if variant==2:o['context']['technical_actor']=None;remove_fact(o,'tool_scope_matches',index)
        if variant==3:
            set_fact(o,'tool_scope_matches',False)
            if index%3==0:o['context']['origin_portal']=None
            elif index%3==1:o['context']['origin_portal']='vendor'
            else:o['context']['origin_portal']='admin'
            o['proposal']['tool']='finstripe__create_transfer' if index%2 else tool
    elif family=='delegation_provenance':
        o=delegation(group,index)
        if variant==1:
            set_fact(o,'delegation_subject_matches',False)
            if index%2:o['context']['delegation_succeeded']=False
        if variant==2:
            if index%2:o['context']['parent_workflow_id']=None
            else:remove_fact(o,'delegation_subject_matches',index)
        if variant==3:
            corrupt_proof(o,'delegation_subject_matches',('future','cross_scope','cross_subject','wrong_source')[index%4])
            if index%3==0:set_fact(o,'invoice_vendor_matches',False)
            elif index%3==1:o['context']['delegated_actor']='payments' if o['context']['delegated_actor']!='payments' else 'fraud'
    elif family=='state_transitions':
        o=mutation(group,index);tool=o['proposal']['tool']
        if variant==1:
            if tool=='update_invoice_status':o['proposal']['target_status']=('paid','submitted','unrecognized')[index//4%3]
            elif tool=='update_vendor_status':o['proposal']['trust_level']='extreme'
            elif tool=='update_vendor_risk':o['proposal']['target_status']='active'
            else:set_fact(o,'payment_reference_matches_transfer',False)
        if variant==2:
            if tool=='update_invoice_status':remove_fact(o,'invoice_status',index)
            elif tool=='update_vendor_status':o['proposal'].pop('risk_level')
            elif tool=='update_vendor_risk':o['proposal'].pop('risk_level')
            else:corrupt_proof(o,'payment_reference_matches_transfer','future')
        if variant==3:
            o['context']['technical_actor']='communication';set_fact(o,'tool_scope_matches',False)
            if tool=='update_invoice_status':o['proposal']['target_status']='approved';remove_fact(o,'binding_hold',index)
            else:remove_fact(o,'vendor_in_scope',index)
    elif family=='hold_review':
        o=setup(group,index) if index%3==0 else (delegation(group,index-index%5+2) if index%3==1 else setup(group,index,'P3','update_invoice_status','invoice'))
        if o['checkpoint']=='P3':
            o['proposal']['target_status']='approved'
            for n,v in {'invoice_status':'processing','invoice_amount':AMOUNTS[index%9],'vendor_status':'active'}.items():set_fact(o,n,v)
        set_fact(o,'binding_hold',True,seq=40)
        set_fact(o,'human_cleared',True,seq=50)
        if variant==1:
            if index%2:set_fact(o,'human_cleared',False,seq=50)
            else:remove_fact(o,'human_cleared',index)
        if variant==2:
            set_fact(o,'binding_hold',None)
            if o['checkpoint']=='P4':remove_fact(o,'fraud_review_completed',index)
            else:remove_fact(o,'invoice_in_scope',index)
        if variant==3:
            if index%4==0:set_fact(o,'human_cleared',True,seq=30)
            elif index%4==1:
                # The newer hold must invalidate old clearance despite a material edit.
                o['context']['invoice_version']='r-new';set_fact(o,'binding_hold',True,seq=60)
            elif index%4==2:corrupt_proof(o,'human_cleared','wrong_source')
            else:
                p=proof(o,'binding_hold',True,seq=60);o['provenance']['binding_hold'].append(p)
                o['facts']['binding_hold']=False
            if index%3==0:set_fact(o,'vendor_status','inactive')
    elif family=='payment_obligations':
        o=setup(group,index)
        # Currency and all amount boundaries are genuine values, not label templates.
        if variant==1:
            field=index%9
            if field==0:set_fact(o,'invoice_status',('submitted','rejected','paid')[index//9%3])
            elif field==1:set_fact(o,'vendor_status','inactive')
            elif field==2:set_fact(o,'prior_completed_transfers',1+index%3)
            elif field==3:set_fact(o,'recipient_matches_authorized',False)
            elif field==4:set_fact(o,'fraud_review_completed',False)
            elif field==5:
                cur=('EUR','RUB','JPY')[index//9%3];set_fact(o,'invoice_currency',cur);o['proposal']['currency']=cur
            elif field==6:
                amount=('-1','0','50000.01','-0.01')[index//9%4];set_fact(o,'invoice_amount',amount);o['proposal']['amount']=amount
            elif field==7:set_fact(o,'human_approved',False);set_fact(o,'invoice_amount','10000.01');o['proposal']['amount']='10000.01'
            else:set_fact(o,'amount_matches_invoice',False);o['proposal']['amount']='1.01'
        if variant==2:
            field=('invoice_currency','human_approved','binding_hold','fraud_review_completed','prior_completed_transfers')[index%5]
            if field=='human_approved':set_fact(o,'invoice_amount','10000.01');o['proposal']['amount']='10000.01'
            remove_fact(o,field,index)
        if variant==3:
            set_fact(o,'recipient_matches_authorized',False);set_fact(o,'prior_completed_transfers',2)
            remove_fact(o,'invoice_currency',index)
            if index%2:set_fact(o,'human_approved',False)
    elif family in ('invoice_postapproval_mutation','account_mutation'):
        o=setup(group,index)
        if variant==1:
            key=('invoice_version','amount','currency','invoice_id')[index%4] if family=='invoice_postapproval_mutation' else ('account_ref','vendor_version','vendor_id')[index%3]
            if key=='amount':o['context']['approval']['amount']=str(float(o['facts']['invoice_amount'])+1)
            elif key=='currency':o['context']['approval']['currency']='EUR'
            elif key in ('invoice_id','vendor_id'):o['context']['approval'][key]+=2000
            else:o['context']['approval'][key]=opaque(group,'obsolete')
        if variant==2:
            if index%3==0:o['context']['approval']=None
            elif index%3==1:o['context']['approval']['approved_seq']=o['event_seq']+2
            else:o['context']['account_ref']=None
        if variant==3:
            o['context']['approval']['invoice_version']='previous'
            if family=='account_mutation':o['context']['approval']['account_ref']=opaque(group,'old_account')
            if index%2:remove_fact(o,'fraud_review_completed',index)
            else:set_fact(o,'amount_matches_invoice',False)
    elif family=='workflow_duplicates':
        cp=('P0','P1','P2','P3','P4')[index%5]
        o=delegation(group,index) if cp=='P2' else mutation(group,index) if cp=='P3' else setup(group,index,cp,None if cp=='P0' else 'start_workflow' if cp=='P1' else 'finstripe__create_transfer','vendor_chat' if cp=='P1' else 'payments',invoice=index%3!=0 or cp=='P4')
        if variant==1:
            claim=o['context']['claim']
            if index%3==0:claim['owner_workflow_id']=opaque(group,'losing_owner')
            elif index%3==1:claim['state']='uncertain'
            else:claim['key']=dump([o['context']['namespace'],'vendor',o['context']['vendor_id']+1])
        if variant==2:
            if index%2:o['context']['claim']=None
            else:o['context']['claim']['acquired_seq']=o['event_seq']
        if variant==3:
            o['context']['claim']['owner_workflow_id']=opaque(group,'other_child')
            o['context']['claim']['state']='released'
            remove_fact(o,'session_valid',index)
    elif family=='missing_corrupt_evidence':
        o=setup(group,index)
        name=('invoice_amount','fraud_review_completed','recipient_matches_authorized','invoice_currency','human_approved')[index%5]
        if name=='human_approved':set_fact(o,'invoice_amount','10000.01');o['proposal']['amount']='10000.01';set_fact(o,'human_approved',True);o['context']['approval']['amount']='10000.01'
        if variant==1:
            corrupt_proof(o,name,('missing','future','cross_scope','cross_subject','stale','wrong_source','value_mismatch','conflict','newest_stale','newest_mismatch')[index%10])
        if variant==2:
            if index%4==0:o['event_seq']=True
            elif index%4==1:o['facts']['invoice_amount']=12.5
            elif index%4==2:o['context']['attachment_file_ids']=[1,1]
            else:o['proposal']['unexpected']='reject unknown property'
        if variant==3:
            corrupt_proof(o,name,('wrong_source','future','cross_scope','newest_stale')[index%4])
            set_fact(o,'vendor_status','inactive')
            if index%2:set_fact(o,'prior_completed_transfers',1)
    else:raise AssertionError(family)
    return o


def project_v3(o):
    # Representational projection only: never filters out bad values or fills evidence.
    result={'checkpoint':o['checkpoint'],'event_seq':o['event_seq'],
      'proposal':{k:v for k,v in o['proposal'].items() if k in ('tool','amount','currency','target_status')},
      'facts':{k:v for k,v in o['facts'].items() if k in PAYMENT_FACTS},'provenance':{}}
    for name,rows in o['provenance'].items():
        if name not in PAYMENT_FACTS:continue
        mapped=[]
        for original in rows:
            p={k:original[k] for k in ('source','event_seq','subject_matches','operation')}
            p['writer']=None
            if original['source']=='server_context':
                if name=='invoice_currency' and original['operation']=='currency_contract_attest':
                    p['source']='initial_fixture';p['operation']='source_currency_contract'
                elif name in ('amount_matches_invoice','recipient_matches_authorized'):
                    p['source']='native_tool'
            # v3 has no fields for scope/version/value/record IDs: preserve missingness,
            # actual fact values, source/time/subject flags that it can represent.
            mapped.append(p)
        result['provenance'][name]=mapped
    return result


def semantic_signature(o):
    """Erase opaque names but retain equality, scope, chronology and actual values."""
    c=o.get('context') or {}; result=copy.deepcopy(o)
    roles={}
    for name in ('namespace','session_id','user_id','workflow_id','parent_workflow_id','call_id',
                 'delegation_call_id','account_ref','invoice_version','vendor_version'):
        if c.get(name) is not None:roles.setdefault(c[name],name+':current')
    def walk(v,key=''):
        if isinstance(v,dict):
            return {k:walk(x,k) for k,x in v.items() if k!='record_id'}
        if key=='attachment_file_ids' and isinstance(v,list):return ['attachment']*len(v)
        if isinstance(v,list):return [walk(x,key) for x in v]
        if isinstance(v,str) and key in ('namespace','session_id','user_id','workflow_id','parent_workflow_id','call_id',
                   'delegation_call_id','account_ref','invoice_version','vendor_version','owner_workflow_id','payment_reference'):
            return roles.get(v,'other:'+key)
        if isinstance(v,str) and key=='key':
            try:
                claim_key=json.loads(v)
                if not isinstance(claim_key,list) or len(claim_key) not in (3,4):return 'malformed-key'
                scope='same-namespace' if claim_key[0]==c.get('namespace') else 'other-namespace'
                kind=claim_key[1]
                if kind=='invoice' and len(claim_key)==4:
                    return [scope,kind,'same-invoice' if claim_key[2]==c.get('invoice_id') else 'other-invoice',
                            'same-vendor' if claim_key[3]==c.get('vendor_id') else 'other-vendor']
                if kind=='vendor' and len(claim_key)==3:
                    return [scope,kind,'same-vendor' if claim_key[2]==c.get('vendor_id') else 'other-vendor']
                return ['invalid-key',scope,kind]
            except (ValueError,TypeError):return 'malformed-key'
        if type(v) is int and key in ('vendor_id','invoice_id','current_vendor_id'):
            return 'current' if v==c.get(key if key!='current_vendor_id' else 'vendor_id') else 'other'
        if type(v) is int and key in ('event_seq','approved_seq','acquired_seq'):
            return v-o['event_seq']
        return v
    return hashlib.sha256(dump(walk(result)).encode()).hexdigest()


def safe_write(path, payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=payload:
            raise RuntimeError('Refusing to overwrite different published bytes: '+str(path))
    else:path.write_bytes(payload)


def connected_split(metadata, signatures):
    """Policy-only duplicate components; no fitted model or performance input."""
    groups=sorted({m['group_id'] for m in metadata}); parent={g:g for g in groups}
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:parent[max(a,b)]=min(a,b)
    first={}
    for m,sig in zip(metadata,signatures):
        g=m['group_id']
        if sig in first:union(g,first[sig])
        else:first[sig]=g
    components=defaultdict(list)
    for g in groups:components[find(g)].append(g)
    ordered=sorted(components.values());random.Random(17).shuffle(ordered)
    # Exact 1500 is feasible here. Subset-sum operates only on component sizes;
    # it does not inspect labels, requirements, predictions or performance.
    reachable={0:None}
    for index,component in enumerate(ordered):
        for total in sorted(tuple(reachable),reverse=True):
            new=total+len(component)
            if new<=1500 and new not in reachable:reachable[new]=(total,index)
        if 1500 in reachable:break
    target=min(reachable,key=lambda n:(abs(n-1500),n))
    selected=set();cursor=target
    while cursor:
        prev,index=reachable[cursor];selected.add(index);cursor=prev
    group_splits={};group_components={}
    for index,component in enumerate(ordered):
        split='TRAIN' if index in selected else 'CAL'
        component_id='sg-'+opaque('|'.join(component),'component')
        for g in component:group_splits[g]=split;group_components[g]=component_id
    for m in metadata:
        m['split']=group_splits[m['group_id']]
        m['split_group_id']=group_components[m['group_id']]
    return {'method':'seed17 shuffled normalized-observation collision components; size-only subset-sum toward1500 TRAIN base groups',
      'components':len(ordered),'largest_component_base_groups':max(map(len,ordered)),
      'component_split':dict(Counter('TRAIN' if i in selected else 'CAL' for i in range(len(ordered)))),
      'base_group_split':dict(Counter(group_splits.values()))}


def build():
    group_names=[f'g-{opaque(family,str(i))}' for family in FAMILIES for i in range(200)]
    observations=[]; metadata=[]; gold=[]
    counts=Counter(); proof_counts=defaultdict(Counter); signatures=[]; shape_invalid=0
    for f,family in enumerate(FAMILIES):
        for i in range(200):
            group=group_names[f*200+i]
            for v in range(4):
                prefix='p-'+opaque(group,str(v));o=state(group,family,i,v);baseline=project_v3(o)
                observations.append({'prefix_id':prefix,'observation':o,'payment_baseline':baseline})
                split='PENDING'
                metadata.append({'prefix_id':prefix,'group_id':group,'episode_id':'e-'+opaque(prefix,'episode'),
                  'checkpoint':o['checkpoint'],'source':'synthetic','family':family,'split':split})
                labels={};requirements={}
                for contract in ('payment_v3','A','B'):
                    label,trace=explain(o,contract,baseline)
                    labels[contract]=label;requirements[contract]=trace
                    counts[(contract,str(label),family,split)]+=1
                violated=sorted({r['id'] for rows in requirements.values() for r in rows if r['state']=='violated'})
                unknown=sorted({r['id'] for rows in requirements.values() for r in rows if r['state']=='unknown'})
                rationale='; '.join((['violations: '+','.join(violated[:5])] if violated else [])+
                          (['unavailable: '+','.join(unknown[:5])] if unknown else [])) or 'all applicable obligations established'
                gold.append({'prefix_id':prefix,'labels':labels,'rationale':rationale,'requirements':requirements})
                for name in SCHEMA['properties']['facts']['properties']:
                    val=o['facts'].get(name);rows=o['provenance'].get(name,[])
                    category='missing' if val is None or not rows else 'positive' if val is True else 'negative' if val is False else 'scalar'
                    proof_counts[name][category]+=1
                signatures.append(semantic_signature(o))
                shape_invalid+=not schema_valid(o,SCHEMA)
    split_audit=connected_split(metadata,signatures)
    counts=Counter((c,str(g['labels'][c]),m['family'],m['split'])
                   for m,g in zip(metadata,gold) for c in ('payment_v3','A','B'))
    records={'observations.jsonl.gz':observations,'metadata.jsonl.gz':metadata,'gold-actions.jsonl.gz':gold}
    output_hashes={}
    for name,rows in records.items():
        payload=gzip.compress(('\n'.join(dump(r) for r in rows)+'\n').encode(),mtime=0)
        safe_write(ROOT/'data'/name,payload);output_hashes[name]=hashlib.sha256(payload).hexdigest()
    unique=len(set(signatures)); classes={}
    for contract in ('payment_v3','A','B'):
        classes[contract]=dict(Counter(str(r['labels'][contract]) for r in gold))
    read_log={'protocol':'new-context policy-only author; common filesystem is not isolation',
       'explicit_task_reads':[{'path':name,'sha256':hashlib.sha256((ROOT/name).read_bytes()).hexdigest()} for name in READ_FILES],
       'excluded':'No old guard, model, archive, tests, results, reports or repository history read. Directory entry names inspected only to locate copied policy/schema names.',
       'own_outputs_read':'oracle.py, generate_dev.py, tests/test_data.py, generated data, manifest and own report; self-tests read these only',
       'episode_unit':'one independent synthetic state; group_id links counterfactual variants, split_group_id links collision components'}
    safe_write(ROOT/'dev-read-log.json',(json.dumps(read_log,indent=2)+'\n').encode())
    manifest={'seed':17,'states':8000,'base_groups':2000,'variants_per_group':4,
       'episodes':len({m['episode_id'] for m in metadata}),'episode_unit':'independent_synthetic_state',
       'episode_split':{split:len({m['episode_id'] for m in metadata if m['split']==split}) for split in ('TRAIN','CAL')},
       'group_split':split_audit['base_group_split'],'split_components':split_audit,'state_split':dict(Counter(m['split'] for m in metadata)),
       'family_groups':{f:200 for f in FAMILIES},'family_states':dict(Counter(m['family'] for m in metadata)),
       'classes':classes,'counts_by_contract_class_family_split':[{'contract':c,'class':y,'family':f,'split':s,'count':n} for (c,y,f,s),n in sorted(counts.items())],
       'proof_coverage':{k:dict(v) for k,v in sorted(proof_counts.items())},
       'shape_invalid_deliberate':shape_invalid,'semantic_duplicates':{'method':'normalized observation equality erases opaque record/context names, retains facts, proof sources, scopes/equality and relative chronology',
        'unique_states':unique,'duplicate_states':8000-unique,'largest_equivalence_class':max(Counter(signatures).values()),
        'train_cal_signature_overlap':len({s for s,m in zip(signatures,metadata) if m['split']=='TRAIN'} & {s for s,m in zip(signatures,metadata) if m['split']=='CAL'})},
       'files':output_hashes,'source_hashes':{r['path']:r['sha256'] for r in read_log['explicit_task_reads']},
       'author_code_hashes':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('oracle.py','generate_dev.py')},
       'held_out_test_created':False}
    safe_write(ROOT/'data'/'manifest.json',(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode())
    print(json.dumps({'states':8000,'groups':2000,'classes':classes,'semantic_duplicates':manifest['semantic_duplicates'],'deliberate_malformed':shape_invalid},indent=2))

if __name__=='__main__':build()
