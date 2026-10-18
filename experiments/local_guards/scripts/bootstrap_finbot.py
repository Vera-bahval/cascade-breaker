#!/usr/bin/env python3
"""Recreate pinned FinBot + colleague instrumentation + tracked local safety patch."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

BASE = "a7f6964fbc60da807e2544d826a5b4e20eb0c5dc"
PROTOTYPE = "2476ceb9d88d003ce86e106c7d1644151ec283c1"
PROTOTYPE_TREE = "88e30027f2a2d6cc176f5b8d27e82d45521cdd09"
PYTHON = "3.13.15"


def git(repo: Path, *args, **kwargs):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, **kwargs)


def setup(workspace: Path, finbot_source: str, prototype_source: str, install=False):
    checkout = workspace / "vendor" / "finbot"
    checkout.parent.mkdir(parents=True, exist_ok=True)
    if not (checkout / ".git").is_dir():
        subprocess.run(["git", "clone", "--no-hardlinks", finbot_source, str(checkout)], check=True)
        git(checkout, "switch", "-c", "cascade-local", BASE)
        with tempfile.TemporaryDirectory(prefix="cascade-prototype-") as temp:
            source = Path(temp)
            subprocess.run(["git", "clone", "--no-hardlinks", prototype_source, str(source)], check=True)
            paths = subprocess.check_output(["git", "-C", str(source), "ls-tree", "-r", "--name-only", PROTOTYPE], text=True).splitlines()
            patches = sorted(p for p in paths if p.startswith("finbot-patches/") and p.endswith(".patch"))
            if len(patches) != 21:
                raise RuntimeError("Pinned prototype patch count differs")
            for name in patches:
                blob = subprocess.check_output(["git", "-C", str(source), "show", f"{PROTOTYPE}:{name}"])
                git(checkout, "-c", "user.name=Cascade local experiment", "-c", "user.email=cascade-local@example.invalid", "am", input=blob)
    git(checkout, "merge-base", "--is-ancestor", BASE, "HEAD")
    tree = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD^{tree}"], text=True).strip()
    if tree != PROTOTYPE_TREE:
        raise RuntimeError("Existing FinBot source tree differs from the pinned base + 21 prototype patches; preserve it and reconcile first")
    patch = workspace / "experiments" / "local_guards" / "finbot-local.patch"
    reverse = subprocess.run(["git", "-C", str(checkout), "apply", "--reverse", "--check", str(patch)], capture_output=True)
    if reverse.returncode:
        git(checkout, "apply", "--check", str(patch))
        git(checkout, "apply", str(patch))
    if subprocess.check_output(["git", "-C", str(checkout), "diff", "--binary", "HEAD"]) != patch.read_bytes():
        raise RuntimeError("FinBot has additional tracked source changes beyond the verified local patch")
    if install:
        package = workspace / "experiments" / "local_guards"
        environment = package / ".venv-finbot"
        env = os.environ.copy() | {"UV_CACHE_DIR": str(workspace / ".cache" / "uv"), "UV_PYTHON_INSTALL_DIR": str(workspace / ".runtime" / "python")}
        lock = package / "requirements-finbot.lock.txt"
        if not lock.is_file():
            raise RuntimeError("Verified FinBot requirements lock is missing")
        subprocess.run(["uv", "venv", "--allow-existing", "--python", PYTHON, str(environment)], env=env, check=True)
        subprocess.run(["uv", "pip", "sync", "--python", str(environment / "bin" / "python"), str(lock)], env=env, check=True)
        subprocess.run(["uv", "pip", "install", "--no-deps", "--no-build-isolation", "--python", str(environment / "bin" / "python"),
                        "-e", str(package), "-e", str(checkout)], env=env, check=True)
    print("Pinned FinBot ready; no server or inference was started.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--source-finbot", default="https://github.com/Vera-bahval/finbot-ctf.git")
    parser.add_argument("--source-prototype", default="https://github.com/Vera-bahval/cascade-breaker.git")
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    setup(args.workspace, args.source_finbot, args.source_prototype, args.install)
