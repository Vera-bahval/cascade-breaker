#!/usr/bin/env python3
"""Deadline-bounded offline evaluation/check/report after model workers exit."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET


def sha(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_model_records(path, inputs, model_dir, expected_id, expected_revision, artifacts_checked):
    """Bind cached model rows to actual frozen payloads, source and weight bytes."""
    input_rows = [json.loads(x) for x in inputs.read_text().splitlines() if x]
    expected = {r["prefix_id"]: r["input_hash"] for r in input_rows}
    for row in input_rows:
        payload_hash = hashlib.sha256(json.dumps(row["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        assert payload_hash == row["input_hash"], "Payload hash mismatch"
    manifest = json.loads(path.with_suffix(".manifest.json").read_text())
    spec = manifest["spec"]
    assert spec["input_file_sha256"] == sha(inputs), "Runtime input file changed"
    assert spec["model_id"] == expected_id and spec["revision"] == expected_revision, "Unexpected model revision"
    assert hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest() == manifest["run_hash"], "Runtime fingerprint mismatch"
    for source, expected_hash in spec["sources"].items():
        assert sha(source) == expected_hash, f"Inference source changed: {source}"
    artifact_file = model_dir / "artifact-manifest.json"
    assert artifact_file.is_file() and sha(artifact_file) == spec["artifact_manifest_sha256"], "Artifact manifest changed/missing"
    artifact = json.loads(artifact_file.read_text())
    assert artifact["model_id"] == expected_id and artifact["revision"] == expected_revision
    if model_dir not in artifacts_checked:
        for relative, description in artifact["files"].items():
            file = model_dir / relative
            assert file.resolve().is_relative_to(model_dir.resolve()), "Artifact escaped model directory"
            assert file.stat().st_size == description["bytes"] and sha(file) == description["sha256"], f"Model artifact changed: {relative}"
        artifacts_checked.add(model_dir)
    rows = [json.loads(x) for x in path.read_text().splitlines() if x]
    assert len(rows) == len(expected) and {r["prefix_id"] for r in rows} == set(expected), "Incomplete/duplicate model population"
    for row in rows:
        assert row["block"] == path.stem, "Scored model block does not match output identity"
        assert row["run_hash"] == manifest["run_hash"] and row["input_hash"] == expected[row["prefix_id"]], "Scored payload identity mismatch"
        assert row["model_metadata"]["model_id"] == expected_id and row["model_metadata"]["revision"] == expected_revision
    return {"rows": len(rows), "run_hash": manifest["run_hash"], "artifact_manifest_sha256": sha(artifact_file), "actual_files_verified": len(artifact["files"])}


def verify_official_pg_identity(model_dir, metadata_path, model_id, revision):
    """A public mirror must preserve the pinned vendor blobs, not just their names."""
    record = json.loads(metadata_path.read_text())
    assert record["status"] == 200
    official = record["data"]
    assert official["sha"] == revision and official["id"] == model_id
    siblings = {r["rfilename"]: r for r in official["siblings"]}
    artifact = json.loads((model_dir / "artifact-manifest.json").read_text())
    required = {"model.safetensors", "config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"}
    assert required <= artifact["files"].keys(), "Incomplete official PG runtime"
    for relative, description in artifact["files"].items():
        source = siblings[relative]
        assert source["size"] == description["bytes"]
        if source.get("lfs"):
            assert source["lfs"]["sha256"] == description["sha256"], "Mirror LFS identity differs from official pin"
        else:
            content = (model_dir / relative).read_bytes()
            assert hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest() == source["blobId"], "Mirror Git blob differs from official pin"
    return {"official_revision": revision, "official_metadata_sha256": sha(metadata_path), "official_files_verified": len(artifact["files"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--resume-postprocessing", action="store_true", help="Reuse unchanged completed evaluation after a check/report failure")
    args = parser.parse_args()
    workspace = args.workspace.resolve(); base = workspace / "experiments/local_guards"
    root = base / "results/cheap-guards"
    run_path = root / "run.json"; run = json.loads(run_path.read_text()); deadline = run["deadline_at"]
    env = {**os.environ, "PYTHONPATH": str(base), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "MPLCONFIGDIR": str(workspace / ".runtime/cheap-guards/matplotlib")}
    status = {"status": "PREPARING", "started_at": time.time(), "commands": []}
    lock = workspace / ".runtime/cheap-guards/heavy-model.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)

    def save():
        (root / "finalizer.json").write_text(json.dumps(status, indent=2) + "\n")

    def command(name, argv):
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError("Original eight-hour deadline reached")
        started = time.time()
        with (root / f"{name}.log").open("a") as log:
            result = subprocess.run(argv, cwd=base, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=remaining)
        status["commands"].append({"name": name, "argv": argv, "started_at": started, "finished_at": time.time(), "exit_code": result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(f"{name} failed; see saved log")

    save()
    try:
        # Same resource lock as every model worker: CPU fitting cannot overlap GPU/CPU inference.
        with lock.open("a+") as lease:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            checks = {p: hashlib.sha256((base / p).read_bytes()).hexdigest() == h for p, h in run["immutable_sha256"].items()}
            if not all(checks.values()):
                raise ValueError("Immutable baseline changed")
            version_probe = (
                "import importlib.metadata as m,json,platform,sys\n"
                "versions={}\n"
                "for name in ['numpy','pandas','scikit-learn','catboost','torch','transformers','safetensors','tokenizers','huggingface-hub','psutil']:\n"
                " try: versions[name]=m.version(name)\n"
                " except m.PackageNotFoundError: versions[name]=None\n"
                "print(json.dumps({'python':sys.version,'platform':platform.platform(),'versions':versions}))\n"
            )
            environments = {}
            for name, python in (("ml", base / ".venv/bin/python"), ("inference", workspace / ".venv-cheap/bin/python"), ("tests_report", base / ".venv-finbot/bin/python")):
                result = subprocess.run([str(python), "-c", version_probe], capture_output=True, text=True, check=True, timeout=30)
                environments[name] = json.loads(result.stdout)
            (root / "environment.json").write_text(json.dumps(environments, indent=2) + "\n")
            rows = [json.loads(x) for x in (base / "data/prefixes.jsonl").read_text().splitlines()]
            expected = {r["prefix_id"] for r in rows if r["control_point"] == "P4.finstripe__create_transfer" and not r["ambiguity"] and not r["already_harmful"]}
            assert len(expected) == 176
            records = [root / "sequence/features.jsonl"]; available = []; coverage = {}
            for block in ("G22", "G86", "N", "M"):
                path = root / "models" / f"{block}.jsonl"
                data = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
                coverage[block] = {"records": len(data), "known": sum(r["status"] == "OK" for r in data)}
                if len(data) == 176 and {r["prefix_id"] for r in data} == expected:
                    records.append(path); available.append(block)
            raw_records = []
            for block in available:
                path = root / "raw64/scores" / f"{block}.jsonl"
                if path.exists() and len(path.read_text().splitlines()) == 64:
                    raw_records.append(path)
            model_specs = {
                "N": ("nli", "cross-encoder/nli-deberta-v3-base", "6c749ce3425cd33b46d187e45b92bbf96ee12ec7"),
                "M": ("minicheck", "lytang/MiniCheck-DeBERTa-v3-Large", "2f2d01a54fa022a7ffadb76260e1ea8bc88c82bb"),
                "G22": ("promptguard22", "meta-llama/Llama-Prompt-Guard-2-22M", "11614a155199674a0a95e6602d6ab0417b790ed0"),
                "G86": ("promptguard86", "meta-llama/Llama-Prompt-Guard-2-86M", "a8ded8e697ce7c355e395a0df51f94adb4a2fd27"),
            }
            evidence = {}; artifacts_checked = set()
            for block in available:
                folder, model_id, revision = model_specs[block]
                model_dir = workspace / ".runtime/cheap-guards" / folder
                evidence[block] = verify_model_records(root / "models" / f"{block}.jsonl", root / "inputs/inputs.jsonl", model_dir, model_id, revision, artifacts_checked)
                if block in ("G22", "G86"):
                    evidence[block]["official_pin_identity"] = verify_official_pg_identity(model_dir, root / "promptguard" / f"mirror-{block[1:]}M-official-metadata.json", model_id, revision)
                profile_path = root / "scalar-profiles" / f"{block}.jsonl"
                if profile_path.exists() and len(profile_path.read_text().splitlines()) == 176:
                    evidence[block + "_scalar_profile"] = verify_model_records(profile_path, root / "inputs/inputs.jsonl", model_dir, model_id, revision, artifacts_checked)
                    full_rows = {r["prefix_id"]: r for r in map(json.loads, (root / "models" / f"{block}.jsonl").read_text().splitlines())}
                    profiles = [json.loads(x) for x in profile_path.read_text().splitlines()]
                    differences = [abs(r["scalar_risk"]-full_rows[r["prefix_id"]]["scalar_risk"]) for r in profiles if r["status"] == "OK" and full_rows[r["prefix_id"]]["status"] == "OK"]
                    assert len(differences) == 176 and max(differences) <= 1e-4, "Scalar-only execution profile not equivalent to main scalar baseline"
                    evidence[block + "_scalar_profile"]["max_scalar_delta"] = max(differences)
                elif profile_path.exists():
                    evidence[block + "_scalar_profile"] = {"status": "INCOMPLETE", "rows": len(profile_path.read_text().splitlines()), "expected": 176}
                raw_path = root / "raw64/scores" / f"{block}.jsonl"
                if raw_path in raw_records:
                    evidence[block + "_raw64"] = verify_model_records(raw_path, root / "raw64/inputs.jsonl", model_dir, model_id, revision, artifacts_checked)
            (root / "inference-audit.json").write_text(json.dumps(evidence, indent=2) + "\n")
            status.update(status="EVALUATING", model_coverage=coverage, available_models=available)
            run.update(status="EVALUATING", lease={"owner": "offline_evaluation", "granted_at": time.time()})
            run_path.write_text(json.dumps(run, indent=2) + "\n"); save()
            argv = [str(base / ".venv/bin/python"), "-m", "cascade_guard.cheap_eval", "--base", str(base), "--records", *map(str, records), "--output", str(root / "evaluation"), "--run"]
            if raw_records:
                argv += ["--raw-records", *map(str, raw_records), "--raw-rows", str(root / "raw64/rows.jsonl"), "--raw-labels", str(root / "raw64/labels.jsonl")]
            if args.resume_postprocessing:
                previous = json.loads((root / "evaluation/manifest.json").read_text())
                assert previous["phase"] == "COMPLETE", "Completed available evaluation required"
                assert {p["path"] for p in previous["record_files"]} == set(map(str, records)), "Available model inputs changed"
                raw_freeze = previous.get("raw_stress_freeze")
                current_raw_inputs = set(map(str, raw_records)) | ({str(root / "raw64/rows.jsonl"), str(root / "raw64/labels.jsonl")} if raw_records else set())
                assert {p["path"] for p in (raw_freeze or {}).get("source_files", [])} == current_raw_inputs, "Raw input availability changed; resume cannot silently omit newly available diagnostics"
                for item in previous["source_files"] + previous["record_files"] + previous["output_files"] + previous.get("raw_stress_outputs", []):
                    assert hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"], f"Evaluation checkpoint changed: {item['path']}"
                status["evaluation_reused"] = True
            else:
                command("evaluation", argv)
            command("tests", [str(base / ".venv-finbot/bin/python"), "-m", "pytest", "tests", f"--junitxml={root / 'tests.xml'}"])
            suites = list(ET.parse(root / "tests.xml").getroot().iter("testsuite"))
            counts = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
            (root / "verification.json").write_text(json.dumps({"counts": counts, "baseline_unchanged": checks, "updated_at": time.time()}, indent=2) + "\n")
            command("plots", [str(base / ".venv/bin/python"), "-m", "cascade_guard.cheap_plots", "--base", str(base)])
            manifest = json.loads((root / "evaluation/manifest.json").read_text())
            run = json.loads(run_path.read_text())
            run.update(status="COMPLETE" if manifest["status"] == "COMPLETE" else "PARTIAL", evaluation_status=manifest["status"], finished_at=time.time(), lease=None, model_coverage=coverage)
            run.pop("error", None); run_path.write_text(json.dumps(run, indent=2) + "\n")
            paths = list((base / "cascade_guard").glob("cheap_*.py")) + list((base / "scripts").glob("*cheap*.py")) + list((base / "tests").glob("test_cheap*.py")) + [base / "CHEAP-GUARDS.md", base / "uv.lock", base / "pyproject.toml", base / "requirements-finbot.lock.txt", workspace / ".runtime/cheap-guards/requirements.lock.txt"]
            (root / "source-manifest.json").write_text(json.dumps({"sha256": {str(p.relative_to(workspace)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}, "generated_at": time.time()}, indent=2) + "\n")
            command("report", [str(base / ".venv-finbot/bin/python"), "-m", "cascade_guard.cheap_report", "--base", str(base)])
            status["status"] = run["status"]
    except Exception as error:
        status.update(status="PARTIAL", error=f"{type(error).__name__}: {error}")
        current = json.loads(run_path.read_text()); current.update(status="PARTIAL", error=status["error"], lease=None)
        run_path.write_text(json.dumps(current, indent=2) + "\n")
    status["finished_at"] = time.time(); save()
    print(json.dumps(status))
    return 1 if status.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
