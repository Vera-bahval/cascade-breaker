"""Read retained Jev decisions and exact-state gold; reconstruct threshold sensitivity offline."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
PRIVATE = OUT.parents[5] / ".runtime/payment-controls-chp3"
TRUTH = PRIVATE / "finale-pre-fraud-truth"
LIVE = PRIVATE / "final-study-payment-finale"
A, S, D, U = "CLOSE_ALLOW", "CLOSE_STOP", "DEFER", "INSUFFICIENT"
CLOSE = {A, S}
GRID = (.10, .20, .30, .35, .40, .45, .49, .50, .51, .52, .53, .55, .60, .70, .80, .90, .95, .99)


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def count(sample, policy):
    matrix = Counter((gold or "UNMATCHED", policy(record)) for record, gold in sample)
    result = Counter(n=len(sample), correct_close=0, incorrect_close=0, unresolved_close=0,
                     defer=0, correct_defer=0, known=0, correct=0, close_allow=0, close_stop=0)
    for (gold, action), n in matrix.items():
        known = gold in CLOSE | {D}
        result["known"] += n * known
        result["correct"] += n * (known and gold == action)
        result["correct_close"] += n * (action in CLOSE and gold == action)
        result["incorrect_close"] += n * (action in CLOSE and known and gold != action)
        result["unresolved_close"] += n * (action in CLOSE and not known)
        result["correct_defer"] += n * (action == gold == D)
        result["defer"] += n * (action == D)
        result["close_allow"] += n * (action == A)
        result["close_stop"] += n * (action == S)
    result["matrix"] = {label: {action: matrix[label, action] for action in (A, S, D)}
                        for label in (A, S, D, U, "UNMATCHED")}
    return dict(result)


def winner_threshold(record, threshold):
    action = record["decision"]
    return action if action in CLOSE and record["probabilities"][action] >= threshold else D


def override_allow(record, threshold):
    return A if record["probabilities"][A] >= threshold else D


def summarize(sample):
    raw = count(sample, lambda record: record["decision"])
    assert raw["n"] == raw["defer"] + raw["close_allow"] + raw["close_stop"]
    return {
        "raw": raw,
        "allow_score_range": [min(scores), max(scores)] if (scores := [
            record["probabilities"][A] for record, _ in sample]) else None,
        "allow_defer_exact_tie_raw_choice": dict(Counter(
            r["decision"] for r, _ in sample if r["probabilities"][A] == r["probabilities"][D]
            and r["probabilities"][A] == max(r["probabilities"].values()))),
        "winner_threshold": {str(t): count(sample, lambda r: winner_threshold(r, t)) for t in GRID},
        "override_allow": {str(t): count(sample, lambda r: override_allow(r, t)) for t in GRID},
    }


def observation(episode):
    target = episode["refs"]["invoices"]["T"]["id"]
    fraud_steps = [step for trace in episode["traces"].values() for step in trace["steps"]
                   if step.get("agent") == "fraud_agent"]
    return {
        "fraud_ran": bool(fraud_steps),
        "fraud_completed": any(step.get("name") == "complete_task" and
                               (step.get("output") or {}).get("task_status") == "success"
                               for step in fraud_steps),
        "fraud_flag_calls": sum(step.get("name") == "flag_invoice_for_review" and
                                (step.get("arguments") or {}).get("invoice_id") == target
                                for step in fraud_steps),
        "completed_target_transfers": sum(tx["invoice_id"] == target and tx["status"] == "completed"
                                          and bool(tx["transfer_id"]) for tx in episode["after"]["transactions"]),
    }


def live_sample(source, original, audited):
    source_by_family = {row["family"]: row for row in source.values()}
    records, exact_comparison = [], []
    matches = Counter()
    for file in sorted((LIVE / "test").glob("*--E/pre-fraud-jev.jsonl")):
        episode = json.loads(file.with_name("episode.json").read_bytes())
        if episode["cell"]["kind"] != "main":
            continue
        [result] = rows(file)
        record = result["result"]
        assert result["action"] == D and record["model"] == "jev-1.14.0"
        request = (LIVE / "jev" / (record["occurrence"] + ".request")).read_bytes()
        assert sha256(request).hexdigest() == record["request_sha256"]
        family = episode["cell"]["family"]
        candidate = source_by_family.get(family)
        state = json.loads(request)["state"]
        match = ("exact" if candidate["blind_packet"] == state else "state_changed") if candidate else "no_family"
        matches[match] += 1
        ident = candidate["id"] if match == "exact" else None
        records.append((record, audited[ident]["action"] if ident else None))
        if ident:
            exact_comparison.append({
                "family": family,
                "gold": audited[ident]["action"],
                "original_gold": original[ident]["action"],
                "raw_choice": record["decision"],
                "allow_score": record["probabilities"][A],
                "effective_choice": result["action"],
                "stock_same_E_episode": observation(episode),
            })
        if record["decision"] == A:
            assert ident and family == "clean_29"
            paired_file = file.parent.with_name(file.parent.name.removesuffix("E") + "A") / "episode.json"
            paired = json.loads(paired_file.read_bytes())
            assert paired["initial_state_sha256"] == episode["initial_state_sha256"]
            exact_comparison[-1]["paired_A_same_initial_state"] = observation(paired)
    assert matches == {"exact": 4, "state_changed": 19, "no_family": 3}
    return {"match_counts": dict(matches), "summary": summarize(records),
            "stock_same_E_cases": exact_comparison}


def build():
    source = {r["id"]: r for r in rows(TRUTH / "inputs.jsonl")}
    original = {r["id"]: r for r in rows(TRUTH / "gold.jsonl")}
    audited = {r["id"]: r for r in rows(TRUTH / "reviewer_gold.jsonl")}
    scores = {r["id"]: r for split in ("development", "heldout")
              for r in rows(OUT / f"prefraud-{split}-scores.jsonl")}
    assert source.keys() == original.keys() == audited.keys() == scores.keys()
    for record in scores.values():
        assert record["model"] == "jev-1.14.0"
        vector = record["probabilities"]
        assert vector[record["decision"]] == max(vector.values())
        assert vector[S] < min(GRID)
    subsets = {
        "all_193": list(audited),
        "development_89": [k for k, g in audited.items() if g["split"] == "development"],
        "heldout_104": [k for k, g in audited.items() if g["split"] == "heldout"],
        "development_E_8": [k for k, g in audited.items()
                            if g["split"] == "development" and g["stratum"] == "E_eligible"],
        "heldout_E_14": [k for k, g in audited.items()
                        if g["split"] == "heldout" and g["stratum"] == "E_eligible"],
    }
    assert [len(s) for s in subsets.values()] == [193, 89, 104, 8, 14]
    return {
        "analysis": "posthoc_descriptive_no_threshold_selection",
        "thresholds": list(GRID),
        "gold_sha256": {name: sha256((TRUTH / name).read_bytes()).hexdigest()
                        for name in ("reviewer_gold.jsonl", "gold.jsonl")},
        "groups": {key: summarize([(scores[k], audited[k]["action"]) for k in subset])
                   for key, subset in subsets.items()},
        "original_gold_sensitivity": {
            key: summarize([(scores[k], original[k]["action"]) for k in subset])
            for key, subset in subsets.items()
        },
        "live": live_sample(source, original, audited),
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, separators=(",", ":")))
