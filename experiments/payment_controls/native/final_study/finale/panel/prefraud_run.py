"""Evaluate observed pre-Fraud packets on blinded gold and freeze a live calibration."""

import argparse
from collections import Counter

from .prefraud import CONFIDENCE_GRID, body, decision, eligible
from .study import OUT, ROOT, digest, dispatch, read_index, rows, wire, write

SOURCE = ROOT / ".runtime/payment-controls-chp3/finale-pre-fraud-truth/inputs.jsonl"
CLASSES = {"CLOSE_ALLOW", "CLOSE_STOP"}


def run(split):
    corpus = [r for r in rows(SOURCE) if r["split"] == split]
    jobs = []
    for row in corpus:
        request = body(row["packet"])
        assert request["state"] == row["blind_packet"]
        assert eligible(row["packet"]) == (row["d_action"] == "DEFER" and not row["mandatory_veto"])
        # Published scores keep families opaque pending independent adjudication.
        group = digest(wire(["finbot-finale-prefraud-family", row["family"]]))[:24]
        jobs.append(({"checkpoint": "pre-Fraud"}, {"id": row["id"], "group_id": group}, "structured", request))
    return dispatch(f"prefraud-{split}", jobs)


def table(records, threshold, allowed):
    counters = Counter()
    for receipt, expected in records:
        action = decision(receipt, threshold, allowed)
        counters["n"] += 1
        counters["known"] += expected in CLASSES | {"DEFER"}
        counters["correct_closes"] += action in CLASSES and action == expected
        counters["incorrect_closes"] += action in CLASSES and expected in CLASSES | {"DEFER"} and action != expected
        counters["unestablished_closes"] += action in CLASSES and expected not in CLASSES | {"DEFER"}
        counters["deferred"] += action == "DEFER"
        counters[expected] += 1
    return dict(counters)


def evaluate(split, gold_path, gold_key):
    source = read_index(SOURCE)
    gold = read_index(gold_path)
    scores = rows(OUT / f"prefraud-{split}-scores.jsonl")
    assert {row["id"] for row in scores} <= gold.keys()
    scoped = [(row, gold[row["id"]][gold_key]) for row in scores
              if source[row["id"]]["d_action"] == "DEFER" and not source[row["id"]]["mandatory_veto"]]
    overall = [(score, gold[score["id"]][gold_key]) for score in scores]
    policies = []
    for threshold in CONFIDENCE_GRID:
        policies.append({"threshold": threshold, "allow_only": table(scoped, threshold, {"CLOSE_ALLOW"}),
                         "jev_first": table(overall, threshold, CLASSES)})
    result = {"split": split, "candidate_thresholds": policies,
              "gold_sha256": digest(gold_path.read_bytes()), "source_sha256": digest(SOURCE.read_bytes()),
              "projection_sha256": digest((OUT / "prefraud.py").read_bytes())}
    write(OUT / f"prefraud-{split}-metrics.json", wire(result))
    if split == "development":
        candidates = [row for row in policies if row["allow_only"]["correct_closes"] > 0
                      and row["allow_only"]["incorrect_closes"] == row["allow_only"]["unestablished_closes"] == 0]
        threshold = max(candidates, key=lambda v: (v["allow_only"]["correct_closes"], v["threshold"]),
                        default={"threshold": None})["threshold"]
        selection = {**result, "threshold": threshold, "allowed_live_classes": ["CLOSE_ALLOW"] if threshold else [],
                     "fallback": "delegate unchanged to native Fraud; mandatory veto or failed/rejected/unavailable classifier may never close"}
        write(OUT / "prefraud_selection.json", wire(selection))
        return selection
    return result


if __name__ == "__main__":
    from argparse import ArgumentParser
    from pathlib import Path
    import json

    parser = ArgumentParser(description=__doc__)
    parser.add_argument("split", choices=("development", "heldout"))
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--gold-key", default="action")
    args = parser.parse_args()
    if args.gold is None:
        _, result = run(args.split)
    else:
        result = evaluate(args.split, args.gold, args.gold_key)
    print(json.dumps(result))
