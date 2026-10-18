#!/usr/bin/env python3
"""Create the verified Python 3.12 MPS environment and public pinned weights.

Run with any Python 3.12+ and an installed uv. It installs CPython 3.12.14 in
workspace runtime storage if needed, creates a separate MPS venv, installs the
exact tested lock, and invokes the checksum-verifying public-weight bootstrap.
It does not start or restart an existing service.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    root = args.workspace.resolve()
    scripts = root / "experiments/local_guards/scripts"
    lock = root / "experiments/local_guards/requirements-secjev-mps.lock.txt"
    environment = root / ".runtime/mps-diagnostics/.venv"
    task_env = {**os.environ, "UV_CACHE_DIR": str(root / ".cache/uv"),
                "UV_PYTHON_INSTALL_DIR": str(root / ".runtime/python")}
    if not (environment / "bin/python").exists():
        subprocess.run(["uv", "venv", "--python", "3.12.14", str(environment)], env=task_env, check=True)
    python = environment / "bin/python"
    subprocess.run(["uv", "pip", "sync", "--python", str(python), str(lock)], env=task_env, check=True)
    download_env = dict(task_env)
    download_env.pop("HF_HUB_OFFLINE", None)
    subprocess.run([str(python), str(scripts / "bootstrap_secjev.py"), "--workspace", str(root)],
                   env=download_env, check=True)
    print("Verified MPS environment and public SecJev-0.8B weights are ready.")
    print("Start from the workspace root with:")
    print(".runtime/mps-diagnostics/.venv/bin/python experiments/local_guards/scripts/serve_secjev_mps.py --port 8012")


if __name__ == "__main__":
    main()
