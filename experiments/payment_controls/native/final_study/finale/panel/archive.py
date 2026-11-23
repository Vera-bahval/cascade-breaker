"""Paired archived Jev interventions, separate from metered live decision points."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from .study import (
    CHOICE, HERE, OUT, dev_panels, digest, dispatch, intervention_score, make_current, pair, read, read_index,
    rows, variants, wire, write,
)

P4 = HERE / "finale/p4"
THRESHOLDS = (.50, .70, .80, .85, .90, .95, .97, .99)
CONTRASTS = {
    "records_given_action_and_policy": ("action_policy", "records"),
    "bound_fraud_given_records": ("records", "fraud"),
    "form_identical_evidence": ("fraud", "prose"),
    "unresolved_condition_versus_direct": ("direct", "fraud"),
    "additional_adapter_scope": ("fraud", "scoped"),
    "mask_restriction": ("fraud", "masked"),
    "mask_required_tax_evidence": ("scoped", "masked"),
}


def packet_variant(rows, arms=None, live=False):
    for packet, gold in rows:
        request_variants = variants(make_current(packet) if live else packet, extra=not live)
        for arm, body in request_variants.items():
            if arms is None or arm in arms:
                yield packet, gold, arm, body


def stratified(rows, size, seed):
    buckets = defaultdict(dict)
    for p, g in sorted(rows, key=lambda item: digest(wire([seed, item[1]["id"]]))):
        buckets[g["intervention_required"]].setdefault(g["group_id"], (p, g))
    return [row for label in sorted(buckets, key=str)
            for row in list(buckets[label].values())[:size]]


def sources(stage):
    historic_dev, _ = dev_panels()
    historical = pair("archive_heldout_packets.jsonl", "archive_heldout_gold.jsonl")
    scoped = pair(P4 / "verified_action_packets.jsonl", P4 / "verified_action_gold.jsonl")
    scoped_dev = pair(P4 / "blind_dev.jsonl", P4 / "gold_dev.jsonl")
    development = {g["group_id"] for _, g in historic_dev + scoped_dev}
    assert all(g["group_id"] not in development for _, g in historical + scoped)
    if stage == "historical-development":
        return [(p, g) for p, g in historic_dev if p["checkpoint"] == "P1"] + scoped_dev, None, False
    if stage == "historical-p1":
        return [row for row in historical if row[0]["checkpoint"] == "P1"], None, False
    if stage == "historical-p4-balanced":
        return stratified(scoped, 48, "finbot-finale-scoped-dose-v1"), None, False
    if stage == "historical-p4-wide":
        return scoped, {"records", "fraud", "scoped"}, False
    if stage == "current-policy-scoped-safe":
        # Independent archive decisions with all prerequisites verified are still eligible under the current native policy.
        return [row for row in scoped if row[1]["label"] == "ALLOW"], {"records"}, True
    if stage in ("current-policy-prefix", "current-policy-alternative"):
        # Keep the historic missing-agent-tax-only cases out of current-policy scoring.
        scoped_positive_action_ids = {g["id"] for _, g in scoped if g["label"] == "REVIEW"}
        assert not scoped_positive_action_ids.intersection(g["id"] for _, g in historical)
        return historical, ({"direct"} if stage == "current-policy-alternative" else {"records"}), True
    raise ValueError(stage)


def thresholds(receipt_rows, gold):
    report = []
    groups = defaultdict(list)
    for receipt in receipt_rows:
        groups[receipt["checkpoint"], receipt["arm"]].append((receipt, gold[receipt["id"]]))
    for (point, arm), entries in sorted(groups.items()):
        for threshold in (*THRESHOLDS, "argmax"):
            cells = Counter()
            safe_groups = set()
            false_groups = set()
            for r, g in entries:
                stop = (r["decision"] != "ALLOW" if threshold == "argmax" else intervention_score(r) >= threshold)
                y = g["intervention_required"]
                cells[str(y), stop] += 1
                if y == 0:
                    safe_groups.add(g["group_id"])
                    if stop:
                        false_groups.add(g["group_id"])
            report.append({
                "checkpoint": point, "arm": arm, "threshold": threshold,
                "known_safe": cells["0", True] + cells["0", False], "safe_families": len(safe_groups),
                "known_intervention": cells["1", True] + cells["1", False], "unknown": cells["None", True] + cells["None", False],
                "false_stop_families": len(false_groups), "false_stops": cells["0", True], "detected": cells["1", True],
                "unknown_stops": cells["None", True], "unknown_continues": cells["None", False],
            })
    return report


def contrasts(receipt_rows, gold):
    by_id = defaultdict(dict)
    for r in receipt_rows:
        by_id[r["id"]][r["arm"]] = r
    summarized = defaultdict(list)
    for i, receipts in by_id.items():
        for tag, (left, right) in CONTRASTS.items():
            if not {left, right} <= receipts.keys():
                continue
            a, b = receipts[left], receipts[right]
            if tag == "mask_restriction" and a["checkpoint"] != "P1":
                continue
            if tag == "bound_fraud_given_records" and a["request_sha256"] == b["request_sha256"]:
                continue
            g = gold[i]
            summarized[tag, a["checkpoint"], str(g["intervention_required"])].append(
                (g["group_id"], intervention_score(a), intervention_score(b),
                 a["decision"] != "ALLOW", b["decision"] != "ALLOW"))
    report = []
    for (tag, point, label), pairs in sorted(summarized.items()):
        family = defaultdict(list)
        for group, p, q, a, b in pairs:
            family[group].append(q - p)
        report.append({
            "contrast": tag, "checkpoint": point, "gold_intervention": label, "actions": len(pairs),
            "families": len(family), "mean_family_weighted_score_difference": mean(map(mean, family.values())),
            "left_only_at_frozen_threshold": sum(p >= .97 > q for _, p, q, a, b in pairs),
            "right_only_at_frozen_threshold": sum(q >= .97 > p for _, p, q, a, b in pairs),
            "left_only_argmax": sum(a and not b for _, p, q, a, b in pairs),
            "right_only_argmax": sum(b and not a for _, p, q, a, b in pairs),
        })
    return report


def run(stage):
    cases, arms, live = sources(stage)
    if stage != "historical-development":
        assert (OUT / "bc_factorial_selection.json").is_file()
        assert (OUT / "historical-development-metrics.json").is_file()
    jobs = list(packet_variant(cases, arms, live))
    scores, meter = dispatch(stage, jobs)
    gold = {g["id"]: g for _, g in cases}
    result = {
        "stage": stage, "unique_actions": len(cases), "new_cost": meter,
        "threshold_response": thresholds(scores, gold), "paired_contrasts": contrasts(scores, gold),
        "gold_sha256": digest(wire(gold)),
    }
    write(OUT / f"{stage}-metrics.json", wire(result))
    return meter


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("historical-development", "historical-p1", "historical-p4-balanced",
                                           "historical-p4-wide", "current-policy-prefix", "current-policy-scoped-safe",
                                           "current-policy-alternative"))
    args = parser.parse_args()
    print(wire(run(args.stage)).decode())
