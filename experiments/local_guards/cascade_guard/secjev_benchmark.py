"""Measure resident CPU inference and record strict CPU/MPS parity on real prefixes."""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import statistics
import time
import urllib.request

from .secjev import SecJevScorer


def compare(reference: dict, candidate: dict, tolerance: float = 1e-3) -> dict:
    if reference["status"] != "OK" or candidate["status"] != "OK":
        return {"passed": False, "error": [reference.get("error"), candidate.get("error")],
                "max_abs_delta": None, "categorical_flips": [], "threshold_flips": []}
    differences, categorical, threshold = [], [], []
    for qid, distribution in reference["probabilities"].items():
        other = candidate["probabilities"][qid]
        differences.extend(abs(p - other[key]) for key, p in distribution.items())
        if max(distribution, key=distribution.get) != max(other, key=other.get):
            categorical.append(qid)
        for cutoff in (0.5, 0.75, 0.9, 0.95, 0.99):
            if "true" in distribution and (distribution["true"] >= cutoff) != (other["true"] >= cutoff):
                threshold.append({"question": qid, "threshold": cutoff})
    maximum = max(differences, default=0.0)
    return {"passed": maximum <= tolerance and not categorical and not threshold,
            "max_abs_delta": maximum, "categorical_flips": categorical,
            "threshold_flips": threshold}


def representative(rows: list[dict]) -> list[dict]:
    selected, seen = [], set()
    for row in rows:
        key = (row["control_point"], row["label"])
        if key not in seen:
            seen.add(key)
            selected.append(row)
    longest = max(rows, key=lambda row: len(json.dumps(row["state"])))
    if longest["prefix_id"] not in {r["prefix_id"] for r in selected}:
        selected.append(longest)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    parser.add_argument("--mps", action="store_true", help="Evaluate exact FP32 MPS against the resident CPU reference")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.input.read_text().splitlines()]
    selected = representative(rows)
    report = {"tolerance": 1e-3, "selected_device": "cpu", "cases": [], "passed": None}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for prefix in selected:
        payload = {"state": prefix["state"], "questions": prefix["questions"]}
        request = urllib.request.Request(args.url.rstrip("/") + "/score", data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.load(response)
        case = {"prefix_id": prefix["prefix_id"], "control_point": prefix["control_point"],
                "label_for_sampling_only": prefix["label"], "cpu": result,
                "cpu_http_total_ms": (time.perf_counter() - started) * 1000}
        report["cases"].append(case)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"prefix_id": prefix["prefix_id"], "device": "cpu", "status": result["status"],
                          "compute_ms": result["timing_ms"]["compute"], "tokens": result["token_counts"]}), flush=True)
    if args.mps:
        candidate = SecJevScorer(args.workspace, "mps")
        for prefix, case in zip(selected, report["cases"]):
            result = candidate.score({"state": prefix["state"], "questions": prefix["questions"]})
            case["mps"] = result
            case["parity"] = compare(case["cpu"], result)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({"prefix_id": prefix["prefix_id"], "device": "mps", "status": result["status"],
                              "compute_ms": result["timing_ms"]["compute"], "parity": case["parity"]}), flush=True)
        report["passed"] = all(case["parity"]["passed"] for case in report["cases"])
        del candidate
        gc.collect()
    times = [case["cpu"]["timing_ms"]["total"] for case in report["cases"] if case["cpu"]["status"] == "OK"]
    if times:
        report["cpu_summary"] = {"requests": len(times), "mean_ms": statistics.mean(times),
                                 "median_ms": statistics.median(times), "max_ms": max(times),
                                 "estimated_1732_requests_s": statistics.mean(times) * 1732 / 1000,
                                 "estimate_caveat": "Representative sample with longest input; not an unbiased runtime forecast."}
    report["selected_device"] = "mps" if report["passed"] else "cpu"
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
