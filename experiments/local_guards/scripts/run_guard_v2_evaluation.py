#!/usr/bin/env python3
"""Barrier-gated serial archive fitting and sealed external prediction; NO SCORE.

No label path or score phase is accepted. The root must separately authorize
unblinding through the independently audited pre-unblind wrapper.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

BLOCKS=('N','M','G22','G86')
DEADLINE='2026-10-15T22:59:58.072112+00:00'
MODEL_CUTOFF='2026-10-15T21:39:58.072112+00:00'
ALL_MODELS=(*BLOCKS,'08','4b')
COLLECTIONS={'archive':'archive-p4','archive-partial':'archive-partial','raw64':'raw64','raw64-partial':'raw64-partial','independent':'independent-p4'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');tmp.replace(path)


def verify(manifest,expected):
    if sha(manifest)!=expected:raise ValueError('Frozen manifest changed: '+str(manifest))
    spec=json.loads(Path(manifest).read_text());pinned=spec.get('sha256')
    if not isinstance(pinned,dict) or not pinned:raise ValueError('Missing pinned SHA256 files')
    for name,wanted in pinned.items():
        if not Path(name).is_file() or sha(name)!=wanted:raise ValueError('Frozen source/input drift: '+name)
    return spec


def verify_all(root,expected,generation=5):
    result={name:verify(path,expected[name]) for name,path in manifest_paths(root,generation).items()}
    method_hash=expected['method']
    if result['split'].get('method_freeze_sha256')!=method_hash:raise ValueError('Split protocol belongs to another method freeze')
    if result['jev'].get('method_freeze_sha256')!=method_hash:raise ValueError('Jev freeze does not bind current method freeze')
    if result['addon'].get('method_freeze_sha256')!=method_hash or result['addon'].get('jev_input_freeze_sha256')!=expected['jev']:
        raise ValueError('Addon freeze does not bind current method/Jev freezes')
    return result


def manifest_paths(root,generation=5):
    return {'method':root/f'METHOD_FREEZE_{generation:02d}.json','jev':root/f'JEV_INPUT_FREEZE_{generation:02d}.json',
            'split':root/f'SPLIT_PROTOCOL_FREEZE_{generation:02d}.json','addon':root/f'NEW_ABLATION_PROTOCOL_{generation:02d}.json'}


def heavy_children():
    scan=subprocess.run(['ps','-axo','pid=,command='],capture_output=True,text=True,check=True)
    found=[]
    for line in scan.stdout.splitlines():
        parts=line.strip().split(None,1)
        if len(parts)!=2:continue
        pid,command=parts
        for module in ('cascade_guard.v2_runtime','cascade_guard.v2_jev'):
            if '-m '+module+' ' in command:
                found.append({'pid':int(pid),'module':module});break
    return found


def complete_model_artifact(root,block,generation):
    """Inspect identity/completeness metadata only, never individual risk values."""
    directory=root/f'scores-v{generation}';source=directory/(block+'.jsonl');manifest=directory/(block+'.manifest.json')
    if not source.is_file() or not manifest.is_file():return False,{'reason':'model artifact or completion manifest missing'}
    state=json.loads(manifest.read_text())
    if state.get('status')!='COMPLETE':return False,{'reason':'per-model manifest not COMPLETE'}
    inventory={}
    for suffix in COLLECTIONS.values():
        with (root/f'inputs-v{generation}'/(suffix+'-inputs.jsonl')).open() as handle:
            for line in handle:
                r=json.loads(line);pid=r['prefix_id']
                if pid in inventory:raise ValueError('Frozen collection inventory overlaps')
                inventory[pid]=r['input_hash']
    if len(inventory)!=720:raise ValueError('Frozen five-collection inventory must have720 prefixes')
    seen=set()
    with source.open() as handle:
        for line in handle:
            row=json.loads(line)
            if row.get('block')!=block:raise ValueError('Completed score filename/model block mismatch')
            pid=row['prefix_id']
            if pid not in inventory or pid in seen:raise ValueError('Score artifact has foreign or duplicate prefix')
            if row['input_hash']!=inventory[pid]:raise ValueError('Score artifact input hash differs from frozen inventory')
            seen.add(pid)
    return seen==set(inventory),{'expected_prefixes':len(inventory),'recorded_prefixes':len(seen),'missing_prefix_count':len(inventory)-len(seen)}


def complete_jev_exports(root,model,generation,entries):
    """Check actual observed checkpoint/collection coverage without risk values."""
    source_names={'archive-all':'archive-p4','archive-partial':'archive-partial','raw64':'raw64','raw64-partial':'raw64-partial','independent-all':'independent-p4'}
    blocks={'J_cur','J_seq','J_agg','J_dynamic','J_prior'} if model=='08' else {'J4_cur'}
    for entry in entries:
        name=entry['collection'];inventory=root/f'inputs-v{generation}'/(source_names[name]+'-inputs.jsonl')
        with inventory.open() as handle:expected={json.loads(line)['prefix_id'] for line in handle}
        seen=set();attempted=True
        with Path(entry['file']).open() as handle:
            for line in handle:
                r=json.loads(line);key=(r['prefix_id'],r['block'])
                if key in seen or r['prefix_id'] not in expected or r['block'] not in blocks:raise ValueError('Jev export has duplicate/foreign prefix or block')
                seen.add(key)
                current_only=model=='4b' or name not in ('archive-all','independent-all')
                if not current_only or r['block'] in ('J_cur','J4_cur'):
                    checkpoints=r['provenance']['checkpoint_inputs']
                    required=1 if current_only or r['block']=='J_cur' else 3 if r['block']=='J_prior' else 4
                    if len(checkpoints)!=required or any(c.get('prefix_id') is None or c.get('input_hash') is None for c in checkpoints):attempted=False
        if seen!={(pid,b) for pid in expected for b in blocks} or not attempted:
            return False,{'collection':name,'reason':'incomplete exact prefix/block or attempted checkpoint coverage'}
    return True,{'complete_collections':5,'actual_checkpoint_coverage':True}


def barrier(root,expected,scan=heavy_children,*,generation=5,now=None,cutoff=None):
    """Prefer all six; after model cutoff accept only complete available blocks.

    Availability uses completed stage records and exact collection export identity,
    never a probability, class label, recall, false-stop rate, or target outcome.
    """
    now=time.time() if now is None else now
    cutoff=dt.datetime.fromisoformat(MODEL_CUTOFF).timestamp() if cutoff is None else cutoff
    prior_path=root/f'scores-v{generation}/runtime-run.json';jev_path=root/f'jev-v{generation}/runtime-run.json'
    if not prior_path.exists() or not jev_path.exists():return False,{'reason':'inference watcher states incomplete'}
    prior=json.loads(prior_path.read_text());jev=json.loads(jev_path.read_text())
    if prior.get('freeze_manifest_sha256')!=expected['method']:raise ValueError('Prior state belongs to another method freeze')
    if jev.get('method_freeze_sha256')!=expected['method'] or jev.get('jev_input_freeze_sha256')!=expected['jev']:raise ValueError('Jev state belongs to another method/input freeze')
    terminal={'COMPLETE','FAILED','DEADLINE','STOPPED_MODEL_CUTOFF','STOPPED','MODEL_CUTOFF','PARTIAL','INTERRUPTED'}
    stages={s.get('block') for s in prior.get('stages',[]) if s.get('exit_code')==0}
    exports=jev.get('exports',{})
    complete=(prior.get('models_unloaded') is True and prior.get('status')=='COMPLETE' and stages==set(BLOCKS) and jev.get('status')=='COMPLETE' and jev.get('models_unloaded') is True and set(exports)=={'08','4b'})
    if not complete:
        if now<cutoff:return False,{'reason':'await all six models before prospective cutoff','prior_status':prior.get('status'),'jev_status':jev.get('status')}
        if prior.get('status') not in terminal or jev.get('status') not in terminal:
            return False,{'reason':'model cutoff reached; wait for both watchers to terminate and release children'}
        if prior.get('models_unloaded') is not True or jev.get('models_unloaded') is not True:return False,{'reason':'both terminal watchers must confirm models unloaded'}
    available=[];artifact_availability={}
    for block in BLOCKS:
        if block not in stages:continue
        artifact_complete,proof=complete_model_artifact(root,block,generation);artifact_availability[block]=proof
        if artifact_complete:available.append(block)
    expected_names={'archive-all','archive-partial','raw64','raw64-partial','independent-all'}
    for model in ('08','4b'):
        if model not in exports:continue
        export=exports[model];entries=export.get('collections',[])
        if len(entries)!=5 or {e.get('collection') for e in entries}!=expected_names:raise ValueError('Incomplete Jev collection export inventory')
        for entry in entries:
            target=root/f'jev-v{generation}'/model/('features-'+entry['collection']+'.jsonl')
            if Path(entry['file']).resolve()!=target.resolve() or sha(target)!=entry['sha256']:raise ValueError('Completed Jev export path/hash mismatch')
        combined=root/f'jev-v{generation}'/model/'features.jsonl'
        if Path(export['all_features']).resolve()!=combined.resolve() or sha(combined)!=export['sha256']:raise ValueError('Completed combined Jev export identity mismatch')
        artifact_complete,proof=complete_jev_exports(root,model,generation,entries);artifact_availability[model]=proof
        if artifact_complete:available.append(model)
    if set(available)!=set(ALL_MODELS):
        complete=False
        if now<cutoff:return False,{'reason':'model completion records do not yet cover all frozen prefixes','artifact_availability':artifact_availability}
    active=scan()
    if active:return False,{'reason':'heavy inference children still present','children':active}
    return True,{'N_M_PG_state_sha256':sha(prior_path),'jev_state_sha256':sha(jev_path),'heavy_children':[],'models_unloaded':True,
                 'available_models':available,'unavailable_models':[m for m in ALL_MODELS if m not in available],
                 'artifact_availability':artifact_availability,'mode':'ALL_SIX_COMPLETE' if complete else 'PROSPECTIVE_COMPLETENESS_ONLY_CUTOFF_FALLBACK'}


@contextlib.contextmanager
def heavy_lease(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:fcntl.flock(handle,fcntl.LOCK_UN)


def record_paths(root,collection,available_models=ALL_MODELS,generation=5):
    folder=root/f'feature-views-v{generation}'/collection;available=set(available_models)
    result=[folder/(b+'.jsonl') for b in BLOCKS if b in available]
    result += [folder/(b+'_'+v+'.jsonl') for b in ('N','M') if b in available for v in ('local','full','facts')]
    result += [folder/('Jev-'+m+'.jsonl') for m in ('08','4b') if m in available]
    return result if result else [folder/'NO_COMPLETED_MODEL_BLOCKS.jsonl']


def commands(workspace,available_models=ALL_MODELS,generation=5):
    base=workspace/'experiments/local_guards';root=base/'results/guard-v2';python=base/'.venv-finbot/bin/python'
    inputs=root/f'inputs-v{generation}';views=root/f'feature-views-v{generation}';main=root/f'evaluation-v{generation}';partial=root/f'evaluation-partial-v{generation}'
    result=[]
    for block in BLOCKS:
        if block not in available_models:continue
        result.append(('blind-split-'+block,[str(python),'-m','cascade_guard.v2_split_features','--inputs-directory',str(inputs),'--scores',str(root/f'scores-v{generation}'/(block+'.jsonl')),'--output',str(views)],None))
    result.append(('blind-normalization-and-projections',[str(python),'-m','cascade_guard.v2_feature_views','--root',str(root),'--jev',str(root/f'jev-v{generation}'),'--destination',str(views),'--inputs-directory',str(inputs),'--available-models',*available_models],None))
    for title,collection,output in [('train-full','archive',main),('train-matched-partial','archive-partial',partial)]:
        result.append((title,[str(python),'-m','cascade_guard.v2_eval','train','--output',str(output),'--rows',str(inputs/(COLLECTIONS[collection]+'-rows.jsonl')),
          '--outcomes',str(root/'evaluation/outcomes214.jsonl'),'--allocations',str(base/'results/cheap-guards/evaluation/fold-allocations.json'),'--records',*map(str,record_paths(root,collection,available_models,generation))],output/'METHODS_FROZEN.json'))
    for title,collection,trained,destination in [
        ('predict-independent','independent',main,main/'independent'),
        ('predict-raw64-full-shift','raw64',main,main/'raw64'),
        ('predict-raw64-partial-matched','raw64-partial',partial,partial/'raw64-partial'),
        ('predict-raw64-partial-shift','raw64-partial',main,main/'raw64-partial-shift')]:
        result.append((title,[str(python),'-m','cascade_guard.v2_eval','predict','--output',str(trained),'--rows',str(inputs/(COLLECTIONS[collection]+'-rows.jsonl')),
             '--destination',str(destination),'--records',*map(str,record_paths(root,collection,available_models,generation))],destination/'PREDICTIONS_FROZEN.json'))
    if any('score' in command for _,command,_ in result):raise AssertionError('Scoring prohibited')
    return result


def verify_completed(marker,stage):
    """Resume only an intact frozen stage, never refit after prediction/unblind."""
    frozen=json.loads(marker.read_text())
    if marker.name=='METHODS_FROZEN.json':
        for entry in frozen['files']:
            if sha(entry['path'])!=entry['sha256']:raise ValueError('Completed training stage drift: '+entry['path'])
        input_spec=json.loads((marker.parent/'training-input-freeze.json').read_text())
        for entry in input_spec['files']:
            if sha(entry['path'])!=entry['sha256']:raise ValueError('Training source drift on resume')
    else:
        if sha(marker.parent/'predictions.jsonl')!=frozen['predictions_sha256']:raise ValueError('Frozen predictions changed')
        if sha(marker.parent.parent/'METHODS_FROZEN.json')!=frozen['methods_freeze_sha256']:raise ValueError('Predictions bind another training freeze')
        if sha(frozen['rows_file']['path'])!=frozen['rows_file']['sha256']:raise ValueError('Frozen external rows changed')
        for item in frozen['records']:
            if sha(item['path'])!=item['sha256']:raise ValueError('Frozen external feature records changed')
    return {'stage':stage,'resume':'verified existing frozen stage','marker_sha256':sha(marker)}


def execute(command,stage,workspace,destination,state,deadline):
    remaining=deadline-time.time()
    if remaining<=0:raise TimeoutError('Technical deadline before '+stage)
    entry={'stage':stage,'command':command,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    environment={**os.environ,'PYTHONPATH':str(workspace/'experiments/local_guards'),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false'}
    with (destination/(stage+'.log')).open('a') as log:
        child=subprocess.Popen(command,cwd=workspace,env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        state['current_stage']=stage;state['child_pid']=child.pid;atomic(destination/'runtime-run.json',state)
        try:code=child.wait(timeout=remaining)
        except (subprocess.TimeoutExpired,KeyboardInterrupt):
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            entry.update(exit_code=child.returncode,status='DEADLINE_OR_INTERRUPTED');state['stages'].append(entry)
            raise TimeoutError('Deadline/interruption during '+stage)
    entry.update(exit_code=code,finished_utc=dt.datetime.now(dt.timezone.utc).isoformat());state['stages'].append(entry)
    state.pop('child_pid',None);atomic(destination/'runtime-run.json',state)
    if code:raise RuntimeError(stage+' failed; inspect log, no labels were opened')


def run(args):
    workspace=args.workspace.resolve();root=workspace/'experiments/local_guards/results/guard-v2';dest=root/f'evaluation-runner-v{args.generation}';dest.mkdir(parents=True,exist_ok=True)
    paths=manifest_paths(root,args.generation);expected={name:sha(path) for name,path in paths.items()};specs=verify_all(root,expected,args.generation)
    deadline=dt.datetime.fromisoformat(args.deadline.replace('Z','+00:00')).timestamp()
    frozen_deadline=dt.datetime.fromisoformat(specs['method']['technical_runner_deadline_utc'].replace('Z','+00:00')).timestamp()
    if deadline>frozen_deadline:raise ValueError('Cannot extend frozen global deadline')
    frozen_cutoff=specs['method'].get('inference_cutoff_utc')
    if frozen_cutoff is None or dt.datetime.fromisoformat(frozen_cutoff.replace('Z','+00:00')).timestamp()!=dt.datetime.fromisoformat(MODEL_CUTOFF).timestamp():raise ValueError('Prospective inference cutoff must match source-frozen method policy')
    if specs['addon'].get('inference_cutoff_utc')!=frozen_cutoff:raise ValueError('Addon inference cutoff differs from method freeze')
    plan=commands(workspace,generation=args.generation)
    if args.plan_only:
        return {'status':'PLAN_ONLY','stages':[{'name':n,'command':c,'freeze_marker':str(m) if m else None} for n,c,m in plan],'labels_read':False}
    state={'status':'WAITING_INFERENCE_BARRIER','pid':os.getpid(),'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
           'deadline':args.deadline,'freeze_sha256':expected,'script_sha256':sha(__file__),'labels_read':False,'scoring_enabled':False,'stages':[]}
    awake=None
    with (dest/'watcher.lock').open('a') as watcher:
        fcntl.flock(watcher,fcntl.LOCK_EX|fcntl.LOCK_NB)
        atomic(dest/'runtime-run.json',state)
        try:
            while True:
                if time.time()>=deadline:raise TimeoutError('Deadline while awaiting inference completion')
                ready,why=barrier(root,expected,generation=args.generation)
                if ready:break
                state['barrier']=why;atomic(dest/'runtime-run.json',state)
                if not args.wait:return {'status':'NOT_READY','barrier':why,'labels_read':False}
                time.sleep(min(30,max(0,deadline-time.time())))
            if not args.run:return {'status':'READY_NO_ACTION','barrier':why,'labels_read':False}
            if not args.future_resource_lease:raise PermissionError('Explicit root future ML resource lease required')
            verify_all(root,expected,args.generation)
            with heavy_lease(workspace/'.runtime/cheap-guards/heavy-model.lock'):
                ready,why=barrier(root,expected,generation=args.generation)
                if not ready:raise RuntimeError('Barrier changed after acquiring ML lock')
                plan=commands(workspace,why['available_models'],args.generation)
                state['available_models']=why['available_models'];state['unavailable_models']=why['unavailable_models']
                state['barrier']=why;state['heavy_lease_acquired_utc']=dt.datetime.now(dt.timezone.utc).isoformat();state['status']='RUNNING'
                if sys.platform=='darwin':awake=subprocess.Popen(['caffeinate','-i','-w',str(os.getpid())])
                for stage,command,marker in plan:
                    verify_all(root,expected,args.generation)
                    if stage.startswith('predict-'):
                        for folder in (root/f'evaluation-v{args.generation}',root/f'evaluation-partial-v{args.generation}'):
                            verify_completed(folder/'METHODS_FROZEN.json','required-both-training-freezes')
                    if marker is not None and marker.exists():
                        state['stages'].append(verify_completed(marker,stage));atomic(dest/'runtime-run.json',state);continue
                    execute(command,stage,workspace,dest,state,deadline)
                    verify_all(root,expected,args.generation)
                    if marker is not None:verify_completed(marker,stage)
                state['status']='PREDICTIONS_FROZEN_AWAITING_ROOT_UNBLIND';state['completed_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
                state['methods_freezes']={name:sha(root/name/'METHODS_FROZEN.json') for name in (f'evaluation-v{args.generation}',f'evaluation-partial-v{args.generation}')}
                # Stop here. No labels, scores, threshold changes or post-test fits.
        except TimeoutError as exc:state['status']='DEADLINE';state['error']=str(exc)
        except Exception as exc:
            state['status']='FAILED';state['error']=f'{type(exc).__name__}: {exc}';raise
        finally:
            if awake is not None:awake.terminate();awake.wait()
            state.pop('child_pid',None);state['finished_utc']=dt.datetime.now(dt.timezone.utc).isoformat();atomic(dest/'runtime-run.json',state)
    return state


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',type=Path,default=Path.cwd());parser.add_argument('--generation',type=int,default=5);parser.add_argument('--deadline',default=DEADLINE)
    parser.add_argument('--plan-only',action='store_true');parser.add_argument('--run',action='store_true');parser.add_argument('--wait',action='store_true');parser.add_argument('--future-resource-lease',action='store_true');args=parser.parse_args()
    result=run(args);print(json.dumps(result,indent=2));return 0 if result['status'] in ('PLAN_ONLY','READY_NO_ACTION','PREDICTIONS_FROZEN_AWAITING_ROOT_UNBLIND') else 75
if __name__=='__main__':raise SystemExit(main())
