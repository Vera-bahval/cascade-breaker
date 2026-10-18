#!/usr/bin/env python3
"""Resume-safe local postprocessing after the serial model supervisor exits.

No inference APIs. The frozen rules evaluation is never repeated here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--resume-postprocessing", action="store_true", help="Reuse verified completed ML evaluation; rerun only failed checks and report")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    base = workspace / "experiments/local_guards"
    root = base / "results/night-4b"
    run_path = root / "run.json"
    initial = json.loads(run_path.read_text())
    deadline = initial["deadline_at"]
    environment = {**os.environ, "PYTHONPATH": str(base)}
    status = {"status": "WAITING_FOR_MODEL", "started_at": time.time(), "deadline_at": deadline, "pid": os.getpid(), "commands": []}

    def save():
        (root / "finalizer.json").write_text(json.dumps(status, indent=2) + "\n")

    def command(name, argv, cwd=workspace):
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError("Night deadline reached")
        started = time.time()
        with (root / f"{name}.log").open("a") as log:
            result = subprocess.run(argv, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=remaining)
        status["commands"].append({"name": name, "started_at": started, "finished_at": time.time(), "exit_code": result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(f"{name} failed; see its log")

    save()
    try:
        while time.time() < deadline:
            pipeline_path = root / "runtime/pipeline.json"
            try:
                pipeline = json.loads(pipeline_path.read_text()) if pipeline_path.exists() else {}
            except json.JSONDecodeError:
                time.sleep(2)
                continue
            if pipeline.get("status") in ("COMPLETE", "DEADLINE", "STOPPED"):
                # A failed numerical/environment gate needs explicit diagnosis;
                # do not silently accept any partially written score file.
                if pipeline.get("status") == "STOPPED":
                    status.update(status="MODEL_STOPPED", model_error=pipeline.get("error"))
                    save()
                    return
                break
            time.sleep(min(5, max(0, deadline - time.time())))
        status["status"] = "POSTPROCESSING"
        save()
        scores = root / "scores.jsonl"
        if not scores.exists():
            raise RuntimeError("No model scores available")
        if args.resume_postprocessing:
            evaluation = json.loads((root / "evaluation/manifest.json").read_text())
            assert evaluation["source_sha256"] == hashlib.sha256((base / "cascade_guard/night_ml.py").read_bytes()).hexdigest(), "ML source changed"
            assert evaluation["format_input_manifest_sha256"] == hashlib.sha256((root / "formats/manifest.json").read_bytes()).hexdigest(), "Format manifest changed"
            assert evaluation["score_sources"] == [{"path": str(scores), "sha256": hashlib.sha256(scores.read_bytes()).hexdigest()}], "Score snapshot changed"
            status["evaluation_reused"] = True
            save()
        else:
            command("evaluation", [str(base / ".venv/bin/python"), "-m", "cascade_guard.night_ml", "--base", str(base), "--scores", str(scores), "--output", str(root / "evaluation")])
        command("tests", [str(base / ".venv-finbot/bin/python"), "-m", "pytest", str(base / "tests"), f"--junitxml={root / 'tests.xml'}"], cwd=base)
        suites = list(ET.parse(root / "tests.xml").getroot().iter("testsuite"))
        counts = {key: sum(int(s.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
        verification_path = root / "verification.json"
        verification = json.loads(verification_path.read_text())
        verification.update(counts=counts, secjev4_numerical_validation="COMPLETE", updated_at=time.time())
        verification_path.write_text(json.dumps(verification, indent=2) + "\n")
        sources = {}
        for path in list((base / "cascade_guard").glob("*.py")) + list((base / "scripts").glob("*.py")) + list(base.glob("*lock*")) + [base / "pyproject.toml", base / "NIGHT-4B.md"]:
            if path.is_file():
                sources[str(path.relative_to(base))] = hashlib.sha256(path.read_bytes()).hexdigest()
        (root / "source-manifest.json").write_text(json.dumps({"sha256": sources, "generated_at": time.time()}, indent=2) + "\n")
        current = json.loads(run_path.read_text())
        manifest = json.loads((root / "evaluation/manifest.json").read_text())
        all_formats = len(manifest["formats_completed"]) == 3
        complete = all_formats and manifest["status"] == "COMPLETE"
        current.update(status="COMPLETE" if complete else "PARTIAL", active_stage="finished", finished_at=time.time(), evaluation_status=manifest["status"])
        current.pop("error", None)
        run_path.write_text(json.dumps(current, indent=2) + "\n")
        command("report", [str(base / ".venv-finbot/bin/python"), "-m", "cascade_guard.night_report", "--base", str(base)])
        status["status"] = current["status"]
    except Exception as error:
        status.update(status="PARTIAL", error=str(error))
        current = json.loads(run_path.read_text())
        current.update(status="PARTIAL", active_stage="postprocessing_failed", error=str(error), finished_at=time.time())
        run_path.write_text(json.dumps(current, indent=2) + "\n")
    status["finished_at"] = time.time()
    save()


if __name__ == "__main__":
    main()
