#!/usr/bin/env python3
"""Launch verified SecJev-0.8B MPS inference without a research dataset.

Uses the frozen DiagnosticScorer implementation with FP32, unmerged adapter,
SDPA, a 64-token shape bucket and the GPU block triangular solver. The original
diagnostic CLI needs recorded reference data even in service mode; this launcher
imports that exact scorer directly, so a clean installation only needs weights.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--port", type=int, default=8012)
    args = parser.parse_args()
    root = args.workspace.resolve()
    sys.path.insert(0, str(root / "experiments/local_guards"))
    # Set these before importing Torch; match the measured environment exactly.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["PYTORCH_MPS_FAST_MATH"] = "0"
    os.environ.pop("PYTORCH_MPS_PREFER_METAL", None)
    os.environ.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
    from cascade_guard.mps_diagnostics import DiagnosticScorer
    from cascade_guard.secjev import serve

    scorer = DiagnosticScorer(root, "mps", "sdpa", 64, "solver_block")
    if not scorer.torch.backends.mps.is_available():
        raise RuntimeError("Apple MPS unavailable; run outside a sandbox that hides the GPU")
    if scorer.metadata["parameter_devices"] != ["mps:0"]:
        raise RuntimeError("The verified service requires all model parameters on MPS")
    if scorer.metadata["parameter_dtypes"] != ["torch.float32"]:
        raise RuntimeError("The verified service requires FP32 parameters")
    serve(scorer, "127.0.0.1", args.port)


if __name__ == "__main__":
    main()
