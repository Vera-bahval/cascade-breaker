#!/usr/bin/env python3
"""Manual one-shot recovery of the frozen scorer's JSONL Path boundary only."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

PLAN_SHA = 'bd8effa043ed587285be284deae9316ce87401af5e8618be0da1c773492238bc'
BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('frozen_completion_05', BASE / 'scripts/finish_guard_v2_05.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
OUTPUTS = ('metrics.json', 'UNBLINDED.json', 'pair-metrics.json', 'external-diagnostics.json')

@contextmanager
def path_adapter(evaluator, dataset):
    """The sole runtime modification; restore the binding even after failure."""
    original = evaluator.read_jsonl
    old.require(original is dataset.read_jsonl, 'Unexpected evaluator JSONL binding')
    def read_jsonl(path):
        return dataset.read_jsonl(Path(path))
    evaluator.read_jsonl = read_jsonl
    try:
        yield
    finally:
        evaluator.read_jsonl = original


def authorize(plan_path, protocol_path, protocol_sha):
    # Delegate all original authorization, deadline and source checks unchanged.
    plan = old.authorization(plan_path, PLAN_SHA)
    old.pinned(protocol_path, protocol_sha)
    protocol = old.read(protocol_path)
    old.require(protocol['authorization_plan_sha256'] == PLAN_SHA, 'Wrong original authorization')
    old.require(protocol['authorization'] == 'ROOT_MANUAL_PATH_ADAPTER_RECOVERY_05', 'Manual recovery authorization absent')
    mandatory = [Path(__file__).resolve(), BASE / 'tests/test_v2_scoring_recovery.py', BASE / 'GUARD-V2-SCORING-RECOVERY-05.md']
    for path in mandatory:
        old.require(str(path) in protocol['source_sha256'], 'Missing recovery source pin: ' + str(path))
    for path, digest in protocol['source_sha256'].items():
        old.pinned(path, digest)
    return plan, protocol


def failure_gate(plan, protocol):
    root = Path(plan['root']); work = root / 'completion-v5'
    old.require(not (work / 'COMPLETE.json').exists(), 'Already complete')
    old.require(not (work / 'MANUAL_RECOVERY_STARTED.json').exists(), 'Manual recovery already started; no automatic retry')
    old.require(not (work / 'MANUAL_RECOVERY_FAILED.json').exists(), 'Manual recovery failed; no automatic retry')
    for name in ('STARTED.json', 'FAILED_MANUAL_RECOVERY_REQUIRED.json'):
        old.pinned(work / name, protocol['original_receipts_sha256'][name])
    started = old.read(work / 'STARTED.json'); failed = old.read(work / 'FAILED_MANUAL_RECOVERY_REQUIRED.json')
    old.require(started['authorization_plan_sha256'] == PLAN_SHA and started['status'] == 'ONE_SHOT_STARTED', 'Unexpected original start')
    old.require(failed['status'] == 'FAILED_MANUAL_RECOVERY_REQUIRED' and failed['error'].startswith('CalledProcessError:'), 'Unexpected original failure')
    entry = protocol['failure_log']; old.pinned(entry['path'], entry['sha256'])
    evidence = Path(entry['path']).read_text()
    for fragment in ('v2_eval.py', "read_jsonl(freeze['rows_file']['path'])", 'dataset.py', "AttributeError: 'str' object has no attribute 'open'"):
        old.require(fragment in evidence, 'Original failure evidence differs: ' + fragment)
    state = old.read(root / 'evaluation-runner-v5/runtime-run.json')
    old.require(state['status'] == 'PREDICTIONS_FROZEN_AWAITING_ROOT_UNBLIND' and not state.get('child_pid'), 'Prediction pipeline not sealed')
    for key, name in [('method', 'METHOD_FREEZE_05.json'), ('addon', 'NEW_ABLATION_PROTOCOL_05.json'), ('jev', 'JEV_INPUT_FREEZE_05.json'), ('split', 'SPLIT_PROTOCOL_FREEZE_05.json')]:
        old.require(state['freeze_sha256'][key] == old.sha(root / name), 'Pipeline freeze differs')
    for folder in ('evaluation-v5', 'evaluation-partial-v5'):
        old.pinned(root / folder / 'METHODS_FROZEN.json', state['methods_freezes'][folder])
    for name in ('METHOD_FREEZE_05.json', 'NEW_ABLATION_PROTOCOL_05.json'):
        for path, digest in old.read(root / name)['sha256'].items():
            old.pinned(path, digest)
    for folder, name, count, key in old.DESTINATIONS:
        dest = root / folder / name
        for output in OUTPUTS:
            old.require(not (dest / output).exists(), 'Existing partial output: ' + str(dest / output))
        marker = old.read(dest / 'ROOT_UNBLIND_05.json')
        old.require(marker['authorization'] == 'UNBLIND' and marker['authorization_plan_sha256'] == PLAN_SHA, 'Existing marker not root authorized')
        old.require(marker['predictions_freeze_sha256'] == old.sha(dest / 'PREDICTIONS_FROZEN.json'), 'Marker prediction pin differs')
        old.require(marker['labels_sha256'] == plan['labels'][key]['sha256'], 'Marker label commitment differs')


def snapshot(plan):
    """Hash sources, sealed models, predictions and inputs without parsing labels."""
    root = Path(plan['root']); paths = set(plan['source_sha256'])
    for name in ('METHOD_FREEZE_05.json', 'NEW_ABLATION_PROTOCOL_05.json'):
        paths.update(old.read(root / name)['sha256'])
    for folder, name, _, _ in old.DESTINATIONS:
        methods = root / folder; dest = methods / name
        for freeze_name in ('METHODS_FROZEN.json', 'training-input-freeze.json'):
            frozen = methods / freeze_name; paths.add(str(frozen))
            paths.update(entry['path'] for entry in old.read(frozen)['files'])
        paths.update(str(dest / name) for name in ('PREDICTIONS_FROZEN.json', 'predictions.jsonl', 'ROOT_UNBLIND_05.json'))
        pf = old.read(dest / 'PREDICTIONS_FROZEN.json')
        paths.add(pf['rows_file']['path']); paths.update(entry['path'] for entry in pf['records'])
    paths.update(str(root / 'completion-v5' / n) for n in ('STARTED.json', 'FAILED_MANUAL_RECOVERY_REQUIRED.json'))
    label_paths = {str(Path(entry['path']).resolve()) for entry in plan['labels'].values()}
    old.require(not label_paths & {str(Path(p).resolve()) for p in paths}, 'Snapshot must not open labels')
    return {path: old.sha(path) for path in sorted(paths)}


def score_all(plan, evaluator, dataset, validator):
    root = Path(plan['root'])
    checks = []
    # Validate EVERY label join/pair population before the first scorer.
    for folder, name, count, key in old.DESTINATIONS:
        old.deadline(plan)
        checks.append(validator(root / folder, root / folder / name, expected_rows=count,
                                labels=Path(plan['labels'][key]['path']), unblind_marker=root / folder / name / 'ROOT_UNBLIND_05.json'))
        old.deadline(plan)
    with path_adapter(evaluator, dataset):
        for folder, name, _, key in old.DESTINATIONS:
            old.deadline(plan)
            evaluator.run_score(root / folder, root / folder / name, Path(plan['labels'][key]['path']))
            old.deadline(plan)
    return checks


def recover(plan_path, protocol_path, protocol_sha, *, execute=False):
    plan, protocol = authorize(plan_path, protocol_path, protocol_sha)
    failure_gate(plan, protocol)
    before = snapshot(plan)
    if not execute:
        return {'status': 'READY_SOURCE_AND_SEALS_ONLY', 'labels_read': False, 'snapshot_sha256': before}
    root = Path(plan['root']); work = root / 'completion-v5'
    old.exclusive(work / 'MANUAL_RECOVERY_STARTED.json', {'authorization_plan_sha256': PLAN_SHA, 'recovery_protocol_sha256': protocol_sha, 'status': 'MANUAL_ONE_SHOT_STARTED', 'before_sha256': before})
    timer_previous = None
    try:
        # Direct scorer is in this process, so enforce the SAME absolute deadline.
        def timed_out(signum, frame):
            raise TimeoutError('Frozen global completion deadline reached')
        timer_previous = signal.signal(signal.SIGALRM, timed_out)
        remaining = dt.datetime.fromisoformat(plan['completion_deadline_utc']).timestamp() - time.time()
        old.require(remaining > 0, 'Completion deadline expired')
        signal.setitimer(signal.ITIMER_REAL, remaining)
        sys.path.insert(0, str(BASE))
        from cascade_guard import v2_eval, dataset
        from cascade_guard.v2_preunblind import validate
        checks = score_all(plan, v2_eval, dataset, validate)
        def run(command):
            old.deadline(plan)
            remaining = dt.datetime.fromisoformat(plan['completion_deadline_utc']).timestamp() - time.time()
            child = subprocess.Popen(command, cwd=BASE, start_new_session=True)
            try:
                code = child.wait(timeout=remaining)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL); child.wait(); raise
            if code:
                raise subprocess.CalledProcessError(code, command)
        for folder, name, _, key in old.DESTINATIONS:
            dest = root / folder / name
            command = [sys.executable, '-m', 'cascade_guard.v2_external_diagnostics', 'run', '--destination', str(dest), '--labels', plan['labels'][key]['path'], '--marker', str(dest / 'ROOT_UNBLIND_05.json'), '--plan', plan['diagnostics_protocol'], '--output', str(dest / 'external-diagnostics.json'), '--method-freeze', str(root / folder / 'METHODS_FROZEN.json')]
            if key == 'independent':
                for flag, path in plan['independent_control'].items():
                    command.extend(['--' + flag, path])
            run(command)
        run([sys.executable, '-m', 'cascade_guard.v2_report', '--base', str(BASE)])
        authorize(plan_path, protocol_path, protocol_sha)
        after = snapshot(plan)
        old.require(after == before, 'Immutable sources/models/predictions changed')
        outputs = {str(root / folder / name / output): old.sha(root / folder / name / output) for folder, name, _, _ in old.DESTINATIONS for output in OUTPUTS}
        receipt = {'status': 'COMPLETE', 'manual_recovery': True, 'authorization_plan_sha256': PLAN_SHA, 'recovery_protocol_sha256': protocol_sha, 'destinations': 4, 'all_label_prevalidations': checks, 'before_sha256': before, 'after_sha256': after, 'outputs_sha256': outputs, 'original_receipts_sha256': protocol['original_receipts_sha256']}
        old.deadline(plan)
        old.exclusive(work / 'MANUAL_RECOVERY_RECEIPT.json', receipt)
        old.exclusive(work / 'COMPLETE.json', {'status': 'COMPLETE', 'manual_recovery': True, 'authorization_plan_sha256': PLAN_SHA, 'recovery_receipt_sha256': old.sha(work / 'MANUAL_RECOVERY_RECEIPT.json'), 'destinations': 4})
        return {'status': 'COMPLETE', 'manual_recovery': True, 'destinations': 4}
    except BaseException as exc:
        old.exclusive(work / 'MANUAL_RECOVERY_FAILED.json', {'status': 'MANUAL_RECOVERY_FAILED_NO_AUTORETRY', 'error': type(exc).__name__ + ': ' + str(exc), 'recovery_protocol_sha256': protocol_sha})
        raise
    finally:
        if timer_previous is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, timer_previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorization-plan', type=Path, required=True)
    parser.add_argument('--recovery-protocol', type=Path, required=True)
    parser.add_argument('--recovery-protocol-sha256', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    print(json.dumps(recover(args.authorization_plan, args.recovery_protocol, args.recovery_protocol_sha256, execute=args.execute), indent=2))

if __name__ == '__main__':
    main()
