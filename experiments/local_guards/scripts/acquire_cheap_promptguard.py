#!/usr/bin/env python3
"""Acquire checksum-proven official Prompt Guard data from a public pinned mirror.

Default is a local dry run. Actual acquisition requires --download-authorized.
Only the eight listed data/document files are accepted; no model imports, pickle,
executable files, credentials, cookies, or gate submissions are used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import urllib.parse
import urllib.request

OFFICIAL = {
    "meta-llama/Llama-Prompt-Guard-2-22M": {
        "revision": "11614a155199674a0a95e6602d6ab0417b790ed0", "target": "promptguard22",
        "mirror_repo": "LLM-Research/Llama-Prompt-Guard-2-22M",
        "mirror_revision": "e5c7f02a4beee961c7aa928626e83d8732de5a89"},
    "meta-llama/Llama-Prompt-Guard-2-86M": {
        "revision": "a8ded8e697ce7c355e395a0df51f94adb4a2fd27", "target": "promptguard86",
        "mirror_repo": "LLM-Research/Llama-Prompt-Guard-2-86M",
        "mirror_revision": "be11c20dd62e7b5391dab63f212c42e2fc25f3ea"},
}
FILES = {"config.json", "tokenizer_config.json", "special_tokens_map.json", "tokenizer.json",
         "model.safetensors", "README.md", "LICENSE", "USE_POLICY.md"}
DEADLINE_TS = datetime(2026, 10, 15, 15, 2, 27, tzinfo=timezone.utc).timestamp()


def check_deadline() -> None:
    if time.time() >= DEADLINE_TS:
        raise TimeoutError("Original cheap-guard experiment deadline reached")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_file(path: Path) -> dict:
    size = path.stat().st_size
    sha256 = hashlib.sha256()
    git_blob = hashlib.sha1(f"blob {size}\0".encode())
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            sha256.update(chunk)
            git_blob.update(chunk)
    return {"bytes": size, "sha256": sha256.hexdigest(), "git_blob_sha1": git_blob.hexdigest()}


def validate_identity(actual: dict, expected: dict) -> None:
    if actual["bytes"] != expected["bytes"] or actual["sha256"] != expected["sha256"]:
        raise ValueError("Downloaded file size/SHA256 differs from proven identity")
    official = expected["official_identity"]
    if official["kind"] == "lfs_sha256":
        if actual["sha256"] != official["value"]:
            raise ValueError("Downloaded file differs from official pinned LFS SHA256")
    elif official["kind"] == "git_blob_sha1":
        if actual["git_blob_sha1"] != official["value"]:
            raise ValueError("Downloaded file differs from official pinned Git blob")
    else:
        raise ValueError("Unsupported official content identity")


def load_plan(path: Path) -> dict:
    plan = json.loads(path.read_text())
    if plan.get("status") != "VERIFIED_OFFICIAL_IDENTICAL_FILES":
        raise ValueError("A completed official identity proof is required")
    if {model["model_id"] for model in plan["models"]} != set(OFFICIAL) or len(plan["models"]) != 2:
        raise ValueError("Plan must contain exactly the two preregistered official models")
    for model in plan["models"]:
        spec = OFFICIAL[model["model_id"]]
        if any(model.get(key) != spec[key] for key in ("revision", "mirror_repo", "mirror_revision")):
            raise ValueError("Plan model or mirror revision differs from the verified checkpoint")
        if set(model["files"]) != FILES:
            raise ValueError("Only the exact eight approved data/document files may be acquired")
        for name, item in model["files"].items():
            expected_url = (f"https://modelscope.cn/api/v1/models/{spec['mirror_repo']}/repo?"
                            + urllib.parse.urlencode({"Revision": spec["mirror_revision"], "FilePath": name}))
            if item["url"] != expected_url:
                raise ValueError("Unexpected mirror file endpoint")
            if not isinstance(item["bytes"], int) or item["bytes"] <= 0:
                raise ValueError("Invalid expected file size")
            if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
                raise ValueError("Invalid expected SHA256")
            identity = item["official_identity"]
            length = 64 if identity["kind"] == "lfs_sha256" else 40
            if identity["kind"] not in ("lfs_sha256", "git_blob_sha1") or not re.fullmatch(
                    "[0-9a-f]{" + str(length) + "}", identity["value"]):
                raise ValueError("Invalid official content identity")
    for evidence in plan["evidence_files"]:
        if sha256_file(Path(evidence["path"])) != evidence["sha256"]:
            raise ValueError("Official identity evidence changed after plan preparation")
    return plan


def acquire(plan_path: Path, authorized: bool = False) -> dict:
    plan = load_plan(plan_path)
    if not authorized:
        return {"status": "DRY_RUN_NO_DOWNLOAD", "models": [
            {"model_id": model["model_id"], "revision": model["revision"],
             "file_count": len(model["files"]), "bytes": sum(item["bytes"] for item in model["files"].values())}
            for model in plan["models"]]}
    workspace = Path(__file__).resolve().parents[3]
    invocation = {"argv": list(sys.argv), "cwd": str(Path.cwd()),
                  "started_at": datetime.now(timezone.utc).isoformat()}
    reports = []
    for model in plan["models"]:
        check_deadline()
        target = workspace / ".runtime/cheap-guards" / OFFICIAL[model["model_id"]]["target"]
        target.mkdir(parents=True, exist_ok=True)
        actual_files = {}
        for name, expected in model["files"].items():
            check_deadline()
            destination = target / name
            if destination.exists():
                actual = inspect_file(destination)
                validate_identity(actual, expected)
            else:
                partial = destination.with_name(destination.name + ".part")
                # Any previous partial is uncommitted data and may be replaced.
                request = urllib.request.Request(expected["url"],
                                                 headers={"User-Agent": "cascade-cheapguard-acquisition/1"})
                try:
                    with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
                        count = 0
                        while chunk := response.read(1024 * 1024):
                            check_deadline()
                            count += len(chunk)
                            if count > expected["bytes"]:
                                raise ValueError("Mirror exceeded the official expected file size")
                            output.write(chunk)
                    actual = inspect_file(partial)
                    validate_identity(actual, expected)
                    partial.replace(destination)
                except Exception:
                    # Do not surface response objects, signed redirect URLs, or credentials.
                    raise RuntimeError("Public data acquisition failed or content identity mismatch: " + name) from None
            actual_files[name] = {**actual, "official_identity": expected["official_identity"],
                                  "acquisition_url": expected["url"]}
        manifest = {"model_id": model["model_id"], "revision": model["revision"],
                    # The frozen generic runtime compares these entries exactly
                    # with its own {bytes,sha256} inventory. Keep acquisition and
                    # official Git/LFS details in the external provenance only.
                    "files": {name: {"bytes": item["bytes"], "sha256": item["sha256"]}
                              for name, item in actual_files.items()},
                    "acquisition": {"source": "public_modelscope_exact_official_file_copy",
                                    "mirror_repo": model["mirror_repo"], "mirror_revision": model["mirror_revision"],
                                    "plan_sha256": sha256_file(plan_path),
                                    "utility_sha256": sha256_file(Path(__file__)),
                                    "invocation": invocation,
                                    "verified_at": datetime.now(timezone.utc).isoformat(),
                                    "official_identity_verified_for_every_file": True,
                                    "credentials_used": False, "forms_submitted": False,
                                    "model_loaded": False}}
        manifest_path = target / "artifact-manifest.json"
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text())
            if (existing.get("model_id") != manifest["model_id"] or existing.get("revision") != manifest["revision"]
                    or existing.get("files") != manifest["files"]):
                raise ValueError("Existing artifact manifest differs; refusing to overwrite")
        else:
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        provenance = {"model_id": model["model_id"], "official_revision": model["revision"],
                      "mirror_repo": model["mirror_repo"], "mirror_revision": model["mirror_revision"],
                      "evidence_files": plan["evidence_files"], "files": actual_files,
                      "acquisition": manifest["acquisition"]}
        # Runtime model directories contain only the proven official data files.
        provenance_path = plan_path.resolve().parent / (OFFICIAL[model["model_id"]]["target"]
                                                       + "-acquisition-provenance.json")
        if not provenance_path.exists():
            provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
        reports.append({"model_id": model["model_id"], "target": str(target),
                        "artifact_manifest_sha256": sha256_file(manifest_path), "files": len(actual_files)})
    return {"status": "ACQUIRED_VERIFIED_DATA_ONLY", "models": reports}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--download-authorized", action="store_true")
    args = parser.parse_args()
    print(json.dumps(acquire(args.plan, args.download_authorized), indent=2))
