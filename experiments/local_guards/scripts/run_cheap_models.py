#!/usr/bin/env python3
"""Serial local adapter runner; requires an explicit root resource lease."""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cascade_guard.cheap_runtime import run_serial

parser = argparse.ArgumentParser()
parser.add_argument("--inputs", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--adapter", default="cascade_guard.cheap_nli:create_adapter")
parser.add_argument("--model-id", required=True)
parser.add_argument("--revision", required=True)
parser.add_argument("--model-dir", type=Path, required=True)
parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
parser.add_argument("--deadline", default="2026-10-15T15:02:27Z")
parser.add_argument("--lock-path", type=Path, default=Path(".runtime/cheap-guards/heavy-model.lock"))
parser.add_argument("--resource-lease", action="store_true")
parser.add_argument("--mps-probe", action="store_true")
parser.add_argument("--limit", type=int)
parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
args = parser.parse_args()
if not args.worker:
    remaining = dt.datetime.fromisoformat(args.deadline.replace("Z", "+00:00")).timestamp() - dt.datetime.now(dt.timezone.utc).timestamp()
    if remaining <= 0:
        print(json.dumps({"status": "DEADLINE", "written": 0})); sys.exit(124)
    child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--worker"])
    try:
        sys.exit(child.wait(timeout=remaining))
    except subprocess.TimeoutExpired:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill(); child.wait()
        print(json.dumps({"status": "DEADLINE", "reason": "external supervisor stopped heavy worker at global deadline"})); sys.exit(124)
print(json.dumps(run_serial(args.inputs, args.output, args.adapter, args.model_id, args.revision, args.model_dir, deadline=args.deadline, device=args.device, resource_lease=args.resource_lease, lock_path=args.lock_path, limit=args.limit, mps_probe=args.mps_probe), indent=2))
