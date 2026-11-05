"""Inventory saved Git archives without importing FinBot or an inference client."""
import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def describe(raw, name):
    result = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
              "native_hook_episodes": 0, "legacy_probe_episodes": 0,
              "finbot_revision": None}
    if name.endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
            files = [m for m in tar if m.isfile()]
            hooks = [m for m in files if m.name.endswith(".hooks.jsonl") or m.name.endswith("/hooks.jsonl")]
            result["native_hook_episodes"] = len(hooks)
            result["hook_members"] = [m.name for m in hooks]
            result["status"] = "native_hook_candidate" if hooks else "source_or_non_native_archive"
            # Version claims are recorded, not guessed from the filename '477'.
            for member in files:
                if member.name.endswith("/manifest.json") and member.size < 2_000_000:
                    try:
                        value = json.loads(tar.extractfile(member).read())
                        for key in ("finbot_commit", "finbot_revision", "finbot_sha", "finbot_base_commit"):
                            if isinstance(value.get(key), str):
                                result["finbot_revision"] = value[key]
                    except (ValueError, AttributeError):
                        pass
    else:
        try:
            lines = gzip.decompress(raw).splitlines() if name.endswith(".gz") else raw.splitlines()
            records = [json.loads(x) for x in lines if x.strip()]
            legacy = [r for r in records if isinstance(r, dict) and "run_id" in r and "steps" in r]
            hooks = [r for r in records if isinstance(r, dict) and "hook_kind" in r]
            result.update(legacy_probe_episodes=len(legacy),
                          native_hook_episodes=len({(r.get("session_id"), r.get("workflow_id")) for r in hooks}),
                          status="legacy_probe_candidate" if legacy else "native_journal_candidate" if hooks else "non_native_records")
        except (ValueError, OSError):
            result["status"] = "unsupported_record_format"
    return result


def inventory(revisions=None):
    refs = revisions or {x: git("rev-parse", x).decode().strip() for x in git("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin", "refs/heads").decode().splitlines()
            if x != "origin/HEAD"}
    blobs = {}
    for ref in sorted(refs):
        for line in git("ls-tree", "-r", refs[ref]).decode().splitlines():
            header, name = line.split("\t", 1)
            if name.startswith("experiments/local_guards_v4/"):
                continue  # Never recursively inventory this derived experiment.
            if not (name.endswith(".tar.gz") or name.endswith(".jsonl.gz")
                    or name.endswith("hooks.jsonl") or "/scenarios/results/" in "/" + name and name.endswith(".json")):
                continue
            oid = header.split()[2]
            blobs.setdefault(oid, []).append({"ref": ref, "path": name})
    records = []
    for oid, locations in sorted(blobs.items()):
        raw = git("cat-file", "blob", oid)
        record = describe(raw, locations[0]["path"])
        record.update(git_blob=oid, locations=locations)
        records.append(record)
    # The explicitly supplied colleague archive also exists outside Git copies.
    old = ROOT.parents[1] / "experiments/local_guards/data/archive/shadow-main.jsonl.gz"
    if old.exists():
        raw = old.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        match = next((r for r in records if r["sha256"] == checksum), None)
        if match is not None:
            match["external_path"] = str(old)
        else:
            record = describe(raw, old.name)
            record.update(git_blob=None, locations=[], external_path=str(old))
            records.append(record)
    return {"kind": "available saved archives, not all admitted evaluation episodes",
            "refs": refs,
            "records": records, "unique_blobs": len(records),
            "statuses": dict(Counter(r["status"] for r in records)),
            "limitations": ["Counts are physical archive members before cross-archive episode/content deduplication.",
                "Unknown source revision remains null; filename/model name is not version evidence.",
                "Only tracked candidate artifacts plus the supplied original shadow archive are inventoried; runtime secrets/configs are not scanned.",
                "An inventory candidate is not proof that pre-action state or outcome can be labeled."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "data/source-inventory.json")
    parser.add_argument("--refs-json", type=Path, help="Existing inventory whose immutable Git revisions should be reused")
    args = parser.parse_args()
    result = inventory(json.loads(args.refs_json.read_text())["refs"] if args.refs_json else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"records", "refs"}}, indent=2))
