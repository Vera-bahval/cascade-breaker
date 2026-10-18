"""Bounded CPU/MPS A/A probe of the exact released security-trained SecJev-2B."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time

from .mps_diagnostics import aa_summary, install_solver_patch
from .secjev import FORMAT_VERSION, SecJevScorer, canonical_hash
from .secjev_benchmark import compare


class SecJev2BScorer(SecJevScorer):
    def __init__(self, workspace: Path, device: str, threads: int, attention: str, patch: str):
        self.workspace, self.device, self.lock = workspace.resolve(), device, threading.Lock()
        runtime = self.workspace / ".runtime/mps-diagnostics/secjev2b"
        provenance = json.loads((runtime / "download-manifest.json").read_text())
        source_provenance = json.loads((self.workspace / ".runtime/secjev/provenance.json").read_text())
        if source_provenance["kev_revision"] != provenance["kev_revision"]:
            raise ValueError("The local Kev source revision does not match the released 2B runtime")
        sys.path.insert(0, provenance["source"])
        import torch
        from kev.api import SystemOneRequest, to_record
        from kev.checkpoint import Checkpoint, LoadOptions
        from kev.model import rows_of
        from transformers.models.qwen3_5 import modeling_qwen3_5 as qwen

        self.torch, self.request_type, self.to_record, self.rows_of = torch, SystemOneRequest, to_record, rows_of
        torch.manual_seed(17)
        torch.set_num_threads(threads)
        checkpoint = Checkpoint(provenance["model_path"])
        if checkpoint.meta.base != provenance["base_repo"] or checkpoint.meta.base_revision != provenance["base_revision"]:
            raise ValueError("The 2B checkpoint metadata does not match the pinned release backbone")
        checkpoint.meta.base, checkpoint.meta.base_revision = provenance["base_path"], None
        self.operator_log = []
        if patch != "none":
            install_solver_patch(torch, qwen, patch, self.operator_log)
        began = time.perf_counter()
        self.tokenizer, self.model = checkpoint.load(device, LoadOptions(dtype=torch.float32, merge=False, attn=attention))
        self.model.eval()
        self._sync()
        self.metadata = {**{k: provenance[k] for k in ("release", "release_commit", "model_archive_sha256", "code_archive_sha256", "base_repo", "base_revision", "base_weights_sha256", "kev_revision")},
                         "model": "SecJev-2B", "device": device, "precision": "FP32", "adapter_merged": False,
                         "attention": attention, "patch": patch, "temperature": float(self.model.head.temperature),
                         "threads": threads, "torch": torch.__version__, "transformers": __import__("transformers").__version__,
                         "python": platform.python_version(), "format_version": FORMAT_VERSION + "-2b-probe",
                         "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                         "diagnostic_patch_sha256": hashlib.sha256((Path(__file__).parent / "mps_diagnostics.py").read_bytes()).hexdigest(),
                         "model_load_ms": (time.perf_counter()-began)*1000,
                         "all_modules_eval": all(not m.training for m in self.model.modules()),
                         "parameter_dtypes": sorted(set(str(p.dtype) for p in self.model.parameters())),
                         "parameter_devices": sorted(set(str(p.device) for p in self.model.parameters())),
                         "model_parameters": sum(p.numel() for p in self.model.parameters()),
                         "environment": {key: os.getenv(key) for key in ("PYTORCH_MPS_FAST_MATH", "PYTORCH_MPS_PREFER_METAL", "PYTORCH_ENABLE_MPS_FALLBACK")}}
        self.fingerprint = canonical_hash({k:v for k,v in self.metadata.items() if k != "model_load_ms"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--input", type=Path, default=Path("experiments/local_guards/data/prefixes.jsonl"))
    parser.add_argument("--cases-from", type=Path, default=Path("experiments/local_guards/results/secjev-runtime.json"))
    parser.add_argument("--case-ids", nargs="*")
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--attention", choices=("sdpa", "eager"), default="sdpa")
    parser.add_argument("--patch", choices=("none", "solver_audit", "solver_cpu", "solver_forward", "solver_block", "solver_flatten"), default="none")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--cpu-reference", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    old = json.loads(args.cases_from.read_text())
    ids = args.case_ids if args.case_ids is not None else ["2154a315fd8101505a96b214", "55f3842b959869ca1ab00e1e", "baea55b592c4314234ad2bb3"]
    old_cases = {c["prefix_id"]: c["cpu"] for c in old["cases"]}
    cpu = {c["prefix_id"]: c["results"][0] for c in json.loads(args.cpu_reference.read_text())["cases"]} if args.cpu_reference else {}
    rows = [json.loads(line) for line in args.input.read_text().splitlines()]
    selected = [next(r for r in rows if r["prefix_id"] == prefix_id) for prefix_id in ids]
    if not 1 <= args.repeats <= 10 or not 1 <= len(selected) <= 10:
        raise ValueError("This diagnostic is bounded to 1–10 cases and 1–10 repeats")
    scorer = SecJev2BScorer(args.workspace, args.device, args.threads, args.attention, args.patch)
    report = {"process_id": os.getpid(), "device": args.device, "model_metadata": scorer.metadata,
              "comparison_note": "0.8B comparisons measure model differences, not numerical parity; same-model parity uses CPU2B reference.", "cases": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for row in selected:
        payload = {"state": row["state"], "questions": row["questions"]}
        results = []
        for i in range(args.repeats):
            result = scorer.score(payload)
            results.append(result)
            print(json.dumps({"prefix_id": row["prefix_id"], "repeat": i, "status": result["status"],
                              "compute_ms": result["timing_ms"]["compute"], "probabilities": result["probabilities"], "error": result["error"]}), flush=True)
        item = {"prefix_id": row["prefix_id"], "control_point": row["control_point"], "payload_hash": canonical_hash(payload),
                "results": results, "aa": aa_summary(results),
                "model_difference_vs_cpu08b": [compare(old_cases[row["prefix_id"]], r) for r in results] if row["prefix_id"] in old_cases else None}
        if row["prefix_id"] in cpu:
            item["cpu2b_parity"] = [compare(cpu[row["prefix_id"]], r) for r in results]
        report["cases"].append(item)
        report["operator_log"] = scorer.operator_log
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")


if __name__ == "__main__":
    main()
