"""Resident, serial SecJev reference inference and a loopback JSON service.

Bootstrap with scripts/bootstrap_secjev.py, then use the dedicated 3.12 runtime:
PYTHONPATH=experiments/local_guards .runtime/secjev/.venv/bin/python -m
cascade_guard.secjev --workspace . --device cpu serve --port 8011
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import platform
import resource
import sys
import threading
import time
from typing import Any

MAX_TOKENS = 8192
FORMAT_VERSION = "secjev-reference-v1"


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def unknown_response(error: str, metadata: dict | None = None,
                     elapsed_ms: float = 0.0, queue_ms: float = 0.0,
                     token_counts: dict | None = None) -> dict:
    return {"status": "UNKNOWN", "probabilities": {},
            "timing_ms": {"tokenize": 0.0, "compute": 0.0, "total": elapsed_ms, "queue": queue_ms},
            "model_metadata": metadata or {}, "token_counts": token_counts or {}, "error": error}


class SecJevScorer:
    """One model instance with an explicit queue and full, unrounded distributions."""

    def __init__(self, workspace: str | Path, device: str = "cpu", threads: int = 4):
        self.workspace = Path(workspace).resolve()
        self.device = device
        self.lock = threading.Lock()
        source = self.workspace / ".runtime/secjev/source/kev"
        sys.path.insert(0, str(source))
        import torch
        from kev.api import SystemOneRequest, to_record
        from kev.checkpoint import Checkpoint, LoadOptions
        from kev.model import rows_of

        self.torch, self.request_type, self.to_record, self.rows_of = torch, SystemOneRequest, to_record, rows_of
        if device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("MPS unavailable; select CPU explicitly")
        if device not in ("cpu", "mps"):
            raise ValueError("This local reference runtime supports CPU and MPS only")
        provenance = json.loads((self.workspace / ".runtime/secjev/provenance.json").read_text())
        checkpoint = Checkpoint(str(self.workspace / "models/SecJev-0.8B"))
        checkpoint.meta.base = str(self.workspace / "models/Qwen3.5-0.8B-Base")
        checkpoint.meta.base_revision = None
        if threads < 1:
            raise ValueError("CPU thread count must be positive")
        torch.set_num_threads(threads)
        started = time.perf_counter()
        self.tokenizer, self.model = checkpoint.load(device, LoadOptions(dtype=torch.float32, merge=False, attn="sdpa"))
        self.model.eval()
        self._sync()
        self.metadata = {**provenance, "model": "SecJev-0.8B", "device": device,
                         "precision": "FP32", "adapter_merged": False, "attention": "sdpa",
                         "temperature": float(self.model.head.temperature), "threads": threads,
                         "torch": torch.__version__, "python": platform.python_version(),
                         "format_version": FORMAT_VERSION,
                         "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                         "model_load_ms": (time.perf_counter() - started) * 1000}
        self.fingerprint = canonical_hash({k: v for k, v in self.metadata.items() if k != "model_load_ms"})

    def _sync(self) -> None:
        if self.device == "mps":
            self.torch.mps.synchronize()

    def memory(self) -> dict:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result = {"process_peak_rss_bytes": int(rss if sys.platform == "darwin" else rss * 1024)}
        if self.device == "mps":
            result.update(mps_allocated_bytes=self.torch.mps.current_allocated_memory(),
                          mps_driver_bytes=self.torch.mps.driver_allocated_memory())
        return result

    def score(self, payload: dict) -> dict:
        queued = time.perf_counter()
        with self.lock:
            began = time.perf_counter()
            queue_ms = (began - queued) * 1000
            counts: dict = {}
            try:
                request = self.request_type.model_validate(payload)
                record, metadata = self.to_record(request)
                encoded = self.model.encode(self.tokenizer, record, max_state=MAX_TOKENS,
                                            max_branch=MAX_TOKENS, strict=True)
                state, _, rows = self.rows_of(encoded)
                counts = {"state": len(state),
                          "questions": {m["id"]: {"branch": len(row["ids"]), "state_plus_branch": len(state) + len(row["ids"])}
                                        for m, row in zip(metadata, rows)},
                          "model_rows_total": sum(len(state) + len(row["ids"]) for row in rows)}
                if any(len(state) + len(row["ids"]) > MAX_TOKENS for row in rows):
                    raise ValueError(f"state + question exceeds {MAX_TOKENS} tokens; no truncation")
                tokenize_ms = (time.perf_counter() - began) * 1000
                self._sync()
                compute_start = time.perf_counter()
                with self.torch.inference_mode():
                    logits = self.model.forward(encoded)
                    distributions = [self.torch.softmax(z.float(), -1).cpu().tolist() for z in logits]
                self._sync()
                compute_ms = (time.perf_counter() - compute_start) * 1000
                result = {}
                for m, distribution in zip(metadata, distributions):
                    if len(distribution) != len(m["keys"]) or not all(math.isfinite(p) and 0 <= p <= 1 for p in distribution):
                        raise ValueError("Invalid probability distribution")
                    if abs(sum(distribution) - 1.0) > 1e-5:
                        raise ValueError("Probability distribution is not normalized")
                    result[m["id"]] = dict(zip(m["keys"], distribution))
                return {"status": "OK", "probabilities": result,
                        "timing_ms": {"tokenize": tokenize_ms, "compute": compute_ms,
                                      "total": (time.perf_counter() - queued) * 1000, "queue": queue_ms},
                        "model_metadata": self.metadata, "token_counts": counts,
                        "memory": self.memory(), "error": None}
            except Exception as exc:
                return unknown_response(f"{type(exc).__name__}: {exc}", self.metadata,
                                        (time.perf_counter() - queued) * 1000, queue_ms, counts)


def serve(scorer: SecJevScorer, host: str, port: int) -> None:
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("SecJev service binds only to loopback")

    class Handler(BaseHTTPRequestHandler):
        def _json(self, value: dict, status: int = 200) -> None:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            if self.path != "/health":
                return self._json({"error": "Not found"}, 404)
            self._json({"status": "READY", "model_metadata": scorer.metadata,
                        "fingerprint": scorer.fingerprint, "memory": scorer.memory()})

        def do_POST(self):
            if self.path not in ("/score", "/v1/systemone"):
                return self._json({"error": "Not found"}, 404)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 2 * 1024 * 1024:
                    raise ValueError("Request body must be between 1 byte and 2 MiB")
                payload = json.loads(self.rfile.read(length))
            except (ValueError, json.JSONDecodeError) as exc:
                return self._json(unknown_response(f"Invalid request: {exc}"), 400)
            self._json(scorer.score(payload))

        def log_message(self, *_):
            # Avoid logging caller-supplied text; the server has no authentication secrets.
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    print(json.dumps({"status": "LISTENING", "url": f"http://{host}:{port}",
                      "model_metadata": scorer.metadata, "memory": scorer.memory()}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--threads", type=int, default=4)
    subs = parser.add_subparsers(dest="command", required=True)
    server_parser = subs.add_parser("serve")
    server_parser.add_argument("--host", default="127.0.0.1")
    server_parser.add_argument("--port", type=int, default=8011)
    score_parser = subs.add_parser("score")
    score_parser.add_argument("request", type=Path)
    args = parser.parse_args()
    scorer = SecJevScorer(args.workspace, args.device, args.threads)
    if args.command == "serve":
        serve(scorer, args.host, args.port)
    else:
        print(json.dumps(scorer.score(json.loads(args.request.read_text())), ensure_ascii=False,
                         indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
