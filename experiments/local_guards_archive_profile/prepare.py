"""Prepare only from sealed pre-action packets, no labels or outcomes."""
from collections import Counter
from pathlib import Path
import json
from .profile import prepare,METHODS
from experiments.local_guards_adapter_repair.inventory import ROOT,rows,sha,write_json
from experiments.local_guards_adapter_repair.prepare import preparation_fence,writer
from experiments.local_guards_archive_comparison.collector import digest
HERE=Path(__file__).resolve().parent
EXP=HERE.parent


def run():
    counts=Counter();sources={};out=HERE/'inputs.jsonl.gz'
    if out.exists():raise FileExistsError(out)
    paths=[('legacy176',EXP/'local_guards_legacy176/prepared-inputs.jsonl.gz'),('p4',EXP/'local_guards_adapter_repair/inputs/p4-inputs.jsonl.gz')]
    paths.extend(('early',p) for p in sorted((EXP/'local_guards_adapter_repair/inputs').glob('early-inputs-*.jsonl.gz')))
    with preparation_fence(),writer(out) as emit:
        for dataset,path in paths:
            sources[str(path.relative_to(ROOT))]=sha(path)
            for row in rows(path):
                if dataset=='legacy176' and row['mode']!='full' or dataset=='p4' and row['mode'] not in ('common','expanded'):continue
                for method in METHODS if dataset!='early' else ('v4.3_archive',):
                    payload=prepare(row,method)
                    record={k:row[k] for k in ('prefix_id','episode_id','case_id','mode','action_boundary') if k in row}
                    record.update(dataset=dataset,method=method,payload=payload,input_sha256=digest(payload),source_sha256=sources[str(path.relative_to(ROOT))])
                    emit(record);counts[dataset+'/'+row['mode']+'/'+method]+=1
    write_json(HERE/'input-manifest.json',dict(base='f4008520be82006fc5b56aa88506565594ca2ca9',code={n:sha(HERE/n) for n in ('profile.py','prepare.py','CONTRACT.md','test_profile.py')},sources=sources,counts=counts,inputs_sha256=sha(out),label_reads=0,model_calls=0))
    print(dict(counts))

if __name__=='__main__':run()
