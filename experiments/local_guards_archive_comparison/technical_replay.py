"""Separate offline technical registry audit; never rewrites frozen predictor input.

SQLite entries attest only this local replay. Object state contains hashes of
actual native observations, not financial decisions, human receipts or locks.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3

HERE=Path(__file__).resolve().parent
TECH_FIELDS=('call_id','parent_workflow_id','source_binding')
BINDING='offline_replay_recorded_source_links'


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def parse(value):
    if not isinstance(value,str):return value
    try:return json.loads(value)
    except (ValueError,TypeError):
        try:return ast.literal_eval(value)
        except (ValueError,SyntaxError,TypeError,RecursionError):return None


def read_rows(path):
    with gzip.open(path,'rt') as stream:
        for line in stream:
            if line.strip():yield json.loads(line)


def file_hash(path):
    result=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):result.update(chunk)
    return result.hexdigest()


class Registry:
    def __init__(self,path=':memory:'):
        self.db=sqlite3.connect(path)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE admissions(task_id TEXT PRIMARY KEY, episode_id TEXT UNIQUE,
          source_ref TEXT, event_seq INTEGER, origin TEXT NOT NULL);
        CREATE TABLE events(event_key TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES admissions,
          event_seq INTEGER NOT NULL, source_ref TEXT NOT NULL, kind TEXT NOT NULL, payload_hash TEXT NOT NULL);
        CREATE TABLE calls(call_key TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES admissions,
          parent_call_key TEXT REFERENCES calls, actor TEXT NOT NULL, tool TEXT NOT NULL,
          args_hash TEXT NOT NULL, source_ref TEXT NOT NULL, event_seq INTEGER NOT NULL,
          return_source_ref TEXT, return_event_seq INTEGER, return_status TEXT);
        CREATE TABLE observed_state(task_id TEXT NOT NULL REFERENCES admissions, subject TEXT NOT NULL,
          field TEXT NOT NULL, value_hash TEXT NOT NULL, source_ref TEXT NOT NULL,event_seq INTEGER NOT NULL,
          PRIMARY KEY(task_id,subject,field));
        CREATE TABLE technical_links(prefix_id TEXT NOT NULL,field TEXT NOT NULL,value TEXT,
          task_id TEXT NOT NULL REFERENCES admissions,call_key TEXT REFERENCES calls,
          source_ref TEXT NOT NULL,event_seq INTEGER NOT NULL,status TEXT NOT NULL,
          PRIMARY KEY(prefix_id,field));
        ''')
    def __enter__(self):return self
    def __exit__(self,*args):self.db.close()
    def admit(self,episode,source_ref,seq,origin):
        task='collector/task/'+digest(episode)[:24]
        with self.db:self.db.execute('INSERT OR IGNORE INTO admissions VALUES(?,?,?,?,?)',(task,episode,source_ref,seq,origin))
        return task
    def event(self,task,seq,ref,kind,payload):
        key=digest([task,ref,kind,digest(payload)])
        with self.db:self.db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)',(key,task,seq,ref,kind,digest(payload)))
    def call(self,task,parent,actor,tool,args,ref,seq):
        key='local-call/'+digest([task,ref,tool,args])[:24]
        with self.db:self.db.execute('INSERT OR IGNORE INTO calls VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,task,parent,actor,tool,digest(args),ref,seq,None,None,None))
        return key
    def returned(self,key,ref,seq,value):
        status='unknown'
        if isinstance(value,dict):
            status='error' if value.get('error') else str(value.get('task_status','observed_result'))
        with self.db:self.db.execute('UPDATE calls SET return_source_ref=?,return_event_seq=?,return_status=? WHERE call_key=?',(ref,seq,status,key))
    def native_observation(self,task,tool,args,value,ref,seq):
        if not isinstance(value,dict) or value.get('error') or value.get('updated') is False:return
        if not (tool.startswith(('get_invoice','update_invoice','get_vendor','update_vendor','update_fraud','update_payment')) or tool in ('flag_invoice_for_review','process_payment')):return
        iid=value.get('invoice_id',args.get('invoice_id'))
        vid=value.get('vendor_id',args.get('vendor_id'))
        subject=canonical({'invoice_id':iid,'vendor_id':vid})
        # Store only source observation hashes. A local revision never becomes
        # an approval, a currency, a human decision or a historical version ID.
        with self.db:
            for field,content in value.items():
                if field.startswith('_'):continue
                self.db.execute('INSERT INTO observed_state VALUES(?,?,?,?,?,?) ON CONFLICT(task_id,subject,field) DO UPDATE SET value_hash=excluded.value_hash,source_ref=excluded.source_ref,event_seq=excluded.event_seq',(task,subject,field,digest(content),ref,seq))
    def link(self,prefix,field,value,task,call,ref,seq,status):
        with self.db:self.db.execute('INSERT INTO technical_links VALUES(?,?,?,?,?,?,?,?)',(prefix,field,value,task,call,ref,seq,status))
    def logical_hash(self):
        content={name:self.db.execute('SELECT * FROM '+name+' ORDER BY 1,2').fetchall() for name in ('admissions','events','calls','observed_state','technical_links')}
        return digest(content)
    def counts(self):
        return {name:self.db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('admissions','events','calls','observed_state','technical_links')}


class EpisodeReplay:
    def __init__(self,registry,episode,source):
        self.registry=registry;self.episode=episode;self.source=source
        self.legacy=bool(re.search(r'#L\d+$',source))
        self.task=None;self.stack=['orchestrator'];self.pending=[];self.processed=[]
        self.models={};self.proposal_occurrences=Counter();self.returns={};self.frame_by_ref={}
        self.admission_ref=None;self.admission_seq=None;self.warnings=Counter()
    def source_ref(self,event):
        seq=event['event_seq']
        if not self.legacy:return self.source+'#L'+str(seq//2)
        base=self.source+'/steps/'+str(seq//2)
        if event.get('source_event_kind')=='recorded_model_proposal':
            output=self.models.get(seq,{})
            calls=output.get('tool_calls',[]) if isinstance(output,dict) else []
            indexes=[i for i,c in enumerate(calls) if c.get('name')==event.get('tool_name') and canonical(c.get('arguments') or {})==canonical(event.get('tool_arguments') or {})]
            key=(seq,event.get('tool_name'),canonical(event.get('tool_arguments') or {}))
            offset=self.proposal_occurrences[key];self.proposal_occurrences[key]+=1
            if offset>=len(indexes):return base+'/unresolved-model-proposal'
            return base+'/output/tool_calls/'+str(indexes[offset])
        return base
    def ensure_admission(self,event):
        if self.task is None:
            ref=self.source_ref(event)
            self.admission_ref=ref;self.admission_seq=event['event_seq']
            origin='observed_prefix_start' if event.get('hook_kind')=='before_model' else 'incomplete_prefix_admission'
            self.task=self.registry.admit(self.episode,ref,event['event_seq'],origin)
    def before(self,event,ref):
        tool=event.get('tool_name') or '';args=event.get('tool_arguments') or {}
        if tool=='complete_task':return
        if ref in self.frame_by_ref:return
        batch=None;call_id=None
        if self.legacy and '/output/tool_calls/' in ref:
            batch=ref.split('/output/tool_calls/')[0]+'/output'
            i=int(ref.rsplit('/',1)[-1]);model=self.models.get(event['event_seq'],{})
            calls=model.get('tool_calls',[]) if isinstance(model,dict) else []
            if i<len(calls):call_id=calls[i].get('call_id',calls[i].get('id'))
        parent=next((p['key'] for p in reversed(self.pending) if p['tool'].startswith('delegate_to_')),None)
        key=self.registry.call(self.task,parent,self.stack[-1],tool,args,ref,event['event_seq'])
        frame=dict(key=key,ref=ref,tool=tool,args=args,actor=self.stack[-1],batch=batch,source_call_id=call_id)
        self.pending.append(frame);self.frame_by_ref[ref]=frame
        if tool.startswith('delegate_to_'):self.stack.append(tool.removeprefix('delegate_to_'))
    def after(self,event,ref):
        tool=event.get('tool_name') or '';args=event.get('tool_arguments') or {}
        candidates=[i for i,p in enumerate(self.pending) if p['tool']==tool and canonical(p['args'])==canonical(args)]
        index=None
        for i in reversed(candidates):
            p=self.pending[i];batch=p['batch']
            if batch is not None and len([j for j in candidates if self.pending[j]['batch']==batch])!=1:continue
            if i==len(self.pending)-1 or (batch and not tool.startswith('delegate_to_') and all(f['batch']==batch and not f['tool'].startswith('delegate_to_') for f in self.pending[i:])):
                index=i;break
        frame=self.pending.pop(index) if index is not None else None
        value=parse(event.get('tool_result'))
        info=dict(frame=frame,actor_stack=list(self.stack),source_ref=ref,event_seq=event['event_seq'])
        self.returns[ref]=info
        if frame:
            self.registry.returned(frame['key'],ref,event['event_seq'],value)
            if event.get('tool_source','native')=='native':self.registry.native_observation(self.task,tool,args,value,ref,event['event_seq'])
        elif tool!='complete_task':self.warnings['unpaired_return']+=1
        if tool.startswith('delegate_to_'):
            target=tool.removeprefix('delegate_to_')
            if len(self.stack)>1 and self.stack[-1]==target:self.stack.pop()
    def consume(self,event):
        self.ensure_admission(event)
        ref=self.source_ref(event)
        self.registry.event(self.task,event['event_seq'],ref,event.get('hook_kind','unknown'),event)
        if event.get('hook_kind')=='after_model' and self.legacy:self.models[event['event_seq']]=parse(event.get('model_output')) or {}
        if event.get('hook_kind')=='before_tool':self.before(event,ref)
        elif event.get('hook_kind')=='after_tool':self.after(event,ref)
    def advance(self,raw,cut):
        events=raw.get('events',[])
        if events and events[0].get('event_seq',cut+1)<=cut:self.ensure_admission(events[0])
        if any(e.get('event_seq',cut+1)>cut for e in events):return 'future_event_in_prefix'
        if events[:len(self.processed)]!=self.processed:return 'non_nested_prefix'
        for event in events[len(self.processed):]:self.consume(event)
        self.processed=list(events)
        return None
    def verify(self,historical,technical):
        cut=historical['event_seq'];raw=historical['raw_context']
        error=self.advance(raw,cut)
        if error:return dict(status='DISCREPANCY',reason=error)
        if self.task is None:return dict(status='UNKNOWN',reason='no_observed_admission_event')
        checkpoint=historical['checkpoint'];prefix=historical['prefix_id']
        if checkpoint=='P4':
            action=raw.get('proposed_action') or {}
            if not action:return dict(status='UNKNOWN',reason='missing_raw_proposal')
            ref=action.get('source_ref')
            if not ref:return dict(status='UNKNOWN',reason='proposal_without_source_ref')
            if self.legacy:
                expected_base=self.source+'/steps/'+str(cut//2)
                valid_source=ref==expected_base or bool(re.fullmatch(re.escape(expected_base)+r'/output/tool_calls/\d+',ref))
            else:valid_source=ref==self.source+'#L'+str(cut//2)
            if not valid_source:return dict(status='DISCREPANCY',reason='foreign_or_misaligned_proposal_source')
            event=dict(event_seq=cut,hook_kind='before_tool',tool_name=action.get('tool_name'),tool_arguments=action.get('tool_arguments') or {})
            self.registry.event(self.task,cut,ref,'recorded_pre_effect_proposal',event)
            self.before(event,ref)
            frame=self.frame_by_ref.get(ref);actor_stack=list(self.stack);paired=False
            # P4 names a proposed invocation, never its future completion.
            call_source=ref;call_key=frame['key'] if frame else None
        elif checkpoint=='P2_afterFraud':
            possible=[info for info in self.returns.values() if info['event_seq']==cut-1]
            if len(possible)!=1:return dict(status='UNKNOWN',reason='missing_or_ambiguous_return_event')
            info=possible[0];ref=info['source_ref'];frame=info['frame'];actor_stack=info['actor_stack'];paired=frame is not None
            call_source=frame['ref'] if frame else ref;call_key=frame['key'] if frame else None
        else:return dict(status='UNKNOWN',reason='checkpoint_outside_replay_contract')
        if call_key is None:return dict(status='UNKNOWN',reason='unpaired_observed_return')
        if self.legacy:
            match=re.search(r'/steps/(\d+)',ref);source_index=int(match[1]) if match else None
        else:
            match=re.search(r'#L(\d+)$',ref);source_index=int(match[1]) if match else None
        if source_index is None:return dict(status='UNKNOWN',reason='unresolved_source_index')
        admission_claim=self.source+'#L1'
        link=dict(prefix_id=prefix,source_ref=ref,source_event_index=source_index,task_admission_ref=admission_claim,call_source_ref=call_source,actor_stack=actor_stack,paired_return=paired)
        expected=dict(call_id='collector/'+digest(link)[:24],parent_workflow_id=self.task,source_binding=BINDING)
        issues=[]
        for field in TECH_FIELDS:
            actual=technical['observation']['context'].get(field)
            provenance=technical['observation']['provenance'].get('context.'+field,[])
            if actual!=expected[field]:issues.append(field+'_value_mismatch')
            if len(provenance)!=1:issues.append(field+'_provenance_count');continue
            p=provenance[0]
            if p.get('value')!=actual or p.get('source_ref')!=ref or p.get('event_seq')!=cut or p.get('derived_from')!=[admission_claim,call_source] or p.get('status')!='instrumented' or p.get('kind')!='declared_instrumentation':issues.append(field+'_provenance_mismatch')
        if issues:return dict(status='DISCREPANCY',reason=','.join(issues),expected=expected)
        status='SUPPORTED' if call_key is not None else 'UNKNOWN'
        if admission_claim!=self.admission_ref:self.warnings['declared_admission_alias_not_literal_source_anchor']+=1
        for field,value in expected.items():self.registry.link(prefix,field,value,self.task,call_key,ref,cut,status)
        readback=self.registry.db.execute('SELECT field,value FROM technical_links WHERE prefix_id=?',(prefix,)).fetchall()
        if dict(readback)!=expected:return dict(status='DISCREPANCY',reason='sqlite_readback_mismatch')
        return dict(status=status,reason='registered_and_read_back' if status=='SUPPORTED' else 'unpaired_observed_return',admission_source_anchor=self.admission_ref,declared_admission_alias=admission_claim,local_call_key=call_key)


def replay_episode(registry,historical_rows,technical_rows):
    technical={r['prefix_id']:r for r in technical_rows};ordered=sorted(historical_rows,key=lambda r:(r['event_seq'],r['prefix_id']))
    if not ordered:return dict(supported=0,unknown=0,discrepancies=0,rows=[],warnings={})
    episode=ordered[0]['episode_id'];source=ordered[0]['observation']['context']['source_refs'][0]
    replay=EpisodeReplay(registry,episode,source);receipts=[]
    for h in ordered:
        t=technical.get(h['prefix_id'])
        if not t:result=dict(status='DISCREPANCY',reason='missing_instrumented_row')
        elif h['raw_context']!=t['raw_context'] or h['observation']['facts']!=t['observation']['facts'] or h['observation']['proposal']!=t['observation']['proposal']:result=dict(status='DISCREPANCY',reason='business_input_difference')
        else:result=replay.verify(h,t)
        receipts.append(dict(prefix_id=h['prefix_id'],episode_id=episode,checkpoint=h['checkpoint'],event_seq=h['event_seq'],**result))
    counts=Counter(r['status'] for r in receipts)
    return dict(supported=counts['SUPPORTED'],unknown=counts['UNKNOWN'],discrepancies=counts['DISCREPANCY'],rows=receipts,warnings=dict(replay.warnings))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--historical',type=Path,default=HERE/'data/historical/observations.jsonl.gz');parser.add_argument('--instrumented',type=Path,default=HERE/'data/instrumented/observations.jsonl.gz');parser.add_argument('--episodes',type=Path,default=HERE/'data/episodes.jsonl.gz');args=parser.parse_args()
    paths=[args.historical,args.instrumented,args.episodes,HERE/'technical_replay.py',HERE/'tests/test_technical_replay.py']
    hashes={str(p):file_hash(p) for p in paths};by=defaultdict(list);technical=defaultdict(list)
    for row in read_rows(args.historical):by[row['episode_id']].append(row)
    for row in read_rows(args.instrumented):technical[row['episode_id']].append(row)
    # The inventory is identity-only; scenario/label/outcome fields are not used.
    inventory=set()
    with gzip.open(args.episodes,'rt') as stream:
        for line in stream:
            match=re.search(r'"episode_id"\s*:\s*("(?:[^"\\]|\\.)*")',line)
            if not match:raise ValueError('Inventory entry without episode identity')
            inventory.add(json.loads(match[1]))
    totals=Counter();warnings=Counter();reasons=Counter();receipts=[];registry_hashes=[];no_cut=[]
    for episode in sorted(inventory|set(by)):
        with Registry(':memory:') as registry:
            if episode not in by:
                registry.admit(episode,None,None,'inventory_identity_only_no_retained_cut_prefix');no_cut.append(episode)
            else:
                result=replay_episode(registry,by[episode],technical.get(episode,[]))
                totals.update({key:result[key] for key in ('supported','unknown','discrepancies')});warnings.update(result['warnings'])
                for row in result['rows']:
                    reasons[row['reason']]+=1
                    if row['status']!='SUPPORTED':receipts.append(row)
            totals.update(registry.counts());registry_hashes.append([episode,registry.logical_hash()])
    unchanged={str(p):file_hash(p)==hashes[str(p)] for p in paths};assert all(unchanged.values())
    report=dict(scope='Actual independent offline SQLite registration and readback of frozen technical context. No executor rerun, historical authorization, model decision or native-quality improvement.',input_hashes=hashes,inputs_unchanged=unchanged,independent_episodes=len(registry_hashes),episodes_without_retained_cut_prefix=len(no_cut),counts=dict(totals),reasons=dict(reasons),warnings=dict(warnings),logical_registry_sha256=digest(registry_hashes),registry_storage='Independent :memory: SQLite database per episode, closed after logical receipt; no SQLite files retained.',financial_or_human_facts_created=False,unresolved=receipts,no_cut_episode_ids=no_cut,registry_episode_hashes=registry_hashes,command='python experiments/local_guards_archive_comparison/technical_replay.py')
    (HERE/'provenance/technical-replay.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('unresolved','no_cut_episode_ids','registry_episode_hashes','input_hashes','inputs_unchanged')},indent=2))

if __name__=='__main__':main()
