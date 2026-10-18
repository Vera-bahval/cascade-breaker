"""Read-only cached SecJev checkpoint features; no inference or model imports.

The population is the night4b main P4 population. Labels are used only to select
eligible P4 prefixes and are never accepted by the numeric feature constructor.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import time

from .dataset import POINTS, build_observable_prefix, canonical, read_jsonl

VERSION = "cheap-sequence-v1"
QUESTION_KEYS = ("untrusted_instruction", "unsupported_authority_used", "action_conflicts_with_hold", "evidence_missing_for_permission")
STAGES = ("invoice_agent", "fraud_agent", "delegate_to_payments", "create_transfer")
BLOCKS = ("J_cur", "J_seq", "J_agg", "J_dynamic", "J_prior")
BLOCK_STAGES = {"J_cur": (3,), "J_seq": (0, 1, 2, 3), "J_agg": (0, 1, 2, 3),
                "J_dynamic": (0, 1, 2, 3), "J_prior": (0, 1, 2)}


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_fingerprint(metadata):
    return digest({k: v for k, v in metadata.items() if k != "model_load_ms"})


def inference_hash(prefix, metadata):
    # This order is the original secjev_batch.inference_input_hash contract.
    value = {"payload": {"state": prefix["state"], "questions": prefix["questions"]},
             "scorer_fingerprint": model_fingerprint(metadata)}
    return hashlib.sha256(json.dumps(value, sort_keys=False, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def vector(score):
    if not score or score.get("unknown") or score.get("status") == "UNKNOWN" or score.get("error"):
        return None
    try:
        values = [score["probabilities"][k] for k in QUESTION_KEYS]
        values = [float(v["true"] if isinstance(v, dict) else v) for v in values]
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return values if all(math.isfinite(v) and 0 <= v <= 1 for v in values) else None


def numeric_features(vectors, block):
    """Pure observable interface: exactly four chronological atomic vectors."""
    if block not in BLOCKS:
        raise ValueError("Unknown sequence block")
    if len(vectors) != 4:
        raise ValueError("Four semantic checkpoint positions required")
    if any(vectors[i] is None for i in BLOCK_STAGES[block]):
        return {}
    result = {}
    for i in BLOCK_STAGES[block]:
        for q, value in zip(QUESTION_KEYS, vectors[i]):
            result[f"checkpoint.{STAGES[i]}.{q}"] = float(value)
    if block == "J_agg":
        result = {k: v for k, v in result.items() if k.startswith("checkpoint.create_transfer.")}
    if block in ("J_agg", "J_dynamic"):
        for j, q in enumerate(QUESTION_KEYS):
            values = [v[j] for v in vectors]
            for name, value in (("min", min(values)), ("max", max(values)),
                                ("mean", statistics.fmean(values)), ("std", statistics.pstdev(values))):
                result[f"aggregate.{name}.{q}"] = float(value)
    if block == "J_dynamic":
        for i in range(3):
            for j, q in enumerate(QUESTION_KEYS):
                result[f"delta.{STAGES[i]}_to_{STAGES[i+1]}.{q}"] = vectors[i+1][j] - vectors[i][j]
        for j, q in enumerate(QUESTION_KEYS):
            result[f"delta.invoice_agent_to_create_transfer.{q}"] = vectors[3][j] - vectors[0][j]
    if not all(math.isfinite(x) for x in result.values()):
        raise ValueError("Non-finite derived feature")
    return result


def feature_schema():
    return {block: list(numeric_features([[0.0] * 4 for _ in range(4)], block)) for block in BLOCKS}


def main_population(prefixes, outcomes, expected_count=176):
    omap = {o["episode_id"]: o for o in outcomes}
    if len(omap) != len(outcomes):
        raise ValueError("Duplicate outcome episode")
    selected = []
    for row in prefixes:
        if row["control_point"] != POINTS[-1]:
            continue
        outcome = omap[row["episode_id"]]
        already = outcome["strict_harm_seq"] is not None and outcome["strict_harm_seq"] <= row["cut_seq"]
        if row["ambiguity"] != outcome["legacy_ambiguous"] or row["already_harmful"] != already:
            raise ValueError("Prefix/outcome population disagreement")
        if not outcome["legacy_ambiguous"] and not already:
            selected.append(row)
    if expected_count is not None and len(selected) != expected_count:
        raise ValueError(f"Main P4 population expected {expected_count}, got {len(selected)}")
    if len({r["episode_id"] for r in selected}) != len(selected):
        raise ValueError("Duplicate P4 episode")
    return sorted(selected, key=lambda r: r["prefix_id"])


def join_checkpoints(target, prefixes, raw_run=None):
    bypoint = defaultdict(list)
    for row in prefixes:
        if row["episode_id"] == target["episode_id"] and row["cut_seq"] <= target["cut_seq"]:
            bypoint[row["control_point"]].append(row)
    if any(len(bypoint[p]) > 1 for p in POINTS):
        raise ValueError("Ambiguous duplicate checkpoint")
    result = [bypoint[p][0] if bypoint[p] else None for p in POINTS]
    observed = [r for r in result if r is not None]
    if any(a["cut_seq"] >= b["cut_seq"] for a, b in zip(observed, observed[1:])):
        raise ValueError("Semantic checkpoint order is not chronological")
    if not result[-1] or result[-1]["prefix_id"] != target["prefix_id"]:
        raise ValueError("P4 checkpoint identity mismatch")
    for row in observed:
        expected_id = hashlib.sha256(f"{row['episode_id']}:{row['control_point']}:{row['cut_seq']}".encode()).hexdigest()[:24]
        if expected_id != row["prefix_id"] or row["max_input_seq"] >= row["cut_seq"]:
            raise ValueError("Invalid prefix identity or future input")
        if raw_run is not None:
            if raw_run["run_id"] != row["episode_id"]:
                raise ValueError("Raw episode identity mismatch")
            contexts = [s for s in raw_run["steps"] if s["kind"] == "guard_context" and
                        s.get("point") == row["control_point"] and s["seq"] <= target["cut_seq"]]
            if len(contexts) != 1 or contexts[0]["seq"] != row["cut_seq"]:
                raise ValueError("Raw archive checkpoint join mismatch")
            rebuilt = build_observable_prefix(raw_run["db_initial"], contexts[0], raw_run["steps"], row["questions"])
            if any(rebuilt[k] != row[k] for k in ("state", "questions", "max_input_seq", "cut_seq", "control_point")):
                raise ValueError("Cached prefix differs from raw observable reconstruction")
    return result


def validate_scores(prefixes, scores):
    """Identity failures reject export; inference failures remain explicit UNKNOWN."""
    byid = {r["prefix_id"]: r for r in prefixes}
    selected, fingerprints = {}, set()
    for score in scores:
        if score.get("ablation") != "plus_rationale":
            continue
        pid = score["prefix_id"]
        if pid not in byid or pid in selected:
            raise ValueError("Unknown or duplicate cached prefix")
        metadata = score.get("model_metadata", {})
        if metadata.get("model") != "SecJev-0.8B" or metadata.get("base_repo") != "Qwen/Qwen3.5-0.8B-Base":
            raise ValueError("Expected the frozen SecJev-0.8B cache")
        if not all(metadata.get(k) for k in ("model_archive_sha256", "base_weights_sha256", "base_revision", "scorer_sha256", "format_version")):
            raise ValueError("Incomplete cached model identity")
        if inference_hash(byid[pid], metadata) != score.get("input_hash"):
            raise ValueError("Cached score input hash mismatch")
        fingerprints.add(model_fingerprint(metadata))
        selected[pid] = score
    if len(fingerprints) != 1:
        raise ValueError("Mixed or missing cached scorer identity")
    return selected


def actual_references(scores):
    references = {}
    for score in scores:
        if score.get("cache_hit") or vector(score) is None:
            continue
        ih = score["input_hash"]
        if ih in references and references[ih]["probabilities"] != score["probabilities"]:
            raise ValueError("Conflicting actual source computations")
        references[ih] = score
    return references


def build_records(targets, prefixes, scoremap, references, runs=None):
    """Return shared numeric feature records; targets carry selection metadata only."""
    records = []
    for target in targets:
        start = time.perf_counter()
        checkpoints = join_checkpoints(target, prefixes, None if runs is None else runs[target["episode_id"]])
        scores = [scoremap.get(r["prefix_id"]) if r else None for r in checkpoints]
        vectors = [vector(s) for s in scores]
        masks = {stage: {"absent": checkpoints[i] is None,
                         "failed": checkpoints[i] is not None and vectors[i] is None}
                 for i, stage in enumerate(STAGES)}
        input_identity = [{"stage": STAGES[i], "prefix_id": r["prefix_id"] if r else None,
                           "input_hash": s.get("input_hash") if s else None}
                          for i, (r, s) in enumerate(zip(checkpoints, scores))]
        join_ms = (time.perf_counter() - start) * 1000
        for block in BLOCKS:
            extraction_start = time.perf_counter()
            indices = BLOCK_STAGES[block]
            feats = numeric_features(vectors, block)
            used_scores = [scores[i] for i in indices if scores[i] is not None]
            refs = [references.get(s["input_hash"]) for s in used_scores]
            known_refs = len(refs) == len(indices) and all(r is not None for r in refs)
            compute = sum(float(r["model_compute_ms"]) for r in refs) if known_refs else None
            latency = sum(float(r["latency_ms"]) for r in refs) if known_refs else None
            memory = {}
            for r in refs:
                for key, value in (r or {}).get("memory", {}).items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        memory[key] = max(memory.get(key, 0), value)
            extraction_ms = (time.perf_counter() - extraction_start) * 1000
            records.append({"prefix_id": target["prefix_id"], "block": block,
                            "status": "OK" if feats else "UNKNOWN", "features": feats,
                            "scalar_risk": max(x for i in indices for x in vectors[i]) if feats else None,
                            "inference_cost_ms": latency,
                            "input_hash": digest({"version": VERSION, "block": block,
                                "inputs": [input_identity[i] for i in indices]}),
                            "model_metadata": {"source_model": "SecJev-0.8B", "inference": "cached_only",
                                "source_fingerprints": sorted({model_fingerprint(s["model_metadata"]) for s in used_scores}),
                                "builder_version": VERSION},
                            "timing_ms": {"cache_join": join_ms, "feature_extraction": extraction_ms,
                                "inference_cost_ms": latency,
                                "reconstructed_live_source_compute": compute,
                                "reconstructed_live_source_latency": latency},
                            "memory": {"source_peak_observed_bytes": memory, "extractor_memory_measured": False},
                            "window_count": len(indices), "provenance": {"checkpoint_masks": masks,
                                "source_inputs": [input_identity[i] for i in indices],
                                "chronological_join": "raw_archive_reconstructed" if runs is not None else "prefix_metadata_only",
                                "complete_four_checkpoints": all(r is not None for r in checkpoints),
                                "scalar_risk_meaning": "maximum source atomic question probability; ranking control, not calibrated p(harm)",
                                "source_cache_hits": sum(bool(s.get("cache_hit")) for s in used_scores),
                                "source_reference_count": sum(r is not None for r in refs),
                                "live_cost_note": "Reconstructed sum of original actual source calls for each used checkpoint; duplicate identical payloads count per checkpoint. Cache extraction is separate. No new live timing."}})
    return records


def export(base: Path, output: Path):
    paths = {"prefixes": base / "data/prefixes.jsonl", "outcomes": base / "data/outcomes.jsonl",
             "archive": base / "data/archive/shadow-main.jsonl.gz", "scores": base / "results/secjev-mps-scores.jsonl",
             "question_definition": base / "cascade_guard/ml.py", "dataset_builder": base / "cascade_guard/dataset.py",
             "source_hash_builder": base / "cascade_guard/secjev_batch.py"}
    # Verify shared tuple without importing ml and its eager heavy dependencies.
    tree = ast.parse(paths["question_definition"].read_text())
    question_tuple = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "QUESTION_KEYS" for t in n.targets))
    if question_tuple != QUESTION_KEYS:
        raise ValueError("Shared atomic question schema changed")
    prefixes, outcomes, scores = (read_jsonl(paths[k]) for k in ("prefixes", "outcomes", "scores"))
    targets = main_population(prefixes, outcomes)
    scoremap = validate_scores(prefixes, scores)
    runs = {r["run_id"]: r for r in map(json.loads, gzip.decompress(paths["archive"].read_bytes()).decode().splitlines())}
    # Freeze source/input identities and the schema before feature export or metrics.
    schema = {"version": VERSION, "question_keys": QUESTION_KEYS, "checkpoints": dict(zip(STAGES, POINTS)),
              "features": feature_schema(), "unknown": "Empty numeric feature map; absent and failed checkpoint masks explicit in provenance.",
              "statistics": "Across four checkpoints, population standard deviation (ddof=0).",
              "dynamic": "raw16 + adjacent delta12 + first-to-last delta4 + aggregate16 =48 unique names"}
    freeze = {"version": VERSION, "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
              "builder_sha256": file_hash(Path(__file__)), "schema_sha256": digest(schema),
              "sources": {k: {"path": str(p), "sha256": file_hash(p)} for k, p in paths.items()},
              "selected_prefix_ids_sha256": digest([r["prefix_id"] for r in targets]), "main_prefixes": len(targets),
              "selection": "night4b: nonambiguous outcome episodes, P4 and not already harmful; expected176",
              "metrics_computed": False, "inference_calls": 0}
    output.mkdir(parents=True, exist_ok=True)
    def dump(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    if (output / "freeze.json").exists():
        old = json.loads((output / "freeze.json").read_text())
        compare = lambda value: {k: v for k, v in value.items() if k != "frozen_at_utc"}
        if compare(old) != compare(freeze):
            raise ValueError("Frozen sequence inputs/builder/schema changed; choose a new output directory")
        freeze = old
    dump("schema.json", schema)
    dump("freeze.json", freeze)
    records = build_records(targets, prefixes, scoremap, actual_references(scores), runs)
    (output / "features.jsonl").write_text("".join(canonical(r) + "\n" for r in records))
    counts = Counter((r["block"], r["status"]) for r in records)
    manifest = {"version": VERSION, "status": "COMPLETE", "main_prefixes": len(targets), "records": len(records),
                "feature_counts": {k: len(v) for k, v in feature_schema().items()},
                "coverage": {b: {s: counts[(b, s)] for s in ("OK", "UNKNOWN")} for b in BLOCKS},
                "all_four_checkpoints_present": all(r["provenance"]["complete_four_checkpoints"] for r in records),
                "all_source_hashes_verified": True, "raw_archive_join_validated": True,
                "features_sha256": file_hash(output / "features.jsonl"), "freeze_sha256": file_hash(output / "freeze.json"),
                "metrics_computed": False, "inference_calls": 0,
                "cost": "Source compute/latency sums reconstructed from actual noncache records including references of cache hits. No new live measurements; source memory uses maxima, never sum."}
    dump("manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path("experiments/local_guards"))
    parser.add_argument("--output", type=Path, default=Path("experiments/local_guards/results/cheap-guards/sequence"))
    args = parser.parse_args()
    print(json.dumps(export(args.base, args.output), indent=2))
