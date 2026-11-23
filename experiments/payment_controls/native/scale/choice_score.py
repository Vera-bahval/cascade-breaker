"""Recompute the factorial from saved request bytes, typed/raw receipts and paid ledger."""
from collections import Counter, defaultdict
from itertools import combinations, product
import json
import math
import random
from statistics import mean, median
import sys

from .choice_design import CAP, HERE, LABELS, PHASES, PINNED_MODEL, POLICY, PRIVATE, QUESTIONS, old
from .choice_run import request_bytes, verified, verify_receipt

LEVELS = tuple(combinations(range(3), 2))


def pairs(a, b):
    return {
        "tv": sum(abs(a["probabilities"][key] - b["probabilities"][key]) for key in LABELS) / 2,
        "flip": int(a["selected"] != b["selected"]),
        "error_delta": b["error"] - a["error"],
        "absolute_error_delta": abs(b["error"] - a["error"]),
        "log_loss_delta": b["log_loss"] - a["log_loss"],
        "absolute_log_loss_delta": abs(b["log_loss"] - a["log_loss"]),
    }


def bootstrap(families):
    strata = defaultdict(list)
    for family, data in families.items():
        strata[tuple(data["stratum"])].append(family)
    rng = random.Random(POLICY["seed"])
    draws = [sum((rng.choices(group, k=len(group)) for group in strata.values()), [])
             for _ in range(10000)]

    def interval(values):
        n = len(values)
        means = sorted(sum(values[key] for key in draw) / n for draw in draws)
        return {"mean": mean(values.values()), "ci95": [means[249], means[9749]], "families": n,
                "nonzero_families": sum(value != 0 for value in values.values())}
    return interval


def arm_metrics(rows):
    return {
        "requests": len(rows), "errors": sum(r["error"] for r in rows), "error": mean(r["error"] for r in rows),
        "log_loss": mean(r["log_loss"] for r in rows), "defer": sum(r["selected"] == "DEFER" for r in rows),
        "mean_confidence": mean(r["answer"]["confidence"] for r in rows),
        "n_maximum_ties": sum(r["tie"] for r in rows),
        "confusion": {key: dict(Counter(r["selected"] for r in rows if r["gold"] == key)) for key in LABELS},
    }


def grouped_comparison(grouped_pairs, interval, *, signed=False):
    grouped = {fam: [pairs(a, b) for a, b in family] for fam, family in grouped_pairs.items()}
    senses = ["tv", "flip", "absolute_error_delta", "absolute_log_loss_delta"]
    if signed:
        senses.extend(["error_delta", "log_loss_delta"])
    return {
        **{key: interval({fam: mean(row[key] for row in family) for fam, family in grouped.items()})
           for key in senses},
        "positive_flip_pairs": sum(row["flip"] for family in grouped.values() for row in family),
        "paired_comparisons": sum(map(len, grouped.values())),
        "error_gains": sum(row["error_delta"] < 0 for family in grouped.values() for row in family),
        "error_losses": sum(row["error_delta"] > 0 for family in grouped.values() for row in family),
        "choice_transitions": dict(sorted(Counter(a["selected"] + " → " + b["selected"]
                                       for family in grouped_pairs.values() for a, b in family).items())),
    }


def score():
    freeze, release = verified()
    assert release == old.read(PRIVATE / "release.json")
    families = freeze["families"]
    ledger = old.prior.billing_entries(PRIVATE / "ledger.sqlite")
    assert set(ledger) == {j["request_id"] for j in freeze["jobs"]}
    assert sum(amount for _, amount, _ in ledger.values()) <= CAP
    receipts = PRIVATE / "receipts"
    assert {x.name for x in receipts.iterdir()} == {j["request_id"] + suffix for j in freeze["jobs"]
                                                        for suffix in (".json", ".raw", ".http.json")}
    rows, all_rows = {}, {}
    response_hashes = {}
    for job in freeze["jobs"]:
        _, body = request_bytes(job)
        ident = job["request_id"]
        r = verify_receipt(job, body, ledger[ident])
        gold = families[job["family"]][job["phase"] + "_gold"]
        probs = r["probabilities"]
        row = {**r, "gold": gold, "error": int(r["selected"] != gold),
               "log_loss": -math.log(max(POLICY["floor"], probs[gold])),
               "tie": sum(p == max(probs.values()) for p in probs.values()) > 1}
        key = (job["family"], job["phase"], job["question"], job["label_rotation"],
               job["order_rotation"], job["occurrence"])
        assert key not in rows
        rows[key] = row
        all_rows[ident] = row
        response_hashes[ident] = r["response_sha256"]
    assert len(rows) == len(all_rows) == 888
    interval = bootstrap(families)
    outcome = {
        "release": release, "model": PINNED_MODEL, "n_families": len(families), "primary_requests": 864,
        "identical_body_repeats": 24, "total_input_tokens": sum(r["usage"]["input_tokens"] for r in rows.values()),
        "cost_usd": math.fsum(r["cost_usd"] for r in rows.values()), "unresolved_reserved_usd": 0,
        "median_seconds": median(r["seconds"] for r in rows.values()), "excluded_cases": freeze["excluded_cases"],
        "excluded_vendors": freeze["excluded_vendors"], "eligible_per_cell": freeze["eligible_per_cell"],
        "arms": {}, "factor_effects": {}, "matched": {},
    }
    experiment_arms = tuple(product(PHASES, QUESTIONS))
    combined = {}
    for phase, question in experiment_arms:
        name = phase + "/" + question
        cells = {(label, order): arm_metrics([rows[f, phase, question, label, order, 0] for f in families])
                 for label, order in product(range(3), repeat=2)}
        outcome["arms"][name] = {
            **arm_metrics([rows[f, phase, question, label, order, 0] for f in families
                           for label, order in cells]),
            "by_cell": {f"{label},{order}": result for (label, order), result in cells.items()},
        }
        outcome["factor_effects"][name] = {}
    for name, ordering in (("letter_assignment", lambda x, y: (x, y)), ("json_semantic_order", lambda x, y: (y, x))):
        factor_pairs = defaultdict(list)
        for phase, question in experiment_arms:
            arm = phase + "/" + question
            detail = {}
            for low, high in LEVELS:
                matched = {
                    f: [(rows[f, phase, question, *ordering(low, fixed), 0],
                         rows[f, phase, question, *ordering(high, fixed), 0]) for fixed in range(3)]
                    for f in families
                }
                detail[f"{low}→{high}"] = grouped_comparison(matched, interval, signed=True)
                for f, group in matched.items():
                    factor_pairs[arm, f].extend(group)
            outcome["factor_effects"][arm][name] = {
                **grouped_comparison({f: factor_pairs[arm, f] for f in families}, interval), "level_pairs": detail,
            }
        combined[name] = {f: [p for phase, question in experiment_arms
                              for p in factor_pairs[phase + "/" + question, f]] for f in families}
    outcome["factor_effects"]["overall"] = {factor: grouped_comparison(matched, interval)
                                             for factor, matched in combined.items()}
    outcome["factor_effects"]["overall"]["assignment_minus_order"] = {
        key: interval({f: mean(pairs(a, b)[key] for a, b in combined["letter_assignment"][f]) -
                          mean(pairs(a, b)[key] for a, b in combined["json_semantic_order"][f]) for f in families})
        for key in ("tv", "flip", "absolute_error_delta", "absolute_log_loss_delta")
    }
    for phase in PHASES:
        matched = {f: [(rows[f, phase, "original", l, o, 0], rows[f, phase, "focused", l, o, 0])
                       for l, o in product(range(3), repeat=2)] for f in families}
        outcome["matched"][phase + "/focused_minus_original"] = grouped_comparison(matched, interval, signed=True)
    for question in QUESTIONS:
        matched = {f: [(rows[f, "full", question, l, o, 0], rows[f, "without_finstripe", question, l, o, 0])
                       for l, o in product(range(3), repeat=2)] for f in families}
        outcome["matched"][question + "/no_receipt_minus_full"] = grouped_comparison(matched, interval, signed=True)
    repeats = {f: [(rows[f, phase, q, l, o, 0], rows[f, phase, q, l, o, 1])]
               for f, phase, q, l, o, occ in rows if occ == 1}
    assert len(repeats) == len(families)
    outcome["repeats"] = grouped_comparison(repeats, interval, signed=True)
    artifact = {"score": outcome, "response_sha256": response_hashes}
    private_path = PRIVATE / "score.json"
    public_path = HERE / "choice_results.json"
    for path, value in [(private_path, artifact), (public_path, outcome)]:
        if path.exists():
            assert old.read(path) == value
        else:
            old.save(path, value)
    print(json.dumps(outcome, indent=2))


if __name__ == "__main__":
    score()
