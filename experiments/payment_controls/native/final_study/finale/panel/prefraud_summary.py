"""Summarize final independent pre-Fraud gold and a later conservative audit overlay."""

from collections import Counter

from .prefraud_run import CLASSES, CONFIDENCE_GRID, SOURCE, table
from .study import OUT, digest, read_index, rows, wire, write


def argmax(rows):
    counts = Counter((gold, r["decision"]) for r, gold in rows)
    return [{"gold": gold, "winner": choice, "actions": n} for (gold, choice), n in sorted(counts.items())]


def summarize(path):
    gold = read_index(path)
    scores = {r["id"]: r for split in ("development", "heldout") for r in rows(OUT / f"prefraud-{split}-scores.jsonl")}
    assert gold.keys() == scores.keys()
    result = {"gold_sha256": digest(path.read_bytes()), "groups": {}}
    for split in ("development", "heldout"):
        groups = result["groups"][split] = {}
        subset = [g for g in gold.values() if g["split"] == split]
        for scope in ("all", "E_eligible"):
            sample = [(scores[g["id"]], g["action"]) for g in subset if scope == "all" or g["stratum"] == scope]
            allowed = CLASSES if scope == "all" else {"CLOSE_ALLOW"}
            groups[scope] = {"argmax": argmax(sample), "confidence": {
                str(t): table(sample, t, allowed) for t in CONFIDENCE_GRID},
                "allow_probability_range": [min(r["probabilities"]["CLOSE_ALLOW"] for r, _ in sample),
                                             max(r["probabilities"]["CLOSE_ALLOW"] for r, _ in sample)]}
    return result


if __name__ == "__main__":
    gold_path = SOURCE.with_name("gold.jsonl")
    audit_path = SOURCE.with_name("reviewer_gold.jsonl")
    write(OUT / "prefraud-final-summary.json", wire({"final_gold": summarize(gold_path),
                                                     "later_conservative_audit": summarize(audit_path)}))
