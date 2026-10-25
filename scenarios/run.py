"""Scenario runner for FinBot: `prepare` puts the data in, `run` starts the scenario.

Run from the finbot/ directory so FinBot and its dependencies are importable:

    cd finbot
    uv run python ../scenarios/run.py prepare invoice_basic
    uv run python ../scenarios/run.py run invoice_basic
    uv run python ../scenarios/run.py list
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# FinBot itself is imported from the current directory, which must be finbot/.
sys.path.insert(1, str(Path.cwd()))

from runner import scenario as scenarios  # noqa: E402
from runner.state import state_path  # noqa: E402

DEFAULT_BASE_URL = "http://localhost:8000"


def _summary(data: dict) -> dict:
    keys = ("scenario", "via", "kind", "vendor_id", "namespace", "workflows", "workflow_id",
            "timed_out", "error", "orchestrator_status", "injection_applied", "wall_s", "path")
    return {k: data[k] for k in keys if k in data}


def cmd_list(_args: argparse.Namespace) -> None:
    for path in scenarios.case_paths():
        sc = scenarios.load(str(path))
        prepared = "prepared" if state_path(sc.id).exists() else ""
        print(f"{sc.id:32} {sc.via:7} {sc.kind:13} {prepared}")


def cmd_prepare(args: argparse.Namespace) -> None:
    sc = scenarios.load(args.scenario)
    if sc.via == "api":
        from runner import api_mode

        state = api_mode.prepare(sc, args.base_url, args.timeout)
    else:
        from runner import direct_mode

        state = direct_mode.prepare(sc)
    print(json.dumps(_summary(state) | {"state": str(state_path(sc.id))}, indent=2))


def cmd_run(args: argparse.Namespace) -> None:
    sc = scenarios.load(args.scenario)
    if sc.via == "api":
        from runner import api_mode

        result = api_mode.run(sc, args.timeout, args.base_url, args.trace_dir)
    else:
        from runner import direct_mode

        result = direct_mode.run(sc)
    print(json.dumps(_summary(result), indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show available scenarios").set_defaults(func=cmd_list)
    for name, func in (("prepare", cmd_prepare), ("run", cmd_run)):
        p = sub.add_parser(name)
        p.add_argument("scenario", help="scenario id from cases/ or a path to a yaml or json file")
        p.add_argument("--base-url", default=None if name == "run" else DEFAULT_BASE_URL,
                       help=f"FinBot address for via=api (default {DEFAULT_BASE_URL})")
        p.add_argument("--timeout", type=float, default=600.0,
                       help="seconds to wait for workflows to finish")
        p.add_argument("--trace-dir", default=os.environ.get("PROBE_TRACE_DIR"),
                       help="where the FinBot server writes workflow traces (default $PROBE_TRACE_DIR)")
        p.set_defaults(func=func)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
