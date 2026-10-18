"""Capture versions and observed outputs without tokens or host identifiers."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]


def hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(2**20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def hardware():
    result = {"system": platform.system(), "release": platform.release(), "machine": platform.machine()}
    if platform.system() == "Darwin":
        try:
            data = json.loads(subprocess.check_output(
                ["system_profiler", "SPHardwareDataType", "-json"], timeout=20
            ))["SPHardwareDataType"][0]
            for key in ("chip_type", "number_processors", "physical_memory", "machine_name"):
                if key in data:
                    result[key] = data[key]
        except (subprocess.SubprocessError, KeyError, ValueError, OSError):
            result["hardware_details"] = "unavailable"
    return result


def create_manifest():
    packages = {}
    for name in ("numpy", "pandas", "scikit-learn", "catboost", "scipy", "openai", "httpx", "PyJWT", "psutil"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    paths = [
        ROOT / "uv.lock", ROOT / "requirements-secjev.txt", ROOT / "requirements-secjev.lock.txt",
        ROOT / "requirements-secjev-mps.lock.txt", ROOT / "requirements-finbot.txt",
        ROOT / "requirements-finbot.lock.txt", ROOT / "finbot-local.patch",
        ROOT / "data/prefixes.jsonl", ROOT / "data/outcomes.jsonl",
        ROOT / "data/archive/shadow-main.jsonl.gz", ROOT / "data/archive/legacy-policy.json",
        WORKSPACE / "research/jev-request.example.json",
    ]
    manifest = {
        "schema_version": 1, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "hardware": hardware(), "ml_packages": packages,
        "files_sha256": {str(p.relative_to(WORKSPACE)): hash_file(p) for p in paths},
        "dataset": read_json(ROOT / "data/dataset-summary.json"),
        "evaluation": {"seeds": [17, 29, 43], "outer_folds": 3, "inner_folds": 2,
                       "target_inner_episode_fpr": .05, "counterfactual_stop_only": True},
        "live": {"requested_model": "gpt-5-nano", "automatic_substitution": False,
                 "credit_cap": 1000, "status": "not_run_pending_separate_oauth_and_model_access"},
        "luna_showcase": {"requested_model": "gpt-6-luna", "max_episodes": 6,
                          "training_or_calibration_data": False,
                          "purpose": "preliminary connection and guard-execution showcase",
                          "status": "prepared_pending_independent_budget_readback"},
    }
    for name in ("secjev-runtime.json", "secjev-cpu-threads.json", "secjev-scores.manifest.json",
                 "secjev-mps-scores.manifest.json", "mps-diagnostics/summary.json",
                 "mps-diagnostics/service-health.json", "mps-diagnostics/secjev2b/summary.json"):
        value = read_json(ROOT / "results" / name)
        if value is not None:
            manifest.setdefault("secjev", {})[name.removesuffix(".json")] = value
    live = read_json(ROOT / "results/live-preflight.json")
    if live is not None:
        manifest["live"] = live
    for name in ("artifacts/frozen-ml/manifest.json", "artifacts/frozen-semantic/manifest.json",
                 "results/replay-integration-summary.json", "results/finbot-harness-provenance.json",
                 "results/finbot-environment.txt", "results/offline/metrics.json", "results/offline/cv-manifest.json",
                 "results/with-semantic/metrics.json", "results/with-semantic/cv-manifest.json",
                 "results/secjev-mps-scores.jsonl", "results/secjev-scores.jsonl",
                 "results/secjev-p4-cpu-mps-parity.json", "results/p4-semantic-cv-parity.json",
                 "results/mps-diagnostics/paired-speed-idle.json", "results/mps-diagnostics/artifacts.manifest.json",
                 "results/diagnostics/fraud-review-status-posthoc.json", "results/verification.json",
                 "results/diagnostics/rules-v3-benign-paired.json",
                 "results/diagnostics/structured-ledger/inputs.jsonl",
                 "results/diagnostics/structured-ledger/factorial/summary.json",
                 "results/diagnostics/structured-ledger/factorial/manifest.json",
                 "results/diagnostics/structured-ledger/factorial/scores.jsonl",
                 "results/diagnostics/structured-ledger/long-context-cpu-parity.json",
                 "results/tests.xml", "results/luna-showcase/summary.json", "results/luna-showcase/episodes.jsonl",
                 "results/luna-showcase/smoke.json", "results/luna-showcase/run-manifest.json",
                 "results/bootstrap-lock-check.json",
                 "examples/luna-showcase.json", "examples/luna-showcase-cases.json"):
        path = ROOT / name
        if path.exists():
            manifest["files_sha256"][str(path.relative_to(WORKSPACE))] = hash_file(path)
    for name in ("offline", "with-semantic"):
        value = read_json(ROOT / f"results/{name}/cv-manifest.json")
        if value is not None:
            manifest.setdefault("completed_cv", {})[name] = value
    for name in ("summary", "preflight"):
        value = read_json(ROOT / "results/luna-showcase" / f"{name}.json")
        if value is not None:
            manifest["luna_showcase"][name] = value
    if "summary" in manifest["luna_showcase"]:
        manifest["luna_showcase"]["status"] = manifest["luna_showcase"]["summary"]["status"]
    manifest["posthoc_diagnostic"] = {"model_history": read_json(ROOT / "results/diagnostics/structured-ledger/factorial/summary.json"),
                                   "not_primary_cv_or_frozen_policy": True,
                                   "cpu_long_context_control": read_json(ROOT / "results/diagnostics/structured-ledger/long-context-cpu-parity.json")}
    manifest["source_sha256"] = {str(p.relative_to(WORKSPACE)): hash_file(p)
                                for folder in (ROOT / "cascade_guard", ROOT / "scripts")
                                for p in sorted(folder.glob("*.py"))}
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "results/experiment-manifest.json")
    args = p.parse_args()
    result = create_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"manifest": str(args.output), "dataset_sha256": result["files_sha256"].get("experiments/local_guards/data/prefixes.jsonl")}))


if __name__ == "__main__":
    main()
