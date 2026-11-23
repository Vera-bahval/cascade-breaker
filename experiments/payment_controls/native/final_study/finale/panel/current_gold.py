"""Preserve historical gold and mark cases whose current-policy counterpart is unestablished."""


from .archive import thresholds
from .study import HERE, OUT, read_index, rows, wire, write

PRIOR_FAILURE_ONLY = {
    "failed_tax_verification_no_successful_replacement",
    "available_historical_tax_check_failed_before_transfer",
}


def adjudicated_transport(gold):
    if (gold["checkpoint"] == "P4" and gold["intervention_required"] == 1
            and gold["reason_code"] in PRIOR_FAILURE_ONLY):
        return {**gold, "intervention_required": None, "label": "INSUFFICIENT",
                "historical_label": gold["label"], "current_policy_transport": "unestablished_prior_external_failure"}
    return {**gold, "historical_label": gold["label"],
            "current_policy_transport": "unchanged_historical_unknown" if gold["intervention_required"] is None
            else "verified_non_tax_or_natively_permitted"}


def compare():
    historic = read_index(HERE / "archive_heldout_gold.jsonl")
    contemporary = {key: adjudicated_transport(gold) for key, gold in historic.items()}
    safe = read_index(HERE / "finale/p4/verified_action_gold.jsonl")
    safe_score = rows(OUT / "current-policy-scoped-safe-scores.jsonl")
    assert all(safe[r["id"]]["label"] == "ALLOW" for r in safe_score)
    return {
        "original_prefix": {stage: thresholds(rows(OUT / (stage + "-scores.jsonl")), contemporary)
                            for stage in ("current-policy-prefix", "current-policy-alternative")
                            if (OUT / (stage + "-scores.jsonl")).is_file()},
        "independently_confirmed_scoped_safe": thresholds(safe_score, safe),
        "transportability_overlay": [
            {key: row[key] for key in ("id", "checkpoint", "historical_label", "label",
                                       "current_policy_transport", "reason_code")}
            for row in contemporary.values()
        ],
        "historical_scoped_requires_tax_reviews_excluded": sum(row["label"] == "REVIEW" for row in safe.values()),
    }


if __name__ == "__main__":
    assert not (PRIOR_FAILURE_ONLY - {r["reason_code"] for r in read_index(HERE / "archive_heldout_gold.jsonl").values()})
    result = compare()
    suffix = "final" if "current-policy-alternative" in result["original_prefix"] else "preliminary"
    write(OUT / f"current-policy-gold-transport-{suffix}.json", wire(result))
