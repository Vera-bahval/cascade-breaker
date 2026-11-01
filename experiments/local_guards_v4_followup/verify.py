"""Read-only verification of archived sources and published derived tables."""
from pathlib import Path
import hashlib
import json
from .summarize import render_tables

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def check(mapping,base):
    for name,expected in mapping.items():
        if digest(base/name)!=expected:
            raise ValueError('hash mismatch: '+name)
    return len(mapping)


def verify():
    baseline=json.loads((HERE/'baseline.json').read_text())
    methods=json.loads((HERE/'methods-freeze.json').read_text())
    evaluation=json.loads((HERE/'evaluation-freeze.json').read_text())
    summary=json.loads((HERE/'results/summary.json').read_text())
    result=dict(baseline_files=check(baseline['files'],ROOT),
        method_sources=check(methods['sources'],ROOT),
        evaluation_sources=check(evaluation['sources'],ROOT),
        summary_inputs=check(summary['input_sha256'],HERE))
    assert summary['script_sha256']==digest(HERE/'summarize.py')
    assert (HERE/'TABLES.md').read_text()==render_tables(summary)
    assert evaluation['configurations_sha256']==digest(HERE/'configurations.json')
    artifacts=HERE/'ARTIFACTS.json'
    if artifacts.exists():
        result['published_files']=check(json.loads(artifacts.read_text())['sha256'],ROOT)
    result.update(status='verified',new_model_inference_calls=0,
        caveat='integrity verification is not production authorization or proof of every policy component')
    return result


if __name__=='__main__':print(json.dumps(verify(),indent=2))
