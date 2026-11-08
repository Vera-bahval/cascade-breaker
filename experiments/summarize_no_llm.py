"""Recount correct autonomous decisions from frozen outputs; no inference/fitting."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
V3, V4 = HERE/'local_guards_v3', HERE/'local_guards_v4'


def rows(path):
    with (gzip.open(path,'rt') if path.suffix=='.gz' else path.open()) as h:
        return [json.loads(line) for line in h]


def main():
    inputs=[V3/'closed-test/gold-actions.jsonl',V3/'results/closed-predictions.jsonl.gz',
            V4/'closed/gold-actions.jsonl.gz',V4/'results/closed-predictions.jsonl.gz']
    gold3={r['prefix_id']:r['decision'] for r in rows(inputs[0])}
    pred3=rows(inputs[1]); gold4={r['prefix_id']:r['target'] for r in rows(inputs[2])};pred4=rows(inputs[3])
    result={}
    for version,gold,pred,names in [('v3',gold3,pred3,['rules','legacy_v1','legacy_v2','structured_logistic','structured_catboost','text_diagnostic']),
                                    ('v4',gold4,pred4,['A_with_P4','A_plus_allB'])]:
        result[version]={}
        for name in names:
            selected=[r for r in pred if r['method']==name and
                      (version=='v4' or (r['strategy']=='P4' and r['seed'] in (None,17)))]
            assert len(selected)==len(gold)==len({r['prefix_id'] for r in selected})
            confusion=Counter((gold[r['prefix_id']],r['decision']) for r in selected)
            correct=sum(confusion[d,d] for d in ('ALLOW','BLOCK'))
            result[version][name]={'cases':len(gold),'decisive_answers':sum(r['decision'] in ('ALLOW','BLOCK') for r in selected),
                'correct_decisive':correct,'correct_decisive_coverage':correct/len(gold),
                'confusion':{a+' -> '+b:n for (a,b),n in sorted(confusion.items())}}
    for name,n in {'rules':255,'legacy_v1':179,'legacy_v2':179,'structured_logistic':86,'structured_catboost':97,'text_diagnostic':160}.items():
        assert result['v3'][name]['correct_decisive']==n
    assert result['v4']['A_plus_allB']['correct_decisive']==291
    result['definition']='gold equals prediction and prediction is ALLOW or BLOCK; UNKNOWN is not solved, even when it stops execution'
    result['inputs']={str(p.relative_to(HERE.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    result['source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['new_inference_api_calls']=0
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
