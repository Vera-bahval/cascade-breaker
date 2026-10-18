"""Isolated SecJev A/A, CPU/MPS parity and operator diagnostics.

This never changes the resident reference scorer or its dependency environment.
Each invocation uses a fresh process; reload IDs therefore identify processes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import threading
import time
import urllib.request

from .secjev import FORMAT_VERSION, SecJevScorer, canonical_hash, serve
from .secjev_benchmark import compare


def aa_summary(results: list[dict]) -> dict:
    comparisons = [compare(results[0], result) for result in results[1:]]
    valid = [row for row in results if row["status"] == "OK"]
    return {"runs": len(results), "valid": len(valid),
            "identical": len(valid) == len(results) and all(c["max_abs_delta"] == 0 for c in comparisons),
            "stable_decisions": len(valid) == len(results) and all(not c["categorical_flips"] and not c["threshold_flips"] for c in comparisons),
            "max_abs_delta": max((c["max_abs_delta"] for c in comparisons if c["max_abs_delta"] is not None), default=None),
            "comparisons": comparisons,
            "median_compute_ms": statistics.median(r["timing_ms"]["compute"] for r in valid) if valid else None}


def unit_lower_inverse(torch, a):
    """Invert a unit lower-triangular matrix by doubling diagonal block size.

    Uses [[A,0],[B,C]]^-1 = [[A^-1,0],[-C^-1 B A^-1,C^-1]].
    The diagonal and upper triangle of the input are ignored, like unitriangular=True.
    Relevant primary report: https://github.com/pytorch/pytorch/issues/198304
    """
    n = a.shape[-1]
    if n != a.shape[-2] or n < 1 or n & (n-1):
        raise ValueError("Block inverse requires square power-of-two matrices")
    prefix = a.shape[:-2]
    inverse = torch.ones(*prefix, n, 1, 1, device=a.device, dtype=a.dtype)
    width = 1
    while width < n:
        blocks = n // (2*width)
        diagonal_blocks = a.reshape(*prefix, blocks, 2*width, blocks, 2*width).diagonal(dim1=-4, dim2=-2).movedim(-1,-3)
        left, right = inverse[...,0::2,:,:], inverse[...,1::2,:,:]
        correction = -(right @ diagonal_blocks[...,width:,:width] @ left)
        inverse = torch.cat((torch.cat((left, torch.zeros_like(left)),dim=-1),
                             torch.cat((correction,right),dim=-1)),dim=-2)
        width *= 2
    return inverse[...,0,:,:]


def install_solver_patch(torch, module, mode: str, operator_log: list[dict]) -> None:
    """Module-local torch proxy: other callers and the resident process are untouched."""
    import types

    original = torch.linalg.solve_triangular

    def solver(a, b, **kw):
        if a.device.type != "mps":
            return original(a, b, **kw)
        if mode == "solver_cpu":
            return original(a.cpu(), b.cpu(), **kw).to(a.device)
        if mode == "solver_flatten":
            # MPS versions differ in support for more than one batch dimension.
            return original(a.reshape(-1, *a.shape[-2:]), b.reshape(-1, *b.shape[-2:]), **kw).reshape(b.shape)
        if mode == "solver_block":
            if kw != {"upper": False, "unitriangular": True}:
                raise ValueError("Diagnostic block solver expects a unit lower-triangular left solve")
            return unit_lower_inverse(torch, a) @ b
        if mode == "solver_forward":
            # Exact unit-lower forward substitution; no CPU tensor computation.
            if kw != {"upper": False, "unitriangular": True}:
                raise ValueError("Diagnostic solver expects a unit lower-triangular left solve")
            out = torch.empty_like(b)
            for i in range(a.shape[-1]):
                correction = (a[..., i, :i].unsqueeze(-1) * out[..., :i, :]).sum(-2)
                out[..., i, :] = b[..., i, :] - correction
            return out
        result = original(a, b, **kw)
        if len(operator_log) < 4:
            reference = original(a.cpu(), b.cpu(), **kw)
            candidate = result.cpu()
            finite = bool(torch.isfinite(candidate).all())
            operator_log.append({"operator": "linalg.solve_triangular", "a_shape": list(a.shape),
                                 "b_shape": list(b.shape), "a_stride": list(a.stride()), "b_stride": list(b.stride()),
                                 "finite": finite, "cpu_reference_finite": bool(torch.isfinite(reference).all()),
                                 "max_abs_delta": float((reference - candidate).abs().max()) if finite else None,
                                 "reference_max_abs": float(reference.abs().max()), "kwargs": kw})
        return result

    linalg_proxy = types.SimpleNamespace(**{name: getattr(torch.linalg, name) for name in dir(torch.linalg)})
    linalg_proxy.solve_triangular = solver
    torch_proxy = types.SimpleNamespace(**{name: getattr(torch, name) for name in dir(torch)})
    torch_proxy.linalg = linalg_proxy
    module.torch = torch_proxy


class DiagnosticScorer(SecJevScorer):
    def __init__(self, workspace: Path, device: str, attention: str, bucket: int, patch: str):
        self.workspace, self.device, self.lock = workspace.resolve(), device, threading.Lock()
        source = self.workspace / ".runtime/secjev/source/kev"
        sys.path.insert(0, str(source))
        import torch
        from kev.api import SystemOneRequest, to_record
        from kev.checkpoint import Checkpoint, LoadOptions
        from kev.model import rows_of
        from transformers.models.qwen3_5 import modeling_qwen3_5 as qwen

        self.torch, self.request_type, self.to_record, self.rows_of = torch, SystemOneRequest, to_record, rows_of
        torch.manual_seed(17)
        torch.set_num_threads(1)
        checkpoint = Checkpoint(str(self.workspace / "models/SecJev-0.8B"))
        checkpoint.meta.base = str(self.workspace / "models/Qwen3.5-0.8B-Base")
        checkpoint.meta.base_revision = None
        self.operator_log = []
        if patch != "none":
            install_solver_patch(torch, qwen, patch, self.operator_log)
        began = time.perf_counter()
        self.tokenizer, self.model = checkpoint.load(device, LoadOptions(dtype=torch.float32, merge=False, attn=attention))
        self.model.SHAPE_BUCKET = bucket
        self.model.eval()
        self._sync()
        provenance = json.loads((self.workspace / ".runtime/secjev/provenance.json").read_text())
        self.metadata = {**provenance, "model": "SecJev-0.8B", "device": device, "precision": "FP32",
                         "adapter_merged": False, "attention": attention, "shape_bucket": bucket,
                         "patch": patch, "temperature": float(self.model.head.temperature), "threads": 1,
                         "torch": torch.__version__, "transformers": __import__("transformers").__version__,
                         "python": platform.python_version(), "format_version": FORMAT_VERSION + "-diagnostic",
                         "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                         "model_load_ms": (time.perf_counter()-began)*1000,
                         "all_modules_eval": all(not m.training for m in self.model.modules()),
                         "parameter_dtypes": sorted(set(str(p.dtype) for p in self.model.parameters())),
                         "parameter_devices": sorted(set(str(p.device) for p in self.model.parameters())),
                         "environment": {key: os.getenv(key) for key in ("PYTORCH_MPS_FAST_MATH", "PYTORCH_MPS_PREFER_METAL", "PYTORCH_ENABLE_MPS_FALLBACK")}}
        self.fingerprint = canonical_hash({k:v for k,v in self.metadata.items() if k != "model_load_ms"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--input", type=Path, default=Path("experiments/local_guards/data/prefixes.jsonl"))
    parser.add_argument("--reference", type=Path, default=Path("experiments/local_guards/results/secjev-runtime.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu","mps","http"), default="mps")
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    parser.add_argument("--attention", choices=("sdpa","eager"), default="sdpa")
    parser.add_argument("--bucket", type=int, default=64)
    parser.add_argument("--patch", choices=("none","solver_audit","solver_cpu","solver_forward","solver_flatten","solver_block"), default="none")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--serve-port", type=int, help="Run the verified candidate as its own loopback service")
    parser.add_argument("--case-ids", nargs="*", default=["2154a315fd8101505a96b214","55f3842b959869ca1ab00e1e"])
    args = parser.parse_args()
    references = {c["prefix_id"]:c["cpu"] for c in json.loads(args.reference.read_text())["cases"]}
    rows = [json.loads(line) for line in args.input.read_text().splitlines()]
    selected = [r for r in rows if r["prefix_id"] in args.case_ids]
    if len(selected) != len(args.case_ids):
        raise ValueError("Some requested prefix IDs are absent")
    scorer = None if args.device == "http" else DiagnosticScorer(args.workspace, args.device, args.attention, args.bucket, args.patch)
    if args.serve_port:
        if not scorer:
            raise ValueError("The HTTP client cannot itself run a model service")
        serve(scorer,"127.0.0.1",args.serve_port)
        return
    report = {"process_id": os.getpid(), "device": args.device, "attention": args.attention,
              "shape_bucket": args.bucket, "patch": args.patch, "model_metadata": scorer.metadata if scorer else None,
              "tolerance": 1e-3, "cases": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for row in selected:
        payload = {"state":row["state"], "questions":row["questions"]}
        result_rows = []
        for i in range(args.repeats):
            if scorer:
                result = scorer.score(payload)
            else:
                req = urllib.request.Request(args.url.rstrip("/")+"/score", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
                with urllib.request.urlopen(req, timeout=300) as response:
                    result = json.load(response)
            result_rows.append(result)
            print(json.dumps({"prefix_id":row["prefix_id"], "repeat":i, "status":result["status"],
                              "compute_ms":result["timing_ms"]["compute"], "parity":compare(references[row["prefix_id"]], result)}), flush=True)
        report["cases"].append({"prefix_id":row["prefix_id"], "payload_hash":canonical_hash(payload),
                                "results":result_rows, "aa":aa_summary(result_rows),
                                "cpu_parity":[compare(references[row["prefix_id"]],r) for r in result_rows]})
        if scorer:
            report["operator_log"] = scorer.operator_log
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")


if __name__ == "__main__":
    main()
