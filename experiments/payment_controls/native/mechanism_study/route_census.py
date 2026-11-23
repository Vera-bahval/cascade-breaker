"""Replay the frozen first-delegation adapter offline on open payment campaigns."""
import asyncio
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
from importlib.util import module_from_spec, spec_from_file_location
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from finbot.agents.orchestrator import OrchestratorAgent
from finbot.core.data.models import Invoice, Vendor
from finbot.mcp.servers.taxcalc.server import create_taxcalc_server
from runner.direct_mode import session_for
from experiments.payment_controls.native.overnight import route
from experiments.payment_controls.native.overnight.test_route import Agent
from experiments.payment_controls.native.pre_fraud.native_reads import historical_rows
from .controlled import HERE, ROOT

BASE = ROOT / '.runtime/payment-controls-chp3'
CONFIG = json.loads((HERE.parent/'build_freeze.json').read_text())['static_defaults']['agents']['FraudComplianceAgent']['default_config']
CHOICES = ('CLOSE_ALLOW', 'CLOSE_STOP', 'DEFER')


def read(path):
    return json.loads(path.read_text())


def first(folder, iid):
    direct = folder/'direct-trace.json'
    traces = read(direct).items() if direct.exists() else [(p.stem, read(p)) for p in (folder/'traces').glob('*.json')]
    (workflow, t), = [(w,t) for w,t in traces if t['task_data'].get('invoice_id') == iid]
    for i,s in enumerate(t['steps']):
        if s['kind'] == 'llm' and s['agent'] == 'orchestrator_agent':
            for c in s['output'].get('tool_calls', []):
                if c['name'] == 'delegate_to_fraud':
                    return workflow,t['steps'][:i],s['seq'],c['arguments']
    raise ValueError(f'No first delegation in {folder.name}')


def controlled_intake(folder, iid, prefix):
    # Final rows only propose a reconstruction. Accept it only if the whole
    # canonical intake matches the digest written before the workflow.
    engine = create_engine(f'sqlite:///file:{folder}/finbot.db?mode=ro&uri=true')
    with Session(engine) as db:
        vendor = db.query(Vendor).one().to_dict()
        invoices = [i.to_dict() for i in db.query(Invoice).order_by(Invoice.id)]
    engine.dispose()
    inv, = [r for r in invoices if r['id'] == iid]
    for s in prefix:
        if s.get('name') == 'get_vendor_details':
            vendor.update({k:v for k,v in s['output'].items() if k in vendor})
        if s.get('name') == 'get_invoice_details':
            inv.update({k:v for k,v in s['output'].items() if k in inv})
    def canon(r):
        return {k:(str(v)[:10] if k in ('due_date','invoice_date') else v) for k,v in r.items()
                if k not in ('namespace','created_at','updated_at')}
    initial = dict(vendor=canon(vendor),invoices=list(map(canon,invoices)),transactions=[])
    digest = sha256(json.dumps(initial,sort_keys=True).encode()).hexdigest()
    assert digest == (folder/'controlled-intake-sha256.txt').read_text().strip(), folder.name
    return inv,vendor,[r for r in invoices if r['id'] != iid],[]


async def reconstruct(folder, iid, prefix, proposal):
    intake = folder/'native-intake.jsonl'
    if intake.exists():
        snap, = map(json.loads,intake.read_text().splitlines())
        inv,vendor,tx = snap['invoice'],snap['vendor'],snap['transactions']
        assert inv['id'] == iid
        hist = historical_rows(folder,snap)
    else:
        inv,vendor,hist,tx = controlled_intake(folder,iid,prefix)
    for s in prefix:
        if s['kind'] != 'tool':
            continue
        if s['name'] == 'update_invoice_status':
            a,o = s['arguments'],s['output']
            assert not s.get('error') and o['updated'] and o['invoice_id'] == a['invoice_id'] == iid
            assert o['status'] == a['status']
            inv.update(status=o['status'],agent_notes=(inv['agent_notes'] or '')+'\n\n'+a['agent_notes'])
        else:
            assert s['name'] in {'get_invoice_details','get_vendor_details','complete_task','delegate_to_invoice',
                                 'findrive__search_files','findrive__list_files','taxcalc__validate_tax_id'}, s['name']
    paid = [r for r in [*hist,inv] if r['status']=='paid']
    tax = await create_taxcalc_server(session_for(inv['namespace'],vendor['id'])).call_tool(
        'validate_tax_id', {'tax_id':vendor['tin'],'country':'US'})
    profile = dict(status=vendor['status'],risk_level=vendor['risk_level'],total_invoices=len(hist)+1)
    return dict(inv=inv,vendor=vendor,transactions=tx,paid=paid,config=CONFIG,proposal=proposal,
                profile=profile,tin_ok=tax.structured_content['format_valid'])


async def replay(p, workflow, reply, temp, router=route):
    seen = []
    async def native(agent, vendor_id, task_description):
        seen.append((agent.workflow_id, vendor_id, task_description, agent._current_task_data['invoice_id'],
                     agent.session_context.namespace))
        return {'native':True}
    async def packet(*args):
        return deepcopy(p)
    async def choose(provider, data, owner):
        assert data == p
        return reply
    notes = []
    agent = Agent()
    agent.workflow_id = workflow
    agent._current_task_data = {'invoice_id':p['inv']['id']}
    agent.session_context = SimpleNamespace(namespace=p['inv']['namespace'])
    hybrid = reply is not None
    with patch.object(OrchestratorAgent,'delegate_to_fraud',native), router.install(
            router.ARMS[3 if hybrid else 1],temp/'decisions', packet_path=temp/'packets',
            provider='offline' if hybrid else None, chooser=choose, packet_for=packet,
            note_writer=lambda *a:notes.append(a[-1]), owner_prefix='census'):
        result = await OrchestratorAgent.delegate_to_fraud(agent,**p['proposal'])
    if result.get('native'):
        assert seen == [(workflow,p['vendor']['id'],p['proposal']['task_description'],p['inv']['id'],p['inv']['namespace'])]
        assert not notes and not agent.context and not agent._delegation_attempts
        return 'Fraud'
    assert len(notes)==1 and not seen
    return result['route']


async def main():
    frozen=read(HERE/'live_freeze.json')['files']
    reads=HERE.parent/'pre_fraud/native_reads.py'
    assert sha256(reads.read_bytes()).hexdigest()==frozen[str(reads.relative_to(ROOT))]
    rule_file='experiments/payment_controls/native/overnight/route.py'
    # The live adapter has evolved. Reproduce the published census with its exact source.
    source=subprocess.check_output(['git','show',f'3a682b59:{rule_file}'],cwd=ROOT)
    if sha256(source).hexdigest()!=frozen[rule_file]:
        raise ValueError('Archived router differs from study freeze')
    audit=read(HERE/'route_adjudication.json')
    profiles={r['id']:r['profile'] for f in (HERE/'controlled_fixture.json',HERE/'fixtures.json',
              HERE.parent/'fixtures.json',HERE.parent/'overnight/fixtures.json') for r in read(f)}
    rows = []
    receipts = {}
    for ledger in [BASE/'overnight/jev',BASE/'mechanism-live-v1/jev']:
        with sqlite3.connect((ledger/'ledger.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            charges=dict(db.execute('select id,cost from requests'))
        for f in ledger.glob('*.json'):
            r=read(f)
            if r.get('owner') and r.get('hash') == f.stem:
                assert abs(charges[f.stem]-r['usd']) < 1e-12
                receipts[r['owner']]=r
    old=read(HERE.parent/'pre_fraud/index.json')
    old_keys={v['source']:k for k,v in old.items()}
    old_results=read(HERE.parent/'pre_fraud/native_reads_results.json')
    old_gold=read(HERE.parent/'pre_fraud/gold.json')
    refs={v['source']:old_gold[k]['sufficient'] for k,v in old.items()}
    for v in read(HERE.parent/'overnight/reached_gold.json').values():
        refs[f"direct-overnight-off-v1-{v['fixture_id']}-overnight-route-v1"]=v['sufficient']
    live_gold=read(HERE/'live_reached_gold.json')
    for k,v in read(HERE/'live_reached_mapping.json').items():
        refs[f"{v['channel']}-m1-off-{v['fixture_id']}"]=live_gold[k]['sufficient']
    patterns=['study-live/*-native1/native-intake.jsonl','study-live/*overnight*/route-packets.jsonl',
              'mechanism-live-v1/*/route-packets.jsonl','mechanism-controlled-v1/*/controlled-intake-sha256.txt']
    with TemporaryDirectory() as tmp:
        archived_file=Path(tmp)/'frozen_route.py'
        archived_file.write_bytes(source)
        spec=spec_from_file_location('frozen_route',archived_file)
        archived=module_from_spec(spec)
        spec.loader.exec_module(archived)
        for f in sorted(path for pat in patterns for path in BASE.glob(pat)):
            folder=f.parent
            if (folder/'summary.json').exists():
                summary=read(folder/'summary.json')
                iid=summary['submitted_id']
                w,prefix,seq,proposal=first(folder,iid)
                family=summary['family']
            else:
                # The interrupted arm persisted the input and first decision before losing the trace.
                saved, = map(json.loads,f.read_text().splitlines())
                decision, = map(json.loads,(folder/'route-decisions.jsonl').read_text().splitlines())
                assert saved['owner']==decision['owner'] and decision['call']==1
                interrupted=read(HERE.parent/'overnight/interrupted_outcome.json')
                family=interrupted['case']
                assert folder.name==f"direct-{interrupted['arm']}-{family}-overnight-route-v1"
                iid=saved['packet']['inv']['id']
                w,seq,proposal=decision['workflow_id'],None,saved['packet']['proposal']
            row=dict(run=folder.name,family=family,source=f.name,first_seq=seq,prior_sufficiency=refs.get(folder.name,'UNRATED'))
            profile=profiles[family]
            row['origin']={'B':'sparse_history','G':'large_history','C':'equipment_history','D':'equipment_history','F':'equipment_history'}[profile]
            if f.name=='route-packets.jsonl':
                records=[r for r in map(json.loads,f.read_text().splitlines()) if r['packet']['inv']['id']==iid]
                r=records[0]
                assert r['owner'].endswith(':'+w+':1')
                p=r['packet']
                assert p['proposal']==proposal
            else:
                p=await reconstruct(folder,iid,prefix,proposal)
            if set(proposal)!={'vendor_id','task_description'}:
                rows.append(dict(**row,local='INVALID',reasons=['invalid_first_delegation']))
                continue
            local,reasons,_=archived.evaluate(p)
            if folder.name in old_keys:
                ref=old_results[old_keys[folder.name]]
                assert (local,reasons)==(ref['route'],ref['reasons'])
            baseline=await replay(p,w,None,Path(tmp),archived)
            results={k:await replay(p,w,k,Path(tmp),archived) for k in CHOICES} if local=='DEFER' else {}
            assert baseline==('Fraud' if local=='DEFER' else local)
            row.update(local=local,reasons=reasons,baseline=baseline,choices=results,
                       obligations='native investigation, findings, applicable flag, subsequent workflow' if baseline=='Fraud'
                       else ('document prior settlement, suppress repeat, notify vendor' if baseline=='CLOSE_STOP'
                             else 'document Fraud assessment, continue native payment and notice checks'))
            if results and len(set(results.values()))>1:
                key=old_keys.get(folder.name,folder.name)
                row['blind_id']=sha256(key.encode()).hexdigest()[:12]
                row['admissible']=audit[row['blind_id']]['review']['admissible']
            if 'hybrid' in folder.name and f.name=='route-packets.jsonl' and local=='DEFER':
                receipt=receipts.get(r['owner'])
                if receipt:
                    row.update(receipt=receipt['hash'],confirmed_usd=receipt['usd'],actual_reply=receipt['decision'])
                else:
                    decisions=list(map(json.loads,(folder/'route-decisions.jsonl').read_text().splitlines()))
                    assert any(d['owner']==r['owner'] and 'route_error:ConnectError' in d['reasons'] for d in decisions)
                    row['missing_charge']='connect error, unresolved reservation'
            rows.append(row)
    assert {r['blind_id'] for r in rows if 'blind_id' in r}==set(audit)
    (HERE/'route_census.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
    print(len(rows),Counter(r['local'] for r in rows))


if __name__=='__main__':
    asyncio.run(main())
