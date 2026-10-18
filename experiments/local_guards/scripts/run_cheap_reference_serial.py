#!/usr/bin/env python3
"""Reproduce the frozen reference through the workspace lock and original deadline.

The frozen reference CLI used a different lock path. Preserve its scientific
source; this launcher supplies the common outer lock for future invocations.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.resolve(); base = workspace / "experiments/local_guards"
    run_path = base / "results/cheap-guards/run.json"
    remaining = json.loads(run_path.read_text())["deadline_at"] - time.time()
    if remaining <= 0:
        parser.error("Original eight-hour deadline reached; it is never reset by this launcher")
    command = [str(base / ".venv/bin/python"), "-m", "cascade_guard.cheap_reference", "--base", str(base)]
    command += ["--freeze-only"] if args.freeze_only else ["--run", "--resource-lease"]
    if args.output:
        command += ["--output", str(args.output.resolve())]
    lock = workspace / ".runtime/cheap-guards/heavy-model.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(base), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    with lock.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            return subprocess.run(command, cwd=workspace, env=env, timeout=remaining).returncode
        except subprocess.TimeoutExpired:
            state = json.loads(run_path.read_text())
            state.update(status="PARTIAL", lease=None, matched_reference_error="Original deadline enforced by serial launcher")
            run_path.write_text(json.dumps(state, indent=2) + "\n")
            return 124


if __name__ == "__main__":
    raise SystemExit(main())
