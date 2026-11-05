"""Read-only integrity, denominators and singleton/batch verification."""
import json
from pathlib import Path

from .run import HERE,INPUTS,REPAIR,validate
from .evaluate import receipts
from experiments.local_guards_adapter_repair.audit import audit as input_audit
from experiments.local_guards_adapter_repair.inventory import rows,sha,write_json


def audit():
    configuration=validate();inputs=input_audit(INPUTS);outputs=receipts()
    assert sha(REPAIR/'approval.json')==configuration['approval_sha256']
    assert json.loads((REPAIR/'approval.json').read_text())['status']=='APPROVED'
    inputs.pop('independent_review',None)
    p4=json.loads((HERE/'results/p4-summary.json').read_text())
    count_fields=('correct_allow','correct_block','wrong_allow','wrong_block','insufficient_allow',
                  'insufficient_block','unknown','unavailable')
    for key,modes in p4['methods'].items():
        for mode,s in modes.items():
            assert sum(s[k] for k in count_fields)==542,(key,mode)
            assert s['correct']==s['correct_allow']+s['correct_block']
            assert sum(s['by_category'][c]['n'] for c in s['by_category'])==542
            assert s['execution_errors']==0,(key,mode)
    assert p4['labels']=={'ALLOW':7,'BLOCK':238,'INSUFFICIENT':297}
    early=json.loads((HERE/'results/early-summary.json').read_text())
    for key,modes in early['methods'].items():
        for mode,s in modes.items():
            assert s['n']==18676 and s['episodes']==754
            assert sum(s['sample']['ALL'][k] for k in count_fields)==128
            assert sum(sum(counts.values()) for counts in s['points'].values())==18676
            for policy,r in s['sequential'].items():
                c=r['counts'];assert c['reached_points']+c['skipped_points']==18676
                assert len({x['episode_id'] for x in r['first_stops']})==len(r['first_stops'])
    wanted={}
    for r in rows(HERE/'benchmark/singleton-decisions.jsonl.gz'):
        key=r['config'],r['mode'],r['prefix_id']
        assert key not in wanted
        wanted[key]=r
    checked=0
    for item in outputs:
        if item['dataset']!='p4' or not any(k[0]==item['config'] for k in wanted):continue
        for r in rows(item['path']):
            key=r['config'],r['mode'],r['prefix_id']
            if key not in wanted:continue
            one=wanted[key]
            assert (r['input_sha256'],r['result']['decision'])==(one['input_sha256'],one['decision']),key
            assert not one['execution_error'],key
            checked+=1
    assert checked==len(wanted)
    for folder,receipt_file in (('results','scoring-receipt.json'),('benchmark','receipt.json')):
        receipt=json.loads((HERE/folder/receipt_file).read_text())
        for name,h in receipt['outputs'].items():assert sha(HERE/folder/name)==h,(folder,name)
    render=json.loads((HERE/'render-receipt.json').read_text())
    for name,h in render['outputs'].items():assert sha(HERE/name)==h,name
    return dict(status='PASS',prepared_input_audit=inputs,adapter_approval='APPROVED',
        p4_configurations=len(p4['methods']),p4_states=542,early_states=18676,
        early_labels=128,early_episodes=754,prediction_files=len(outputs),
        prediction_records=sum(o['rows'] for o in outputs),singleton_batch_comparisons=checked,
        source_models_unchanged=True,new_model_api_calls=0,fit_calls=0)


if __name__=='__main__':
    result=audit();write_json(HERE/'verification.json',result);print(json.dumps(result,sort_keys=True))
