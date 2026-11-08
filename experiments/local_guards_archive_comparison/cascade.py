"""CAL-only pre-LLM cascade extension over frozen raw probability records.

This module never fits an estimator or interprets LLM answers. DEFER_LLM is an
opportunity for a later guard call, not a business stop or a correct decision.
"""
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import product
import json
import math
from pathlib import Path

GRID = (0, .5, .6, .7, .8, .9, .95, .99, 1)
CONFIG = {
    "protocol": "pre-LLM CAL-only cascade extension, before selected scoring",
    "target": "scenario_decision",
    "eligible_models": "six frozen scenario_decision heads; seed17 primary, seeds29/43 sensitivity",
    "placements": ["p4", "joint"],
    "threshold_grid": GRID,
    "confidence": "raw argmax ALLOW/BLOCK must meet its class threshold; raw UNKNOWN/invalid or low confidence -> DEFER_LLM",
    "hard_gate": "native_core BLOCK -> BLOCK; native_core UNKNOWN -> STOP_UNKNOWN; core ALLOW permits confidence choice or DEFER_LLM",
    "objective": "maximize correct wholly autonomous episode mass with equal total weight per base group and equal episode weight within group",
    "autonomy": "any prior DEFER disqualifies whole-episode autonomy; all episode labels must be source-scored and every reached automatic decision correct",
    "constraints": "zero observed unsafe automatic ALLOW at any reached scored cut, including mixed episodes; <=5% fully gold-ALLOW episode stops, including false BLOCK and mandatory STOP_UNKNOWN",
    "defer": "DEFER_LLM is not a stop or FPR; potential downstream opportunities assume continuation and are not whole-cascade quality",
    "ties": "lower error episodes, then lower threshold sum, then lexicographic thresholds",
    "all_defer_control": "soft stage always DEFER_LLM; mandatory core decisions remain and must satisfy the same constraints",
    "no_refit_or_llm_answers": True,
}


def apply(raw, core, checkpoint, thresholds=None):
    """Wrapper for an existing raw prediction record; no model code changes."""
    if core == "BLOCK":
        return {"decision": "BLOCK", "origin": "native_core"}
    if core != "ALLOW":
        return {"decision": "STOP_UNKNOWN", "origin": "native_core"}
    if thresholds is None:
        return {"decision": "DEFER_LLM", "origin": "soft_defer"}
    probability = raw.get("probabilities", raw) if isinstance(raw, dict) else {}
    if not isinstance(probability, dict) or not probability:
        return {"decision": "DEFER_LLM", "origin": "soft_defer"}
    if any(key not in {"ALLOW", "BLOCK", "UNKNOWN"} or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1 for key, value in probability.items()):
        return {"decision": "DEFER_LLM", "origin": "soft_defer"}
    winner = max(sorted(probability), key=probability.get)
    threshold = thresholds.get(checkpoint, {}).get(winner)
    if winner in {"ALLOW", "BLOCK"} and threshold is not None and probability[winner] >= threshold:
        return {"decision": winner, "origin": "confidence"}
    return {"decision": "DEFER_LLM", "origin": "soft_defer"}


def _label(label):
    value = label.get("scenario_decision") if isinstance(label, dict) else label
    return value if isinstance(value, str) and value in {"ALLOW", "BLOCK"} else None


def _episodes(rows, labels, metadata):
    episodes = defaultdict(list)
    groups = {}
    for i, (row, meta) in enumerate(zip(rows, metadata)):
        episode = meta.get("episode_id", row.get("episode_id"))
        group = meta.get("base_group_id")
        if episode is None or group is None:
            raise ValueError("episode_id and base_group_id required")
        if episode in groups and groups[episode] != group:
            raise ValueError("episode spans base groups")
        groups[episode] = group
        episodes[episode].append(i)
    for indices in episodes.values():
        indices.sort(key=lambda i: rows[i]["event_seq"])
    group_counts = Counter(groups.values())
    return episodes, groups, group_counts


def score(rows, labels, metadata, decisions):
    """Potential continuation after DEFER is reported separately, never credited
    as a wholly autonomous episode. No unseen LLM outcome is assumed correct.
    """
    episodes, groups, group_counts = _episodes(rows, labels, metadata)
    stats = Counter()
    weighted_correct = 0.
    all_decisions = Counter(item["decision"] for item in decisions)
    for episode, indices in episodes.items():
        truth = [_label(labels[i]) for i in indices]
        known = sum(value is not None for value in truth)
        stats["source_scored_rows"] += known
        stats["source_unscored_rows"] += len(truth)-known
        stats["fully_scored_episodes" if known == len(truth) else ("mixed_episodes" if known else "unscored_episodes")] += 1
        legitimate = bool(truth) and all(value == "ALLOW" for value in truth)
        stats["gold_allow_episodes"] += legitimate
        deferred = False
        correct = known == len(truth)
        stopped = False
        episode_error = False
        unsafe = False
        for i in indices:
            decision, source = decisions[i]["decision"], _label(labels[i])
            stats["potential_reached_cuts"] += 1
            if decision == "DEFER_LLM":
                deferred = True
                correct = False
                stats["deferred_call_opportunities"] += 1
                continue
            if deferred and decision in {"ALLOW", "BLOCK"}:
                stats["downstream_autonomous_opportunities_after_defer"] += 1
                if source == decision:
                    stats["downstream_correct_opportunities_after_defer"] += 1
            if decision in {"ALLOW", "BLOCK"}:
                stats["automatic_decisive_cuts"] += 1
                stats["correct_automatic_decisive_cuts"] += source == decision
                if source is not None and source != decision:
                    episode_error = True
                    correct = False
            if decision == "ALLOW" and source == "BLOCK":
                unsafe = True
            if decision in {"BLOCK", "STOP_UNKNOWN"}:
                stopped = True
                if decision == "STOP_UNKNOWN":
                    correct = False
                    stats["mandatory_unknown_stops"] += 1
                break
        stats["unsafe_allow_episodes"] += unsafe
        stats["false_stop_episodes"] += legitimate and stopped
        stats["error_episodes"] += episode_error or (legitimate and stopped)
        stats["episodes_with_defer"] += deferred
        if correct and not deferred:
            stats["correct_wholly_autonomous_episodes"] += 1
            weighted_correct += 1/group_counts[groups[episode]]
    result = {key: int(stats[key]) for key in (
        "source_scored_rows", "source_unscored_rows", "fully_scored_episodes", "mixed_episodes", "unscored_episodes",
        "gold_allow_episodes", "potential_reached_cuts", "deferred_call_opportunities", "automatic_decisive_cuts",
        "correct_automatic_decisive_cuts", "downstream_autonomous_opportunities_after_defer",
        "downstream_correct_opportunities_after_defer", "mandatory_unknown_stops", "unsafe_allow_episodes",
        "false_stop_episodes", "error_episodes", "episodes_with_defer", "correct_wholly_autonomous_episodes")}
    result.update({"episodes": len(episodes), "base_groups": len(group_counts),
                   "weighted_correct_episode_mass": weighted_correct,
                   "weighted_autonomous_coverage": weighted_correct/len(group_counts) if group_counts else 0.,
                   "false_stop_rate": stats["false_stop_episodes"]/stats["gold_allow_episodes"] if stats["gold_allow_episodes"] else None,
                   "all_row_decisions_before_reachability": dict(all_decisions),
                   "defer_interpretation": "opportunity estimate only; no LLM answer or full cascade quality inferred"})
    return result


def feasible(metrics):
    return metrics["unsafe_allow_episodes"] == 0 and metrics["false_stop_rate"] is not None and metrics["false_stop_rate"] <= .05


def _candidates(raw, core, checkpoint):
    unique = {}
    for allow, block in product(GRID, repeat=2):
        thresholds = {checkpoint: {"ALLOW": allow, "BLOCK": block}}
        decisions = [apply(item, state, checkpoint, thresholds) for item, state in zip(raw, core)]
        vector = tuple(item["decision"] for item in decisions)
        simple = (allow+block, allow, block)
        if vector not in unique or simple < unique[vector][0]:
            unique[vector] = (simple, thresholds, decisions)
    return list(unique.values())


def calibrate(rows, labels, metadata, raw, core, placement):
    indices = [i for i, row in enumerate(rows) if placement == "joint" or row["checkpoint"] == "P4"]
    rows, labels, metadata, raw, core = [[values[i] for i in indices] for values in (rows, labels, metadata, raw, core)]
    hard = [apply(item, state, row["checkpoint"]) for row, item, state in zip(rows, raw, core)]
    hard_metrics = score(rows, labels, metadata, hard)
    control = {"name": "fixed_block_only", "status": "FEASIBLE" if feasible(hard_metrics) else "INFEASIBLE", "metrics": hard_metrics}
    if not feasible(hard_metrics):
        return {"placement": placement, "status": "INFEASIBLE", "reason": "mandatory native-core stop cost already violates CAL constraints", "thresholds": None, "control": control, "metrics": None}
    checkpoints = sorted({row["checkpoint"] for row in rows})
    by_checkpoint = {checkpoint: [i for i, row in enumerate(rows) if row["checkpoint"] == checkpoint] for checkpoint in checkpoints}
    candidates = [_candidates([raw[i] for i in by_checkpoint[checkpoint]], [core[i] for i in by_checkpoint[checkpoint]], checkpoint) for checkpoint in checkpoints]
    # Explicit all-DEFER soft-stage control is feasible only after the hard check.
    best = {"placement": placement, "status": "FEASIBLE", "mode": "all_defer", "thresholds": None, "metrics": hard_metrics, "control": control}
    best_key = (-hard_metrics["weighted_correct_episode_mass"], hard_metrics["error_episodes"], -1., ())
    for combination in product(*candidates):
        decisions, thresholds, simple = [None]*len(rows), {}, []
        for checkpoint, (key, threshold, values) in zip(checkpoints, combination):
            thresholds.update(threshold)
            simple.extend(key[1:])
            for i, value in zip(by_checkpoint[checkpoint], values):
                decisions[i] = value
        metrics = score(rows, labels, metadata, decisions)
        if not feasible(metrics):
            continue
        key = (-metrics["weighted_correct_episode_mass"], metrics["error_episodes"], sum(simple), tuple(simple))
        if key < best_key:
            best = {"placement": placement, "status": "FEASIBLE", "mode": "confidence", "thresholds": thresholds, "metrics": metrics, "control": control}
            best_key = key
    best["unique_candidate_vectors_per_checkpoint"] = {checkpoint: len(values) for checkpoint, values in zip(checkpoints, candidates)}
    return best


def predict(raw_record, core_decision, checkpoint, operating_point):
    """Evaluator wrapper; INFEASIBLE remains labeled and uses the explicit
    fixed block-only control, never a claimed feasible automatic replacement.
    """
    thresholds = operating_point.get("thresholds") if operating_point.get("mode") == "confidence" else None
    result = apply(raw_record, core_decision, checkpoint, thresholds)
    result.update({"cal_status": operating_point["status"], "placement": operating_point["placement"]})
    return result


def canonical_hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
