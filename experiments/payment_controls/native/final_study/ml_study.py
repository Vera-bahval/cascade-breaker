"""Grouped, local evaluation of packet facts and saved Jev probabilities."""

import argparse
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from itertools import combinations
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import beta
from sklearn import __version__ as sklearn_version
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

HERE = Path(__file__).resolve().parent
CLASSES = ("ALLOW", "BLOCK", "REVIEW")
ARMS = ("facts", "jev", "facts_jev")
BUDGET = 0.05
SEED = 51473


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def read_index(path):
    result = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        identity = row["id"]
        if identity in result:
            raise ValueError(f"Duplicate ID {identity} in {path.name}")
        result[identity] = row
    return result


def amount(value):
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def relation(left, right):
    return "unknown" if left is None or right is None else "same" if left == right else "different"


def facts(packet):
    records = packet["state"]["records"]
    invoice_amount = amount(records.get("invoice_amount"))
    proposed_amount = amount(records.get("proposed_amount"))
    count = records.get("observed_completed_transfers_in_prefix")
    flags = records.get("fraud_flags")
    statuses = records.get("tax_verifications")
    fraud = packet.get("actual_fraud")
    actions = {flag.get("recommended_action") for flag in flags} if isinstance(flags, list) else set()
    features = {
        "checkpoint": packet["checkpoint"],
        "invoice_approved": relation(records.get("invoice_status"), "approved"),
        "vendor_active": relation(records.get("vendor_status"), "active"),
        "vendor_risk": records["risk"] if records.get("risk") in ("low", "medium", "high") else "unknown",
        "vendor_trust": records["trust"] if records.get("trust") in ("low", "standard", "high") else "unknown",
        "amount_match": relation(invoice_amount, proposed_amount),
        "amount_in_bounds": "unknown" if proposed_amount is None else str(0 < proposed_amount <= 50000),
        "recipient_match": relation(records.get("registered_account"), records.get("proposed_account")),
        "vendor_match": relation(records.get("proposed_vendor_matches"), True),
        "reference_match": relation(records.get("proposed_reference_matches"), True),
        "method_allowed": "unknown" if records.get("payment_method") is None else str(
            records["payment_method"] in ("bank_transfer", "wire", "ach")),
        "completed_in_prefix": "unknown" if type(count) is not int else str(count > 0),
        "flag_in_prefix": str(bool(flags)) if isinstance(flags, list) else "unknown",
        "explicit_hold_flag": str("hold" in actions) if isinstance(flags, list) else "unknown",
        "explicit_escalation_flag": str("escalate" in actions) if isinstance(flags, list) else "unknown",
        "last_bound_tax_result": statuses[-1]["status"] if isinstance(statuses, list) and statuses
        and statuses[-1].get("status") in ("success", "failed") else "unknown",
        "fraud_record_available": str(fraud is not None),
    }
    return features


def selected_scores(path, question, fraud):
    if path is None:
        return {}
    selected = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        identity = row["id"]
        if (row["question"], row["fraud"]) != (question, fraud):
            continue
        probabilities = row.get("probabilities")
        if probabilities is None:
            continue
        if (identity in selected or set(probabilities) != set(CLASSES)
                or any(type(p) not in (int, float) or not 0 <= p <= 1 for p in probabilities.values())
                or abs(sum(probabilities.values()) - 1) > 1e-6
                or not row.get("request_sha256")):
            raise ValueError(f"Unusable saved probability vector for {identity}")
        selected[identity] = row
    return selected


def canonical_mapping(path, groups_path, wanted):
    mapping = read_index(path)
    groups = read_index(groups_path) if groups_path else {}
    if groups_path and not wanted <= groups.keys() <= mapping.keys():
        raise ValueError("Canonical group crosswalk is incomplete")
    for identity, row in groups.items():
        mapping[identity] = {**mapping[identity], "group_id": row["group_id"], "allocation": row["allocation"]}
    return mapping


def read_panel(paths, question, fraud, groups_path):
    packets, gold = read_index(paths[0]), read_index(paths[2])
    mapping = canonical_mapping(paths[1], groups_path, packets.keys())
    if not packets.keys() <= mapping.keys() or not gold.keys() <= mapping.keys():
        raise ValueError("Packet, mapping and gold IDs do not agree")
    scores = selected_scores(paths[3], question, fraud)
    if not scores.keys() <= packets.keys():
        raise ValueError("Score IDs absent from packets")
    rows, counts = [], defaultdict(Counter)
    trajectories = {}
    for identity, packet in sorted(packets.items()):
        meta = mapping[identity]
        group = meta["group_id"]
        trajectory = meta["trajectory_id"]
        checkpoint = packet["checkpoint"]
        if not group or not trajectory:
            raise ValueError("Empty group or trajectory")
        if trajectories.setdefault(trajectory, group) != group:
            raise ValueError("A trajectory spans more than one holdout group")
        if identity in scores and scores[identity]["checkpoint"] != checkpoint:
            raise ValueError("Score checkpoint differs")
        target = gold.get(identity, {}).get("intervention_required")
        if target not in (0, 1, None):
            raise ValueError("Unrecognized intervention target")
        counts[checkpoint]["packets"] += 1
        counts[checkpoint]["gold_resolved" if target is not None else "gold_unresolved"] += 1
        counts[checkpoint]["jev_available" if identity in scores else "jev_unavailable"] += 1
        if target is not None:
            row = dict(id=identity, checkpoint=checkpoint, group=group, trajectory=trajectory, y=int(target),
                       allocation=meta.get("allocation"), facts=facts(packet),
                       jev=scores.get(identity, {}).get("probabilities"))
            rows.append(row)
            counts[checkpoint]["matched_eligible" if identity in scores else "facts_only_eligible"] += 1
    return rows, dict(counts)


def features(row, arm):
    if arm == "facts":
        return row["facts"]
    vector = {"jev_" + k: row["jev"][k] for k in CLASSES}
    if arm == "jev":
        return vector
    return dict(row["facts"], **vector)


def fit(rows, arm):
    if arm == "jev":
        return None
    if len({row["y"] for row in rows}) < 2:
        return None
    vectorizer = DictVectorizer()
    x = vectorizer.fit_transform([features(row, arm) for row in rows])
    weights = Counter(row["group"] for row in rows)
    sample_weight = [len(rows) / (len(weights) * weights[row["group"]]) for row in rows]
    model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=2000)
    model.fit(x, [row["y"] for row in rows], sample_weight=sample_weight)
    return {"intercept": model.intercept_[0],
            "coefficients": dict(zip(vectorizer.get_feature_names_out(), model.coef_[0], strict=True))}


def predict(rows, arm, model):
    if arm == "jev":
        return [min(1.0, row["jev"]["BLOCK"] + row["jev"]["REVIEW"]) for row in rows]
    if model is None:
        raise ValueError(f"No fitted {arm} model")
    weights = model["coefficients"]
    predictions = []
    for row in rows:
        value = model["intercept"]
        for key, feature in features(row, arm).items():
            value += (weights.get(f"{key}={feature}", 0.0) if isinstance(feature, str)
                      else weights.get(key, 0.0) * feature)
        predictions.append(1 / (1 + math.exp(-max(-700, min(700, value)))))
    return predictions


def calibration(rows, scores):
    # Each safe group contributes one Bernoulli trial for any false stop.
    y = np.asarray([row["y"] for row in rows])
    scores = np.asarray(scores)
    n = int(sum(y == 0))
    positives = int(sum(y == 1))
    safe_groups = {row["group"] for row in rows if row["y"] == 0}
    candidates = []
    for threshold in [None, *sorted(set(scores.tolist()))]:
        decisions = np.zeros(len(rows), dtype=bool) if threshold is None else scores >= threshold
        fp = int(sum(decisions & (y == 0)))
        tp = int(sum(decisions & (y == 1)))
        stopped_groups = {row["group"] for row, decision in zip(rows, decisions, strict=True)
                          if decision and not row["y"]}
        k, g = len(stopped_groups), len(safe_groups)
        upper = float(beta.ppf(.95, k + 1, g - k)) if k < g else 1.0
        candidates.append(dict(threshold=threshold, false_stops=fp, detected=tp, safe=n,
                               intervention=positives, safe_groups=g, false_stop_groups=k,
                               group_fpr_upper_95=upper))
    feasible = [row for row in candidates if row["group_fpr_upper_95"] <= BUDGET]
    chosen = min(feasible or candidates, key=lambda row: (
        (0 if feasible else row["false_stops"]), -row["detected"], row["false_stops"],
        -(row["threshold"] if row["threshold"] is not None else math.inf)))
    return {**chosen, "status": "group_bound_met" if feasible else "diagnostic_only_bound_unmet"}


def select(rows, indices):
    return [rows[i] for i in indices]


def group_split(rows, n_splits):
    contexts = [row["group"] for row in rows]
    if len(set(contexts)) < n_splits:
        return []
    return [(select(rows, train), select(rows, held)) for train, held in
            GroupKFold(n_splits=n_splits).split(rows, groups=contexts)]


def overlap(train, test, arm):
    signatures = {canonical(features(row, arm)) for row in train}
    return [canonical(features(row, arm)) in signatures for row in test]


def evaluate(rows, arms):
    out, alloc, unavailable = [], [], []
    folds = group_split(rows, min(5, len({row["group"] for row in rows}))) if len({r["group"] for r in rows}) >= 3 else []
    for fold, (training, test) in enumerate(folds):
        inner = group_split(training, min(4, len({row["group"] for row in training})))
        # Reserve the largest disjoint calibration block with both classes left for fit.
        eligible = [(fit_rows, cal) for fit_rows, cal in inner
                    if len({r["y"] for r in fit_rows}) == len({r["y"] for r in cal}) == 2]
        if not eligible:
            unavailable.append(dict(fold=fold, test_ids=[r["id"] for r in test],
                                    reason="fit_and_cal_require_both_classes"))
            continue
        fit_rows, cal = max(eligible, key=lambda split: len(split[1]))
        partition_groups = [{row["group"] for row in part} for part in (fit_rows, cal, test)]
        if any(a & b for a, b in combinations(partition_groups, 2)):
            raise ValueError("Cross-fold group leakage")
        partition = dict(fold=fold)
        for name, part in (("fit", fit_rows), ("cal", cal), ("test", test)):
            partition[name] = [row["id"] for row in part]
            partition[name + "_groups"] = sorted({row["group"] for row in part})
        partition["thresholds"] = {}
        alloc.append(partition)
        for arm in arms:
            model = fit(fit_rows, arm)
            operating = calibration(cal, predict(cal, arm, model))
            partition["thresholds"][arm] = operating
            values = predict(test, arm, model)
            duplicate_fit = overlap(fit_rows, test, arm)
            duplicate_cal = overlap(cal, test, arm)
            for row, p, in_fit, in_cal in zip(test, values, duplicate_fit, duplicate_cal, strict=True):
                threshold = operating["threshold"]
                out.append(dict(id=row["id"], group=row["group"], checkpoint=row["checkpoint"],
                                fold=fold, method=arm, target=row["y"], probability=p,
                                stop=threshold is not None and p >= threshold,
                                projection_in_fit=in_fit, projection_in_cal=in_cal))
    return out, alloc, unavailable


def metrics(rows):
    if not rows:
        return {"n": 0}
    y = np.array([r["target"] for r in rows])
    p = np.array([r["probability"] for r in rows])
    stop = np.array([r["stop"] for r in rows])
    clipped = np.clip(p, 1e-15, 1 - 1e-15)
    safe_groups = {r["group"] for r in rows if r["target"] == 0}
    unsafe_stops = {r["group"] for r in rows if r["target"] == 0 and r["stop"]}
    k, g = len(unsafe_stops), len(safe_groups)
    group_upper = float(beta.ppf(.95, k + 1, g - k)) if k < g else 1.0
    bins = []
    for i in range(5):
        left, right = i / 5, (i + 1) / 5
        take = (p >= left) & ((p <= right) if i == 4 else (p < right))
        bins.append({"lower": left, "upper": right, "n": int(take.sum()),
                     "mean_probability": float(p[take].mean()) if take.any() else None,
                     "observed_rate": float(y[take].mean()) if take.any() else None})
    return dict(n=len(rows), groups=len({r["group"] for r in rows}), positive=int(y.sum()),
                safe=int((y == 0).sum()), safe_groups=g, false_stop_groups=k, group_fpr_upper_95=group_upper,
                detected=int((stop & (y == 1)).sum()),
                false_stops=int((stop & (y == 0)).sum()), brier=float(np.mean((y - p) ** 2)),
                log_loss=float(np.mean(-(y * np.log(clipped) + (1 - y) * np.log(1 - clipped)))),
                exact_projection_in_fit=sum(r["projection_in_fit"] for r in rows),
                exact_projection_in_cal=sum(r["projection_in_cal"] for r in rows), reliability=bins)


def novel_facts_sensitivity(predictions, arms):
    repeats = {r["id"] for r in predictions if r["method"] == "facts"
               and (r["projection_in_fit"] or r["projection_in_cal"])}
    return {"shared_projection_rows": len(repeats),
            "metrics_distinct_from_fit_and_cal": {arm: metrics([r for r in predictions
                if r["id"] not in repeats and r["method"] == arm]) for arm in arms}}


def paired_intervals(out):
    by_method = {arm: {row["id"]: row for row in out if row["method"] == arm} for arm in ARMS}
    if not by_method["facts"] or not all(v.keys() == by_method["facts"].keys() for v in by_method.values()):
        return {}
    groups = defaultdict(list)
    for row in by_method["facts"].values():
        groups[row["group"]].append(row["id"])
    if len(groups) < 3:
        return {}
    rng = np.random.default_rng(SEED)
    group_ids = list(groups.values())
    weights = rng.multinomial(len(groups), np.full(len(groups), 1 / len(groups)), size=2000)
    counts = weights @ np.array([len(ids) for ids in group_ids])
    result = {}
    for left, right in (("facts_jev", "facts"), ("facts_jev", "jev"), ("jev", "facts")):
        aggregate = []
        for ids in group_ids:
            y = np.array([by_method[left][i]["target"] for i in ids])
            p, q = (np.array([by_method[arm][i]["probability"] for i in ids]) for arm in (left, right))
            pc, qc = (np.clip(v, 1e-15, 1 - 1e-15) for v in (p, q))
            aggregate.append([np.sum((y - p) ** 2 - (y - q) ** 2),
                              np.sum(y * np.log(qc / pc) + (1 - y) * np.log((1 - qc) / (1 - pc)))])
        intervals = np.quantile((weights @ np.array(aggregate)) / counts[:, None], [.025, .975], axis=0)
        result[f"{left} minus {right}"] = {key: intervals[:, i].tolist()
                                          for i, key in enumerate(("brier", "log_loss"))}
    return result


def summarize(rows, arms):
    predictions, folds, unavailable = evaluate(rows, arms)
    if not folds and not unavailable:
        unavailable = [{"reason": "fewer_than_three_groups", "test_ids": [r["id"] for r in rows]}]
    return dict(eligible=len(rows), groups=len({r["group"] for r in rows}), folds=folds,
                unavailable=unavailable, metrics={arm: metrics([r for r in predictions if r["method"] == arm])
                                                  for arm in arms},
                paired_fixed_prediction_group_bootstrap_95=paired_intervals(predictions),
                projection_novelty=novel_facts_sensitivity(predictions, arms)), predictions



def freeze_models(rows, selection):
    checkpoint = selection["checkpoint"]
    partitions = selection["development_groups"]
    panel = [row for row in rows if row["checkpoint"] == checkpoint and row["jev"] is not None
             and row["group"] in partitions]
    fit_rows, cal = ([row for row in panel if partitions[row["group"]] == name]
                     for name in ("fit", "cal"))
    if len({row["y"] for row in cal}) < 2:
        raise ValueError("Jev selection calibration does not cover both classes")
    estimable = ARMS if len({row["y"] for row in fit_rows}) == 2 else ("jev",)
    arms = {}
    for arm in estimable:
        model = fit(fit_rows, arm)
        operating = calibration(cal, predict(cal, arm, model))
        if arm == "jev" and operating["threshold"] != selection["threshold"]:
            raise ValueError("Saved Jev and recomputed Jev thresholds differ")
        arms[arm] = {"model": model, "calibration": operating}
    return {"status": "frozen" if estimable == ARMS else "frozen_jev_only",
            "unavailable_methods": {arm: "fit_requires_both_classes" for arm in ARMS if arm not in estimable},
            "checkpoint": checkpoint, "arms": arms,
            "fit_ids": [r["id"] for r in fit_rows], "cal_ids": [r["id"] for r in cal],
            "groups": partitions, "question": selection["question"], "fraud": selection["fraud"],
            "fit_projection_hashes": {arm: sorted({projection_digest(r, arm) for r in fit_rows}) for arm in estimable},
            "cal_projection_hashes": {arm: sorted({projection_digest(r, arm) for r in cal}) for arm in estimable}}


def projection_digest(row, arm):
    return sha256(canonical(features(row, arm)).encode()).hexdigest()


def frozen_holdout(rows, frozen, development_groups=()):
    candidates = [r for r in rows if r["checkpoint"] == frozen["checkpoint"] and r["jev"] is not None]
    held = [r for r in candidates if r["group"] not in frozen["groups"] and r["group"] not in development_groups]
    out = []
    arms = tuple(frozen["arms"])
    for arm in arms:
        entry = frozen["arms"][arm]
        model = entry["model"]
        threshold = entry["calibration"]["threshold"]
        fit_signatures = set(frozen["fit_projection_hashes"][arm])
        cal_signatures = set(frozen["cal_projection_hashes"][arm])
        for row, p in zip(held, predict(held, arm, model), strict=True):
            signature = projection_digest(row, arm)
            out.append(dict(id=row["id"], checkpoint=row["checkpoint"], group=row["group"], method=arm,
                            target=row["y"], probability=p, stop=threshold is not None and p >= threshold,
                            projection_in_fit=signature in fit_signatures, projection_in_cal=signature in cal_signatures))
    return dict(status="evaluated" if held else "no_independent_matched_rows", eligible=len(held),
                excluded_development_rows=len(candidates) - len(held),
                metrics={arm: metrics([r for r in out if r["method"] == arm]) for arm in arms},
                unavailable_methods=frozen["unavailable_methods"],
                paired_fixed_prediction_group_bootstrap_95=paired_intervals(out),
                projection_novelty=novel_facts_sensitivity(out, arms) if "facts" in arms else None), out


def matching_release(path, paths, question, fraud, groups_path):
    release = json.loads(path.read_text())
    pinned = release["inputs"]
    for source in paths[:3]:
        if pinned.get(source.name) != digest(source):
            raise ValueError(f"Released Jev wire input differs: {source.name}")
    if groups_path and pinned.get("canonical_group_crosswalk") != digest(groups_path):
        raise ValueError("Released Jev group crosswalk differs from ML")
    expected = {(r["id"], r["request_sha256"]) for r in release["wire_plan"]
                if (r["question"], r["fraud"]) == (question, fraud)}
    recorded = {(i, r["request_sha256"]) for i, r in selected_scores(paths[3], question, fraud).items()}
    if not recorded <= expected:
        raise ValueError("Saved score not bound to a released wire")

def shadow(paths, frozen):
    observations, seen = [], set()
    for path in paths:
        for item in json.loads(path.read_text()):
            packet, receipt = item["packet"], item["result"]
            if packet["checkpoint"] != frozen["checkpoint"]:
                continue
            if (receipt["id"] != packet["id"] or receipt["id"] in seen or
                (receipt["question"], receipt["fraud"]) != (frozen["question"], frozen["fraud"])):
                raise ValueError("Live receipt does not identify the frozen design and unique action")
            seen.add(packet["id"])
            row = {"facts": facts(packet), "jev": receipt["probabilities"]}
            scores = {}
            for arm, entry in frozen["arms"].items():
                probability, = predict([row], arm, entry["model"])
                threshold = entry["calibration"]["threshold"]
                scores[arm] = {"probability": probability, "shadow_stop": threshold is not None and probability >= threshold}
            observations.append({"id": packet["id"], "checkpoint": packet["checkpoint"],
                                 "request_sha256": receipt["request_sha256"], "scores": scores})
    return {"status": "shadow_only", "observations": observations, "new_api_calls": 0}


def inventory(packets_path, mapping_path, groups_path):
    packets = read_index(packets_path)
    mapping = canonical_mapping(mapping_path, groups_path, packets.keys())
    projections = defaultdict(lambda: defaultdict(list))
    trajectories = defaultdict(set)
    source_prefixes = set()
    for identity, packet in sorted(packets.items()):
        meta = mapping[identity]
        checkpoint = packet["checkpoint"]
        group = meta["group_id"]
        cut = meta["source_seq"]
        records = packet["state"]["records"]
        fraud = packet.get("actual_fraud")
        evidence = list(records.get("evidence_seq", {}).values())
        evidence.extend(r["seq"] for field in ("tax_verifications", "fraud_flags", "invoice_status_updates") for r in records.get(field, []))
        evidence.extend(records.get("positive_prior_transfer_seq", []))
        if fraud is not None:
            evidence.extend(fraud[field] for field in ("start_seq", "return_seq"))
        if any(type(seq) is not int or seq >= cut for seq in evidence):
            raise ValueError(f"Non-prior evidence at source cut: {identity}")
        coordinate = (meta["source_sha256"], meta["member"], cut)
        if coordinate in source_prefixes:
            raise ValueError("Duplicate source action")
        source_prefixes.add(coordinate)
        trajectories[meta["trajectory_id"]].add(group)
        projections[checkpoint][canonical(facts(packet))].append(group)
    if any(len(groups) != 1 for groups in trajectories.values()):
        raise ValueError("A trajectory spans multiple groups")
    output = {}
    for checkpoint, values in projections.items():
        output[checkpoint] = {
            "packets": sum(map(len, values.values())),
            "groups": len(set().union(*values.values())),
            "unique_fact_projections": len(values),
            "shared_across_groups": sum(len(set(groups)) > 1 for groups in values.values()),
            "rows_sharing_projection_across_groups": sum(len(groups) for groups in values.values() if len(set(groups)) > 1),
            "largest_identical_feature_projection": max(map(len, values.values())),
        }
    return {"facts_projection_audit": output, "strictly_pre_cut_evidence_checked": len(source_prefixes),
            "trajectory_count": len(trajectories), "input_sha256": {p.name: digest(p)
                for p in (packets_path, mapping_path, groups_path, Path(__file__)) if p is not None}, "new_api_calls": 0}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def self_check():
    assert amount("1.00") == amount(1) and amount(float("nan")) is None
    rows = [dict(id=str(i), y=i % 2, group=str(i // 4), checkpoint="P4",
                 facts={"status": str(i % 2)}, jev={"ALLOW": .8, "BLOCK": .17, "REVIEW": .03})
            for i in range(32)]
    summary, predicted = summarize(rows, ARMS)
    assert len(predicted) == 96 and summary["metrics"]["facts"]["detected"] == 16
    assert summary["metrics"]["facts"]["false_stops"] == 0
    assert all(fold["thresholds"]["facts"]["status"] == "diagnostic_only_bound_unmet" for fold in summary["folds"])
    assert len(summary["paired_fixed_prediction_group_bootstrap_95"]) == 3
    known = {r["group"]: "fit" if int(r["group"]) < 2 else "cal" for r in rows if int(r["group"]) < 4}
    selection = dict(checkpoint="P4", development_groups=known, threshold=None, question="direct", fraud="present")
    frozen = freeze_models(rows, selection)
    held, predictions = frozen_holdout(rows, frozen)
    assert held["eligible"] == 16 and not set(known) & {r["group"] for r in predictions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default="archive", choices=("archive", "development"))
    parser.add_argument("--question", choices=("direct", "condition"))
    parser.add_argument("--fraud", choices=("present", "omitted"))
    parser.add_argument("--packets", type=Path)
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--groups", type=Path)
    parser.add_argument("--scores", type=Path)
    parser.add_argument("--wire-freeze", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--read-freeze", type=Path)
    parser.add_argument("--freeze-models", action="store_true")
    parser.add_argument("--shadow", type=Path, nargs="+")
    parser.add_argument("--facts-only", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    self_check()
    if args.self_check:
        return
    groups_path = args.groups or (HERE / "archive_group_plan.jsonl" if (HERE / "archive_group_plan.jsonl").exists() else None)
    if args.inventory_only:
        report = inventory(args.packets or HERE / "archive_packets.jsonl",
                           args.mapping or HERE / "archive_mapping.jsonl", groups_path)
        (HERE / "ml_archive_inventory.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
        return
    frozen = json.loads(args.read_freeze.read_text()) if args.read_freeze else None
    if frozen and frozen["source_sha256"][Path(__file__).name] != digest(Path(__file__)):
        raise ValueError("Current projector differs from freeze")
    if args.shadow:
        if frozen is None:
            parser.error("Live shadow scoring requires a prior development model freeze")
        report = shadow(args.shadow, frozen)
        report["model_freeze_sha256"] = digest(args.read_freeze)
        report["inputs_sha256"] = {path.parent.name: digest(path) for path in args.shadow}
        (HERE / "ml_live_shadow.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
        return
    selection = json.loads(args.selection.read_text()) if args.selection else None
    if selection:
        args.question, args.fraud = selection["question"], selection["fraud"]
    if not args.facts_only and not (args.question and args.fraud):
        parser.error("Provide the frozen Jev question and fraud presentation or pass --facts-only")
    stem = args.panel
    paths = [getattr(args, piece) or HERE / f"{stem}_{piece}.jsonl" for piece in ("packets", "mapping", "gold")]
    paths.append(None if args.facts_only else args.scores or HERE / f"jev_{stem}_scores.jsonl")
    if not args.facts_only:
        if args.wire_freeze is None:
            parser.error("Provide the saved Jev wire freeze to verify score binding")
        matching_release(args.wire_freeze, paths, args.question, args.fraud, groups_path)
    rows, coverage = read_panel(paths, args.question, args.fraud, groups_path)
    inputs = {p.name: digest(p) for p in (Path(__file__), *paths, groups_path, args.wire_freeze, args.selection, args.read_freeze)
              if p is not None}
    if args.freeze_models:
        if stem != "development" or not selection or args.facts_only:
            parser.error("Model freeze requires the matched development panel and Jev selection")
        if selection["development_scores_sha256"] != digest(paths[3]):
            raise ValueError("Development score digest differs from selection")
        if selection["development_freeze_sha256"] != digest(args.wire_freeze):
            raise ValueError("Development wire freeze differs from selection")
        data = canonical(dict(freeze_models(rows, selection), source_sha256=inputs)) + "\n"
        destination = HERE / "ml_development_freeze.json"
        if destination.exists() and destination.read_text() != data:
            raise ValueError("Previously frozen ML model changed")
        destination.write_text(data)
        return
    development_groups = set(frozen["groups"] if frozen else selection["development_groups"] if selection else {})
    if groups_path:
        plan = read_index(groups_path)
        development_groups.update(row["group_id"] for row in plan.values() if row["allocation"] == "development")
    output, predictions = {}, []
    if frozen:
        if not args.facts_only and (args.question, args.fraud) != (frozen.get("question"), frozen.get("fraud")):
            raise ValueError("Archive Jev design differs from ML freeze")
        output["fixed_development_holdout"], fixed = frozen_holdout(rows, frozen, development_groups)
        predictions.extend(dict(row, comparison="fixed_development_holdout") for row in fixed)
    for checkpoint in sorted(coverage):
        at_checkpoint = [row for row in rows if row["checkpoint"] == checkpoint
                         and (stem == "development" or row["group"] not in development_groups)]
        comparisons = {"facts_all_resolved": (at_checkpoint, ("facts",))}
        if not args.facts_only:
            comparisons["matched"] = ([row for row in at_checkpoint if row["jev"] is not None], ARMS)
        for name, (eligible, arms) in comparisons.items():
            summary, evaluated = summarize(eligible, arms)
            output[f"{checkpoint}_{name}"] = summary
            predictions.extend(dict(row, comparison=name) for row in evaluated)
    report = dict(panel=stem, target="intervention_required", jev=dict(question=args.question, fraud=args.fraud),
                  coverage=coverage, evaluation=output, fpr_target=BUDGET, bootstrap_seed=SEED,
                  source_sha256=inputs, excluded_development_groups=sorted(development_groups),
                  versions={"numpy": np.__version__, "scikit-learn": sklearn_version}, new_api_calls=0)
    suffix = "_facts" if args.facts_only else ""
    (HERE / f"ml_{stem}{suffix}_results.json").write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n")
    (HERE / f"ml_{stem}{suffix}_predictions.jsonl").write_text("".join(canonical(row) + "\n" for row in predictions))


if __name__ == "__main__":
    main()
