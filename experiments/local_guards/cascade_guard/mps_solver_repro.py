"""Reproduce Qwen3.5's five-dimensional unit-triangular solve on Apple MPS."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from .mps_diagnostics import unit_lower_inverse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    import torch
    torch.manual_seed(17)
    torch.set_num_threads(1)
    a = torch.randn(4,16,8,64,64)*.01
    b = torch.randn(4,16,8,64,128)
    reference = torch.linalg.solve_triangular(a,b,upper=False,unitriangular=True)
    am,bm = a.to("mps"),b.to("mps")
    report = {"torch":torch.__version__,"shape_a":list(a.shape),"shape_b":list(b.shape),"variants":{}}
    solvers = {"native_5d":lambda:torch.linalg.solve_triangular(am,bm,upper=False,unitriangular=True),
               "flattened_3d":lambda:torch.linalg.solve_triangular(am.reshape(-1,64,64),bm.reshape(-1,64,128),upper=False,unitriangular=True).reshape(b.shape),
               "block_inverse":lambda:unit_lower_inverse(torch,am)@bm}
    for label,solve in solvers.items():
        rows=[]
        for repeat in range(3):
            torch.mps.synchronize(); start=time.perf_counter(); result=solve(); torch.mps.synchronize()
            elapsed=(time.perf_counter()-start)*1000
            candidate=result.cpu(); finite=torch.isfinite(candidate)
            diff=(reference-candidate).abs()
            rows.append({"repeat":repeat,"finite_elements":int(finite.sum()),"elements":candidate.numel(),
                         "max_abs_delta":float(diff.max()) if bool(finite.all()) else None,
                         "fraction_with_abs_error_gt_1e_4":float((diff>1e-4).float().mean()),
                         "time_ms":elapsed})
        report["variants"][label]=rows
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__ == "__main__":main()
