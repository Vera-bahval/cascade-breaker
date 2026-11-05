"""Approved offline inference. No labels, fits, network or live FinBot runs."""
import argparse
from collections import Counter,defaultdict
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import pickle
import sys
import time

from experiments.local_guards_adapter_repair.inventory import HERE as REPAIR, ROOT, rows,sha,write_json
from experiments.local_guards_adapter_repair.prepare import preparation_fence,writer
from experiments.local_guards_adapter_repair.execute_reviewed import load_checker

HERE=Path(__file__).resolve().parent
INPUTS=REPAIR/'inputs'
REGISTRY=json.loads((REPAIR/'methods.json').read_text())['methods']
BASE='c42ca3833dc770a5aa71a815c409cc3ccd55d8ad'


def config_id(method,variant='rule',profile='A'):
    return method+'|'+variant+'|'+profile


def configs():
    result=[]
    for m in REGISTRY:
        method=m['method']
        if m['kind']=='ml':
            variants=m['variants']+(['argmax_diagnostic'] if method.startswith(('frozen/','frozen_revision2/')) else [])
            result.extend(dict(id=config_id(method,v),method=method,variant=v,profile='A',
                               family=m['payload_family'],kind='ml') for v in variants)
        elif method in ('v4','v4.2','v4.3'):
            result.extend(dict(id=config_id(method,'rule',p),method=method,variant='rule',profile=p,
                               family=method,kind='rule') for p in ('A','A08','early','A+B01','A+B02','A+B03','B'))
        else:
            result.append(dict(id=config_id(method),method=method,variant='rule',profile='A',family=method,kind='rule'))
    result.extend(dict(id=config_id('constant_'+d),method='constant_'+d,variant='rule',profile='A',family='v3',kind='constant')
                  for d in ('ALLOW','BLOCK','UNKNOWN'))
    return result


def policy(profile):
    if profile=='A08':return {'profile':'A','enabled_requirements':['A08']}
    if profile=='early':return {'profile':'A','enabled_requirements':['A01','A02','A03','A04','A05','A06','A07','A09']}
    if profile.startswith('A+'):
        return {'profile':'B','enabled_requirements':['A01','A02','A03','A04','A05','A06','A07','A08','A09',profile[2:]]}
    return profile


def checker(config):
    if config['kind']=='constant':
        return lambda payload:{'decision':config['method'].split('_',1)[1],'reasons':['constant_control']}
    return load_checker(config['method'],config['variant'] if config['kind']=='ml' else 'raw',policy(config['profile']))[0]


def freeze():
    from experiments.local_guards_adapter_repair.execute_reviewed import approval
    admitted=approval(INPUTS,REPAIR/'approval.json')
    value=dict(base=BASE,adapter_reviewed_commit=admitted['reviewed_commit'],
               preparation_revision=2,input_manifest_sha256=sha(INPUTS/'manifest.json'),
               approval_sha256=sha(REPAIR/'approval.json'),registry_sha256=sha(REPAIR/'methods.json'),
               protocol_sha256=sha(HERE/'PROTOCOL.md'),runner_sha256=sha(Path(__file__)),
               methods=configs(),new_model_calls=0,fit_allowed=False)
    write_json(HERE/'configuration.json',value)


def validate():
    frozen=json.loads((HERE/'configuration.json').read_text())
    assert frozen['runner_sha256']==sha(Path(__file__))
    assert frozen['input_manifest_sha256']==sha(INPUTS/'manifest.json')
    assert frozen['registry_sha256']==sha(REPAIR/'methods.json')
    assert frozen['protocol_sha256']==sha(HERE/'PROTOCOL.md')
    assert frozen['methods']==configs()
    return frozen


def record(row,config,result,elapsed=None):
    result=dict(result)
    # Batch throughput and embedded model timers are not single-request latency.
    result.pop('timing',None);result.pop('timing_ms',None)
    return dict(prefix_id=row['prefix_id'],case_id=row.get('case_id'),episode_id=row.get('episode_id'),
                mode=row['mode'],event_seq=row['event_seq'],checkpoint=row['checkpoint'],
                config=config['id'],method=config['method'],variant=config['variant'],profile=config['profile'],
                input_sha256=row['sha'],feature_sha256=row.get('feature_sha256'),
                result=result,decision_ms=elapsed)


def selected_inputs(family,dataset='p4'):
    manifest=json.loads((INPUTS/'manifest.json').read_text())
    for name in manifest['outputs']:
        if not name.startswith(dataset+'-inputs'):continue
        for row in rows(INPUTS/name):
            adapted=row['adapters'].get(family)
            if adapted is None:raise ValueError('missing prepared adapter')
            yield dict(prefix_id=row['prefix_id'],case_id=row.get('case_id'),episode_id=row.get('episode_id'),
                mode=row['mode'],event_seq=row['bundle']['event_seq'],checkpoint=row['bundle']['checkpoint'],
                payload=adapted['payload'],applicable=adapted['applicable'],sha=row['payload_sha256'][family],
                features=row['features'],feature_sha256=row['feature_sha256'])


class Output:
    def __init__(self,directory,dataset,config):
        self.path=directory/(dataset+'-'+sha256(config['id'].encode()).hexdigest()[:16]+'.jsonl.gz')
        self.config=config;self.dataset=dataset;self.counts=Counter()
    def __enter__(self):
        self.context=writer(self.path);self.write=self.context.__enter__();return self
    def emit(self,row,result,elapsed=None):
        self.write(record(row,self.config,result,elapsed));self.counts[row['mode']]+=1
    def __exit__(self,*exc):
        self.context.__exit__(*exc)
    def receipt(self):
        return dict(file=self.path.name,config=self.config['id'],dataset=self.dataset,
                    modes=dict(self.counts),rows=sum(self.counts.values()))


def call_one(fn,payload):
    try:return fn(payload)
    except Exception as error:
        return dict(decision='UNKNOWN',execution_error=True,error_type=type(error).__name__,
                    error=str(error),reasons=['verifier_exception'],stop=True)


def run_rules(directory,all_configs):
    outputs=[]
    with ExitStack() as stack:
        active=[(c,checker(c)) for c in all_configs if c['kind']!='ml']
        sinks={c['id']:stack.enter_context(Output(directory,'p4',c)) for c,_ in active}
        manifest=json.loads((INPUTS/'manifest.json').read_text())
        for row in rows(INPUTS/'p4-inputs.jsonl.gz'):
            for c,fn in active:
                adapted=row['adapters'][c['family']]
                inp=dict(prefix_id=row['prefix_id'],case_id=row.get('case_id'),mode=row['mode'],
                    event_seq=row['bundle']['event_seq'],checkpoint='P4',sha=row['payload_sha256'][c['family']])
                start=time.perf_counter_ns()
                result=call_one(fn,adapted['payload']) if adapted['applicable'] else {'decision':None,'availability':'ADAPTER_UNAVAILABLE'}
                sinks[c['id']].emit(inp,result,(time.perf_counter_ns()-start)/1e6)
    outputs.extend(s.receipt() for s in sinks.values())
    early=[(c,fn) for c,fn in active if c['method'] in ('v4','v4.2','v4.3') and c['profile']!='A08']
    with ExitStack() as stack:
        sinks={c['id']:stack.enter_context(Output(directory,'early',c)) for c,_ in early}
        total=0
        for name in manifest['outputs']:
            if not name.startswith('early-inputs'):continue
            for row in rows(INPUTS/name):
                for c,fn in early:
                    inp=dict(prefix_id=row['prefix_id'],episode_id=row['episode_id'],mode=row['mode'],
                        event_seq=row['bundle']['event_seq'],checkpoint=row['bundle']['checkpoint'],
                        sha=row['payload_sha256'][c['family']])
                    start=time.perf_counter_ns();result=call_one(fn,row['adapters'][c['family']]['payload'])
                    sinks[c['id']].emit(inp,result,(time.perf_counter_ns()-start)/1e6)
                total+=1
                if total%4000==0:print(json.dumps({'early_rows':total}),flush=True)
    outputs.extend(s.receipt() for s in sinks.values())
    return outputs,[]


def retrained(directory,all_configs,stem):
    root=ROOT/'experiments/local_guards_ml_retrain';sys.path.insert(0,str(root))
    if stem=='frozen_revision2':
        from experiments.local_guards_ml_retrain import evaluation_revision2 as ev
    else:
        from experiments.local_guards_ml_retrain import evaluation as ev
    manifest=json.loads((root/stem/'freeze-manifest.json').read_text())
    inputs=list(selected_inputs('retrain_ml'));output=[];checks=[]
    for method in manifest['methods']:
        candidate=ev.Frozen(root/stem,method,manifest)
        cs=[c for c in all_configs if c['method']==stem+'/'+method['name']]
        ps=ev.probabilities(candidate.model,ev.FeatureBatch(
            [r['features']['retrain_revision2_'+method['feature_mode'] if stem=='frozen_revision2' else 'retrain_original_'+method['feature_mode']] for r in inputs],method['feature_mode']))
        for config in cs:
            with Output(directory,'p4',config) as sink:
                parity=0
                for row,p in zip(inputs,ps,strict=True):
                    row=dict(row,feature_sha256=row['feature_sha256'][
                        ('retrain_revision2_' if stem=='frozen_revision2' else 'retrain_original_')+method['feature_mode']])
                    if not ev.eligible(row['payload'],candidate.contract):
                        result={'decision':None,'availability':'NOT_APPLICABLE','checked':False}
                    elif config['variant']=='argmax_diagnostic':
                        winners=[k for k in ev.CLASSES if p[k]==max(p.values())]
                        result={'decision':winners[0] if len(winners)==1 else 'UNKNOWN','probabilities':p,'diagnostic_only':True}
                    else:
                        result=candidate.from_probability(row['payload'],p,config['variant'])
                        if parity<3:
                            original=candidate.one(row['payload'],config['variant'])
                            assert result['decision']==original['decision']
                            assert max(abs(p[k]-original['probabilities'][k]) for k in p)<1e-10
                            parity+=1
                    sink.emit(row,result)
            output.append(sink.receipt())
            checks.append(dict(config=config['id'],single_batch_parity=parity,feature_api='frozen FeatureBatch'))
        print(json.dumps({'model':stem+'/'+method['name']}),flush=True)
    return output,checks


def archive_ml(directory,all_configs):
    from experiments.local_guards_archive_comparison import ml
    sys.modules.setdefault('ml',ml)
    inputs=list(selected_inputs('archive_ml'));output=[];checks=[]
    from experiments.local_guards_archive_comparison.methods import guard
    for entry in REGISTRY:
        if not entry['method'].startswith('archive_ml/'):continue
        candidate=ml.load(ROOT/entry['model_file'])
        ps=ml.probabilities(candidate.payload['model'],[r['payload'] for r in inputs])
        cs=[c for c in all_configs if c['method']==entry['method']]
        for config in cs:
            with Output(directory,'p4',config) as sink:
                for i,(row,p) in enumerate(zip(inputs,ps,strict=True)):
                    raw=max(sorted(p),key=p.get)
                    op=candidate.payload['operating_point']['p4']
                    thresholds=(op.get('thresholds') or {}).get(row['checkpoint'])
                    calibrated=ml.selective(p,thresholds) if op['status']=='FEASIBLE' and thresholds is not None else 'UNKNOWN'
                    variant=config['variant'];result={'decision':raw if variant=='raw' else calibrated,'probabilities':p,
                        'raw_decision':raw,'calibrated_decision':calibrated,'operating_point_status':op['status']}
                    if variant=='gated':
                        gate=guard(row['payload'],'native_core')
                        result['decision']='BLOCK' if gate['decision']=='BLOCK' else 'UNKNOWN' if gate['decision']=='UNKNOWN' and calibrated=='ALLOW' else calibrated
                        result['native_gate']=gate
                    if i<3:
                        original=candidate.predict(row['payload'],native_gate=variant=='gated')
                        assert result['decision']==original[{'raw':'raw_decision','calibrated':'calibrated_decision','gated':'gated_decision'}[variant]]
                        assert max(abs(p[k]-original['probabilities'][k]) for k in p)<1e-10
                    sink.emit(dict(row,feature_sha256=row['feature_sha256']['archive']),result)
            output.append(sink.receipt());checks.append(dict(config=config['id'],single_batch_parity=3))
    return output,checks


def v3_ml(directory,all_configs):
    root=ROOT/'experiments/local_guards_v3';sys.path.insert(0,str(root))
    from experiments.local_guards_v3 import evaluate_v3 as ev
    inputs=list(selected_inputs('v3_ml'));output=[];checks=[]
    policy_data=json.loads((root/'results/frozen/policy.json').read_text())
    grouped=defaultdict(list)
    for entry in REGISTRY:
        if entry['method'].startswith('v3_ml/'):grouped[entry['model_file']].append(entry)
    for filename,entries in grouped.items():
        model=pickle.loads((ROOT/filename).read_bytes())
        payloads=[dict(r['payload'],prefix_id=str(i)) for i,r in enumerate(inputs)]
        scored=ev.score_rows(payloads,[dict(prefix_id=str(i),episode_id=str(i)) for i in range(len(inputs))],policy_data,model)
        for entry in entries:
            config=next(c for c in all_configs if c['method']==entry['method'])
            cfg=entry['configuration']
            preds=ev.apply_threshold(scored,ev.unbound(cfg.get('high',cfg.get('threshold'))),cfg['combined'],
                                    ev.unbound(cfg['low']) if cfg['kind']=='router' else None)
            with Output(directory,'p4',config) as sink:
                fn=checker(config)
                for i,(row,result) in enumerate(zip(inputs,preds,strict=True)):
                    if not ev.eligible(row['payload'],cfg['strategy']):result={'decision':None,'availability':'NOT_APPLICABLE'}
                    elif i<3:assert result['decision']==fn(row['payload'])['decision']
                    result.pop('timing_ms',None)
                    sink.emit(dict(row,feature_sha256=row['feature_sha256']['v3_text' if 'text_diagnostic' in entry['method'] else 'v3_structured']),result)
            output.append(sink.receipt());checks.append(dict(config=config['id'],single_batch_parity=3))
    return output,checks


def run(group,directory):
    frozen=validate();directory.mkdir(parents=True,exist_ok=False)
    with preparation_fence():
        if group=='rules':outputs,checks=run_rules(directory,frozen['methods'])
        elif group=='v3_ml':outputs,checks=v3_ml(directory,frozen['methods'])
        elif group=='archive_ml':outputs,checks=archive_ml(directory,frozen['methods'])
        else:outputs,checks=retrained(directory,frozen['methods'],group)
    assert validate()==frozen
    # Read only completed output bytes, after the label-blind inference fence.
    for output in outputs:output['sha256']=sha(directory/output['file'])
    write_json(directory/'receipt.json',dict(group=group,base=BASE,
        configuration_sha256=sha(HERE/'configuration.json'),outputs=outputs,checks=checks,
        label_reads=0,model_api_calls=0,fit_calls=0))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',action='store_true')
    parser.add_argument('--group',choices=['rules','v3_ml','archive_ml','frozen','frozen_revision2'])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    freeze() if args.freeze else run(args.group,args.output)
