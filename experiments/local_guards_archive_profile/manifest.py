import argparse,json
from .prepare import HERE
from experiments.local_guards_adapter_repair.inventory import sha,write_json
EXCLUDED={'release-manifest.json','FINAL_REVIEW.md','review-receipt.json'}
def manifest():
    return dict(report_sha256=sha(HERE.parent/'NO_LLM_REPORT.md'),files={str(p.relative_to(HERE)):sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in EXCLUDED},new_model_calls=0)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();m=manifest()
    if a.check:
        assert m==json.loads((HERE/'release-manifest.json').read_text());print('ARCHIVE_PROFILE_MANIFEST_PASS')
    else:write_json(HERE/'release-manifest.json',m)
