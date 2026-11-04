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


def cmd_mast(args: argparse.Namespace) -> None:
    from runner import mast_mode

    names = args.scenarios or [p.stem for p in mast_mode.mast_paths()]
    out = Path(__file__).resolve().parent / "results" / "api-mast" / args.batch
    mast_mode.run_batch(names, args.repeats, args.workers, args.attempts, args.base_url, args.timeout,
                        args.trace_dir, out)


def cmd_unified(args: argparse.Namespace) -> None:
    from runner import mast_mode

    if args.scenarios:
        names = args.scenarios
    elif args.suite == ["base"]:
        names = mast_mode.base_scenarios()
    else:
        names = [c["id"] for suite in args.suite for c in mast_mode.unified_cases(suite)]
        if args.via == "api":
            names += [p.stem for p in mast_mode.mast_paths() if p.stem in mast_mode.api_additions()]
    out = Path(__file__).resolve().parent / "results" / "unified" / args.via / args.batch
    mast_mode.run_batch(names, args.repeats, args.workers, args.attempts, args.base_url, args.timeout,
                        args.trace_dir, out, via=args.via)


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
    p = sub.add_parser("mast", help="run the API MAST scenarios in scenarios/api-mast/")
    p.add_argument("scenarios", nargs="*", help="ids such as S01_n (default: all 48)")
    p.add_argument("--batch", required=True, help="results go to results/api-mast/<batch>/; existing files are kept")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--attempts", type=int, default=2, help="attempts for a repeat that breaks")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--timeout", type=float, default=900.0)
    p.add_argument("--trace-dir", default=os.environ.get("PROBE_TRACE_DIR"))
    p.set_defaults(func=cmd_mast)
    p = sub.add_parser("unified", help="run the unified cases in scenarios/unified/ via direct or api")
    p.add_argument("scenarios", nargs="*", help="case ids such as TA501@C or S25_n (default: every case of --suite)")
    p.add_argument("--via", choices=("direct", "api"), required=True)
    p.add_argument("--suite", nargs="+", default=["core", "honest"],
                   help="unified suites: core honest matrix profiles pairs sweep (default: core honest); "
                        "via api also adds the API scenarios listed in unified/api_additions.yaml. "
                        "`base` alone runs one scenario per MAST mode and its partner (unified/base.yaml)")
    p.add_argument("--batch", required=True,
                   help="results go to results/unified/<via>/<batch>/; existing files are kept")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--attempts", type=int, default=2, help="attempts for a repeat that breaks")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--timeout", type=float, default=900.0)
    p.add_argument("--trace-dir", default=os.environ.get("PROBE_TRACE_DIR"))
    p.set_defaults(func=cmd_unified)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
