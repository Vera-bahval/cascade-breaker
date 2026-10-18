#!/usr/bin/env python3
"""Root-only caller compatibility for frozen __main__.Model joblib artifacts."""
from __future__ import annotations
import argparse
import ast
from contextlib import contextmanager
import datetime as dt
import importlib.util
import inspect
import json
from pathlib import Path
import signal
import sys
import time
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from cascade_guard import v2_archive_latency_partial_05 as frozen, v2_eval
spec = importlib.util.spec_from_file_location('completion_05_profile', BASE / 'scripts/finish_guard_v2_05.py')
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
PLAN_SHA = 'bd8effa043ed587285be284deae9316ce87401af5e8618be0da1c773492238bc'

@contextmanager
def model_alias():
    import __main__
    absent = object(); previous = getattr(__main__, 'Model', absent)
    old.require(previous is absent or previous is v2_eval.Model, 'Unexpected existing __main__.Model')
    old.require(inspect.getfile(v2_eval.Model) == v2_eval.__file__, 'Model is not canonical frozen source')
    classes = [n.name for n in ast.parse(Path(v2_eval.__file__).read_text()).body if isinstance(n, ast.ClassDef)]
    old.require(classes == ['Model', 'RuleMap'], 'Unexpected frozen custom class inventory')
    __main__.Model = v2_eval.Model
    try:
        yield
    finally:
        if previous is absent: del __main__.Model
        else: __main__.Model = previous


def immutable_hashes(args, plan):
    paths = {p for p in plan['source_sha256'] if Path(p).suffix == '.py'}
    for name in ('METHOD_FREEZE_05.json', 'NEW_ABLATION_PROTOCOL_05.json'):
        paths.update(p for p in old.read(Path(plan['root']) / name)['sha256'] if Path(p).suffix == '.py')
    for name in ('METHODS_FROZEN.json', 'training-input-freeze.json'):
        path = args.methods / name; paths.add(str(path))
        paths.update(e['path'] for e in old.read(path)['files'])
    paths.update((str(args.methods / 'models.json'), str(args.completion)))
    paths.update(str(args.methods / 'models' / e['filename']) for e in old.read(args.methods / 'models.json'))
    return {str(p): old.sha(p) for p in sorted(paths)}


def execute(args):
    old.pinned(args.authorization_plan, PLAN_SHA)
    plan = old.read(args.authorization_plan)
    old.deadline(plan)
    old.pinned(args.compat_protocol, args.compat_protocol_sha256)
    compatibility = old.read(args.compat_protocol)
    old.require(compatibility['authorization'] == 'ROOT_PARTIAL_ARCHIVE_NAME_COMPAT_05', 'Wrong compatibility authorization')
    old.require(compatibility['authorization_plan_sha256'] == PLAN_SHA, 'Wrong original authorization')
    for p, h in compatibility['source_sha256'].items(): old.pinned(p, h)
    for p in (Path(__file__).resolve(), BASE / 'tests/test_v2_partial_profile_compat.py', BASE / 'GUARD-V2-PARTIAL-PROFILE-COMPAT-05.md'):
        old.require(str(p) in compatibility['source_sha256'], 'Missing compatibility source pin')
    old.pinned(args.completion, compatibility['completion_sha256'])
    old.pinned(args.plan, compatibility['original_profile_protocol_sha256'])
    old.pinned(compatibility['failure_log']['path'], compatibility['failure_log']['sha256'])
    error = Path(compatibility['failure_log']['path']).read_text()
    old.require('Only explicit archive rows allowed' in error, 'Unexpected original partial profiler failure')
    root = Path(plan['root'])
    old.require(args.methods.resolve() == (root / 'evaluation-partial-v5').resolve(), 'Partial methods required')
    old.require(args.rows.resolve() == (root / 'inputs-v5/archive-partial-rows.jsonl').resolve(), 'Actual pinned partial archive rows required')
    old.require([str(p.resolve()) for p in args.records] == compatibility['archive_records'], 'Partial records differ from original call')
    old.require(args.max_seconds == compatibility['max_seconds'], 'Partial profiling budget differs from original call')
    original = BASE / 'cascade_guard/v2_archive_latency.py'
    changed = BASE / 'cascade_guard/v2_archive_latency_partial_05.py'
    before = "('archive-p4-rows.jsonl','partial-archive-p4-rows.jsonl','archive-partial-p4-rows.jsonl','archive-p4-partial-rows.jsonl')"
    after = before[:-1] + ",'archive-partial-rows.jsonl')"
    old.require(original.read_text().count(before) == 1 and changed.read_text() == original.read_text().replace(before, after), 'Partial profiler has changes beyond single filename admission')
    for name, digest in compatibility['original_partial_receipts_sha256'].items():
        old.pinned(args.methods / name, digest)
    old.require(not args.output.exists(), 'Profile output already exists')
    old.require(args.output.name == 'profile.json' and args.output.parent == args.methods, 'Unexpected profiler output')
    # Run the original gate unchanged before installing the caller alias.
    frozen.validate_completion(args.methods, args.source_freeze, args.completion, args.authorization_plan, PLAN_SHA)
    before = immutable_hashes(args, plan)
    receipt = args.methods / 'PARTIAL_PROFILE_COMPAT_STARTED_05.json'
    old.exclusive(receipt, {'status': 'ONE_SHOT_STARTED', 'compat_protocol_sha256': args.compat_protocol_sha256, 'before_sha256': before})
    previous = None
    try:
        def timeout(signum, frame): raise TimeoutError('Frozen global deadline reached')
        previous = signal.signal(signal.SIGALRM, timeout)
        remaining = dt.datetime.fromisoformat(plan['completion_deadline_utc']).timestamp() - time.time()
        old.require(remaining > 0, 'Frozen deadline expired'); signal.setitimer(signal.ITIMER_REAL, remaining)
        with model_alias():
            result = frozen.run(args.methods, args.rows, args.records, args.source_freeze, args.plan, args.output, args.max_seconds, completion=args.completion, authorization_plan=args.authorization_plan, authorization_sha=PLAN_SHA)
        old.deadline(plan)
        after = immutable_hashes(args, plan); old.require(before == after, 'Frozen sources/models changed')
        for path, digest in compatibility['source_sha256'].items(): old.pinned(path, digest)
        old.exclusive(args.methods / 'PARTIAL_PROFILE_COMPAT_RECEIPT_05.json', {'status': 'COMPLETE', 'compat_protocol_sha256': args.compat_protocol_sha256, 'before_sha256': before, 'after_sha256': after, 'profile_sha256': old.sha(args.output), 'profile_complete': result['complete']})
        return {'status': 'COMPLETE', 'profile_complete': result['complete']}
    except BaseException as exc:
        old.exclusive(args.methods / 'PARTIAL_PROFILE_COMPAT_FAILED_05.json', {'status': 'FAILED_NO_AUTORETRY', 'error': type(exc).__name__ + ': ' + str(exc)})
        raise
    finally:
        if previous is not None:
            signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compat-protocol', type=Path, required=True); p.add_argument('--compat-protocol-sha256', required=True)
    p.add_argument('--authorization-plan', type=Path, required=True); p.add_argument('--completion', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True); p.add_argument('--source-freeze', type=Path, required=True)
    p.add_argument('--methods', type=Path, required=True); p.add_argument('--rows', type=Path, required=True)
    p.add_argument('--records', type=Path, nargs='+', required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--max-seconds', type=float, default=300); p.add_argument('--execute', action='store_true', required=True)
    print(json.dumps(execute(p.parse_args())))
if __name__ == '__main__': main()
