"""Account for the original finale runtime by intent-to-treat, retry, arm and position."""

import argparse
from collections import defaultdict
from contextlib import closing
import gzip
import json
import math
from pathlib import Path
import sqlite3
from statistics import mean, median


def ledger(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return {key: (status, reserve, cost) for key, status, reserve, cost in db.execute(
            "SELECT id,status,reserve,cost FROM requests"
        )}


def audit(runtime):
    original = json.loads((runtime / "complete-readback.json").read_text())
    payments_book = ledger(runtime / "test/executor.sqlite")
    guard_book = ledger(runtime / "jev/ledger.sqlite")
    rows = []
    ids = set()
    guard_ids = set()
    for request_path in sorted((runtime / "test").glob("*/calls.jsonl.gz")):
        path = request_path.with_name("episode.json")
        interrupted = not path.exists()
        if interrupted:
            # A retry retains its failed predecessor's assignment manifest.
            retry = path.parent.with_name(path.parent.name + ".retry-1") / "episode.json"
            obj = json.loads(retry.read_text())
        else:
            obj = json.loads(path.read_text())
        arm = obj["arm"]
        group = obj["cell"]
        counts = defaultdict(int)
        cost = 0
        unknown = 0
        latency = 0
        with gzip.open(request_path, "rt") as stream:
            for row in map(json.loads, stream):
                if row["event"] == "request":
                    counts["requests"] += 1
                    ident = row["attempt_id"]
                    if ident in ids:
                        raise ValueError("Repeated provider transaction")
                    ids.add(ident)
                    status, reserve, charge = payments_book[ident]
                    if status == "unknown":
                        unknown += 1
                    if charge is None:
                        counts["reserve"] += reserve
                    else:
                        cost += charge
                elif row["event"] == "response" and row["http_status"] == 200:
                    latency += row.get("latency_s") or 0
                elif row["event"] == "accounting":
                    counts["accounted"] += 1
                    counts["input_tokens"] += row["input_tokens"] or 0
                    counts["cached_tokens"] += row["cached_tokens"] or 0
        config = path.with_name("verifier.json")
        judge = 0
        if config.exists():
            for obs in json.loads(config.read_text()):
                if not obs["result"]:
                    continue
                key = obs["packet"]["id"]
                judge += guard_book[key][2]
                guard_ids.add(key)
        config = path.with_name("pre-fraud-jev.jsonl")
        if config.exists():
            for obs in map(json.loads, config.read_text().splitlines()):
                if not obs.get("result"):
                    continue
                key = obs["result"]["occurrence"]
                judge += guard_book[key][2]
                guard_ids.add(key)
        rows.append({"assignment": path.parent.name, "arm": arm, "group": group["kind"],
                     "family": group["family"], "position": group["order"].index(arm) + 1,
                     "attempt": 0 if interrupted else obj["attempt"],
                     "technical": bool(interrupted or unknown or obj["operational"]["transport_errors"]
                                       or obj["technical_judge_errors"]),
                     "wall_seconds": None if interrupted else obj["seconds"], "provider_response_seconds": latency,
                     "eliza_usd": cost, "jev_usd": judge, **counts})
    legacy_continuations = {}
    for path in sorted((runtime / "continuation").glob("*/calls.jsonl.gz")):
        with gzip.open(path, "rt") as stream:
            attempts = [r["attempt_id"] for r in map(json.loads, stream) if r["event"] == "request"]
        if ids.intersection(attempts) or any(payments_book[key][0] != "completed" for key in attempts):
            raise ValueError("Unsettled or ambiguous legacy continuation")
        legacy_continuations[path.parent.name] = {
            "requests": len(attempts), "eliza_usd": sum(payments_book[key][2] for key in attempts)
        }
        ids.update(attempts)
    if ids != set(payments_book) or guard_ids != set(guard_book):
        raise ValueError(f"Episode receipt mismatch: {len(ids)=} {len(payments_book)=} {len(guard_ids)=} {len(guard_book)=}")
    for key, meter in (("eliza_usd", "eliza"), ("jev_usd", "jev")):
        if not math.isclose(sum(row[key] for row in rows), original["meters"][meter]["settled_usd"], abs_tol=1e-9):
            raise ValueError("Costs differ from original independently reconciled totals")

    def summarize(records):
        return {"attempts": len(records), "technical": sum(r["technical"] for r in records),
                "provider_requests": sum(r["requests"] for r in records),
                "accounted_requests": sum(r["accounted"] for r in records),
                "eliza_usd": round(sum(r["eliza_usd"] for r in records), 12),
                "jev_usd": round(sum(r["jev_usd"] for r in records), 12),
                "open_reserve_usd": round(sum(r.get("reserve", 0) for r in records), 12),
                "mean_episode_s": round(mean(r["wall_seconds"] for r in records if r["wall_seconds"] is not None), 3),
                "median_episode_s": round(median(r["wall_seconds"] for r in records if r["wall_seconds"] is not None), 3),
                "mean_recorded_response_s_per_episode": round(mean(r["provider_response_seconds"] for r in records), 3),
                "cached_input_token_fraction": round(sum(r.get("cached_tokens", 0) for r in records)
                                                      / sum(r.get("input_tokens", 0) for r in records), 5)}

    main = [r for r in rows if not r["attempt"] and r["group"] == "main"]
    families = {r["family"] for r in main} - {r["family"] for r in main if r["technical"]}
    paired = [r for r in main if r["family"] in families]
    assert len(paired) == len(families) * 5
    arms = "ABCDE"
    by_family = defaultdict(dict)
    for r in paired:
        by_family[r["family"]][r["arm"]] = r
    return {
        "original_freeze_sha256": original["freeze_sha256"],
        "legacy_continuations_separate": legacy_continuations,
        "all_first_attempts": summarize([r for r in rows if not r["attempt"]]),
        "main_first_by_arm": {a: summarize([r for r in main if r["arm"] == a]) for a in arms},
        "repeat_first": summarize([r for r in rows if not r["attempt"] and r["group"] == "repeat"]),
        "retry_or_interrupted_attempts": [r for r in rows if r["attempt"] or r["technical"]],
        "complete_first_attempt_families": len(families),
        "complete_first_attempt_by_arm": {a: summarize([r for r in paired if r["arm"] == a]) for a in arms},
        "complete_first_attempt_paired_median_seconds_minus_A": {
            a: round(median(group[a]["wall_seconds"] - group["A"]["wall_seconds"]
                            for group in by_family.values()), 3) for a in "BCDE"
        },
        "complete_first_attempt_by_assignment_position": {
            str(position): summarize([r for r in paired if r["position"] == position])
            for position in range(1, 6)
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.runtime), indent=2, sort_keys=True))
