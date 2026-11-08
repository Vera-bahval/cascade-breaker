"""Correct archive cluster intervals from saved predictions; no inference/fit.

The immutable scorer prefixes global task groups with source. This separate
postprocessing uses exact metadata.group_id for the 51 primary operating modes.
All point summaries must remain exactly equal to the saved scorer output.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analysis as io
import evaluation_revision2 as ev


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=HERE / "analysis/archive-global-intervals.json")
    args = parser.parse_args()
    io.record(Path(__file__))
    io.record(HERE / "evaluation_revision2.py")
    io.record(HERE / "analysis.py")
    score_path = HERE / "results/revision2/archive-scores"
    io.verify_artifacts(score_path)
    document = io.read_json(score_path / "metrics.json")
    source = document["inputs"]
    selected = {r["method"]: r for r in document["metrics"] if r["slice_dimension"] == "all"
                and (r["family"] == "rule" or r["seed"] == 17 and r["variant"] in {"raw", "gated"})}
    assert len(selected) == 51
    data = HERE.parent / "local_guards_v4/data"
    paths = {name: data / filename for name, filename in (
        ("observations", "observations.jsonl.gz"), ("metadata", "metadata.jsonl.gz"),
        ("labels", "gold-actions.jsonl.gz"), ("outcomes", "gold-outcomes.jsonl.gz"),
        ("episodes", "episodes.jsonl.gz"))}
    for name, path in paths.items():
        assert io.digest(io.record(path)) == source[name + "_sha256"]
    # Preserve actual source event_seq. Never borrow a metadata time or coerce it.
    compact = {}
    eligible = defaultdict(set)
    for row in io.read_lines(paths["observations"]):
        observation = ev.obj(row)
        compact[row["prefix_id"]] = dict(checkpoint=observation["checkpoint"], event_seq=observation.get("event_seq"))
        for contract in ev.CONTRACTS:
            if ev.eligible(row, contract):
                eligible[contract].add(row["prefix_id"])
    keys = ("prefix_id", "episode_id", "group_id", "split_group_id", "source_class", "source",
            "source_version", "executor", "dataset", "split", "family", "source_intent")
    metadata = {r["prefix_id"]: {key: r[key] for key in keys if key in r} for r in io.read_lines(paths["metadata"])}
    gold = {r["prefix_id"]: {c: ev.gold_label(r, c) for c in ev.CONTRACTS} for r in io.read_lines(paths["labels"])}
    outcomes = {r["episode_id"]: r for r in io.read_lines(paths["outcomes"])}
    assert set(compact) == set(metadata) == set(gold)
    assert all(m.get("group_id") is not None for m in metadata.values())
    global_groups = {m["group_id"] for m in metadata.values()}
    assert len(global_groups) == 308
    results = []
    for prediction_input in source["predictions"]:
        directory = Path(prediction_input["path"])
        receipt_path = directory / "receipt.json"
        assert io.digest(io.record(receipt_path)) == prediction_input["receipt_sha256"]
        receipt = io.read_json(receipt_path)
        assert receipt["labels_opened"] is False and receipt["fit_called"] is False
        for key in ("observations_sha256", "metadata_sha256"):
            assert receipt[key] == source[key]
        files = defaultdict(list)
        for item in receipt["files"]:
            if item["method"] in selected:
                files[item["method"]].append(item)
        for name, shards in files.items():
            expected = selected[name]
            contract = expected["contract"]
            rows = []
            for shard in shards:
                path = directory / shard["path"]
                assert path.resolve().is_relative_to(directory.resolve())
                assert io.digest(io.record(path)) == shard["sha256"]
                count = 0
                for prediction in io.read_lines(path):
                    pid = prediction["prefix_id"]
                    assert prediction["method"] == name and prediction["contract"] == contract
                    assert prediction.get("event_seq") == compact[pid]["event_seq"]
                    joined = ev.join_record(prediction, metadata[pid], compact[pid], gold[pid][contract])
                    joined["cluster"] = metadata[pid]["group_id"]
                    rows.append(joined)
                    count += 1
                assert count == shard["rows"]
            assert len(rows) == len({r["prefix_id"] for r in rows}) == receipt["expected_eligible"][name]
            assert {r["prefix_id"] for r in rows} == eligible[contract]
            rows = ev.mark_reachability(rows)
            corrected = ev.summarize(rows, outcomes, bootstrap=args.bootstrap)
            for section, value in corrected.items():
                if section != "intervals":
                    assert value == expected[section], (name, section)
            results.append(dict(method=name, contract=contract, family=expected["family"], arm=expected.get("arm"),
                seed=expected.get("seed"), variant=expected["variant"],
                eligible_actions=len(rows), eligible_episodes=corrected["episodes"]["eligible"],
                original_source_prefixed_cluster_count=expected["intervals"]["cluster_count"],
                corrected_global_cluster_count=corrected["intervals"]["cluster_count"],
                all_point_summary_sections_exactly_equal=True, intervals=corrected["intervals"]))
            print(name, "groups", expected["intervals"]["cluster_count"], "->", corrected["intervals"]["cluster_count"], flush=True)
    assert {r["method"] for r in results} == set(selected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    io.write_json(args.output, dict(scope="51 primary seed17 raw/gated methods plus unchanged rules; all-source archive only",
        source_global_group_count=len(global_groups), bootstrap=args.bootstrap, seed=17,
        grouping="exact global metadata.group_id; no executor, cohort, source or file prefix",
        interpretation="descriptive task-group percentile bootstrap, not an IID task-population confidence interval",
        supersedes="source-prefixed archive intervals for these51 all-source methods; all other original archive source/split/seed/diagnostic intervals are withheld from report claims",
        point_estimates="every returned point-summary section equals original scorer exactly; full-registry point bounds remain unchanged in original scores",
        methods=results, source_sha256=io.INPUTS))
    print("PASS", len(results), "primary methods; all point estimates unchanged")


if __name__ == "__main__":
    main()
