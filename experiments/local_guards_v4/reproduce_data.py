"""Rebuild the frozen archive package in a fresh directory, leaving it intact."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'data').mkdir()
    shutil.copyfile(here / 'policy.json', args.output / 'policy.json')
    shutil.copyfile(here / 'data/source-inventory.json', args.output / 'data/source-inventory.json')
    spec = importlib.util.spec_from_file_location('frozen_v4_custodian', here / 'prepare_data.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Output location only. ROOT, V3, native source revisions and all methods
    # remain pinned to the real checkout. No implementation file is changed.
    module.HERE = args.output.resolve()
    module.main()
    expected = json.loads((here / 'data/manifest.json').read_text())['files']
    checks = {name: digest(args.output / 'data' / name) == value for name, value in expected.items()}
    for name in ('observations.jsonl.gz', 'gold-actions.jsonl.gz'):
        checks['train-package/' + name] = digest(args.output / 'data/train-package' / name) == digest(here / 'data/train-package' / name)
    result = {'payload_checks': checks, 'all_equal': all(checks.values()),
              'manifest_path_difference': 'Only output manifest paths differ; payload bytes must match.'}
    (args.output / 'reproduction-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return int(not result['all_equal'])


if __name__ == '__main__':
    raise SystemExit(main())
