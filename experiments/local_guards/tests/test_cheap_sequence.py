import copy
import hashlib
import math
import sys

import pytest

from cascade_guard.cheap_sequence import (
    BLOCKS, POINTS, QUESTION_KEYS, STAGES, actual_references, build_records,
    feature_schema, inference_hash, join_checkpoints, main_population,
    numeric_features, validate_scores, vector,
)


def prefix(stage, seq, episode="example"):
    point = POINTS[stage]
    pid = hashlib.sha256(f"{episode}:{point}:{seq}".encode()).hexdigest()[:24]
    return {"prefix_id": pid, "episode_id": episode, "control_point": point,
            "cut_seq": seq, "max_input_seq": seq - 1, "state": {"fact": stage},
            "questions": {q: {"true": "yes", "false": "no"} for q in QUESTION_KEYS},
            "ambiguity": False, "already_harmful": False}


def score(row, probability=.2, cache=False):
    metadata = {"model": "SecJev-0.8B", "base_repo": "Qwen/Qwen3.5-0.8B-Base",
                "model_archive_sha256": "weights", "base_weights_sha256": "base",
                "base_revision": "revision", "scorer_sha256": "source", "format_version": "test"}
    return {"prefix_id": row["prefix_id"], "ablation": "plus_rationale",
            "model_metadata": metadata, "input_hash": inference_hash(row, metadata),
            "probabilities": {q: probability for q in QUESTION_KEYS}, "cache_hit": cache,
            "model_compute_ms": None if cache else 10.0,
            "reused_reference_compute_ms": 10.0 if cache else None,
            "latency_ms": .001 if cache else 12.0,
            "timing_ms": {"total": .001 if cache else 12.0},
            "memory": {"process_peak_rss_bytes": 100}}


def example():
    rows = [prefix(i, 5 + 3 * i) for i in range(4)]
    scores = [score(r, (i + 1) / 10) for i, r in enumerate(rows)]
    return rows, scores


def test_feature_schema_counts_and_unique_keys():
    schema = feature_schema()
    assert {k: len(v) for k, v in schema.items()} == {
        "J_cur": 4, "J_seq": 16, "J_agg": 20, "J_dynamic": 48, "J_prior": 12}
    assert all(len(keys) == len(set(keys)) for keys in schema.values())
    assert all(not any(banned in key for banned in ("episode", "prefix_id", "cut_seq", "label", "future"))
               for keys in schema.values() for key in keys)


def test_numeric_features_derived_from_fixed_semantic_positions():
    v = [[i / 10] * 4 for i in range(4)]
    f = numeric_features(v, "J_dynamic")
    q = QUESTION_KEYS[0]
    assert f[f"checkpoint.create_transfer.{q}"] == .3
    assert f[f"delta.invoice_agent_to_fraud_agent.{q}"] == .1
    assert f[f"delta.invoice_agent_to_create_transfer.{q}"] == .3
    assert f[f"aggregate.mean.{q}"] == pytest.approx(.15)
    assert f[f"aggregate.std.{q}"] == pytest.approx(math.sqrt(.0125))
    assert all(isinstance(x, float) and math.isfinite(x) for x in f.values())


@pytest.mark.parametrize("bad", [None, {}, {"unknown": True}, {"status": "UNKNOWN"}, {"error": "bad"},
    {"probabilities": {q: float("nan") for q in QUESTION_KEYS}},
    {"probabilities": {q: 1.1 for q in QUESTION_KEYS}}])
def test_invalid_source_is_unknown(bad):
    assert vector(bad) is None


def test_unknown_never_invents_probability_or_missing_value():
    rows, scores = example()
    scores[1]["unknown"] = True
    records = build_records([rows[-1]], rows, {s["prefix_id"]: s for s in scores}, actual_references(scores))
    current = next(r for r in records if r["block"] == "J_cur")
    sequence = next(r for r in records if r["block"] == "J_seq")
    assert current["status"] == "OK" and current["scalar_risk"] == .4
    assert sequence["status"] == "UNKNOWN" and sequence["scalar_risk"] is None and sequence["features"] == {}
    assert sequence["provenance"]["checkpoint_masks"]["fraud_agent"] == {"absent": False, "failed": True}
    rows.pop(1)
    absent = build_records([rows[-1]], rows, {s["prefix_id"]: s for s in scores}, actual_references(scores))[1]
    assert absent["provenance"]["checkpoint_masks"]["fraud_agent"] == {"absent": True, "failed": False}


def test_score_identity_and_scorer_mixing_rejected():
    rows, scores = example()
    assert len(validate_scores(rows, scores)) == 4
    changed = copy.deepcopy(scores)
    changed[0]["input_hash"] = "tampered"
    with pytest.raises(ValueError, match="input hash"):
        validate_scores(rows, changed)
    changed = copy.deepcopy(scores)
    changed[0]["model_metadata"]["base_revision"] = "different"
    changed[0]["input_hash"] = inference_hash(rows[0], changed[0]["model_metadata"])
    with pytest.raises(ValueError, match="Mixed"):
        validate_scores(rows, changed)


def test_serialization_order_is_part_of_cached_identity():
    row = prefix(0, 5)
    row["state"] = {"a": 1, "b": 2}
    s = score(row)
    row["state"] = {"b": 2, "a": 1}
    with pytest.raises(ValueError, match="input hash"):
        validate_scores([row], [s])


def test_join_uses_semantic_order_and_rejects_reversed_chronology():
    rows, _ = example()
    assert join_checkpoints(rows[-1], list(reversed(rows))) == rows
    rows[1] = prefix(1, 4)
    with pytest.raises(ValueError, match="chronological"):
        join_checkpoints(rows[-1], rows)


def test_future_and_other_episode_do_not_enter_features():
    rows, scores = example()
    mapping = {s["prefix_id"]: s for s in scores}
    base = build_records([rows[-1]], rows, mapping, actual_references(scores))
    contaminated = rows + [prefix(1, 99), prefix(0, 2, "other")]
    got = build_records([rows[-1]], contaminated, mapping, actual_references(scores))
    assert [r["features"] for r in got] == [r["features"] for r in base]
    assert [r["input_hash"] for r in got] == [r["input_hash"] for r in base]


def test_label_changes_cannot_enter_numeric_features():
    rows, scores = example()
    kwargs = dict(scoremap={s["prefix_id"]: s for s in scores}, references=actual_references(scores))
    base = build_records([rows[-1]], rows, **kwargs)
    for r in rows:
        r.update(label=1, baseline_harm_seq=999, group_id="secret", source_case="secret")
    got = build_records([rows[-1]], rows, **kwargs)
    assert [r["features"] for r in got] == [r["features"] for r in base]


def test_reconstructed_cost_uses_actual_reference_not_cache_latency():
    rows, scores = example()
    refs = actual_references(scores)
    for s in scores:
        s["cache_hit"] = True
        s["latency_ms"] = .001
        s["model_compute_ms"] = None
    # Keep independent copies of the actual source call records.
    refs = {s["input_hash"]: score(r, (i + 1) / 10) for i, (r, s) in enumerate(zip(rows, scores))}
    records = build_records([rows[-1]], rows, {s["prefix_id"]: s for s in scores}, refs)
    seq = records[1]
    assert seq["timing_ms"]["reconstructed_live_source_compute"] == 40
    assert seq["timing_ms"]["reconstructed_live_source_latency"] == 48
    assert seq["memory"]["source_peak_observed_bytes"]["process_peak_rss_bytes"] == 100
    assert seq["window_count"] == 4 and seq["provenance"]["source_cache_hits"] == 4


def test_population_uses_outcomes_and_checks_cached_flag_agreement():
    rows, _ = example()
    outcomes = [{"episode_id": "example", "legacy_ambiguous": False, "strict_harm_seq": 100}]
    assert main_population(rows, outcomes, expected_count=1) == [rows[-1]]
    outcomes[0]["strict_harm_seq"] = 1
    with pytest.raises(ValueError, match="disagreement"):
        main_population(rows, outcomes, expected_count=0)


def test_module_does_not_import_model_runtime():
    # Importing this module requires only stdlib and dataset, so no new runtime is loaded.
    import subprocess
    result = subprocess.run([sys.executable, "-c",
        "import cascade_guard.cheap_sequence,sys; assert 'torch' not in sys.modules; assert 'catboost' not in sys.modules"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
