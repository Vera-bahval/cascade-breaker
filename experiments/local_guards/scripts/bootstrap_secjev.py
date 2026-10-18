#!/usr/bin/env python3
"""Download verified public SecJev components; never needs an API credential."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request

RELEASE = "v1.0.0"
BASE_REPO = "Qwen/Qwen3.5-0.8B-Base"
BASE_REVISION = "dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68"
BASE_WEIGHTS = "model.safetensors-00001-of-00001.safetensors"
BASE_SHA256 = "c2b1e5a17d9c1e27685d92ed9b382911ebb99955ecd89052d1721241adfbab6c"
KEV_REVISION = "90990a5fac2995b9faa3190f7d437e84f2067768"
KEV_ARCHIVE_SHA256 = "8d438f17b446a32f43002942b2a90314f77c6cd551fc6f84d182b8be3d5a1e00"
MODEL_SHA256 = "afb7e216edfbde4bfc19335312e4ae6577e98f29c915545ae2f7284e052e13dc"
CODE_SHA256 = "91b712d3c0715f6975833ed953bb586bf9dc86df858f52e78706ac2f741d572a"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def acquire(url: str, destination: Path, expected: str | None) -> str:
    if not destination.exists() or (expected and digest(destination) != expected):
        partial = destination.with_suffix(destination.suffix + ".partial")
        print(f"Downloading public component: {destination.name}", flush=True)
        with urllib.request.urlopen(url, timeout=120) as source, partial.open("wb") as target:
            shutil.copyfileobj(source, target)
        observed = digest(partial)
        if expected and observed != expected:
            partial.unlink()
            raise ValueError(f"SHA256 mismatch for {destination.name}: {observed}")
        partial.replace(destination)
    observed = digest(destination)
    if expected and observed != expected:
        raise ValueError(f"SHA256 mismatch for {destination.name}")
    return observed


def extract(archive: Path, destination: Path, strip_root: bool = False) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            relative = Path(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe archive path")
            if strip_root:
                relative = Path(*relative.parts[1:])
            if not relative.parts or member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Archive contains a non-file entry")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    root = args.workspace.resolve()
    runtime = root / ".runtime/secjev"
    downloads = runtime / "downloads"
    models = root / "models"
    downloads.mkdir(parents=True, exist_ok=True)
    models.mkdir(parents=True, exist_ok=True)
    release_root = f"https://github.com/UESTC1010/SecJev/releases/download/{RELEASE}"
    model_archive = downloads / "SecJev-0.8B-v1.0.0.tar.gz"
    code_archive = downloads / "SecJev-code-v1.0.0.tar.gz"
    kev_archive = downloads / f"kev-{KEV_REVISION}.tar.gz"
    acquire(f"{release_root}/{model_archive.name}", model_archive, MODEL_SHA256)
    acquire(f"{release_root}/{code_archive.name}", code_archive, CODE_SHA256)
    kev_hash = acquire(f"https://codeload.github.com/jaredpalmer/kev/tar.gz/{KEV_REVISION}", kev_archive, KEV_ARCHIVE_SHA256)
    extract(model_archive, models)
    extract(code_archive, runtime / "source/secjev", strip_root=True)
    extract(kev_archive, runtime / "source/kev", strip_root=True)

    from huggingface_hub import snapshot_download

    base = models / "Qwen3.5-0.8B-Base"
    print(f"Downloading pinned public backbone {BASE_REPO}@{BASE_REVISION}", flush=True)
    snapshot_download(BASE_REPO, revision=BASE_REVISION, local_dir=base, token=False,
                      allow_patterns=["*.json", "*.safetensors", "*.pt", "*.txt", "*.jinja"])
    if digest(base / BASE_WEIGHTS) != BASE_SHA256:
        raise ValueError("Pinned Qwen backbone checksum mismatch")
    metadata = {
        "release": RELEASE,
        "model_archive_sha256": MODEL_SHA256,
        "code_archive_sha256": CODE_SHA256,
        "base_repo": BASE_REPO,
        "base_revision": BASE_REVISION,
        "base_weights_sha256": BASE_SHA256,
        "kev_revision": KEV_REVISION,
        "kev_archive_sha256": kev_hash,
    }
    (runtime / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
    for path in [models / "SecJev-0.8B/head.pt", models / "SecJev-0.8B/adapter_model.safetensors",
                 runtime / "source/kev/kev/model.py"]:
        if not path.is_file():
            raise FileNotFoundError(path)
    print(json.dumps({"status": "READY", "provenance": metadata}, indent=2), flush=True)


if __name__ == "__main__":
    main()
