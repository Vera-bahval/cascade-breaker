"""One label-free, equality-preserving view for rules, ML, and the guard LLM."""
import argparse
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from .collector import read_jsonl, write_jsonl, file_hash, parse_result

HERE=Path(__file__).resolve().parent
FORBIDDEN={'gold','label','expected_pay','truth','source_intent','source_requires_stop',
           'continuation_harm','contract_continuation_harm','split','executor','cohort',
           'group_id','episode_id','case_id','run_id','source_attempt_harm'}
STRING_IDS={
    'invoice_number':'reference','invoice_reference':'reference','payment_reference':'reference',
    'namespace':'namespace','namespace_token':'namespace','session_id':'session',
    'workflow_id':'workflow','parent_workflow_id':'workflow',
    'call_id':'call','source_call_id':'call','source_ref':'source','source_refs':'source',
    'derived_from':'source','record_id':'source',
    'vendor_account_token':'account','bank_account_number':'account',
    'vendor_bank_account_number':'account','vendor_account':'account','bank_account':'account',
    'company_name':'vendor_identity','vendor_company_name':'vendor_identity',
    'bank_account_holder_name':'vendor_identity','vendor_bank_account_holder_name':'vendor_identity',
    'contact_name':'contact','email':'email','vendor_email':'email','contact_email':'email',
    'native_policy_hash':'policy','native_revision':'revision'}
SERIALIZED={'tool_result','model_output','arguments'}


def predictor_view(row):
    view={k:copy.deepcopy(row[k]) for k in ('checkpoint','event_seq','mode','evidence_status','raw_context','observation')}
    aliases={};counts={}
    def bind(group,value):
        key=(group,str(value))
        if key not in aliases:
            counts[group]=counts.get(group,0)+1;aliases[key]=f'{group}/{counts[group]}'
        return aliases[key]
    # This join-only identifier is used solely to remove benchmark run labels
    # that the historical fixture embedded in vendor names, email and queries.
    if row.get('episode_id'):bind('run',row['episode_id'].rsplit('/',1)[-1])
    def scan(value,key='',source_data=False):
        if key=='evidence_status':return
        if isinstance(value,dict):
            if FORBIDDEN.intersection(value) and not source_data:raise ValueError('annotation metadata inside predictor view')
            for k in sorted(value):scan(value[k],str(value.get('field','')).rsplit('.',1)[-1] if k=='value' and 'field' in value else k,
                source_data or k=='events' or k.endswith('_history'))
        elif isinstance(value,list):
            for x in value:scan(x,key,source_data)
        elif value is not None:
            if isinstance(value,str) and key in SERIALIZED:
                parsed=parse_result(value)
                if isinstance(parsed,(dict,list)):scan(parsed,key,source_data)
            if key in STRING_IDS and isinstance(value,str) and value.strip():
                group=STRING_IDS[key]
                if group=='account' and key!='vendor_account_token':
                    token='account/'+hashlib.sha256(json.dumps(str(value),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
                    if ('account',token) in aliases:aliases[('account',str(value))]=aliases[('account',token)]
                    else:aliases[('account',token)]=bind(group,value)
                bind(group,value)
    scan(view)
    # Identifiers embedded in native notes are replaced too; source text that
    # itself claims an approval/label stays text and never becomes a trusted field.
    replacements=sorted(((old,new) for (_,old),new in aliases.items() if len(old)>=3),key=lambda x:-len(x[0]))
    replacement_map=dict(replacements)
    pattern=re.compile(r'(?<![^\W_])(?:'+'|'.join(re.escape(old) for old,_ in replacements)+r')(?![^\W_])') if replacements else None
    def rewrite(value,key=''):
        if key=='evidence_status':return copy.deepcopy(value)
        if isinstance(value,dict):return {k:rewrite(v,str(value.get('field','')).rsplit('.',1)[-1] if k=='value' and 'field' in value else k) for k,v in value.items()}
        if isinstance(value,list):return [rewrite(v,key) for v in value]
        if value is None:return None
        if key in STRING_IDS:return aliases[(STRING_IDS[key],value)] if isinstance(value,str) and value.strip() else value
        if isinstance(value,str) and key in SERIALIZED:
            parsed=parse_result(value)
            if isinstance(parsed,(dict,list)):
                return json.dumps(rewrite(parsed),ensure_ascii=False,sort_keys=True)
        if isinstance(value,str) and not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',value):
            if pattern:value=pattern.sub(lambda m:replacement_map[m.group()],value)
        return value
    return rewrite(view)


def pack_view(view):
    """Replace repeated long strings by explicit path references, without loss.

    No business text is selected or removed. Local methods use the expanded view;
    the LLM receives exactly the same content with duplicate copies referenced.
    """
    locations=defaultdict(list)
    def find(value,path=()):
        if isinstance(value,dict):
            for key,child in value.items():find(child,path+(key,))
        elif isinstance(value,list):
            for i,child in enumerate(value):find(child,path+(i,))
        elif isinstance(value,str) and len(value)>=128:locations[value].append(list(path))
    find(view)
    payload=copy.deepcopy(view);strings=[];references=[]
    for value,paths in locations.items():
        overhead=sum(len(json.dumps(path))+12 for path in paths)
        if len(paths)<2 or len(value)*(len(paths)-1)<=overhead:continue
        index=len(strings);strings.append(value)
        for path in paths:
            node=payload
            for key in path[:-1]:node=node[key]
            node[path[-1]]=None;references.append([path,index])
    return dict(format='lossless-path-references-v1',payload=payload,strings=strings,references=references)


def unpack_view(packet):
    if packet['format']!='lossless-path-references-v1':raise ValueError('unknown encoding')
    payload=copy.deepcopy(packet['payload'])
    for path,index in packet['references']:
        node=payload
        for key in path[:-1]:node=node[key]
        node[path[-1]]=packet['strings'][index]
    return payload


def prepare(data=HERE/'data',output=HERE/'views'):
    output.mkdir(parents=True,exist_ok=True)
    meta={x['prefix_id']:x for x in read_jsonl(data/'split-metadata.jsonl.gz')}
    script_sha=file_hash(Path(__file__))
    manifest={'script_sha256':script_sha,'input_sha256':{},'outputs':{},'normalization':'opaque nonempty string identifiers and source paths; malformed/empty values preserved; native numeric object IDs retained join-only, excluded ML'}
    for mode in ('historical','instrumented'):
        source=data/mode/'observations.jsonl.gz';rows=[]
        for row in read_jsonl(source):
            m=meta[row['prefix_id']]
            rows.append(dict(case_id=mode+'/'+row['prefix_id'],prefix_id=row['prefix_id'],
                             split=m['split'],input=predictor_view(row)))
        write_jsonl(output/(mode+'.jsonl.gz'),rows)
        for split in ('TRAIN','CAL'):
            write_jsonl(output/(mode+'-'+split+'.jsonl.gz'),[r for r in rows if r['split']==split])
        write_jsonl(output/(mode+'-selected.jsonl.gz'),[r for r in rows if r['split'] in ('REPRESENTATIVE','CHALLENGE')])
        manifest['input_sha256'][str(source)]=file_hash(source)
        manifest['outputs'][mode]={'rows':len(rows),'sha256':file_hash(output/(mode+'.jsonl.gz'))}
    schema=json.loads((HERE/'schema.json').read_text())
    for key in ('prefix_id','episode_id'):
        schema['properties'].pop(key,None)
        if key in schema.get('required',[]):schema['required'].remove(key)
    (output/'input-schema.json').write_text(json.dumps(schema,indent=2)+'\n')
    if file_hash(Path(__file__))!=script_sha:raise RuntimeError('view source changed during generation')
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=HERE/'data')
    parser.add_argument('--output',type=Path,default=HERE/'views')
    args=parser.parse_args();print(json.dumps(prepare(args.data,args.output),indent=2))
