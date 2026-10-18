"""Select CPU thread count using identical FP32 prefixes and strict parity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics

from .secjev import SecJevScorer
from .secjev_benchmark import compare


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prefixes = [json.loads(line) for line in args.input.read_text().splitlines()]
    selected = []
    for label in (0, 1):
        selected.append(next(row for row in prefixes if row["control_point"] == "P4.finstripe__create_transfer" and row["label"] == label))
    scorer = SecJevScorer(args.workspace, "cpu", 4)
    report = {"tolerance": 1e-3, "reference_threads": 4, "candidates": {}, "selected_threads": 4}
    warm = scorer.score({"state": selected[0]["state"], "questions": selected[0]["questions"]})
    report["warmup_compute_ms"] = warm["timing_ms"]["compute"]
    references = []
    for threads in (4, 1, 8):
        scorer.torch.set_num_threads(threads)
        scorer.metadata["threads"] = threads
        cases = []
        for index, prefix in enumerate(selected):
            result = scorer.score({"state": prefix["state"], "questions": prefix["questions"]})
            result["model_metadata"] = dict(result["model_metadata"])
            if threads == 4:
                references.append(result)
            cases.append({"prefix_id": prefix["prefix_id"], "label_for_sampling_only": prefix["label"],
                          "result": result, "parity": compare(references[index], result)})
            print(json.dumps({"threads": threads, "prefix_id": prefix["prefix_id"],
                              "status": result["status"], "compute_ms": result["timing_ms"]["compute"],
                              "parity": cases[-1]["parity"]}), flush=True)
        passed = all(case["parity"]["passed"] for case in cases)
        med = statistics.median(case["result"]["timing_ms"]["compute"] for case in cases)
        report["candidates"][str(threads)] = {"passed": passed, "median_compute_ms": med, "cases": cases}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    passing = {int(t): values["median_compute_ms"] for t, values in report["candidates"].items() if values["passed"]}
    best = min(passing, key=passing.get)
    # Avoid changing operational defaults for a tiny or noisy improvement.
    if passing[best] < 0.9 * passing[4]:
        report["selected_threads"] = best
    report["estimated_1135_inferences_s"] = passing[report["selected_threads"]] * 1135 / 1000
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "candidates"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
