"""Bounded Eliza-only guard inference; never imports or runs FinBot."""
from __future__ import annotations
import argparse
import asyncio
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid
from contextlib import closing

BASE = 'https://api.eliza.yandex.net'
MODEL = 'deepseek-flash'


def query_identity(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def append(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('ab') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as stream:
            stream.write((json.dumps(value, ensure_ascii=False, allow_nan=False)+'\n').encode())
        raw.flush(); os.fsync(raw.fileno())


def read_rows(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt') as stream:
        for line in stream:
            if line.strip(): yield json.loads(line)


class Ledger:
    def __init__(self, path, cap):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        if type(cap) not in (int,float) or not math.isfinite(cap) or cap <= 0:
            raise ValueError('cap must be finite and positive')
        self.cap = float(cap); self.owner = uuid.uuid4().hex
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS requests '
                       '(id TEXT PRIMARY KEY, owner TEXT, reserve REAL, cost REAL, status TEXT)')

    def reserve(self, identity, worst):
        if type(worst) not in (float,int) or not math.isfinite(worst) or worst <= 0:
            raise ValueError('invalid reservation')
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT id,owner,reserve,cost,status FROM requests').fetchall()
            if any(r[4]=='overrun' for r in rows): raise RuntimeError('cost-bound overrun requires audit')
            if any(r[0]==identity for r in rows): raise RuntimeError('duplicate request')
            if any(r[4]=='pending' and r[1]!=self.owner for r in rows):
                raise RuntimeError('unreconciled request from previous process; no automatic retry')
            if sum(r[2] if r[3] is None else r[3] for r in rows)+worst > self.cap:
                raise RuntimeError('research spend cap')
            db.execute('INSERT INTO requests VALUES (?,?,?,?,?)',
                       (identity,self.owner,worst,None,'pending'))

    def complete(self, identity, cost):
        if type(cost) not in (int,float) or not math.isfinite(cost) or cost < 0:
            raise ValueError('missing or invalid actual Eliza charge')
        with closing(sqlite3.connect(self.path)) as db, db:
            row=db.execute('SELECT reserve FROM requests WHERE id=? AND cost IS NULL',(identity,)).fetchone()
            if row is None: raise RuntimeError('unknown or completed request')
            overrun=cost>row[0]
            if db.execute('UPDATE requests SET cost=?,status=? WHERE id=? AND cost IS NULL',
                          (cost,'overrun' if overrun else 'complete',identity)).rowcount != 1:
                raise RuntimeError('unknown or completed request')
        if overrun: raise RuntimeError('actual charge exceeded reservation; saved and stopped')

    def summary(self):
        with closing(sqlite3.connect(self.path)) as db:
            rows=db.execute('SELECT reserve,cost,status FROM requests').fetchall()
        return dict(requests=len(rows), cost_usd=sum(r[1] or 0 for r in rows),
                    pending=sum(r[2]=='pending' for r in rows),
                    unresolved_reserved_usd=sum(r[0] for r in rows if r[1] is None),cap_usd=self.cap)


def parse_answer(text):
    try:
        value=json.loads(text)
        if not isinstance(value,dict) or value.get('decision') not in ('ALLOW','BLOCK','UNKNOWN'):
            raise ValueError()
        return dict(decision=value['decision'], reason=str(value.get('reason','')),
                    parsed=True, raw=text)
    except (ValueError, TypeError):
        return dict(decision='UNKNOWN',reason='unparseable_guard_response',parsed=False,raw=text)


def remaining(meta):
    limits=meta['quotas']['quotas']['external']['limits']
    all_limit=next(r for r in limits if r['name']=='all')
    family=next(r for r in limits if r['name']=='chain:top_opensource')
    monthly=next(r['usage']['cost'] for r in family['limits'] if r['type']=='monthly')
    daily=next(r['usage']['cost'] for r in all_limit['limits'] if r['type']=='daily')
    usage=meta['usage']['usage']
    return dict(monthly_usd=float(monthly)-usage['chain:top_opensource']['stats']['monthly']['cost'],
                daily_usd=float(daily)-sum(v['stats']['daily']['cost'] for v in usage.values()))


def token():
    sys.path.insert(0,str(Path.home()/'.agents/skills/store/scripts'))
    from agent_auth_client import resolve
    return resolve('eliza',store=True)


def sanitize_metadata(meta):
    def counts(value):
        return {k:v for k,v in value.items() if k in ('cost','requests') and type(v) in (int,float) and math.isfinite(v)}
    limits=[]
    for row in meta['quotas']['quotas']['external']['limits']:
        if row.get('name') not in ('all','chain:top_opensource'):continue
        limits.append(dict(name=row['name'],limits=[dict(type=x['type'],usage=counts(x['usage']))
            for x in row['limits'] if x.get('type') in ('daily','monthly')]))
    usage={}
    for name,row in meta['usage']['usage'].items():
        if not name.startswith('chain:'):continue
        usage[name]={'stats':{period:counts(value) for period,value in row.get('stats',{}).items()
                              if period in ('daily','monthly')}}
    models=[]
    for row in meta['model']['data']:
        if row.get('id')!=MODEL:continue
        model={k:row[k] for k in ('id','vendor','vendor_model','endpoint','disabled') if k in row}
        prices={k:float(row['prices'][k]) for k in ('input_tokens','output_tokens')}
        if any(not math.isfinite(v) or v<0 for v in prices.values()):raise ValueError('invalid live prices')
        model['prices']=prices;models.append(model)
    return {'quotas':{'quotas':{'external':{'limits':limits}}},'usage':{'usage':usage},'model':{'data':models}}


def metadata():
    import httpx
    with httpx.Client(timeout=30,headers={'Authorization':'OAuth '+token()}) as client:
        result={}
        for name,path in [('quotas','/v2/quotas'),('usage','/v2/usage'),('model','/v1/models?id='+MODEL)]:
            response=client.get(BASE+path); response.raise_for_status();result[name]=response.json()
    safe=sanitize_metadata(result);safe['remaining']=remaining(safe)
    if any(not math.isfinite(x) for x in safe['remaining'].values()):raise RuntimeError('invalid quota response')
    return safe


def validate_inputs(args):
    """All checks precede auth, metadata calls and paid generation."""
    if not math.isfinite(args.cap) or args.cap<=0:raise ValueError('finite positive cap required')
    config=json.loads(Path(args.config).read_text())
    freeze=json.loads(Path(args.freeze).read_text())
    required=[str(Path(__file__).relative_to(Path.cwd())),args.config,args.inputs,
              config['prompt_path'],freeze['method_manifest'],freeze['input_schema_path']]
    sources=freeze['sources']
    if not sources or any(name not in sources for name in required):
        raise RuntimeError('freeze missing mandatory source/config/prompt/input/method/schema binding')
    for name,expected in sources.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('source/model freeze mismatch: '+name)
    methods=json.loads(Path(freeze['method_manifest']).read_text())
    if not methods.get('sources'):raise RuntimeError('empty methods freeze')
    for name,expected in methods['sources'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('method freeze mismatch: '+name)
    if Path(args.output).resolve()!=Path(freeze['run_output']).resolve():
        raise RuntimeError('pilot/main must share the frozen ledger/cache directory')
    rows=list(read_rows(args.inputs))
    if len({r['case_id'] for r in rows})!=len(rows):raise RuntimeError('duplicate case identity')
    if sorted(r['case_id'] for r in rows)!=sorted(freeze['selected_case_ids']):
        raise RuntimeError('changed selected inputs')
    import jsonschema
    schema=json.loads(Path(freeze['input_schema_path']).read_text())
    for row in rows:
        if row.get('split') not in ('REPRESENTATIVE','CHALLENGE'):
            raise RuntimeError('inference outside selected groups')
        jsonschema.validate(row['input'],schema)
    if config['model']!=MODEL or config['endpoint']!='/deepseek/chat/completions':
        raise RuntimeError('outside authorized model/route')
    for key in ('input_price_cap','output_price_cap','max_tokens'):
        if type(config[key]) not in (int,float) or not math.isfinite(config[key]) or config[key]<=0:
            raise RuntimeError('invalid price/token bound')
    return config,rows


async def run(args):
    import httpx
    config,rows=validate_inputs(args)
    root=Path(args.output); root.mkdir(parents=True,exist_ok=True)
    prompt=Path(config['prompt_path']).read_text()
    meta=metadata()
    model=next(r for r in meta['model']['data'] if r['id']==MODEL)
    if model.get('disabled') or model.get('endpoint')!=config['endpoint']:
        raise RuntimeError('model endpoint unavailable/changed')
    for frozen,live in [('input_price_cap','input_tokens'),('output_price_cap','output_tokens')]:
        if float(model['prices'][live])>config[frozen]:raise RuntimeError('live price exceeds frozen bound')
    (root/'quota-before.json').write_text(json.dumps(meta,indent=2)+'\n')
    cap=min(args.cap,meta['remaining']['daily_usd']-.5,meta['remaining']['monthly_usd']-.5)
    if cap<=0: raise RuntimeError('insufficient quota')
    ledger=Ledger(root/'ledger.sqlite',cap)
    cached={r['query_id']:r for r in read_rows(root/'responses.jsonl.gz')} if (root/'responses.jsonl.gz').exists() else {}
    mapped={r['case_id'] for r in read_rows(root/'case-mapping.jsonl.gz')} if (root/'case-mapping.jsonl.gz').exists() else set()
    async with httpx.AsyncClient(timeout=90,headers={'Authorization':'OAuth '+token(),
                'X-Retries':'1','X-Request-Timeout':'60s'}) as client:
        for i,row in enumerate(rows):
            body={k:config[k] for k in ('model','temperature','max_tokens','thinking','reasoning_effort')}
            body.update(stream=False,messages=[{'role':'system','content':prompt},
                {'role':'user','content':json.dumps(row['input'],ensure_ascii=False,sort_keys=True)}])
            identity=query_identity(body)
            if row['case_id'] not in mapped:
                append(root/'case-mapping.jsonl.gz',dict(case_id=row['case_id'],query_id=identity))
                mapped.add(row['case_id'])
            if identity in cached: continue
            if args.limit and ledger.summary()['requests']>=args.limit: break
            payload=json.dumps(body,ensure_ascii=False).encode()
            worst=(len(payload)+1024)*float(config['input_price_cap'])+config['max_tokens']*float(config['output_price_cap'])
            ledger.reserve(identity,worst)
            append(root/'requests.jsonl.gz',dict(query_id=identity,case_id=row['case_id'],request=body))
            started=time.perf_counter()
            response=await client.post(BASE+config['endpoint'],content=payload,
                                       headers={'Content-Type':'application/json'})
            elapsed=time.perf_counter()-started
            try: value=response.json()
            except ValueError:
                append(root/'errors.jsonl.gz',dict(query_id=identity,http_status=response.status_code,
                       error='invalid_response_json',latency_s=elapsed))
                raise RuntimeError('unreconciled charge; stopped')
            # Never persist auth headers, Eliza key identity, or arbitrary envelope fields.
            charge=value.get('cost')
            if type(charge) in (int,float): ledger.complete(identity,charge)
            else: raise RuntimeError('unknown actual charge; stopped')
            if response.status_code!=200:
                append(root/'errors.jsonl.gz',dict(query_id=identity,http_status=response.status_code,cost=charge))
                raise RuntimeError('non-success response; stopped without automatic paid retry')
            if value.get('attempt_count')!=1: raise RuntimeError('unexpected provider retry count')
            inner=value['response']; text=inner['choices'][0]['message']['content']
            result=dict(case_id=row['case_id'],query_id=identity,latency_s=elapsed,cost_usd=charge,
                        usage=inner.get('usage'),response_model=inner.get('model'),
                        response_id=inner.get('id'),**parse_answer(text))
            append(root/'responses.jsonl.gz',result);cached[identity]=result
            if (i+1)%25==0:
                (root/'progress.json').write_text(json.dumps(ledger.summary(),indent=2)+'\n')
                print(json.dumps(ledger.summary()),flush=True)
    (root/'quota-after.json').write_text(json.dumps(metadata(),indent=2)+'\n')
    (root/'summary.json').write_text(json.dumps(ledger.summary(),indent=2)+'\n')
    print(json.dumps(ledger.summary()))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--inputs',required=True);parser.add_argument('--config',required=True)
    parser.add_argument('--freeze',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--cap',type=float,default=14.5);parser.add_argument('--limit',type=int,default=0)
    asyncio.run(run(parser.parse_args()))
