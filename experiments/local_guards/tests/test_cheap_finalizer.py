"""A successful score must remain bound to its payload, code and actual weights."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/finish_cheap_series.py"
spec = importlib.util.spec_from_file_location("cheap_finalizer_under_test", SCRIPT)
finalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finalizer)


def canonical(value):
    import hashlib
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def fixture(tmp_path):
    model = tmp_path / "model"; model.mkdir()
    weight = model / "weights.bin"; weight.write_bytes(b"weights")
    identity = {"model_id": "official/model", "revision": "a" * 40}
    artifact = {**identity, "files": {"weights.bin": {"bytes": 7, "sha256": finalizer.sha(weight)}}}
    artifact_path = model / "artifact-manifest.json"; artifact_path.write_text(json.dumps(artifact))
    payload = {"evidence": "pre-cut only"}
    row = {"prefix_id": "p", "payload": payload, "input_hash": canonical(payload)}
    inputs = tmp_path / "inputs.jsonl"; inputs.write_text(json.dumps(row) + "\n")
    source = tmp_path / "source.py"; source.write_text("version = 1\n")
    run_spec = {**identity, "input_file_sha256": finalizer.sha(inputs), "artifact_manifest_sha256": finalizer.sha(artifact_path), "sources": {str(source): finalizer.sha(source)}}
    run_hash = canonical(run_spec)
    path = tmp_path / "N.jsonl"; path.write_text(json.dumps({"prefix_id": "p", "block": "N", "input_hash": row["input_hash"], "run_hash": run_hash, "model_metadata": identity}) + "\n")
    path.with_suffix(".manifest.json").write_text(json.dumps({"spec": run_spec, "run_hash": run_hash}))
    return path, inputs, model, identity, source, weight


def test_actual_score_binding(tmp_path):
    path, inputs, model, identity, _, _ = fixture(tmp_path)
    result = finalizer.verify_model_records(path, inputs, model, identity["model_id"], identity["revision"], set())
    assert result["rows"] == 1 and result["actual_files_verified"] == 1


@pytest.mark.parametrize("what", ["weights", "source", "payload"])
def test_score_binding_rejects_mutated_evidence(tmp_path, what):
    path, inputs, model, identity, source, weight = fixture(tmp_path)
    if what == "weights":
        weight.write_bytes(b"WEIGHTS")
    elif what == "source":
        source.write_text("version = 2\n")
    else:
        row = json.loads(inputs.read_text()); row["payload"]["evidence"] = "changed"
        inputs.write_text(json.dumps(row) + "\n")
    with pytest.raises(AssertionError):
        finalizer.verify_model_records(path, inputs, model, identity["model_id"], identity["revision"], set())


@pytest.mark.parametrize("mutation", [None, "git_blob", "lfs"])
def test_public_mirror_must_match_official_pinned_blobs(tmp_path, mutation):
    import hashlib
    model = tmp_path / "mirror"; model.mkdir()
    siblings = []; files = {}
    for name in ("model.safetensors", "config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"):
        data = name.encode(); (model / name).write_bytes(data)
        description = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        files[name] = description
        sibling = {"rfilename": name, "size": len(data), "blobId": hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()}
        if name.endswith("safetensors"):
            sibling["lfs"] = {"sha256": description["sha256"]}
        siblings.append(sibling)
    if mutation == "git_blob":
        siblings[1]["blobId"] = "0" * 40
    if mutation == "lfs":
        siblings[0]["lfs"]["sha256"] = "0" * 64
    (model / "artifact-manifest.json").write_text(json.dumps({"files": files}))
    metadata = tmp_path / "official.json"
    metadata.write_text(json.dumps({"status": 200, "data": {"id": "official/model", "sha": "a" * 40, "siblings": siblings}}))
    if mutation:
        with pytest.raises(AssertionError):
            finalizer.verify_official_pg_identity(model, metadata, "official/model", "a" * 40)
    else:
        assert finalizer.verify_official_pg_identity(model, metadata, "official/model", "a" * 40)["official_files_verified"] == 5
