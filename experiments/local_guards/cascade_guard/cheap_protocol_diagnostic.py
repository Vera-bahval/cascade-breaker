"""Posthoc protocol diagnosis: independently calibrated component OR frozen R1.

No fitting, inference, threshold selection, or selection by outer outcomes.
This does not replace the frozen primary experiment.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def wrap_independent(records, controls=None):
    controls = records if controls is None else controls
    rule = {(r["seed"], r["prefix_id"]): r for r in controls if r["arm"] == "R1"}
    if len(rule) != sum(r["arm"] == "R1" for r in controls):
        raise ValueError("Duplicate R1 control")
    output = []
    for row in records:
        if not row["arm"].endswith(":none"):
            continue
        key = row["seed"], row["prefix_id"]
        if key not in rule:
            raise ValueError("Missing exact R1 control for component row")
        decision = rule[key]
        if row.get("cut_seq") != decision.get("cut_seq"):
            raise ValueError("Component and R1 cutoffs differ")
        result = dict(row, arm="independent_then_R1:" + row["arm"][:-5],
                      source_component_arm=row["arm"],
                      block=bool(row["block"] or decision["block"]),
                      rule_stop=bool(decision["block"]),
                      calibration_policy="reuse frozen standalone-component inner OOF threshold; no joint R1 recalibration",
                      analysis_scope="posthoc protocol diagnosis; not frozen primary comparison")
        if all(row.get(k) is not None for k in ("inference_cost_ms", "decision_model_ms")) and decision.get("rule_wrapper_ms") is not None:
            result["rule_wrapper_ms"] = decision["rule_wrapper_ms"]
            result["reconstructed_total_guard_ms"] = row["inference_cost_ms"] + row["decision_model_ms"] + decision["rule_wrapper_ms"]
        else:
            result.pop("reconstructed_total_guard_ms", None)
        output.append(result)
    return output


def freeze_plan(base):
    root = base / "results/cheap-guards"
    output = root / "protocol-diagnostic"
    output.mkdir(exist_ok=True)
    plan = {
        "schema": "independent-component-or-r1-posthoc-v1",
        "role": "Exploratory diagnosis after primary results; not confirmatory or a replacement of primary protocol",
        "hypothesis": "Joint calibration with min FP/highest threshold disables every learned component when R1 already covers all inner harms",
        "preexisting_evidence": "Authority group held out in outer fold2 in all seeds; 243/243 fixed +R1 thresholds infinity, inner R1 recall1 and FP0",
        "operation": "Every available standalone :none component's unchanged outer decisions OR exact preexisting R1 control. Preserve its threshold, risk probability and original training-only selection.",
        "selection": "No outer selection; include all standalone arms and the preexisting train_selected_combo:none winner, and corresponding matched reference arms when available",
        "populations": "Same primary176P4/214outcomes, plus descriptive supported raw64 only",
        "new_inference": False, "new_fits": False, "new_threshold_search": False,
        "source_sha256": sha(__file__),
        "shared_metric_sources": {name: sha(base / "cascade_guard" / name) for name in ("cheap_eval.py", "night_ml.py")},
        "created_at": time.time(),
    }
    path = output / "plan.json"
    if path.exists():
        old = json.loads(path.read_text())
        assert old["source_sha256"] == plan["source_sha256"], "Frozen diagnostic source changed"
        return old
    path.write_text(json.dumps(plan, indent=2) + "\n")
    return plan


def run(base):
    # Import shared metrics only here; freezing the plan does not load ML packages.
    from .cheap_eval import counts, decisions_from_records, raw_metrics

    root = base / "results/cheap-guards"
    output = root / "protocol-diagnostic"
    plan = json.loads((output / "plan.json").read_text())
    assert sha(__file__) == plan["source_sha256"]
    for name, expected in plan["shared_metric_sources"].items():
        assert sha(base / "cascade_guard" / name) == expected
    main_file = root / "evaluation/predictions.jsonl"
    primary = read(main_file)
    sources = [main_file, base / "data/outcomes.jsonl", Path(__file__)]
    sources += [base / "cascade_guard" / name for name in plan["shared_metric_sources"]]
    main = wrap_independent(primary)
    reference = root / "matched-reference/predictions.jsonl"
    if reference.exists():
        main.extend(wrap_independent(read(reference), primary))
        sources.append(reference)
    outcomes = [r for r in read(base / "data/outcomes.jsonl") if not r["legacy_ambiguous"]]
    grouped = defaultdict(list)
    for row in main:
        grouped[row["seed"], row["arm"]].append(row)
    metrics = []
    for (seed, arm), rows in sorted(grouped.items()):
        if len(rows) != 176 or len({r["prefix_id"] for r in rows}) != 176:
            raise ValueError("Incomplete or colliding diagnostic arm")
        metric = counts(outcomes, decisions_from_records(rows))
        metric.update(seed=seed, arm=arm, prefixes=176, complete=not any(r.get("fit_failed") for r in rows), scope=plan["role"])
        metrics.append(metric)
    raw_file = root / "evaluation/raw64/predictions.jsonl"
    raw_predictions = wrap_independent(read(raw_file)) if raw_file.exists() else []
    raw_aggregates = []
    if raw_predictions:
        labels_path = root / "raw64/labels.jsonl"
        labels = read(labels_path)
        sources += [raw_file, labels_path]
        raw_grouped = defaultdict(list)
        for row in raw_predictions:
            raw_grouped[row["seed"], row["arm"]].append(row)
        for (seed, arm), rows in sorted(raw_grouped.items()):
            if len(rows) != 64 or len({r["prefix_id"] for r in rows}) != 64:
                raise ValueError("Incomplete raw diagnostic arm")
            metric = raw_metrics(rows, labels)
            metric.update(seed=seed, arm=arm, complete=not any(r.get("fit_failed") for r in rows))
            raw_aggregates.append(metric)
    for name, data in (("predictions.jsonl", main), ("raw-predictions.jsonl", raw_predictions)):
        (output / name).write_text("".join(json.dumps(r, allow_nan=False) + "\n" for r in data))
    (output / "metrics.json").write_text(json.dumps({"aggregates": metrics, "raw_aggregates": raw_aggregates, "scope": plan["role"]}, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps({"status": "COMPLETE", "created_at": time.time(), "plan_sha256": sha(output / "plan.json"), "sources": {str(p): sha(p) for p in sources}, "outputs": {p.name: sha(p) for p in output.glob('*') if p.name not in ('manifest.json', 'plan.json')}, "no_new_fit_inference_or_threshold": True}, indent=2) + "\n")
    return {"main_aggregates": len(metrics), "raw_aggregates": len(raw_aggregates), "output": str(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(freeze_plan(args.base) if args.freeze_only else run(args.base)))
