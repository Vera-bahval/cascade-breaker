"""Admitted deterministic inference only, no scoring, models or network."""
import json
from .prepare import HERE,ROOT,METHODS
from .audit_inputs import audit
from experiments.local_guards_adapter_repair.inventory import rows,sha,write_json
from experiments.local_guards_adapter_repair.prepare import preparation_fence,writer
from experiments.local_guards_adapter_repair.execute_reviewed import load_checker

CONFIGS=[dict(name=m,family=m,profile='A') for m in METHODS]+[
    dict(name='v4.3_payment',family='v4.3',profile='A08'),
    dict(name='constant_ALLOW',family=None,profile=None),dict(name='constant_BLOCK',family=None,profile=None)]


def admitted():
    p=json.loads((HERE/'approval.json').read_text())
    assert p['status']=='APPROVED' and p['input_manifest_sha256']==sha(HERE/'input-manifest.json')
    audit()
    return p


def checker(config):
    if config['family'] is None:
        return lambda payload:dict(decision=config['name'].split('_')[1],reasons=['constant_control'])
    return load_checker(config['family'],'raw',config['profile'])[0]


def decision(fn,payload):
    try:
        result=dict(fn(payload));result.pop('timing_ms',None);result.pop('timing',None)
        return result
    except Exception as e:return dict(decision='UNKNOWN',execution_error=type(e).__name__,reason=str(e))


def run():
    approved=admitted();path=HERE/'predictions.jsonl.gz'
    if path.exists():raise FileExistsError(path)
    with preparation_fence(),writer(path) as emit:
        checkers=[(c,checker(c)) for c in CONFIGS]
        count=0
        for row in rows(HERE/'prepared-inputs.jsonl.gz'):
            for config,fn in checkers:
                adapted=row['adapters'][config['family']] if config['family'] else dict(payload={},applicable=True)
                result=decision(fn,adapted['payload']) if adapted['applicable'] else dict(decision=None,availability='ADAPTER_UNAVAILABLE')
                emit(dict(prefix_id=row['prefix_id'],episode_id=row['episode_id'],cut_seq=row['cut_seq'],mode=row['mode'],
                    method=config['name'],input_sha256=row['payload_sha256'].get(config['family']),result=result))
                count+=1
    write_json(HERE/'prediction-freeze.json',dict(input_manifest_sha256=sha(HERE/'input-manifest.json'),approval_sha256=sha(HERE/'approval.json'),
        runner_sha256=sha(__file__),predictions_sha256=sha(path),records=count,configs=CONFIGS,label_reads=0,new_model_calls=0))

if __name__=='__main__':run()
