"""Read-only P4 archive audit; evaluate the saved CatBoost fold models locally."""

from collections import Counter
import csv
from decimal import Decimal
from importlib.metadata import version
from itertools import combinations
import json
from pathlib import Path

import joblib
import numpy as np

from experiments.local_guards_completion import ml
from experiments.local_guards_archive_comparison.collector import digest
from experiments.payment_controls.study.archive import index, audit, SRC, EXP

HERE = Path(__file__).resolve().parent
MODELS = SRC / "ml-results"
REPAIRED = EXP / "local_guards_repaired_evaluation"


def read_json(path):
    return json.loads(path.read_text())


def verify(path, sha):
    if ml.digest(path) != sha:
        raise ValueError(f"Changed input: {path}")
    return path


def rerun_catboost(records, labels):
    summary = read_json(MODELS / "summary.json")
    folds = read_json(verify(MODELS / "folds.json", summary["folds_sha256"]))
    frozen = index(r for r in ml.read_rows(verify(MODELS / "predictions.jsonl.gz", summary["predictions_sha256"]))
                   if r["method"] == "catboost")
    assert folds["versions"] == {name: version(name) for name in folds["versions"]}
    values = {pid: ml.features(record) for pid, record in records.items()}
    hashes = {pid: ml.feature_hash(value) for pid, value in values.items()}
    assert all(hashes[pid] == frozen[pid]["feature_sha256"] for pid in records)
    models = {m["fold"]: m for m in summary["models"] if m["method"] == "catboost"}
    assert len(models) == len(folds["folds"]) == 5
    scores, exposure, partitions = {}, {}, []
    maximum_delta = 0.0
    for fold in folds["folds"]:
        number = fold["index"]
        ids = {name: set(fold[name]) for name in ("fit", "cal", "test")}
        groups = {name: {records[pid]["group_id"] for pid in pids} for name, pids in ids.items()}
        assert set.union(*ids.values()) == set(records)
        assert not any(ids[a] & ids[b] or groups[a] & groups[b] for a, b in combinations(ids, 2))
        assert all(groups[name] == set(fold["groups"][name]) for name in ids)
        frozen_model = models[number]
        # Only the bundled, receipt-verified artifacts are eligible for deserialization.
        assert frozen_model["file"] == f"catboost-fold{number}.joblib"
        bundle = joblib.load(verify(MODELS / frozen_model["file"], frozen_model["sha256"]))
        model, operating = bundle["model"], bundle["operating_point"]
        assert bundle["fold"] == number and bundle["method"] == "catboost"
        assert operating == frozen_model["operating_point"] and model["available"]
        fit = {pid for pid in ids["fit"] if labels[pid]["action_label"] in ml.CLASSES}
        assert fit == set(model["resolved_fit_prefixes"])
        fit_hashes = {hashes[pid] for pid in fit}
        cal_hashes = {hashes[pid] for pid in ids["cal"]}
        assert not (ids["test"] & scores.keys())
        assert sorted(ids["test"]) == fold["test"]
        probabilities = ml.predict(model, [records[pid] for pid in fold["test"]], values)
        for pid, probability in zip(fold["test"], probabilities, strict=True):
            prior, record = frozen[pid], records[pid]
            assert (number, record["group_id"], record["episode_id"]) == (
                prior["fold"], prior["group_id"], prior["episode_id"])
            delta = max(abs(probability[key] - prior["probabilities"][key]) for key in ml.CLASSES)
            maximum_delta = max(maximum_delta, delta)
            argmax = ml.decide(probability, dict(ALLOW=0, BLOCK=0))
            calibrated = ml.decide(probability, operating["thresholds"]) if operating["status"] == "FEASIBLE" else "UNKNOWN"
            in_fit, in_cal = hashes[pid] in fit_hashes, hashes[pid] in cal_hashes
            assert delta <= 1e-10 and (calibrated, argmax, in_fit) == (
                prior["decision"], prior["argmax_decision"], prior["seen_projection_in_fit"])
            exposure[pid] = "fit+cal" if in_fit and in_cal else "fit" if in_fit else "cal" if in_cal else "neither"
            scores[pid] = dict(catboost_calibrated=calibrated, catboost_argmax=argmax)
        partitions.append(dict(fold=number, counts={name: len(pids) for name, pids in ids.items()},
                               groups={name: len(value) for name, value in groups.items()},
                               fit_labels=dict(Counter(labels[pid]["action_label"] for pid in fit)),
                               calibration=operating["status"], thresholds=operating["thresholds"]))
    assert set(scores) == set(records)
    return scores, exposure, dict(folds=partitions, max_absolute_probability_delta=maximum_delta)


def metrics(labels, decisions, ids, axis):
    return ml.metrics([labels[pid][axis] for pid in ids], [decisions[pid] for pid in ids])


def audit_report():
    summary = read_json(MODELS / "summary.json")
    labels = index(ml.read_rows(verify(SRC / "labels.jsonl", summary["labels_sha256"])))
    records = index(ml.read_rows(verify(SRC / "records.jsonl.gz", summary["records_sha256"])))
    assert records.keys() == labels.keys() and len({r["episode_id"] for r in records.values()}) == 542
    assert len({r["group_id"] for r in records.values()}) == 58
    assert all(r["native"]["checkpoint"] == r["observation"]["checkpoint"] == "P4" for r in records.values())
    verify(SRC / "results/predictions.jsonl.gz",
           read_json(SRC / "results/prediction-freeze.json")["predictions_sha256"])
    saved_path = REPAIRED / "results/saved-deepseek.jsonl.gz"
    release = read_json(REPAIRED / "release-manifest.json")
    saved_path = verify(saved_path, release["files"]["results/saved-deepseek.jsonl.gz"])
    saved = index(ml.read_rows(saved_path))
    queries = index(r for r in ml.read_rows(SRC / "results/predictions.jsonl.gz")
                    if (r["dataset"], r["mode"], r["method"]) == ("p4", "common", "current"))
    assert all((q["query_id"], q["event_seq"], q["input_sha256"]) == (
        saved[pid]["query_id"], records[pid]["native"]["event_seq"], digest(records[pid]["observation"]))
        for pid, q in queries.items())
    assert len({row["query_id"] for row in saved.values()}) == 542

    archived = list(audit())
    with (EXP / "payment_controls/study/archive_decisions.csv").open() as stream:
        assert archived == list(csv.DictReader(stream))
    scores, exposure, receipt = rerun_catboost(records, labels)
    assert all(r["catboost"] == scores[r["prefix"]]["catboost_calibrated"] for r in archived)
    archived = {r["prefix"]: r for r in archived}
    vectors = {name: {pid: r[field] for pid, r in archived.items()}
               for name, field in (("rules_historical", "original"), ("rules_delegated_tax", "delegated_tax"),
                                    ("deepseek_saved", "deepseek"))}
    vectors.update({name: {pid: score[name] for pid, score in scores.items()}
                    for name in next(iter(scores.values()))})
    axes = ("action_label", "without_tax_label", "substantive_label", "process_label")
    changes = {}
    for left, right in (("rules_historical", "rules_delegated_tax"),
                        ("rules_delegated_tax", "catboost_calibrated"),
                        ("rules_delegated_tax", "catboost_argmax"),
                        ("rules_delegated_tax", "deepseek_saved"),
                        ("catboost_calibrated", "deepseek_saved"),
                        ("catboost_argmax", "deepseek_saved")):
        transitions = {}
        for axis in axes:
            transitions[axis] = dict(Counter(
                f"{labels[pid][axis]}: {vectors[left][pid]} -> {vectors[right][pid]}"
                for pid in records if vectors[left][pid] != vectors[right][pid]))
        changes[f"{left} -> {right}"] = transitions

    reason_flips = {}
    for target in ("ALLOW", "BLOCK", "INSUFFICIENT"):
        selected = [r for pid, r in archived.items() if labels[pid]["substantive_label"] == target
                    and r["original"] != r["delegated_tax"]]
        reason_flips[target] = dict(
            count=len(selected), transitions=dict(Counter(f'{r["original"]} -> {r["delegated_tax"]}' for r in selected)),
            revised_reasons=dict(Counter(reason for r in selected for reason in r["revised_reasons"].split("|"))),
            violated_requirements=dict(Counter(reason for r in selected for reason in r["recorded_violations"].split("|") if reason)),
            revised_label_on_allow=dict(Counter(labels[r["prefix"]]["without_tax_label"] for r in selected if r["delegated_tax"] == "ALLOW")))
    stats = read_json(SRC / "results-summary.json")["p4"]
    benchmark = read_json(MODELS / "benchmark-receipt.json")
    rule_benchmark = read_json(SRC / "results/benchmark-receipt.json")
    verify(SRC / "results/benchmark.jsonl.gz", rule_benchmark["benchmark_sha256"])
    verify(MODELS / "benchmark.jsonl.gz", benchmark["benchmark_sha256"])
    timing = {}
    labels_for_timing = ("rules_historical", "catboost_calibrated", "catboost_argmax", "deepseek_saved")
    native_tax_keys = {"tax_configuration", "tax_category", "tax_jurisdiction"}
    for name, archived_method in zip(labels_for_timing, ("completion/current", "oof/catboost/calibrated",
                                                        "oof/catboost/argmax_diagnostic", "deepseek"), strict=True):
        routed = stats["cascades"][archived_method]["llm" if name == "deepseek_saved" else "local"]
        timing[name] = {key: routed[key] for key in ("latency_n", "p50_ms", "p95_ms")}
    timing["deepseek_saved_full542_ms"] = dict(zip(("p50_ms", "p95_ms"), map(float,
        np.quantile([row["decision_ms"] for row in saved.values()], [.50, .95])), strict=True))
    timing["deepseek_saved_full542_ms"]["timing_scope_counts"] = dict(Counter(row["timing_scope"] for row in saved.values()))
    audited_inputs = (
        SRC / "labels.jsonl", SRC / "records.jsonl.gz", SRC / "results/predictions.jsonl.gz",
        SRC / "results-summary.json", saved_path, MODELS / "folds.json", MODELS / "summary.json",
        MODELS / "predictions.jsonl.gz", SRC / "results/benchmark.jsonl.gz", MODELS / "benchmark.jsonl.gz",
        EXP / "payment_controls/study/archive_decisions.csv",
        *(MODELS / f"catboost-fold{number}.joblib" for number in range(5)),
    )
    return dict(n=len(records), episodes=542, scenario_groups=58, new_api_calls=0, new_fits=0,
                input_sha256={str(path.relative_to(EXP.parent)): ml.digest(path) for path in audited_inputs},
                historical_deepseek_charge_usd=str(sum((Decimal(str(row["charge_usd"])) for row in saved.values()), Decimal(0))),
                saved_artifact_and_fold_verification=receipt, paired_historical_latency=timing,
                new_native_p4_projection=dict(fully_observed_tax_inputs=sum(
                    native_tax_keys <= (r["native"]["observation"]["facts"].keys() | r["observation"]["facts"].keys())
                    for r in records.values()), n=len(records)),
                projection_exposure=dict(Counter(exposure.values())),
                exposure_metrics={bucket: {name: {axis: metrics(labels, values, sorted(pid for pid, v in exposure.items() if v == bucket), axis)
                                                   for axis in axes}
                                           for name, values in vectors.items()} for bucket in sorted(set(exposure.values()))},
                methods={name: {axis: metrics(labels, values, sorted(records), axis) for axis in axes}
                         for name, values in vectors.items()},
                rule_change_reasons=reason_flips, disagreements=changes)


if __name__ == "__main__":
    print(json.dumps(audit_report(), sort_keys=True, indent=2))
