"""Offline sensitivity check on the frozen P1 archive evaluation."""

from collections import Counter
import json

from ml_archive import read, waves_data
from ml_study import HERE, calibration, canonical, digest, fit, predict, read_index, read_panel


def metrics(rows, scores, threshold):
    stop = [threshold is not None and score >= threshold for score in scores]
    return {
        "positive": sum(row["y"] for row in rows),
        "safe": sum(not row["y"] for row in rows),
        "detected": sum(row["y"] and decision for row, decision in zip(rows, stop, strict=True)),
        "false_stops": sum(not row["y"] and decision for row, decision in zip(rows, stop, strict=True)),
        "brier": sum((row["y"] - score) ** 2 for row, score in zip(rows, scores, strict=True)) / len(rows),
    }


def main():
    frozen = read(HERE / "ml_development_freeze.json")
    model = frozen["arms"]["facts"]["model"]
    cutoff = frozen["arms"]["facts"]["calibration"]["threshold"]
    links = HERE / "archive_wave_family_links.jsonl"
    manifest = read(HERE / "ml_archive_results.json")
    waves_root = HERE.parents[3] / ".runtime/finbot-final-study/jev/archive/waves"
    wave_names = sorted({name.split("/")[0] for name in manifest["archive_wave_sha256"]})
    archive, _, hashes = waves_data([waves_root / name for name in wave_names], set(HERE.glob("*.jsonl")),
                                    frozen, read_index(links))
    assert hashes == manifest["archive_wave_sha256"]
    assert digest(HERE / "ml_study.py") == frozen["source_sha256"]["ml_study.py"]
    stored = {row["id"]: row for row in map(json.loads, (HERE / "ml_archive_predictions.jsonl").read_text().splitlines())
              if row["comparison"] == "fixed_development_holdout" and row["method"] == "facts"}
    held = [row for row in archive if row["checkpoint"] == "P1" and row["jev"] is not None
            and row["group"] not in frozen["groups"] and row["group"] not in manifest["development_groups_excluded"]]
    assert len(held) == len(stored) and {row["id"] for row in held} == set(stored)
    for row, p in zip(held, predict(held, "facts", model), strict=True):
        old = stored[row["id"]]
        assert old["target"] == row["y"] and old["group"] == row["group"]
        assert abs(old["probability"] - p) < 1e-12 and old["stop"] == (p >= cutoff)

    plan = HERE / "archive_group_plan.jsonl"
    sources = [HERE / name for name in ("archive_development_packets.jsonl", "archive_mapping.jsonl",
                                      "archive_development_gold.jsonl")]
    assert all(digest(path) == frozen["source_sha256"][path.name] for path in [*sources, plan])
    dev, _ = read_panel([*sources, None], None, None, plan)
    by_id = {row["id"]: row for row in dev}
    training, cal = ([by_id[i] for i in frozen[key]] for key in ("fit_ids", "cal_ids"))
    fit_profiles, cal_profiles = ({canonical(row["facts"]) for row in part} for part in (training, cal))
    for row in held:
        old = stored[row["id"]]
        assert old["projection_in_fit"] == (canonical(row["facts"]) in fit_profiles)
        assert old["projection_in_cal"] == (canonical(row["facts"]) in cal_profiles)
    seen = [row for row in held if canonical(row["facts"]) in fit_profiles | cal_profiles]
    novel = [row for row in held if canonical(row["facts"]) not in fit_profiles | cal_profiles]

    def rule(row, *fields):
        return float(any(row["facts"][field] == "True" for field in fields))

    result = {"frozen_threshold": cutoff, "cohorts": {}, "ablation": {}}
    hold = "explicit_hold_flag"
    escalate = "explicit_escalation_flag"
    flag = "flag_in_prefix"
    assert all(stored[row["id"]]["stop"] == bool(rule(row, hold, escalate)) == bool(rule(row, flag))
               for row in held)
    irrelevant = set()
    for field in training[0]["facts"]:
        if len({row["facts"][field] for row in training}) == 1:
            irrelevant.add(field)
    result["varying_fit_fields"] = sorted(set(training[0]["facts"]) - irrelevant)
    result["fixed_probability_by_marker"] = {}
    for name, rows in (("HOLD", [row for row in held if rule(row, hold)]),
                       ("ESCALATE", [row for row in held if rule(row, escalate) and not rule(row, hold)]),
                       ("no_flag", [row for row in held if not rule(row, flag)])):
        scores = predict(rows, "facts", model)
        result["fixed_probability_by_marker"][name] = {"min": min(scores), "max": max(scores)}
    for name, rows in (("all", held), ("seen", seen), ("novel", novel),
                       ("without_hold", [row for row in held if not rule(row, hold)])):
        result["cohorts"][name] = {
            "groups": len({row["group"] for row in rows}),
            "projections": len({canonical(row["facts"]) for row in rows}),
            "lr": metrics(rows, predict(rows, "facts", model), cutoff),
            "hold": metrics(rows, [rule(row, hold) for row in rows], .5),
            "hold_or_escalation": metrics(rows, [rule(row, hold, escalate) for row in rows], .5),
            "any_flag": metrics(rows, [rule(row, flag) for row in rows], .5),
        }
    for name, fields in (("hold_and_escalation", {hold, escalate}),
                         ("all_flag_markers", {hold, escalate, flag}),
                         ("all_fraud_markers", {hold, escalate, flag, "fraud_record_available"})):
        def mask(rows):
            return [{**row, "facts": {k: v for k, v in row["facts"].items() if k not in fields}} for row in rows]
        reduced = fit(mask(training), "facts")
        operating = calibration(mask(cal), predict(mask(cal), "facts", reduced))
        result["ablation"][name] = {
            "calibration": operating,
            "masked_and_refit": metrics(held, predict(mask(held), "facts", reduced), operating["threshold"]),
            "masked_frozen": metrics(held, predict(mask(held), "facts", model), cutoff),
        }
    result["heldout_vendor_risk_targets"] = Counter(
        f'{row["facts"]["vendor_risk"]}/{row["y"]}' for row in held)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
