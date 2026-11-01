"""Postprocessing only: saved scores/predictions, no model or rule imports.

Run only after the controller releases the quiet measurement CPU hold.
All output lives below --output; every consumed input is SHA256 recorded.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import csv
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
LABELS = ("ALLOW", "BLOCK", "UNKNOWN")
INPUTS = {}
PAYMENT = ("invoice_amount", "invoice_currency", "invoice_status", "vendor_status",
           "fraud_review_completed", "binding_hold", "human_cleared",
           "prior_completed_transfers", "amount_matches_invoice",
           "recipient_matches_authorized", "human_approved")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def record(path):
    path = Path(path).resolve()
    INPUTS[str(path)] = digest(path)
    return path


def read_json(path):
    return json.loads(record(path).read_text())


def read_lines(path):
    path = record(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def write_csv(path, rows):
    rows = list(rows)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with ExitStack() as stack:
        if path.suffix == ".gz":
            raw = stack.enter_context(path.open("wb"))
            compressed = stack.enter_context(gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0))
            stream = stack.enter_context(io.TextIOWrapper(compressed, newline=""))
        else:
            stream = stack.enter_context(path.open("w", newline=""))
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: canonical(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def verify_artifacts(directory):
    hashes = read_json(directory / "artifact-hashes.json")
    for name, expected in hashes.items():
        if digest(record(directory / name)) != expected:
            raise ValueError(f"artifact mismatch: {directory / name}")


def ratio(a, b):
    return a / b if b else None


def counts(rows, weights=None):
    c = Counter()
    confusion = {g: {d: 0.0 for d in LABELS} for g in LABELS}
    for row in rows:
        weight = weights.get(row["prefix_id"], 1.0) if weights else 1.0
        decision, gold = row["decision"], row["gold"]
        values = {
            "eligible": True, "correct_decisive": decision == gold and gold != "UNKNOWN",
            "correct_unknown": decision == gold == "UNKNOWN", "unknown": decision == "UNKNOWN",
            "gold_unknown": gold == "UNKNOWN", "false_allow": decision == "ALLOW" and gold != "ALLOW",
            "false_allow_block": decision == "ALLOW" and gold == "BLOCK",
            "false_allow_unknown": decision == "ALLOW" and gold == "UNKNOWN",
            "safe": gold == "ALLOW", "safe_stop": gold == "ALLOW" and decision != "ALLOW",
            "execution_error": bool(row.get("execution_error")),
            "classifier_unknown": decision == "UNKNOWN" and not row.get("execution_error") and not row.get("gate_changed"),
            "gate_changed": bool(row.get("gate_changed")),
            "gate_avoided_false_allow": bool(row.get("gate_changed")) and gold != "ALLOW",
            "gate_interrupted_safe": bool(row.get("gate_changed")) and gold == "ALLOW",
        }
        for key, enabled in values.items():
            c[key] += weight * enabled
        confusion[gold][decision] += weight
    return dict(c, correct_decisive_coverage=ratio(c["correct_decisive"], c["eligible"]),
                false_allow_rate=ratio(c["false_allow"], c["eligible"]),
                safe_stop_fpr=ratio(c["safe_stop"], c["safe"]),
                unknown_rate=ratio(c["unknown"], c["eligible"]), confusion=confusion)


def balanced_weights(rows, membership):
    sizes = Counter(membership[r["prefix_id"]] for r in rows)
    return {r["prefix_id"]: 1 / sizes[membership[r["prefix_id"]]] for r in rows}


def group_membership(ids, duplicate_groups):
    result = {pid: pid for pid in ids}
    for key, members in duplicate_groups.items():
        for pid in members:
            result[pid] = key
    return result


def interval(rows, components, replicates):
    groups = defaultdict(list)
    for row in rows:
        groups[components[row["prefix_id"]]].append(row)
    if len(groups) < 2:
        return dict(cluster_count=len(groups), replicates=0, requested_replicates=replicates, seed=17,
                    interpretation="interval unavailable: fewer than two connected dependency components; resampling one component gives no uncertainty information",
                    metrics={})
    sufficient = [counts(group) for _, group in sorted(groups.items())]
    metrics = (("correct_decisive", "eligible"), ("false_allow", "eligible"),
               ("safe_stop", "safe"), ("unknown", "eligible"))
    samples = defaultdict(list)
    rng = random.Random(17)
    for _ in range(replicates):
        chosen = [sufficient[rng.randrange(len(sufficient))] for _ in sufficient]
        for a, b in metrics:
            denominator = sum(c[b] for c in chosen)
            if denominator:
                samples[a + "/" + b].append(sum(c[a] for c in chosen) / denominator)
    result = {}
    for key, values in samples.items():
        values.sort()
        result[key] = dict(low=values[max(0, math.ceil(.025 * len(values)) - 1)],
                           high=values[math.ceil(.975 * len(values)) - 1], valid_replicates=len(values))
    return dict(cluster_count=len(groups), replicates=replicates, seed=17,
                interpretation="descriptive percentile component bootstrap; no independent-task population claim",
                metrics=result)


def decimal(value):
    try:
        number = Decimal(value) if isinstance(value, str) else None
        return number if number is not None and number.is_finite() else None
    except InvalidOperation:
        return None


def baseline_key(row):
    """Exact common-v3 P4 baseline recipe from closed_review_revision2.py.

    No rule/label invocation. Administrative IDs never enter this view. Amount
    equality/order and monetary partitions match the independent review recipe.
    Only separately supplied v3 baselines are accepted here.
    """
    o = row["payment_baseline"]
    if o.get("checkpoint") != "P4" or o.get("proposal", {}).get("tool") != "finstripe__create_transfer":
        return None
    facts, times = {}, {}
    for key in PAYMENT:
        sources = {"independent_registry"} if key in {"human_cleared", "human_approved"} else {"native_tool", "initial_fixture", "independent_registry"}
        proofs = [p for p in o.get("provenance", {}).get(key, [])
                  if p.get("source") in sources and p.get("subject_matches") is True
                  and type(p.get("event_seq")) is int and type(o.get("event_seq")) is int
                  and 0 <= p["event_seq"] < o["event_seq"]]
        facts[key] = o.get("facts", {}).get(key) if proofs else None
        times[key] = max((p["event_seq"] for p in proofs), default=None)
    value = dict(checkpoint="P4", proposal={k: o.get("proposal", {}).get(k) for k in ("tool", "amount", "currency")}, facts=facts)
    if facts["binding_hold"] is True:
        value["clearance_after_hold"] = None if times["human_cleared"] is None or times["binding_hold"] is None else times["human_cleared"] > times["binding_hold"]
    amounts = sorted({d for d in (decimal(value["proposal"]["amount"]), decimal(facts["invoice_amount"])) if d is not None})
    def walk(x, key=""):
        if isinstance(x, dict):
            return {k: walk(v, k) for k, v in sorted(x.items())}
        d = decimal(x)
        if key in {"amount", "invoice_amount"} and d is not None:
            part = ("negative" if d < 0 else "zero" if d == 0 else "0_to_5000" if d < 5000
                    else "5000" if d == 5000 else "5000_to_10000" if d < 10000 else "10000" if d == 10000
                    else "10000_to_50000" if d < 50000 else "50000" if d == 50000 else "over_50000")
            return ["amount", part, amounts.index(d)]
        return x
    return hashlib.sha256(canonical(walk(value)).encode()).hexdigest()


def prediction_groups(directory, observations, metadata):
    receipt = read_json(directory / "receipt.json")
    for key, path in (("observations", observations), ("metadata", metadata)):
        assert receipt[key + "_sha256"] == digest(path), (directory, key)
    assert receipt["labels_opened"] is False and receipt["fit_called"] is False
    if receipt.get("freeze_path"):
        manifest_path = Path(receipt["freeze_path"]) / "freeze-manifest.json"
        assert digest(record(manifest_path)) == receipt["freeze_sha256"]
        manifest = read_json(manifest_path)
        assert len(manifest["methods"]) == 72
        expected_methods = {m["name"] + "__" + variant for m in manifest["methods"] for variant in ("raw", "gated", "argmax_diagnostic")}
    else:
        expected_methods = {"rule_payment_v3", "rule_A", "rule_B"}
    assert {m["name"] for m in receipt["methods"]} == expected_methods
    assert len(receipt["methods"]) == len(expected_methods)
    files = defaultdict(list)
    for item in receipt["files"]:
        path = directory / item["path"]
        assert path.resolve().is_relative_to(directory.resolve())
        assert digest(record(path)) == item["sha256"]
        files[item["method"]].append((path, item["rows"]))
    for method in receipt["methods"]:
        rows = []
        for path, expected in files[method["name"]]:
            part = list(read_lines(path))
            assert len(part) == expected
            rows.extend(part)
        assert len(rows) == receipt["expected_eligible"][method["name"]]
        assert len({r["prefix_id"] for r in rows}) == len(rows)
        yield method, rows


def render_tables(output, tables, calibration, timing_rows, sensitivity):
    """Readable projections of the complete machine tables, no extra scoring."""
    def pct(v): return "н/д" if v is None else f"{100*v:.2f}"
    def num(v): return "н/д" if v is None else f"{v:.3f}"
    def label(r):
        if r.get("family") == "rule": return "Правила"
        feature, source = r["arm"].split("/")
        return ("LR" if r["family"] == "logistic" else "CatBoost") + ", " + ("старые" if feature == "old" else "новые") + ", " + ("архив" if source == "archive" else "смесь")
    cal = {r["method"]: r for r in calibration if r["dataset"] == "CAL"}
    times = {r["method"]: r for r in timing_rows}
    lines = ["## Основной seed17: все сочетания", "", "Покрытие и UNKNOWN указаны в процентах от N. FA включает gold BLOCK и UNKNOWN. STOP безопасных указан числом и знаменателем ALLOW. Время одиночного вызова включает признаки; миллисекунды, p50/p95.", ""]
    primary = [r for r in tables if r["dataset"] == "new1200" and r["slice_dimension"] == "all" and (r["seed"] == 17 and r["variant"] in {"raw", "gated"} or r["family"] == "rule")]
    for contract in ("payment_v3", "A", "B"):
        lines += [f"### Контракт `{contract}`", "", "| Метод, признаки, данные | Режим | N | Верные ALLOW/BLOCK, % | FA | STOP безопасных | UNKNOWN, % | Принят замороженным CAL-поиском | Одиночный, мс |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |"]
        for r in primary:
            if r["contract"] != contract: continue
            timing = (times[r["method"]].get("single") or {}).get("single_call", {})
            feasible = cal.get(r["method"], {}).get("feasible")
            cal_text = "да" if feasible is True else "нет" if feasible is False else "контроль"
            lines.append(f"| {label(r)} | {r['variant']} | {r['eligible']} | {pct(r['correct_decisive_coverage'])} | {r['false_allow_block']+r['false_allow_unknown']} | {r['false_safe_stop_block']+r['false_safe_stop_unknown']}/{r['safe']} | {pct(r['unknown']/r['eligible'])} | {cal_text} | {num(timing.get('p50_ms'))}/{num(timing.get('p95_ms'))} |")
        lines.append("")
    lines += ["### Argmax: диагностическое обучение без допустимого рабочего порога", "", "Эта таблица показывает наиболее вероятный класс, без CAL-ограничений и проверки доказательств. Её результаты не являются выбранным режимом исполнения.", "", "| Контракт | Метод, признаки, данные | Верные ALLOW/BLOCK, % | FA | STOP безопасных | UNKNOWN |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    for r in tables:
        if r["dataset"] == "new1200" and r["slice_dimension"] == "all" and r["seed"] == 17 and r["variant"] == "argmax_diagnostic":
            lines.append(f"| {r['contract']} | {label(r)} | {pct(r['correct_decisive_coverage'])} | {r['false_allow_block']+r['false_allow_unknown']} | {r['false_safe_stop_block']+r['false_safe_stop_unknown']}/{r['safe']} | {r['unknown']} |")
    lines += ["", "### Матрицы решений основного seed17", "", "Порядок истинных и предсказанных классов: ALLOW, BLOCK, UNKNOWN. Каждая ячейка таблицы содержит три счётчика предсказаний для указанной истинной метки.", "", "| Контракт | Метод | Режим | Истинный ALLOW | Истинный BLOCK | Истинный UNKNOWN |", "| --- | --- | --- | --- | --- | --- |"]
    for r in primary:
        cells = [" / ".join(str(r["confusion"][g][d]) for d in LABELS) for g in LABELS]
        lines.append(f"| {r['contract']} | {label(r)} | {r['variant']} | " + " | ".join(cells) + " |")
    lines += ["", "### Чувствительность к seed", "", "Все три заранее заданных seed17/29/43 показаны в одном порядке; выбор лучшего по тесту не проводился. CAL означает принятие замороженным поиском порогов; новый строгий учёт оставляет полную проверку исполнения неподтверждённой из-за восьми эпизодов с недоступным порядком.", "", "| Контракт | Метод | Режим | Покрытие 17 / 29 / 43, % | FA 17 / 29 / 43 | CAL-поиск 17 / 29 / 43 |", "| --- | --- | --- | --- | --- | --- |"]
    indexed = {r["method"]: r for r in tables if r["dataset"] == "new1200" and r["slice_dimension"] == "all"}
    for r in primary:
        if r["seed"] != 17: continue
        names = [r["method"].replace("__17__", f"__{seed}__") for seed in (17,29,43)]
        rs = [indexed[n] for n in names]
        lines.append(f"| {r['contract']} | {label(r)} | {r['variant']} | " + " / ".join(pct(x["correct_decisive_coverage"]) for x in rs) + " | " + " / ".join(str(x["false_allow_block"]+x["false_allow_unknown"]) for x in rs) + " | " + " / ".join("да" if cal.get(n,{}).get("feasible") else "нет" for n in names) + " |")
    lines += ["", "### Чувствительность к представлению платёжного состояния", "", "Взвешенные строки дают каждой уникальной проекции одинаковую массу; FA в них также взвешен. Н/д означает отсутствие gold ALLOW. Все платёжные строки принадлежат одной связанной компоненте: содержательный кластерный интервал для этого среза недоступен.", "", "| Метод | Срез | Строк | Эффективная масса | Покрытие, % | FA | STOP безопасных, % |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    selected = {"payment_v3__old__mixed__catboost__17__gated", "payment_v3__new__mixed__logistic__17__gated", "rule_payment_v3"}
    for r in sensitivity:
        if r["assessment"] == "revision2" and r["method"] in selected:
            lines.append(f"| {label(r)} | `{r['sensitivity']}` | {r['raw_rows']} | {r['eligible']:.2f} | {pct(r['correct_decisive_coverage'])} | {r['false_allow']:.2f} | {pct(r['safe_stop_fpr'])} |")
    (output / "tables.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "analysis")
    parser.add_argument("--bootstrap", type=int, default=1000)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output
    record(Path(__file__))
    review = read_json(HERE / "closed2-review.json")
    final_review = read_json(HERE / "closed2-rereview.json")
    assert final_review["summary"]["spec_verdict"] == "PASS"
    observations_path = HERE / "closed_revision2/observations.jsonl.gz"
    metadata_path = HERE / "closed_revision2/metadata.jsonl.gz"
    observations = {r["prefix_id"]: r for r in read_lines(observations_path)}
    metadata = {r["prefix_id"]: r for r in read_lines(metadata_path)}
    gold = {r["prefix_id"]: r["labels"] for r in read_lines(HERE / "closed_revision2/gold.jsonl.gz")}
    assert len(observations) == len(metadata) == len(gold) == 1200
    assert set(observations) == set(metadata) == set(gold)
    release = read_json(HERE / "results/closed2/gold-release.json")
    commitment = read_json(HERE / "results/closed2/prediction-commitment.json")
    assert release["prediction_commitment_sha256"] == digest(HERE / "results/closed2/prediction-commitment.json")
    assert release["gold_sha256"] == digest(HERE / "closed_revision2/gold.jsonl.gz")
    components = group_membership(observations, review["bootstrap_components"])
    component_ids = [pid for members in review["bootstrap_components"].values() for pid in members]
    assert len(component_ids) == 1200 and set(component_ids) == set(observations)
    assert len(set(components.values())) == 31
    full = group_membership(observations, review["duplicate_components"]["normalized_full"])
    assert len(set(full.values())) == 1112
    common = group_membership(observations, review["duplicate_components"]["common_v3_p4"])
    baseline = {pid: baseline_key(row) for pid, row in observations.items() if row["observation"].get("checkpoint") == "P4" and row["observation"].get("proposal", {}).get("tool") == "finstripe__create_transfer"}
    assert len(baseline) == 460 and len(set(baseline.values())) == 148
    assert len({common[pid] for pid in baseline}) == 149
    devkeys = {baseline_key(row) for row in read_lines(HERE / "data/observations.jsonl.gz") if "payment_baseline" in row}
    devkeys.discard(None)
    shared = {pid for pid, key in baseline.items() if key in devkeys}
    assert len(shared) == 302 and len(set(baseline.values()) & devkeys) == 61
    assert len(devkeys) == 315
    temporal = {r["prefix_id"] for r in review["label_mismatches"] if r.get("status") == "ambiguous_v3_temporal_projection"}
    assert len(temporal) == 14
    record(HERE / "closed_review_revision2.py")
    memberships = [dict(prefix_id=pid, component=components[pid], full_view=full[pid],
                        common_payment_view=common[pid] if pid in baseline else None,
                        supplied_payment_view=baseline.get(pid), supplied_payment_shared_dev=pid in shared,
                        prior_temporal_projection_ambiguity=pid in temporal) for pid in observations]
    write_csv(output / "state-memberships.csv", memberships)
    sensitivity, examples, error_rows, gate_attribution = [], [], [], []
    per_method = {}
    for assessment, directories in (
        ("revision2", (HERE / "results/closed2/revision2-replay", HERE / "results/closed2/controls")),
        ("original_v1", (HERE / "results/closed2/original-replay",)),
    ):
        for directory in directories:
            assert digest(directory / "receipt.json") == commitment["prediction_validations"][directory.name]["receipt_sha256"]
            for method, predictions in prediction_groups(directory, observations_path, metadata_path):
                name, contract = method["name"], method["contract"]
                joined = [dict(r, gold=gold[r["prefix_id"]][contract]) for r in predictions]
                expected = 460 if contract == "payment_v3" else 1180
                assert len(joined) == expected and all(r["gold"] in LABELS for r in joined)
                desc = dict(assessment=assessment, method=name, contract=contract,
                            family=method.get("family", "rule"), arm=method.get("arm"), seed=method.get("seed"),
                            variant=method.get("variant", "rule"))
                raw = counts(joined)
                per_method[(assessment, name)] = raw
                if method.get("variant") == "gated":
                    before = counts([dict(r, decision=r.get("raw_decision") or "UNKNOWN", gate_changed=False) for r in joined])
                    gate_attribution.append(dict(desc, before_same_gated_thresholds=before, after_gate=raw,
                        avoided_false_allow=raw["gate_avoided_false_allow"], interrupted_safe=raw["gate_interrupted_safe"],
                        gained_correct_BLOCK=0,
                        interpretation="Same gated operating thresholds; distinct from raw-versus-gated separately calibrated thresholds."))
                slices = [("rows", joined, None), ("deduplicated_full", joined, balanced_weights(joined, full))]
                if contract == "payment_v3":
                    slices += [("balanced_common_payment", joined, balanced_weights(joined, common)),
                               ("balanced_supplied_payment", joined, balanced_weights(joined, baseline)),
                               ("exclude_prior_temporal_ambiguity", [r for r in joined if r["prefix_id"] not in temporal], None)]
                    for label, subset in (("shared_dev", shared), ("outside_dev", set(baseline) - shared), ("prior_temporal_ambiguity", temporal)):
                        rows = [r for r in joined if r["prefix_id"] in subset]
                        slices += [(label, rows, None), (label + "_balanced", rows, balanced_weights(rows, baseline))]
                for label, rows, weights in slices:
                    sensitivity.append(dict(desc, sensitivity=label, raw_rows=len(rows), **counts(rows, weights)))
                if assessment == "revision2":
                    sensitivity[-len(slices)]["component_interval"] = interval(joined, components, args.bootstrap)
                errors = Counter((r.get("execution_error_stage"), r.get("execution_error_class")) for r in joined if r.get("execution_error"))
                for (stage, error_class), n in errors.items():
                    error_rows.append(dict(desc, stage=stage, error_class=error_class, rows=n))
                if assessment == "revision2" and (method.get("seed") == 17 or name.startswith("rule_")):
                    for row in joined:
                        pid = row["prefix_id"]
                        examples.append(dict(desc, prefix_id=pid, checkpoint=metadata[pid].get("checkpoint"),
                                             data_family=metadata[pid].get("family"), recipe=metadata[pid].get("recipe"),
                                             gold=row["gold"], decision=row["decision"], raw_decision=row.get("raw_decision"),
                                             gate_changed=row.get("gate_changed"), gate_reasons=row.get("gate_reasons"),
                                             execution_error=row.get("execution_error", False)))
    write_json(output / "sensitivity.json", sensitivity)
    write_csv(output / "sensitivity.csv", sensitivity)
    write_csv(output / "examples-index.csv.gz", examples)
    selected_cases = ("r2c-0524", "r2c-0525", "r2c-0740", "r2c-0243", "r2c-0619")
    write_json(output / "representative-cases.json", [dict(prefix_id=pid,
        observation_source=str(observations_path), observation_line=list(observations).index(pid)+1,
        observation=observations[pid], metadata=metadata[pid], gold=gold[pid],
        primary_decisions=[r for r in examples if r["prefix_id"] == pid]) for pid in selected_cases])
    write_csv(output / "execution-errors.csv", error_rows)
    write_json(output / "gate-attribution.json", gate_attribution)
    write_csv(output / "gate-attribution.csv", gate_attribution)
    datasets = {
        "new1200": HERE / "results/closed2/revision2-scores",
        "CAL": HERE / "results/revision2/cal-scores",
        "archive": HERE / "results/revision2/archive-scores",
        "old320_open": HERE / "results/revision2/old320-scores",
        "old400_open": HERE / "results/revision2/old400-scores",
        "first1200_open": HERE / "results/revision2/first1200-scores",
        "new1200_original_v1": HERE / "results/closed2/original-scores",
        "archive_original_v1": HERE / "results/original-v1-corrected-accounting/archive-scores",
        "CAL_original_v1": HERE / "results/original-v1-corrected-accounting/cal-scores",
    }
    tables, calibration, missing = [], [], []
    for dataset, directory in datasets.items():
        if not (directory / "metrics.json").exists():
            missing.append(str(directory)); continue
        verify_artifacts(directory)
        document = read_json(directory / "metrics.json")
        for r in document["metrics"]:
            entry = dict(dataset=dataset, **{k: r.get(k) for k in ("method", "contract", "family", "arm", "seed", "variant", "slice_dimension", "slice_value")},
                         **r["actions"], episodes=r["episodes"], reached_actions=r["reached_actions"],
                         outcomes=r["outcomes"], outcomes_all_registry=r.get("outcomes_all_registry"),
                         ordering=r.get("ordering"), calibration_constraints=r["calibration_constraints"])
            tables.append(entry)
            if dataset.startswith("new1200") and r["slice_dimension"] == "all":
                assessment = "original_v1" if dataset.endswith("original_v1") and not r["method"].startswith("rule_") else "revision2"
                calculated = per_method[(assessment, r["method"])]
                for key in ("eligible", "correct_decisive", "unknown", "false_allow_block", "false_allow_unknown", "safe", "gate_changed"):
                    assert calculated[key] == r["actions"][key], (dataset, r["method"], key)
                assert calculated["safe_stop"] == r["actions"]["false_safe_stop_block"] + r["actions"]["false_safe_stop_unknown"]
        if dataset in {"CAL", "CAL_original_v1"}:
            calibration += [dict(dataset=dataset, **m) for m in read_json(directory / "frozen-calibration.json")["methods"]]
    write_csv(output / "all-scores.csv.gz", tables)
    for dimension in ("source", "checkpoint", "family", "split"):
        write_csv(output / (dimension + "-slices.csv.gz"), (r for r in tables if r["slice_dimension"] == dimension))
    write_json(output / "calibration.json", calibration)
    write_csv(output / "calibration.csv", calibration)
    all_rows = {(r["dataset"], r["method"]): r for r in tables if r["slice_dimension"] == "all"}
    reconciliation = []
    for frozen_cal in calibration:
        scored = all_rows[(frozen_cal["dataset"], frozen_cal["method"])]
        frozen_counts, episodes = frozen_cal["cal_metrics"], scored["episodes"]
        for old, new in (("episodes", "eligible"), ("safe_episodes", "safe"), ("safe_stops", "safe_stops")):
            assert frozen_counts[old] == episodes[new], (frozen_cal["method"], old)
        assert frozen_counts["false_allows"] == scored["reached_actions"]["false_allow_block"] + scored["reached_actions"]["false_allow_unknown"]
        reconciliation.append(dict(dataset=frozen_cal["dataset"], method=frozen_cal["method"],
            frozen_search_feasible=frozen_cal["feasible"],
            execution_constraints=scored["calibration_constraints"],
            ordering_unassessed_episodes=episodes.get("ordering_unassessed", 0),
            false_allow_all_eligible_actions=scored["false_allow_block"] + scored["false_allow_unknown"],
            zero_false_allow_under_any_order_of_recorded_actions=(scored["false_allow_block"] + scored["false_allow_unknown"] == 0),
            safe_episode_ordering_complete=episodes.get("safe_ordering_assessed", episodes["safe"]) == episodes["safe"],
            episode_safe_and_false_allow_counts_match=True))
    write_json(output / "cal-reconciliation.json", reconciliation)
    contrasts = []
    for (dataset, name), row in all_rows.items():
        if row["seed"] not in (17, 29, 43) or row["variant"] not in ("raw", "gated", "argmax_diagnostic"):
            continue
        feature, source = row["arm"].split("/")
        comparisons = []
        if feature == "new": comparisons.append(("features", name.replace("__new__", "__old__")))
        if source == "mixed": comparisons.append(("development_diversity", name.replace("__mixed__", "__archive__")))
        if row["variant"] == "gated": comparisons.append(("operating_point_plus_gate", name.removesuffix("__gated") + "__raw"))
        for factor, base_name in comparisons:
            base = all_rows.get((dataset, base_name))
            if base:
                contrasts.append(dict(dataset=dataset, factor=factor, method=name, baseline=base_name,
                                      seed=row["seed"], contract=row["contract"],
                                      correct_decisive_delta=row["correct_decisive_coverage"] - base["correct_decisive_coverage"],
                                      false_allow_count_delta=row["false_allow_block"] + row["false_allow_unknown"] - base["false_allow_block"] - base["false_allow_unknown"],
                                      safe_stop_fpr_delta=(row["safe_stop_fpr"] - base["safe_stop_fpr"]) if row["safe_stop_fpr"] is not None and base["safe_stop_fpr"] is not None else None))
    write_csv(output / "factorial-contrasts.csv", contrasts)
    revision_contrasts = []
    for (dataset, name), row in all_rows.items():
        if dataset != "new1200" or row["seed"] not in (17, 29, 43):
            continue
        original = all_rows.get(("new1200_original_v1", name))
        if original:
            revision_contrasts.append(dict(method=name, contract=row["contract"], seed=row["seed"], variant=row["variant"],
                original_correct_decisive=original["correct_decisive"], revision2_correct_decisive=row["correct_decisive"],
                original_false_allow=original["false_allow_block"]+original["false_allow_unknown"],
                revision2_false_allow=row["false_allow_block"]+row["false_allow_unknown"],
                coverage_delta=row["correct_decisive_coverage"]-original["correct_decisive_coverage"]))
    write_csv(output / "revision-contrasts.csv", revision_contrasts)
    timings = {}
    for kind in ("native-quiet", "single", "load"):
        directory = HERE / "results/revision2" / kind
        if not (directory / "summary.json").exists():
            missing.append(str(directory)); continue
        verify_artifacts(directory)
        timings[kind] = read_json(directory / "summary.json")
    timing_rows = []
    frozen = read_json(HERE / "frozen_revision2/freeze-manifest.json")
    cold = {r["method"]: r for r in timings.get("load", {}).get("raw", [])}
    native_effects = defaultdict(Counter)
    if "native-quiet" in timings:
        directory = HERE / "results/revision2/native-quiet"
        for item in timings["native-quiet"]["raw_files"]:
            for trial in read_lines(directory / item["path"]):
                effects = native_effects[trial["method"]]
                effects["trials"] += 1
                effects["completed"] += trial["status"] == "completed"
                effects["stopped"] += trial["status"] == "stopped"
                effects["confirmed_transfers"] += trial["confirmed_transfers"]
                effects[trial.get("stop_effect_phase") or "no_stop"] += 1
                effects["stop_" + str(trial.get("stop_checkpoint"))] += trial["status"] == "stopped"
    for method in frozen["methods"]:
        for variant in ("raw", "gated"):
            name = method["name"] + "__" + variant
            native = timings.get("native-quiet", {}).get("summary", {}).get(name)
            single = timings.get("single", {}).get("summary", {}).get(name)
            timing_rows.append(dict(method=name, contract=method["contract"], arm=method["arm"], family=method["family"], seed=method["seed"], variant=variant,
                                    native=native, native_effects=dict(native_effects[name]), single=single,
                                    cold_gated_one_per_model=cold.get(method["name"])))
            if timings: assert native is not None or "native-quiet" not in timings
            if "single" in timings: assert single is not None
            if "load" in timings: assert method["name"] in cold
    remaining = (set(timings.get("native-quiet", {}).get("summary", {})) |
                 set(timings.get("single", {}).get("summary", {}))) - {r["method"] for r in timing_rows}
    for name in sorted(remaining):
        timing_rows.append(dict(method=name, native=timings.get("native-quiet", {}).get("summary", {}).get(name),
                               native_effects=dict(native_effects[name]), single=timings.get("single", {}).get("summary", {}).get(name)))
    write_csv(output / "timings.csv", timing_rows)
    write_json(output / "timings.json", timing_rows)
    primary = [r for r in tables if r["dataset"] == "new1200" and r["slice_dimension"] == "all" and (r["seed"] == 17 and r["variant"] in {"raw", "gated"} or r["family"] == "rule")]
    write_csv(output / "primary.csv", primary)
    render_tables(output, tables, calibration, timing_rows, sensitivity)
    if (HERE / "analysis/pair-feature-diagnostic.json").exists():
        record(HERE / "analysis/pair-feature-diagnostic.json")
    write_json(output / "summary.json", dict(missing_requested_inputs=missing, primary=primary,
                reviewed_units=final_review["summary"], prediction_commit=release["prediction_commit"],
                prediction_validations=commitment["prediction_validations"], score_rows=len(tables),
                sensitivity_rows=len(sensitivity), original_assessment="P2 representation defect retained",
                timing_methods=len(timing_rows), baseline_overlap=dict(rows=460, unique=148, shared_rows=302, outside_rows=158, shared_unique=61),
                normalizer="closed_review_revision2.py normalize_full/common; saved full/common memberships, separately reproduced supplied-baseline view",
                ci="31 conservative connected task/semantic components; contract subset can contain fewer", bootstrap=args.bootstrap))
    write_json(output / "source-hashes.json", INPUTS)
    print(json.dumps(dict(score_rows=len(tables), sensitivity_rows=len(sensitivity), missing=missing)))


if __name__ == "__main__":
    main()
