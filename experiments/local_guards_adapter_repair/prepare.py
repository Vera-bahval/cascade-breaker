"""Prepare immutable inputs only. No prediction, scoring or model execution."""
import argparse
from contextlib import ExitStack
import ast
from contextlib import contextmanager
from copy import deepcopy
from functools import lru_cache
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import socket
import ssl  # Load socket subclasses before the temporary network fence.
from types import FunctionType
from unittest.mock import patch

from .inventory import ROOT, HERE, EXP, rows, sha, write_json
from .evidence import build_evidence
from .adapters import adapt
from .authority import actor_at, code_authority
from experiments.local_guards_archive_comparison import views
from experiments.local_guards_archive_comparison.collector import digest
from experiments.local_guards_final_replay.expanded import Archive
from experiments.local_guards_final_replay import early, projection

ARCHIVE=EXP/'local_guards_archive_comparison'
ANNOTATION=EXP/'local_guards_archive_annotation'
PREVIOUS=EXP/'local_guards_final_replay'
ELIZA=ARCHIVE/'results/eliza-run'

# The frozen view omitted transfer_id from reference equality. Keep that
# original available for request identity, and repair only this adapter's view.
repair_view=FunctionType(views.predictor_view.__code__,
    dict(vars(views),STRING_IDS=dict(views.STRING_IDS,transfer_id='reference')),
    'repair_view')


@contextmanager
def preparation_fence():
    """Block accidental evaluator access, final-DB reads and network creation."""
    real_open=io.open
    def guarded_open(file,mode='r',*args,**kwargs):
        name=str(file)
        if not any(c in mode for c in 'wax+'):
            forbidden=('/labels/','/predictions/','/adjudication/','gold-private','consensus',
                       'responses.jsonl','historical-local.jsonl','deepseek-historical.jsonl',
                       'p4-predictions','early-predictions','snapshot.sqlite','database.json','.db.json')
            if any(part in name for part in forbidden):
                raise PermissionError('Preparation forbidden source: '+name)
        return real_open(file,mode,*args,**kwargs)
    with patch('builtins.open',guarded_open),patch('io.open',guarded_open), \
         patch.object(socket,'create_connection',side_effect=RuntimeError('network forbidden')), \
         patch.object(socket,'socket',side_effect=RuntimeError('network forbidden')):
        yield


@contextmanager
def writer(path):
    with path.open('wb') as raw, gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as stream:
        yield lambda row:stream.write((json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode())


def packet_from_request(saved, expected):
    body=saved['request']
    identity=hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if identity!=saved['query_id']:
        raise ValueError('request hash mismatch')
    if [m['role'] for m in body['messages']]!=['system','user']:
        raise ValueError('request message roles mismatch')
    packet=views.unpack_view(json.loads(body['messages'][1]['content']))
    if packet!=expected or packet['checkpoint']!='P4':
        raise ValueError('request/state mismatch')
    proposal=packet['raw_context']['proposed_action']
    if (proposal['event_seq']!=packet['event_seq'] or proposal['tool_name']!='finstripe__create_transfer'
            or proposal['source_event_kind']!='before_tool_hook'):
        raise ValueError('not the actual pre-transfer action')
    return packet


@lru_cache(maxsize=None)
def verified_code(executor):
    archive=Archive(ROOT,{})
    payloads=archive._members(executor+'-source-and-acceptance.tar.gz')
    manifest=json.loads(next(v for k,v in payloads.items() if k.endswith('/manifest.json')))
    hashes=manifest['execution_spec']['finbot_hashes']
    runtime=archive.workspace/'deepseek-flash-control-placement/experiments/control-placement/deepseek_flash/.runtime/finbot'
    code={}
    for rel in ['finbot/agents/runner.py','finbot/agents/orchestrator.py','finbot/agents/cascade.py',
                'finbot/mcp/servers/finstripe/server.py',
                *sorted(p for p in hashes if p.startswith('finbot/agents/specialized/') and p.endswith('.py'))]:
        path=runtime/rel
        if sha(path)!=hashes[rel]:
            raise ValueError('unverified callable source: '+rel)
        code[rel]=path.read_bytes()
    authority=code_authority(code['finbot/agents/runner.py'],code['finbot/agents/orchestrator.py'],
                             {'runner':hashes['finbot/agents/runner.py'],'orchestrator':hashes['finbot/agents/orchestrator.py']})
    cascade=ast.parse(code['finbot/agents/cascade.py'])
    if not any(isinstance(n,ast.ClassDef) and n.name=='CascadeOrchestratorAgent'
               and any(isinstance(b,ast.Name) and b.id=='OrchestratorAgent' for b in n.bases) for n in ast.walk(cascade)):
        raise ValueError('root callable class changed')
    defaults={}
    for fn in ast.walk(ast.parse(code['finbot/mcp/servers/finstripe/server.py'])):
        if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)) and fn.name=='create_transfer':
            for arg,value in zip(fn.args.args[-len(fn.args.defaults):],fn.args.defaults):
                if arg.arg=='currency' and isinstance(value,ast.Constant) and isinstance(value.value,str):
                    defaults['currency']=value.value
    authority['root_callable']='run_cascade_orchestrator'
    authority['source_hashes']['cascade']=hashes['finbot/agents/cascade.py']
    return authority,defaults


def source_context(metadata, receipts, row, conditional):
    source={k:metadata[k] for k in ('source','source_sha256','fixture_ref','verified_source_version') if metadata.get(k)}
    source['source_ref']=row.get('raw_context',{}).get('source_ref') or (str(metadata.get('source'))+'::'+str(metadata.get('member')))
    source['source_instance']=digest([metadata.get('source_sha256'),metadata.get('member')])
    source['initial_state_origin']=next((r['status'] for r in receipts if r.get('field')=='raw_context.initial_state' and r.get('status') in {'observed','derived'}),'observed')
    binding=next((r['runner_binding'] for r in receipts if r.get('runner_binding')),None)
    if binding:
        authority,defaults=verified_code(metadata['executor'])
        source['actor_proof']=actor_at(row,authority)
        source['delegation_proof']=(source['actor_proof'] or {}).get('delegated')
        source['runner_binding']=binding
        source['proposal_defaults']=defaults
        source['authority_sources']=authority['source_hashes']
    if conditional and binding:
        _,modern,_=projection.project(row,source,conditional=True)
        fields={'session_valid','tool_scope_matches','invoice_in_scope','vendor_in_scope',
                'invoice_vendor_matches','attachments_in_scope','delegation_subject_matches'}
        source['technical_observation']={
            'context':{k:v for k,v in modern['context'].items() if k not in ('technical_actor','delegated_actor')},
            'facts':{k:v for k,v in modern['facts'].items() if k in fields},
            'provenance':{k:v for k,v in modern['provenance'].items() if k in fields}}
    return source


def normalized(row,source):
    """Tokenise identifiers together, retaining equality across source/context."""
    raw=deepcopy(row)
    raw.setdefault('mode','historical')
    raw.setdefault('evidence_status',{})
    raw['raw_context']['repair_source']=source
    if 'anchor' in raw:
        raw['raw_context']['repair_anchor_history']=[raw['anchor']]
    view=repair_view(raw)
    source=view['raw_context'].pop('repair_source')
    if 'repair_anchor_history' in view['raw_context']:
        view['anchor']=view['raw_context'].pop('repair_anchor_history')[0]
    return view,source


def prepared(identity,row,source,methods,ml_features=False):
    row,source=normalized(row,source)
    bundle=build_evidence(row,source)
    if (bundle['proposal'].get('tool')=='finstripe__create_transfer'
            and 'currency' not in bundle['proposal'] and source.get('proposal_defaults',{}).get('currency')):
        bundle['proposal']['currency']=source['proposal_defaults']['currency']
        bundle['coordinates'].append({'field':'proposal.currency','status':'derived',
            'reason':'verified_callable_default_not_invoice_currency','source_hashes':source['authority_sources']})
    anchor=row.get('anchor') or {}
    boundary=row['raw_context'].get('proposed_action') or anchor.get('return_event') or anchor.get('event') or {}
    action={k:deepcopy(boundary[k]) for k in ('event_seq','tool_name','tool_arguments','source_event_index','hook_kind','source_event_kind') if k in boundary}
    if action.get('tool_name') and bundle['proposal'].get('tool')!=action['tool_name']:
        raise ValueError('source action lost during preparation')
    adapters={name:adapt(bundle,name) for name in methods}
    if ml_features:
        from experiments.local_guards_archive_comparison.ml import features as archive_features
        from experiments.local_guards_v3 import ml_v3
        from experiments.local_guards_ml_retrain.features_revision2 import features as retrain_features
        from experiments.local_guards_ml_retrain.features import features as retrain_original_features
        feature_inputs={
            'v3_structured':ml_v3.features(adapt(bundle,'v3_ml')['payload']),
            'v3_text':ml_v3._text_rows([adapt(bundle,'v3_ml')['payload']]),
            **({'archive':archive_features(adapt(bundle,'archive_ml')['payload'])} if ml_features!='early' else {}),
            'retrain_revision2_old':retrain_features(adapt(bundle,'retrain_ml')['payload'],'old'),
            'retrain_revision2_new':retrain_features(adapt(bundle,'retrain_ml')['payload'],'new'),
            'retrain_original_old':retrain_original_features(adapt(bundle,'retrain_ml')['payload'],'old'),
            'retrain_original_new':retrain_original_features(adapt(bundle,'retrain_ml')['payload'],'new')}
    else:
        feature_inputs={}
    bundle.pop('raw_input')
    # Account values are already tokenised. Provenance and every recovered
    # value are preserved, even if no frozen representation can admit them.
    return dict(identity,bundle=bundle,action_boundary=action,adapters=adapters,features=feature_inputs,
                payload_sha256={k:digest(v['payload']) for k,v in adapters.items()},
                feature_sha256={k:digest(v) for k,v in feature_inputs.items()})


def p4_inputs(inventory,out):
    cases=inventory['p4']
    mapping={r['case_id']:r['query_id'] for r in rows(ELIZA/'case-mapping.jsonl.gz')}
    ids={mapping[c['case_id']] for c in cases}
    requests={r['query_id']:r for r in rows(ELIZA/'requests.jsonl.gz') if r['query_id'] in ids}
    prefixes={c['prefix_id'] for c in cases}
    originals={r['prefix_id']:r for r in rows(ARCHIVE/'data/historical/observations.jsonl.gz') if r['prefix_id'] in prefixes}
    recovery=Archive(ROOT,{'cases':cases})
    count=0
    with writer(out/'p4-inputs.jsonl.gz') as emit:
        for case in cases:
            expected_path=ANNOTATION/'action_inputs'/(case['annotation_id']+'.json')
            if sha(expected_path)!=case['input_sha256']:
                raise ValueError('frozen action input changed')
            expected=json.loads(expected_path.read_text())
            query=mapping[case['case_id']]
            common=packet_from_request(requests[query],expected)
            original=originals[case['prefix_id']]
            if views.predictor_view(original)!=expected:
                raise ValueError('raw archive/request identity mismatch')
            expanded,receipts=recovery.enrich(original,case['metadata'])
            for mode,row in [('common',common),('expanded',expanded),('conditional',expanded)]:
                source={} if mode=='common' else source_context(case['metadata'],receipts,row,mode=='conditional')
                identity={k:case[k] for k in ('case_id','prefix_id')}
                identity.update(mode=mode,query_id=query if mode=='common' else None,
                                request_sha256=query if mode=='common' else None)
                emit(prepared(identity,row,source,
                    ('v1','v2','v3','v4','v4.2','v4.3','native','native_core','archive_ml','retrain_ml','v3_ml'),True))
                count+=1
    return count


def early_inputs(inventory,out):
    # Frozen exports contain coordinates only. Re-read source journals instead
    # of treating the old v4 reconstructed facts as historical evidence.
    episodes=list(inventory['early_episodes'].values())
    wanted={r['prefix_id']:r for r in rows(PREVIOUS/'early-data/early-inputs.jsonl.gz')}
    if set(wanted)!=set(inventory['early_prefixes']):
        raise ValueError('early cohort changed')
    recovery=Archive(ROOT,{})
    count=0
    with ExitStack() as stack:
        emit=None
        for ep,journal,initial,member in early.raw_episodes(episodes,ROOT.parent/'finbot-four-model-report'):
            events=early.legacy_events(journal) if initial is not None else early.native_events(journal)
            anchors=early.index_anchors(ep['episode_id'],events,initial is not None)
            first=events[0] if events else {}
            opening=deepcopy(initial.get('db_initial') or {}) if initial else {}
            # Candidate selectors are not access grants. Only the root task is
            # inspected, never a future tool read, to find the requested object.
            text=first.get('user_message') or ''
            hints={k:int(m.group(1)) for k in ('invoice_id','vendor_id')
                   if (m:=re.search(r'\b'+k+r':\s*(\d+)\b',text))}
            if opening:
                hints.update({kind+'_id':(opening.get(kind) or {}).get('id') for kind in ('invoice','vendor')})
            root=dict(episode_id=ep['episode_id'],event_seq=first.get('event_seq',0),checkpoint='P0',
                      observation={'context':dict(hints,prefix_complete=True),'facts':{},'provenance':{}},
                      raw_context={'events':[first] if first else [],'initial_state':opening})
            _,receipts=recovery.enrich(root,ep)
            if not opening:
                restored,_=recovery.enrich(root,ep)
                opening=restored['raw_context'].get('initial_state') or {}
            for prefix,anchor in anchors.items():
                if prefix not in wanted:
                    continue
                selected=wanted.pop(prefix)
                if (selected['episode_id'],selected['checkpoint'],selected['event_seq'])!=(ep['episode_id'],anchor['checkpoint'],anchor['event_seq']):
                    raise ValueError('early source boundary mismatch')
                cut=anchor['event_seq']
                row=dict(prefix_id=prefix,episode_id=ep['episode_id'],checkpoint=anchor['checkpoint'],event_seq=cut,
                    anchor={'event':anchor['event'],'return_event':anchor.get('return_event')},
                    observation={'context':dict(hints,prefix_complete=True),'facts':{},'provenance':{}},
                    raw_context={'events':[dict(e,source_ref=member+'#'+str(e['source_event_index'])) for e in events if e['event_seq']<cut],
                                 'initial_state':opening,'initial_fixture':{},'source_ref':member})
                for mode in ('historical','conditional'):
                    source=source_context(ep,receipts,row,mode=='conditional')
                    if count%1000==0:
                        if emit is not None:
                            stack.close()
                        emit=stack.enter_context(writer(out/('early-inputs-%03d.jsonl.gz'%(count//1000))))
                    emit(prepared({'prefix_id':prefix,'episode_id':ep['episode_id'],'mode':mode,
                                   'selected_for_annotation':prefix in inventory['early_selected_prefixes']},
                                  row,source,('v4','v4.2','v4.3','retrain_ml','v3_ml'),'early'))
                    count+=1
                    if count%2000==0:
                        print(json.dumps({'prepared_early_rows':count}),flush=True)
    if wanted:
        raise ValueError('unmatched early prefixes: '+str(len(wanted)))
    return count


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    inventory=json.loads((HERE/'inventory.json').read_text())
    initial_hashes={p.name:sha(p) for p in HERE.glob('*.py')}
    with preparation_fence():
        p4_count=p4_inputs(inventory,output)
        print(json.dumps({'prepared_p4_rows':p4_count}),flush=True)
        early_count=early_inputs(inventory,output)
    if (p4_count,early_count)!=(542*3,18676*2):
        raise ValueError('unexpected prepared cohort size')
    source_hashes={p.name:sha(p) for p in HERE.glob('*.py')}
    if source_hashes!=initial_hashes:
        raise ValueError('preparation source changed during generation')
    write_json(output/'manifest.json',{'status':'PREPARED_AWAITING_INDEPENDENT_REVIEW',
        'preparation_revision':2,
        'base':inventory['base'],'inventory_sha256':sha(HERE/'inventory.json'),
        'frozen_sources_sha256':sha(HERE/'frozen-sources.json'),'methods_sha256':sha(HERE/'methods.json'),'source_hashes':source_hashes,
        'counts':{'p4_states':542,'p4_mode_rows':p4_count,'early_episodes':754,
                  'early_states':18676,'early_mode_rows':early_count,'early_selected':128},
        'outputs':{p.name:sha(p) for p in output.glob('*.gz')},
        'method_predictions':0,'model_api_calls':0,'quality_evaluation':False})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
