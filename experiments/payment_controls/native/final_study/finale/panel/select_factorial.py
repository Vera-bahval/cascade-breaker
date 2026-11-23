"""Select one live B/C wire and threshold using the frozen current-policy development scores."""

from collections import defaultdict
from statistics import mean

from .study import HERE, OUT, digest, rates, read, read_index, rows, wire, write


def select():
    directory = HERE / "finale/p4"
    gold = read_index(HERE / "archive_development_gold.jsonl") | read_index(directory / "gold_dev.jsonl")
    scores = OUT / "bc-development-scores.jsonl"
    variants = defaultdict(lambda: defaultdict(list))
    for row in rows(scores):
        if row["arm"] != "masked":
            variants[row["arm"]][row["checkpoint"]].append((row, gold[row["id"]]))
    contract = {
        "action_policy": ("condition", "omitted", "action_policy"),
        "records": ("condition", "omitted", "structured"),
        "fraud": ("condition", "present", "structured"),
        "prose": ("condition", "present", "prose"),
        "direct": ("direct", "present", "structured"),
    }
    assert variants.keys() == contract.keys()
    candidates = []
    for variant, checkpoints in sorted(variants.items()):
        question, fraud, representation = contract[variant]
        for threshold in (.90, .97):
            candidates.append({
                "variant": variant, "question": question, "fraud": fraud, "representation": representation,
                "threshold": threshold, "checkpoints": {k: rates(v, threshold) for k, v in checkpoints.items()},
                "mean_call_usd": mean(row["cost_usd"] for group in checkpoints.values() for row, _ in group),
            })

    def rank(candidate):
        metrics = list(candidate["checkpoints"].values())
        return (max(m["family_fpr"] for m in metrics),
                -min(m["detected"] / m["intervention"] for m in metrics),
                -sum(m["detected"] for m in metrics),
                candidate["mean_call_usd"], -candidate["threshold"], candidate["variant"])

    candidates = sorted(candidates, key=rank)
    natural = read(OUT / "bc_selection.json")
    picked = candidates[0]
    assert picked["representation"] == "structured"  # current live adapter wraps keyed records
    result = {
        **{key: natural[key] for key in ("model", "boundary", "score", "state_projection", "p4_label_scope",
                                         "template_sha256", "projection_sha256", "gold_sha256", "factorial_scores_sha256")},
        **picked, "ranked_candidates": candidates,
        "method": "Minimize maximum empirical family false-stop rate. Maximize the lower of the two checkpoint "
                  "sensitivities, then overall detected positives. Prefer lower mean cost, then .97. "
                  "The information-masked diagnostic is excluded from deployment eligibility.",
        "natural_fraud_fixed_contract_sha256": digest((OUT / "bc_selection.json").read_bytes()),
        "selection_code_sha256": digest(__import__("pathlib").Path(__file__).read_bytes()),
    }
    write(OUT / "bc_factorial_selection.json", wire(result))
    return picked


if __name__ == "__main__":
    print(wire(select()).decode())
