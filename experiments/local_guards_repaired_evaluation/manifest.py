"""Pin released artifacts; --check verifies bytes without recomputation."""
import argparse
import json
from .run import HERE,REPAIR
from experiments.local_guards_adapter_repair.inventory import sha,write_json

EXCLUDED={'release-manifest.json','REVIEW.md','review-receipt.json'}

def manifest():
    files={str(p.relative_to(HERE)):sha(p) for p in sorted(HERE.rglob('*'))
           if p.is_file() and '__pycache__' not in p.parts and p.name not in EXCLUDED}
    return dict(adapter_manifest_sha256=sha(REPAIR/'inputs/manifest.json'),
                adapter_approval_sha256=sha(REPAIR/'approval.json'),
                report_sha256=sha(HERE.parent/'NO_LLM_REPORT.md'),files=files)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true');args=parser.parse_args()
    current=manifest()
    if args.check:
        assert current==json.loads((HERE/'release-manifest.json').read_text())
        print('RELEASE_MANIFEST_PASS')
    else:write_json(HERE/'release-manifest.json',current)
