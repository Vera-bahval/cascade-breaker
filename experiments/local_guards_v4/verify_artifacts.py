"""Verify delivered artifact bytes and frozen method/data provenance, offline."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, default=HERE / 'research-manifest.json')
    args = p.parse_args()
    delivered = json.loads(args.manifest.read_text())
    failures, checked = [], 0
    for relative, expected in delivered['files'].items():
        path = ROOT / relative
        checked += 1
        if not path.is_file() or digest(path) != expected:
            failures.append(relative)
    frozen = json.loads((HERE / 'results/frozen-methods.json').read_text())
    for name, expected in {**frozen['sources'], **frozen['files']}.items():
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        checked += 1
        if not path.is_file() or digest(path) != expected:
            failures.append('frozen:' + name)
    baseline = subprocess.run(['git', 'diff', '--quiet', delivered['baseline_revision'], '--',
                               'experiments/local_guards_v3'], cwd=ROOT)
    if baseline.returncode:
        failures.append('v3 baseline diff')
    record = {'checked_hashes': checked, 'failures': failures,
              'v3_unchanged_from_baseline': baseline.returncode == 0,
              'new_inference_api_calls': 0}
    print(json.dumps(record, indent=2))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
