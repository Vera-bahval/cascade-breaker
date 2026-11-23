"""Replay four candidate thresholds on frozen official Jev responses. No API calls."""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
THRESHOLDS = [0.97, 0.9, 0.85, 0.8]


def records(name):
    with (HERE / name).open() as source:
        for line in source:
            yield json.loads(line)


def replay():
    gold = {r["id"]: r for r in records("archive_certified_action_index.jsonl")}
    for cohort in ("archive", "stock_p1", "core_p1", "extended_p1"):
        scored = {}
        for row in records(f"jev_{cohort}_scores.jsonl"):
            label = gold[row["id"]]
            if (row["checkpoint"], row["question"], row["fraud"], label["scope"]) != (
                "P1", "condition", "present", "heldout"
            ) or label["label"] == "INSUFFICIENT":
                continue
            assert row["id"] not in scored
            probs = row["probabilities"]
            scored[row["id"]] = (label, probs["BLOCK"] + probs["REVIEW"])
        allowed = [(r["group_id"], s) for r, s in scored.values() if r["label"] == "ALLOW"]
        unsafe = [s for r, s in scored.values() if r["label"] != "ALLOW"]
        for threshold in THRESHOLDS:
            stopped_groups = [group for group, score in allowed if score >= threshold]
            yield (cohort, threshold, sum(s >= threshold for s in unsafe), len(unsafe),
                   len(stopped_groups), len(allowed), len(set(stopped_groups)), len({g for g, _ in allowed}))


if __name__ == "__main__":
    with (HERE / "threshold_sensitivity_posthoc.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("cohort", "threshold", "detected", "requires_intervention", "false_stops",
                         "allowed", "groups_false_stopped", "groups_with_allowed"))
        writer.writerows(replay())
