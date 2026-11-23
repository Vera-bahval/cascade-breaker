"""Recompute descriptive Choice calibration from local paid research receipts."""
import argparse
import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from experiments.payment_controls.native.completion.jev_choice import PINNED_MODEL, validate_choice, validate_vector
from experiments.payment_controls.question_control import DECODING
from experiments.payment_controls.study.development import cases, decode, labels

HERE = Path(__file__).resolve().parent
NATIVE = HERE.parent
RUNTIME = HERE.parents[3] / ".runtime/payment-controls-chp3"
BINS = (0, .5, .7, .9, .95, 1)
# The historical omission inventory is confined to the seven original route archives.
LEGACY_ROUTE_ARCHIVES = (
    "checkpoint-live-auth-restored", "expansion-natural-live", "mechanism-live-v1",
    "mechanism-panel-v1", "native-confirmation-compatible-live-after-timeout",
    "native-confirmation-live", "overnight",
)


def load(path):
    return json.loads(path.read_bytes())


def add(groups, group, tag, family, receipt, mapping, reference, decision):
    probs = receipt.get("probabilities")
    if probs is None:
        groups["missing_vectors"][group] += 1
        return
    choice = receipt.get("choice", receipt.get("selected"))
    assert receipt.get("model", receipt.get("response_model")) == PINNED_MODEL
    assert receipt["valid"] and mapping[choice] == decision
    validate_vector(choice, probs, mapping)
    reference = [reference] if isinstance(reference, str) else reference
    assert set(mapping.values()) >= set(reference)
    groups["data"][group].append((tag, family, {mapping[k]: v for k, v in probs.items()}, decision, reference))


def archived_pilot(groups):
    folder = RUNTIME / "jev"
    with gzip.open(folder / "responses.jsonl.gz", "rt") as stream:
        raw = {r["id"]: r for r in map(json.loads, stream) if r["http_status"] == 200}
    mismatch = []
    for path in folder.glob("[0-9a-f]" * 64 + ".json"):
        row = load(path)
        wire = raw[path.stem]
        answer = wire["answer"]["check"]
        validate_choice(answer, row["request"]["questions"]["check"]["criteria"])
        assert (row["selected"], row["probabilities"], row["response_model"], row["usage"]) == (
            answer["choice"], answer["probabilities"], wire["model"], wire["usage"])
        pmax = answer["probabilities"][answer["choice"]]
        calculated = (3 * pmax - 1) / 2
        mismatch.append(abs(answer["confidence"] - calculated))
    groups["archive_readback"] = {"raw_files_checked": len(mismatch), "provider_confidence_max_abs_delta": max(mismatch)}
    with (NATIVE.parent / "pilot_results.csv").open() as stream:
        for row in csv.DictReader(stream):
            if row["provider"] != "jev":
                continue
            receipt = load(folder / (row["request_hash"] + ".json"))
            options = receipt["probabilities"]
            mapping = DECODING if row["phase"] == "control" else {
                k: {"active_hold": "BLOCK", "no_active_hold": "ALLOW", "insufficient_records": "REVIEW"}.get(k, k)
                for k in options
            }
            add(groups, "/".join([row["phase"], row["form"], "summary-" + row["summary"]]),
                row["case_id"], row["family"], receipt, mapping, row["gold"], row["decision"])
    for series, index in (("dev", "development"), ("confirmation", "confirmation")):
        orders = {row["family"]: decode(i) for i, row in enumerate(cases(series))}
        targets = labels(series)
        for ref in load(folder / (index + "_observations.json")):
            ident, form = ref["case_id"], ref["form"]
            receipt = load(folder / (ref["receipt"] + ".json"))
            add(groups, "document/" + series + "/" + form, ident, ident, receipt, orders[ident],
                targets[ident]["masked" if form == "masked" else "step"], orders[ident][receipt["selected"]])


def newer_panels(groups):
    from experiments.payment_controls.native.checkpoint import panel_live as checkpoint

    cases = checkpoint.cases(RUNTIME / "checkpoint-live/blind-reviewed")
    result = load(NATIVE / "checkpoint/panel_jev_results.json")
    assert checkpoint.panel.fingerprint(checkpoint.manifest(cases)) == result["freeze"]
    for row in result["rows"]:
        ident, form = row["case"], row["form"]
        case = cases[ident]
        probe = case["probes"][form]
        assert row["request_hash"] == checkpoint.panel.fingerprint(probe["bodies"]["jev"])
        raw = load(RUNTIME / "checkpoint-panel/jev" / (row["request_hash"] + ".json"))
        assert all(raw[k] == row[k] for k in raw)
        add(groups, "native/checkpoint/" + form, ident, case["case"].split("@")[0], row,
            dict(zip("ABC", probe["labels"], strict=True)), row["expected"], row["decision"])
    validation = NATIVE / "validation"
    manifest = load(validation / "semantic_freeze.json")["rows"]
    for row in load(validation / "semantic_results.json")["rows"]:
        ident, jev = row["id"], row["jev"]
        ref = manifest[ident]
        assert jev["request_hash"] == ref["prompt_sha256"]["jev"]
        raw = load(RUNTIME / "native-return-semantic/jev" / (jev["request_hash"] + ".json"))
        assert all(raw[k] == jev[k] for k in raw)
        add(groups, "native/semantic", ident, ref["source_sha256"], jev, ref["options"], ref["text_gold"], jev["extraction"])
    manifest = load(validation / "scope_model_freeze.json")["rows"]
    gold = load(validation / "scope_model_gold.json")["rows"]
    for ident, row in load(validation / "scope_model_results.json")["receipts"].items():
        jev, ref = row["jev"], manifest[ident]
        assert jev["request_hash"] == ref["prompt_sha256"]["jev"]
        raw = load(RUNTIME / "scope-model/jev" / (jev["request_hash"] + ".json"))
        assert all(raw[k] == jev[k] for k in raw)
        add(groups, "native/scope_model", ident, ref["archive_sha256"], jev, ref["options"],
            gold[ident]["admissible"], jev["prediction"])
    for directory in sorted(RUNTIME.glob("expansion-register-panel*")):
        result, gold = (load(directory / name) for name in ("results.json", "gold.json"))
        options = [load(path) for path in directory.glob("freeze*.json") if path.name in ("freeze-v2.json", "freeze.json")]
        by_id = {job["case_id"]: job for manifest in options for job in manifest["jobs"]}
        matrix = defaultdict(Counter)
        for row in result["rows"]:
            if row["provider"] != "jev":
                continue
            ident, phase = row["case_id"], row["phase"]
            ref = by_id[ident]
            assert row["request_hash"] == ref[phase]["request_sha256"]["jev"]
            raw = load(directory / "jev" / (row["request_hash"] + ".json"))
            assert all(raw[k] == row[k] for k in raw)
            target = gold[ident] if phase == "full" else "DEFER"
            matrix[phase][target, row["prediction"]] += 1
            add(groups, directory.name + "/" + phase, ident, ref["structure_sha256"], row,
                dict(zip("ABC", ref["labels"], strict=True)), target, row["prediction"])
        filename = "register_panel_results_ct.json" if directory.name.endswith("-ct") else "register_panel_results.json"
        published = load(NATIVE / "expansion" / filename)
        assert result["freeze_sha256"] == published["freeze_sha256"]
        for phase, cells in matrix.items():
            expected = published["phases"][phase]["provider"]["jev"]["confusion"]
            assert cells == Counter({(k, v): n for k, values in expected.items() for v, n in values.items()})
    for row in load(NATIVE / "confirmation/panel_results.json")["rows"]:
        if row["provider"] != "jev":
            continue
        ident = row["case"]
        raw = load(RUNTIME / "confirmation-panel/jev" / (row["request_hash"] + ".json"))
        assert all(raw[k] == row[k] for k in raw)
        add(groups, "native/confirmation/route", ident, ident.split("@")[0], row,
            dict(zip("ABC", ("CLOSE_ALLOW", "CLOSE_STOP", "DEFER"))), row["gold"], row["decision"])


def summary(rows):
    unique = [row for row in rows if len(row[4]) == 1]
    losses = [prob[ref[0]] for _, _, prob, _, ref in unique]
    brier = [sum((p - (k == ref[0])) ** 2 for k, p in prob.items()) for _, _, prob, _, ref in unique]
    bins = []
    for lo, hi in zip(BINS, BINS[1:]):
        matched = [(family, prob[pred], pred in ref) for _, family, prob, pred, ref in rows
                   if lo <= prob[pred] < hi or (hi == 1 and prob[pred] == 1)]
        family_counts = Counter(family for family, _, _ in matched)
        weights = [1 / family_counts[f] for f, _, _ in matched]
        bins.append({
            "interval": f"[{lo},{hi}{']' if hi == 1 else ')'}",
            "rows": len(matched), "family_ids": len(family_counts),
            "mean_p_choice": mean(p for _, p, _ in matched) if matched else None,
            "compatible": sum(correct for _, _, correct in matched),
            "family_balanced_mean_p_choice": sum(p * w for (_, p, _), w in zip(matched, weights)) / sum(weights) if matched else None,
            "family_balanced_compatible_rate": sum(c * w for (_, _, c), w in zip(matched, weights)) / sum(weights) if matched else None,
        })
    return {
        "n": len(rows), "family_ids": len({r[1] for r in rows}), "compatible": sum(r[3] in r[4] for r in rows),
        "singleton_gold_n": len(unique), "brier_multiclass": mean(brier) if brier else None,
        "log_loss": ("infinite" if 0 in losses else mean(-math.log(p) for p in losses)) if unique else None,
        "zero_p_gold": losses.count(0), "log_loss_floor_1e_6": mean(-math.log(max(1e-6, p)) for p in losses) if unique else None,
        "bins": bins,
        "confident_errors": [{"case": tag, "family": family, "probabilities": prob, "choice": pred, "gold": ref}
                             for tag, family, prob, pred, ref in rows if pred not in ref and prob[pred] >= .9],
    }


def missing_vectors(folder):
    paths = list(folder.glob("[0-9a-f]" * 64 + ".json"))
    count = 0
    for path in paths:
        receipt = load(path)
        vector = receipt.get("probabilities")
        if vector is None and isinstance(receipt.get("answer"), dict):
            vector = receipt["answer"].get("probabilities")
        count += not isinstance(vector, dict) or not vector
    return count


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--supplements", action="store_true",
                     help="also inspect later route folders, apart from the historical omission cohort")
    args = cli.parse_args()
    groups = {"data": defaultdict(list), "missing_vectors": Counter()}
    archived_pilot(groups)
    newer_panels(groups)
    for archive in LEGACY_ROUTE_ARCHIVES:
        count = missing_vectors(RUNTIME / archive / "jev")
        if count:
            groups["missing_vectors"][archive] = count
    if args.supplements:
        groups["supplement_missing_vectors"] = {
            folder.parent.name: missing_vectors(folder)
            for folder in sorted(RUNTIME.glob("*/jev")) if folder.parent.name not in LEGACY_ROUTE_ARCHIVES
        }
    groups["data"] = {group: summary(rows) for group, rows in sorted(groups["data"].items())}
    print(json.dumps(groups, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
