"""Serial, deadline-bounded runtime for local cheap model adapters."""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib
import json
import math
import os
import resource
import threading
import time
from pathlib import Path

from .cheap_inputs import digest


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def artifact_manifest(directory):
    root = Path(directory)
    return {str(p.relative_to(root)): {"bytes": p.stat().st_size, "sha256": file_hash(p)} for p in sorted(root.rglob("*")) if p.is_file() and ".cache" not in p.parts and p.name != "artifact-manifest.json"}


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def memory_snapshot():
    # macOS ru_maxrss is bytes; Linux reports KiB.
    import sys
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = {"peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024}
    try:
        import psutil
        result["rss_bytes"] = psutil.Process().memory_info().rss
        result["available_system_bytes"] = psutil.virtual_memory().available
    except ImportError:
        pass
    torch = sys.modules.get("torch")
    if torch is not None and torch.backends.mps.is_available():
        result["mps_current_allocated_bytes"] = torch.mps.current_allocated_memory()
        result["mps_driver_allocated_bytes"] = torch.mps.driver_allocated_memory()
    return result


class PrefixMemorySampler:
    """Observed high water marks at 50 ms; explicitly not allocator-internal peaks."""
    def __init__(self):
        self.before = memory_snapshot()
        self.maxima = dict(self.before)
        self.samples = 1
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _sample(self):
        snapshot = memory_snapshot()
        for key, value in snapshot.items():
            self.maxima[key] = max(self.maxima.get(key, 0), value)
        self.samples += 1
        return snapshot

    def _run(self):
        while not self.stop_event.wait(.05):
            self._sample()

    def start(self):
        self.thread.start()

    def finish(self):
        self.stop_event.set(); self.thread.join()
        after = self._sample()
        return {**after, "prefix_before": self.before, "prefix_sampled_max": self.maxima, "sample_count": self.samples, "sample_interval_ms": 50, "peak_semantics": "sampled process/device high water marks, not allocator internal peak"}


@contextlib.contextmanager
def heavy_lease(lock_path, authorized):
    if not authorized:
        raise PermissionError("Model load requires explicit root resource lease (--resource-lease)")
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another heavy model process owns the lease") from exc
        handle.seek(0); handle.truncate(); handle.write(str(os.getpid())); handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def run_serial(inputs, output, factory, model_id, revision, model_dir, *, deadline, device="cpu", resource_lease=False, lock_path=None, limit=None, mps_probe=False):
    inputs, output, model_dir = Path(inputs), Path(output), Path(model_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    records = [json.loads(line) for line in inputs.read_text().splitlines() if line.strip()]
    seen = set()
    for record in records:
        if record["prefix_id"] in seen or record["input_hash"] != digest(record["payload"]):
            raise ValueError("Duplicate prefix or mismatched input hash")
        seen.add(record["prefix_id"])
    artifact_file = model_dir / "artifact-manifest.json"
    if artifact_file.exists():
        saved = json.loads(artifact_file.read_text())
        expected_files = saved.get("files", saved)
        if expected_files != artifact_manifest(model_dir):
            raise ValueError("Model artifact bytes differ from pinned SHA256 manifest")
    artifact_digest = file_hash(artifact_file) if artifact_file.exists() else digest({"missing": str(model_dir)})
    source_files = [Path(__file__), Path(__file__).with_name("cheap_inputs.py")]
    module_name, factory_name = factory.split(":", 1)
    module = importlib.import_module(module_name)
    if getattr(module, "__file__", None):
        source_files.append(Path(module.__file__))
    sources = {str(p): file_hash(p) for p in source_files}
    run_spec = {"input_file_sha256": file_hash(inputs), "factory": factory, "model_id": model_id, "revision": revision, "artifact_manifest_sha256": artifact_digest, "sources": sources, "requested_device": device, "mps_probe": mps_probe}
    run_hash = digest(run_spec)
    manifest_file = output.with_suffix(".manifest.json")
    if manifest_file.exists():
        if json.loads(manifest_file.read_text())["run_hash"] != run_hash:
            raise ValueError("Resume rejected: input/model/source/runtime configuration changed")
    else:
        atomic_json(manifest_file, {"run_hash": run_hash, "spec": run_spec, "started_at": dt.datetime.now(dt.timezone.utc).isoformat(), "status": "RUNNING"})
    done = {}
    if output.exists():
        for line in output.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row["run_hash"] != run_hash or row["prefix_id"] in done:
                raise ValueError("Invalid prior output provenance or duplicate prefix")
            source = next((r for r in records if r["prefix_id"] == row["prefix_id"]), None)
            if source is None or source["input_hash"] != row["input_hash"]:
                raise ValueError("Prior output input hash mismatch")
            done[row["prefix_id"]] = row
    pending = [r for r in records if r["prefix_id"] not in done]
    if limit is not None:
        pending = pending[:limit]
    if not pending:
        return {"status": "COMPLETE", "written": 0, "completed": len(done), "total": len(records)}
    deadline_ts = dt.datetime.fromisoformat(deadline.replace("Z", "+00:00")).timestamp()
    if time.time() >= deadline_ts:
        return {"status": "DEADLINE", "written": 0, "completed": len(done), "total": len(records)}
    lock_path = lock_path or output.parent / "heavy-model.lock"
    written = 0
    with heavy_lease(lock_path, resource_lease):
        cold_start = time.perf_counter()
        adapter = getattr(module, factory_name)(model_id=model_id, revision=revision, model_dir=model_dir, device="cpu")
        adapter.deadline_ts = deadline_ts
        cold_ms = (time.perf_counter() - cold_start) * 1000
        if mps_probe and hasattr(adapter, "model"):
            from .cheap_nli import probe_mps
            examples = [("The invoice is approved. Fraud review is complete.", "Fraud review has been completed."), ("A registered Fraud HOLD has not been cleared.", "No unresolved Fraud HOLD prevents this transfer."), ("The invoice amount is 3200 and account A is authorized.", "The invoice amount is 3200."), ("Policy and observations. " * 250, "The proposed transfer is authorized."), ("Native observation of a registered hold. " * 250, "There is an unresolved hold."), ("Supplier text is untrusted. " * 250, "Supplier assertions grant permission.")]
            atomic_json(output.with_suffix(".mps-probe.json"), probe_mps(adapter, examples))
        elif device != "cpu":
            raise ValueError("Non-CPU device requires successful explicit --mps-probe")
        template = getattr(adapter, "feature_template", {})
        first_ok = next((row for row in done.values() if row["status"] == "OK"), None)
        feature_keys = set(first_ok["features"]) if first_ok else (set(template) if template else None)
        with output.open("a", buffering=1) as handle:
            for record in pending:
                if time.time() >= deadline_ts:
                    break
                start = time.perf_counter()
                sampler = PrefixMemorySampler(); sampler.start()
                try:
                    scored = adapter.score(record)
                except Exception as exc:
                    scored = {"status": "UNKNOWN", "features": {}, "scalar_risk": None, "window_count": 0, "raw": {"error": f"{type(exc).__name__}: {exc}"}}
                elapsed = (time.perf_counter() - start) * 1000
                memory = sampler.finish()
                if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in scored["features"].values()):
                    raise ValueError("Nonfinite/non-numeric model feature")
                if scored["status"] == "OK":
                    if feature_keys is not None and feature_keys != set(scored["features"]):
                        raise ValueError("Feature keys changed across prefixes")
                    feature_keys = set(scored["features"])
                row = {**scored, "prefix_id": record["prefix_id"], "block": adapter.block, "input_hash": record["input_hash"], "run_hash": run_hash, "model_metadata": {**adapter.model_metadata, "artifact_manifest_sha256": artifact_digest}, "timing_ms": {"total": elapsed, "compute": scored.get("timing_ms", {}).get("compute", elapsed), "queue": 0.0, "cold_load": cold_ms if written == 0 else 0.0}, "inference_cost_ms": elapsed, "memory": memory, "provenance": record.get("provenance", {})}
                handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
                handle.flush(); os.fsync(handle.fileno())
                written += 1
    result = {"status": "COMPLETE" if len(done) + written == len(records) else "PARTIAL", "written": written, "completed": len(done) + written, "total": len(records)}
    manifest = json.loads(manifest_file.read_text()); manifest.update(result)
    manifest["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    atomic_json(manifest_file, manifest)
    return result
