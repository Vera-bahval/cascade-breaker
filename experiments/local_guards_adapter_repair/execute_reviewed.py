"""Future local inference entry point. Requires independent approval of inputs.

This command is shipped for the next task and is not run during preparation.
It writes individual predictions only, without labels, scoring or report edits.
"""
import argparse
import json
from pathlib import Path
import sys

from .inventory import HERE, EXP, ROOT, rows, sha
from .prepare import writer
from .audit import audit


def approval(inputs,path):
    receipt=json.loads(Path(path).read_text())
    if receipt.get('status')!='APPROVED' or not receipt.get('reviewer') or not receipt.get('reviewed_commit'):
        raise ValueError('independent review approval required')
    if receipt.get('input_manifest_sha256')!=sha(Path(inputs)/'manifest.json'):
        raise ValueError('approval is for different inputs')
    audit(inputs)
    return receipt


def load_checker(method,variant,profile):
    if method in ('v1','v2'):
        from experiments.local_guards_v3.legacy import rules,rules_v2
        def legacy(payload):
            state=payload['state']
            if method=='v2':
                state=rules_v2.enrich_state(state,payload['prior'])
            issues=(rules if method=='v1' else rules_v2).violations(state)
            return {'decision':'BLOCK' if issues else 'ALLOW','reasons':issues}
        return legacy,method
    if method=='v3':
        from experiments.local_guards_v3.rules_v3 import guard
        return guard,method
    if method in ('v4','v4.2','v4.3'):
        if method=='v4':
            from experiments.local_guards_v4.guard import guard
        elif method=='v4.2':
            from experiments.local_guards_v4_followup.guard import guard
        else:
            from .guard43 import guard
        policy={'profile':'A','enabled_requirements':['A08']} if profile=='A08' else profile
        return lambda payload:guard(payload,policy),method
    if method in ('native','native_core'):
        from experiments.local_guards_archive_comparison.methods import guard
        return lambda payload:guard(payload,method),method
    registry=json.loads((HERE/'methods.json').read_text())['methods']
    entry=next((m for m in registry if m['method']==method),None)
    if entry is None or entry['kind']!='ml':
        raise ValueError('unknown method')
    if method.startswith('v3_ml/'):
        if variant!='frozen':
            raise ValueError('v3 ML uses its frozen threshold configuration')
        import pickle
        root=EXP/'local_guards_v3'
        sys.path.insert(0,str(root))
        from experiments.local_guards_v3 import evaluate_v3
        model=pickle.loads((ROOT/entry['model_file']).read_bytes())
        policy=json.loads((root/'results/frozen/policy.json').read_text())
        config=entry['configuration']
        def predict(payload):
            if not evaluate_v3.eligible(payload,config['strategy']):
                return {'decision':None,'checked':False,'availability':'NOT_APPLICABLE'}
            payload=dict(payload,prefix_id='input')
            scored=evaluate_v3.score_rows([payload],[{'prefix_id':'input','episode_id':'input'}],policy,model)
            return evaluate_v3.apply_threshold(scored,evaluate_v3.unbound(config.get('high',config.get('threshold'))),
                config['combined'],evaluate_v3.unbound(config['low']) if config['kind']=='router' else None)[0]
        return predict,'v3_ml'
    if variant not in entry['variants']:
        raise ValueError('unsupported variant for this frozen ML method')
    if method.startswith('archive_ml/'):
        from experiments.local_guards_archive_comparison import ml
        # Historical pickles may refer to the original standalone module name.
        sys.modules.setdefault('ml',ml)
        predictor=ml.load(ROOT/entry['model_file'])
        def predict(payload):
            result=predictor.predict(payload,native_gate=variant=='gated',placement='p4')
            key={'raw':'raw_decision','calibrated':'calibrated_decision','gated':'gated_decision'}[variant]
            return dict(result,decision=result[key])
        return predict,'archive_ml'
    root=EXP/'local_guards_ml_retrain'
    sys.path.insert(0,str(root))
    if method.startswith('frozen_revision2/'):
        from experiments.local_guards_ml_retrain import evaluation_revision2 as evaluation
        folder='frozen_revision2'
    else:
        from experiments.local_guards_ml_retrain import evaluation
        folder='frozen'
    release=root/folder
    manifest=json.loads((release/'freeze-manifest.json').read_text())
    name=method.split('/',1)[1]
    configuration=next(m for m in manifest['methods'] if m['name']==name)
    predictor=evaluation.Frozen(release,configuration,manifest)
    return lambda payload:predictor.one(payload,variant),'retrain_ml'


def execute(args):
    allowed={'p4':{'common','expanded','conditional'},'early':{'historical','conditional'}}
    if args.mode not in allowed[args.dataset]:
        raise ValueError('mode is incompatible with dataset')
    approval(args.inputs,args.approval)
    checker,family=load_checker(args.method,args.variant,args.profile)
    manifest=json.loads((args.inputs/'manifest.json').read_text())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    with writer(args.output) as emit:
        for name in manifest['outputs']:
            if not name.startswith(args.dataset+'-inputs'):
                continue
            for row in rows(args.inputs/name):
                if row['mode']!=args.mode:
                    continue
                adapted=row['adapters'].get(family)
                if adapted is None:
                    result={'decision':None,'availability':'NOT_APPLICABLE'}
                elif not adapted['applicable']:
                    result={'decision':None,'availability':'ADAPTER_UNAVAILABLE','coverage':adapted['coverage']}
                else:
                    result=checker(adapted['payload'])
                emit({'prefix_id':row['prefix_id'],'mode':row['mode'],'method':args.method,
                      'variant':args.variant,'profile':args.profile,'result':result,
                      'input_sha256':row['payload_sha256'].get(family)})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--approval',type=Path,required=True)
    parser.add_argument('--method',required=True)
    parser.add_argument('--dataset',choices=['p4','early'],required=True)
    parser.add_argument('--mode',required=True)
    parser.add_argument('--variant',choices=['raw','calibrated','gated','frozen'],default='raw')
    parser.add_argument('--profile',choices=['A','A08','B'],default='A')
    parser.add_argument('--output',type=Path,required=True)
    execute(parser.parse_args())
