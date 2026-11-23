"""Read-only historical target, split and projection audit."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LOCAL = ROOT.parent.parent / "experiments/local_guards"
EXP = ROOT / "experiments"


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-secjev", action="store_true")
    args = parser.parse_args()
    guard = LOCAL / "results/guard-v2"
    path = {
        "old_prefixes": guard / "inputs-v5/archive-p4-rows.jsonl",
        "old_outcomes": guard / "evaluation/outcomes214.jsonl",
        "old_folds": LOCAL / "results/cheap-guards/evaluation/fold-allocations.json",
        "old_jev_catboost": LOCAL / "results/secjev9b-night-20261018/analysis-v1/catboost-comparison.json",
        "action_oof_audit": HERE.parent / "checkpoint/ml_audit.json",
        "v3_fit": EXP / "local_guards_v3/results/frozen/freeze-manifest.json",
        "v3_metadata": EXP / "local_guards_v3/data/metadata.jsonl",
        "v3_gold": EXP / "local_guards_v3/data/gold-actions.jsonl",
        "v3_observations": EXP / "local_guards_v3/data/observations.jsonl",
        "synthetic_retrain_audit": EXP / "local_guards_ml_retrain/final-audit.json",
    }
    prefixes = rows(path["old_prefixes"])
    outcomes = {row["episode_id"]: row for row in rows(path["old_outcomes"])}
    for row in prefixes:
        assert row["label"] == outcomes[row["episode_id"]]["strict_harm"]
    folds = read(path["old_folds"])
    for fold in folds:
        assert not set(fold["train_groups"]) & set(fold["test_groups"])
        for inner in fold["inner"]:
            assert not set(inner["train_groups"]) & set(inner["test_groups"])
            assert (set(inner["train_episode_ids"]) | set(inner["test_episode_ids"])) <= set(fold["train_episode_ids"])
    compare = read(path["old_jev_catboost"])
    assert compare["old_arm_reproduced_exactly"]
    for file, digest in compare["source_sha256"].items():
        assert sha256((LOCAL / file).read_bytes()).hexdigest() == digest, file

    secjev_replay = None
    if args.replay_secjev:
        script = LOCAL / "scripts/analyze_secjev9b_catboost.py"
        original = path["old_jev_catboost"].parent
        with TemporaryDirectory(prefix="finbot-ml-history-") as tmp:
            temp = Path(tmp)
            run = runpy.run_path(str(script))["main"]
            run.__globals__["OUT"] = temp
            # Existing reproducer prints the temporary path after its write.
            from contextlib import redirect_stdout
            from io import StringIO
            with redirect_stdout(StringIO()):
                run()
            secjev_replay = {}
            for file in ("catboost-comparison.json", "catboost-predictions.jsonl"):
                assert (temp / file).read_bytes() == (original / file).read_bytes()
                secjev_replay[file] = "byte_identical"

    p4 = read(path["action_oof_audit"])
    assert p4["saved_artifact_and_fold_verification"]["max_absolute_probability_delta"] == 0
    for file, digest in p4["input_sha256"].items():
        assert sha256((ROOT / file).read_bytes()).hexdigest() == digest, file
    v3 = read(path["v3_fit"])
    for name in ("v3_metadata", "v3_gold", "v3_observations"):
        assert sha256(path[name].read_bytes()).hexdigest() == v3["data_hashes"][path[name].name]
    metadata = rows(path["v3_metadata"])
    group_splits = defaultdict(set)
    for row in metadata:
        if row["split"] in {"TRAIN", "CAL"}:
            group_splits[row["group_id"]].add(row["split"])
    assert all(len(v) == 1 for v in group_splits.values())
    train_ids = {row["prefix_id"] for row in metadata if row["split"] == "TRAIN"}
    train = set()
    for row in rows(path["v3_observations"]):
        if row["prefix_id"] not in train_ids:
            continue
        proposal = row.get("proposal", {})
        tool = row.get("tool", proposal.get("tool"))
        stage = row.get("checkpoint")
        if ((stage, tool) in {("P4", "finstripe__create_transfer"), ("P2", "delegate_to_fraud")} or
                (stage, tool, row.get("target_status", proposal.get("target_status"))) ==
                ("P3", "update_invoice_status", "approved")):
            train.add(row["prefix_id"])
    train_counts = Counter(r["decision"] for r in rows(path["v3_gold"])
                           if r["prefix_id"] in train and r["decision"] in ("ALLOW", "BLOCK"))
    assert train_counts == v3["fit"]["labels"], train_counts
    retrain = read(path["synthetic_retrain_audit"])
    exposure = next(r["details"] for r in retrain["checks"] if r["id"] == "overlap_split_verification")
    report = {
        "old_secjev_catboost": {
            "target": "strict_harm continuation outcome, joined separately by episode",
            "label_counts": dict(Counter(str(r["label"]) for r in prefixes)),
            "reached_prefixes": len(prefixes),
            "underlying_episode_denominator": len(outcomes),
            "seeds": compare["seeds"],
            "outer_allocations": len(folds),
            "inner_allocations": sum(len(fold["inner"]) for fold in folds),
            "fold_group_overlap": 0,
            "prior_exact_reproduction_receipt": compare["old_arm_reproduced_exactly"],
            "local_replay": secjev_replay,
        },
        "action_oof_catboost": {
            "target": "historical full action admissibility",
            "fit_test_projection_overlap": p4["projection_exposure"],
            "full_action": p4["methods"]["catboost_calibrated"]["action_label"],
            "substantive": p4["methods"]["catboost_calibrated"]["substantive_label"],
            "folds": p4["saved_artifact_and_fold_verification"]["folds"],
        },
        "v3_structured_logistic_and_catboost": {
            "target": "action_requires_intervention",
            "fit": v3["fit"],
            "TRAIN_gold_counts_recomputed": train_counts,
        },
        "synthetic_retrain_normalized_p4_exposure": exposure["new_test_rows"],
        "source_sha256": {k: sha256(p.read_bytes()).hexdigest() for k, p in path.items()},
        "new_api_calls": 0,
    }
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
