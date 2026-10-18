"""Resumable SecJev scoring of prefix JSONL, with both rationale ablations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from .secjev import SecJevScorer, canonical_hash


def inference_input_hash(payload: dict, fingerprint: str) -> str:
    # Kev renders dictionaries in insertion order; option/state order can affect
    # predictions, so cache equivalence must preserve that order as well.
    value = {"payload": payload, "scorer_fingerprint": fingerprint}
    return hashlib.sha256(json.dumps(value, sort_keys=False, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def batch_row(prefix: dict, ablation: str, result: dict, input_hash: str) -> dict:
    distributions = result.get("probabilities", {})
    probabilities = {qid: values["true"] for qid, values in distributions.items() if "true" in values}
    return {"prefix_id": prefix["prefix_id"], "ablation": ablation, "input_hash": input_hash,
            "probabilities": probabilities, "distributions": distributions,
            "latency_ms": result["timing_ms"]["total"], "timing_ms": result["timing_ms"],
            "unknown": result["status"] != "OK", "error": result.get("error"),
            "cache_hit": False, "model_compute_ms": result["timing_ms"].get("compute"),
            "reused_reference_compute_ms": None,
            "model_metadata": result.get("model_metadata", {}),
            "token_counts": result.get("token_counts", {}), "memory": result.get("memory", {})}


def run_batch(source: Path, destination: Path, score, fingerprint: str) -> dict:
    existing = {}
    input_cache = {}
    if destination.exists():
        with destination.open() as stream:
            for line in stream:
                row = json.loads(line)
                if not row.get("unknown"):
                    existing[(row["prefix_id"], row["ablation"], row["input_hash"])] = row
                    if row["input_hash"] not in input_cache or not row.get("cache_hit"):
                        input_cache[row["input_hash"]] = row
    destination.parent.mkdir(parents=True, exist_ok=True)
    processed = skipped = unknown = cache_hits = model_calls = 0
    started = time.perf_counter()
    prefixes = [json.loads(line) for line in source.read_text().splitlines()]
    # Complete the main action gate first, while still covering every input.
    prefixes.sort(key=lambda row: 0 if row.get("control_point") == "P4.finstripe__create_transfer" else 1)
    with destination.open("a", buffering=1) as outputs:
        for prefix in prefixes:
            for ablation, state_key in [("facts_action", "state_facts_action"), ("plus_rationale", "state")]:
                if state_key not in prefix:
                    raise ValueError(f"Prefix {prefix['prefix_id']} missing {state_key}")
                payload = {"state": prefix[state_key], "questions": prefix["questions"]}
                input_hash = inference_input_hash(payload, fingerprint)
                key = (prefix["prefix_id"], ablation, input_hash)
                if key in existing:
                    skipped += 1
                    continue
                retrieval = time.perf_counter()
                reference = input_cache.get(input_hash)
                if reference is not None:
                    cache_hits += 1
                    row = {**reference, "prefix_id": prefix["prefix_id"], "ablation": ablation,
                           "cache_hit": True, "model_compute_ms": None,
                           "reused_reference_compute_ms": reference.get("model_compute_ms") or reference.get("reused_reference_compute_ms")}
                    elapsed_ms = (time.perf_counter() - retrieval) * 1000
                    row["latency_ms"] = elapsed_ms
                    row["timing_ms"] = {"tokenize": 0.0, "compute": 0.0, "total": elapsed_ms, "queue": 0.0}
                else:
                    result = score(payload)
                    row = batch_row(prefix, ablation, result, input_hash)
                    model_calls += 1
                    if not row["unknown"]:
                        input_cache[input_hash] = row
                outputs.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                processed += 1
                unknown += row["unknown"]
                if not row["unknown"]:
                    existing[key] = row
                if processed % 20 == 0:
                    elapsed = time.perf_counter() - started
                    print(json.dumps({"processed": processed, "skipped": skipped, "unknown": unknown,
                                      "cache_hits": cache_hits, "model_calls": model_calls,
                                      "elapsed_s": round(elapsed, 2), "seconds_per_inference": round(elapsed / max(model_calls, 1), 3)}), flush=True)
    return {"processed": processed, "skipped": skipped, "unknown": unknown,
            "cache_hits": cache_hits, "model_calls": model_calls,
            "elapsed_s": time.perf_counter() - started, "destination": str(destination)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--url", help="Resident service URL, such as http://127.0.0.1:8011")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.url:
        with urllib.request.urlopen(args.url.rstrip("/") + "/health", timeout=30) as response:
            health = json.load(response)
        fingerprint = health["fingerprint"]

        def score(payload):
            request = urllib.request.Request(args.url.rstrip("/") + "/score", data=json.dumps(payload).encode(),
                                             headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.load(response)
    else:
        scorer = SecJevScorer(args.workspace, args.device)
        score, fingerprint = scorer.score, scorer.fingerprint
    print(json.dumps(run_batch(args.input, args.output, score, fingerprint), indent=2))


if __name__ == "__main__":
    main()
