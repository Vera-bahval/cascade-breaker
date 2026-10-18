"""Pinned SecJev-4B FP32 scorer for the night experiment."""
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


class SecJev4BScorer(SecJevScorer):
    def __init__(self, workspace: Path, device: str, threads: int, attention: str, patch: str):
        self.workspace, self.device, self.lock = workspace.resolve(), device, threading.Lock()
        runtime = self.workspace / ".runtime/secjev4b"
        provenance = json.loads((runtime / "provenance.json").read_text())
        source_provenance = json.loads((self.workspace / ".runtime/secjev/provenance.json").read_text())
        if source_provenance["kev_revision"] != provenance["kev_revision"]:
            raise ValueError("The local Kev source revision does not match the released 4B runtime")
        provenance["source"] = str(self.workspace/".runtime/secjev4b/source/kev")
        provenance["model_path"] = str(self.workspace/"models/SecJev-4B")
        provenance["base_path"] = str(self.workspace/"models/Qwen3.5-4B-Base")
        provenance["release_commit"] = "3ef7ecf0ec6af725c3bb295249dbb0ca8a2ef13c"
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
            raise ValueError("The 4B checkpoint metadata does not match the pinned release backbone")
        checkpoint.meta.base, checkpoint.meta.base_revision = provenance["base_path"], None
        self.operator_log = []
        if patch != "none":
            install_solver_patch(torch, qwen, patch, self.operator_log)
        began = time.perf_counter()
        self.tokenizer, self.model = checkpoint.load(device, LoadOptions(dtype=torch.float32, merge=False, attn=attention))
        self.model.eval()
        self._sync()
        self.metadata = {**{k: provenance[k] for k in ("release", "release_commit", "model_archive_sha256", "code_archive_sha256", "base_repo", "base_revision", "base_weights_sha256", "kev_revision")},
                         "model": "SecJev-4B", "device": device, "precision": "FP32", "adapter_merged": False,
                         "attention": attention, "patch": patch, "temperature": float(self.model.head.temperature),
                         "threads": threads, "torch": torch.__version__, "transformers": __import__("transformers").__version__,
                         "python": platform.python_version(), "format_version": FORMAT_VERSION + "-4b-night",
                         "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                         "diagnostic_patch_sha256": hashlib.sha256((Path(__file__).parent / "mps_diagnostics.py").read_bytes()).hexdigest(),
                         "model_load_ms": (time.perf_counter()-began)*1000,
                         "all_modules_eval": all(not m.training for m in self.model.modules()),
                         "parameter_dtypes": sorted(set(str(p.dtype) for p in self.model.parameters())),
                         "parameter_devices": sorted(set(str(p.device) for p in self.model.parameters())),
                         "model_parameters": sum(p.numel() for p in self.model.parameters()),
                         "environment": {key: os.getenv(key) for key in ("PYTORCH_MPS_FAST_MATH", "PYTORCH_MPS_PREFER_METAL", "PYTORCH_ENABLE_MPS_FALLBACK")}}
        self.fingerprint = canonical_hash({k:v for k,v in self.metadata.items() if k != "model_load_ms"})

