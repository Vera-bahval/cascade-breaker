"""Pin released files; check without inference or recomputation."""
import argparse,json
from .prepare import HERE
from experiments.local_guards_adapter_repair.inventory import sha,write_json

EXCLUDED={'release-manifest.json','FINAL_REVIEW.md','final-review-receipt.json'}

def manifest():
    files={str(p.relative_to(HERE)):sha(p) for p in sorted(HERE.rglob('*'))
        if p.is_file() and '__pycache__' not in p.parts and p.name not in EXCLUDED}
    return dict(report_sha256=sha(HERE.parent/'NO_LLM_REPORT.md'),files=files,new_model_calls=0)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    current=manifest()
    if args.check:
        assert current==json.loads((HERE/'release-manifest.json').read_text())
        print('LEGACY176_RELEASE_PASS')
    else:write_json(HERE/'release-manifest.json',current)
