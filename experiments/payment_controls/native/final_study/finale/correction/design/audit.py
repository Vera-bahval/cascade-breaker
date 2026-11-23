"""Read-only independent audit for the frozen first-assignment cohort."""

import itertools
import json
import statistics
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

HERE = Path(__file__).resolve().parent
FINALE = HERE.parent.parent
ROOT = FINALE.parents[4]
RUNTIME = ROOT / ".runtime/payment-controls-chp3/final-study-payment-finale"
ARMS = "ABCDE"
ENDPOINTS = ("financial", "notification", "procedural", "source_fulfillment", "wrong_stop")
CONTRASTS = ("BC", "BA", "CA", "ED", "EA", "DA")
COST_FIELDS = (
    "total_cost_usd", "attempted_cost_usd", "operational_cost_with_retries_usd", "elapsed_seconds"
)


def read(path):
    return json.loads(path.read_text())


def outcomes(rows):
    return {key: Counter(str(row.get(key)) for row in rows) for key in ENDPOINTS}


def pair_stats(cells, endpoint):
    scores = {}
    for left, right in CONTRASTS:
        counts = Counter(
            (arms[left].get(endpoint), arms[right].get(endpoint)) for arms in cells
        )
        known = sum(
            n for (a, b), n in counts.items() if a in ("MET", "VIOLATED") and b in ("MET", "VIOLATED")
        )
        first = counts["VIOLATED", "MET"]
        second = counts["MET", "VIOLATED"]
        scores[left + right] = {
            "known": known, "first_only": first, "second_only": second,
            "unknown": len(cells) - known,
            "difference_per_100": 100 * (first - second) / known if known else None,
        }
    return scores


def summarize(cells, endpoint="financial"):
    return {
        "families": len(cells),
        "arms": {arm: outcomes([arms[arm] for arms in cells]) for arm in ARMS},
        "pairs": pair_stats(cells, endpoint),
    }


def pre_overlay(row, overlay):
    fields = row.get(overlay, {})
    return {**row, **{key: fields[key] for key in ENDPOINTS if key in fields}}


def mean(values):
    return statistics.fmean(values) if values else None


def order_stats(cells):
    return {
        str(position): {
            arm: {
                "n": len(rows),
                "observed_financial": Counter(row["financial"] for row in rows),
                "mean_cost_usd": mean([row["total_cost_usd"] for row in rows if row["total_cost_usd"] is not None]),
                "mean_elapsed_seconds": mean([row["elapsed_seconds"] for row in rows if row["elapsed_seconds"] is not None]),
            }
            for arm in ARMS
            if (rows := [arms[arm] for arms in cells if arms[arm]["position"] == position])
        }
        for position in range(1, len(ARMS) + 1)
    }


def paired_resources(cells):
    result = {}
    for left, right in CONTRASTS:
        result[left + right] = {}
        for field in COST_FIELDS:
            diff = [
                arms[left][field] - arms[right][field]
                for arms in cells
                if arms[left][field] is not None and arms[right][field] is not None
            ]
            result[left + right][field] = {"paired": len(diff), "mean_difference": mean(diff)}
    return result


def policy_audit(rows_by_family, frozen):
    path = FINALE / "correction/policy/assignment-overlay.jsonl"
    revised = {row["assignment"]: row for row in map(json.loads, path.read_text().splitlines())}
    assert len(revised) == sum(map(len, rows_by_family.values()))
    cohorts = defaultdict(list)
    transitions = defaultdict(Counter)
    for family, arms in rows_by_family.items():
        cell = frozen[family]["cell"]
        updated = {}
        for arm, original in arms.items():
            row = revised[original["assignment"]]
            assert row["family"] == family and row["arm"] == arm
            assert row["prior_gold"]["financial"] == original["financial"]
            updated[arm] = {
                **original,
                "financial": row["financial"],
                "wrong_stop": row["wrong_stop"],
            }
            transitions[arm][f"{original['financial']} -> {row['financial']}"] += 1
        cohorts[cell["source_path"], cell["channel"]].append(updated)

    def policy_counts(cells):
        return {
            "families": len(cells),
            "financial": {arm: Counter(arms[arm]["financial"] for arms in cells) for arm in ARMS},
            "false_stop": {arm: Counter(str(arms[arm]["wrong_stop"]) for arms in cells) for arm in ARMS},
            "financial_pairs": pair_stats(cells, "financial"),
        }

    cells = list(itertools.chain.from_iterable(cohorts.values()))
    return {
        "sha256": sha256(path.read_bytes()).hexdigest(),
        "overall": policy_counts(cells),
        "financial_transitions": transitions,
        "by_source_channel": {
            f"{source} | {channel}": policy_counts(group)
            for (source, channel), group in sorted(cohorts.items())
        },
        "leave_one_source_out": {
            source: policy_counts(list(itertools.chain.from_iterable(
                group for (other, _), group in cohorts.items() if other != source
            )))
            for source in sorted({source for source, _ in cohorts})
        },
        "relative_order": {
            left + right: {
                "left_first": pair_stats(
                    [arms for arms in cells if arms[left]["position"] < arms[right]["position"]],
                    "financial",
                )[left + right],
                "right_first": pair_stats(
                    [arms for arms in cells if arms[left]["position"] > arms[right]["position"]],
                    "financial",
                )[left + right],
            }
            for left, right in CONTRASTS
        },
    }


def main():
    freeze_path = RUNTIME / "freeze.json"
    outcome_path = FINALE / "review/assignment_outcomes.json"
    groups = read(freeze_path)["groups"]
    frozen = {entry["cell"]["family"]: entry for entry in groups if entry["cell"]["kind"] == "main"}
    rows_by_family = defaultdict(dict)
    planned_repeats = []
    for row in read(outcome_path):
        if row["kind"] == "repeat":
            planned_repeats.append(row)
            continue
        entry = frozen[row["family"]]
        assert row["source_cell"] == entry["cell"]["key"] and row["channel"] == entry["cell"]["channel"]
        assert row["replicate"] == 1 and row["arm"] not in rows_by_family[row["family"]]
        rows_by_family[row["family"]][row["arm"]] = {
            **row, "position": entry["arms"].index(row["arm"]) + 1,
        }
    cells = list(rows_by_family.values())
    assert len(cells) == len(frozen) == 221
    assert all(set(arms) == set(ARMS) for arms in cells)

    by_source_channel = defaultdict(list)
    for family, arms in rows_by_family.items():
        cell = frozen[family]["cell"]
        source = cell["source_path"]
        by_source_channel[source, cell["channel"]].append(arms)
    sources = sorted({source for source, _ in by_source_channel})

    pre_duties = {
        family: {arm: pre_overlay(row, "before_mandatory_duties_revision") for arm, row in arms.items()}
        for family, arms in rows_by_family.items()
    }
    blind = {
        family: {arm: pre_overlay(row, "first_review_outcomes") for arm, row in arms.items()}
        for family, arms in pre_duties.items()
    }
    overlays = {}
    for name, before, after, field in (
        ("structured", blind, pre_duties, "first_review_outcomes"),
        ("duties", pre_duties, rows_by_family, "before_mandatory_duties_revision"),
    ):
        overlays[name] = {}
        for arm in ARMS:
            touched = [family for family in before if field in after[family][arm]]
            overlays[name][arm] = {
                "reviewed": len(touched),
                "transition": {
                    key: Counter(
                        f"{before[f][arm].get(key)} -> {after[f][arm].get(key)}"
                        for f in touched if before[f][arm].get(key) != after[f][arm].get(key)
                    ) for key in ENDPOINTS
                },
            }

    terminal_order_disagreements = []
    for family, entry in frozen.items():
        arms = rows_by_family[family]
        terminal = {}
        for arm, row in arms.items():
            path = RUNTIME / "test" / row["assignment"] / "episode.json"
            if path.exists():
                terminal[arm] = read(path)["completed_at"]
        expected = [arm for arm in entry["arms"] if arm in terminal]
        if expected != sorted(terminal, key=terminal.get):
            terminal_order_disagreements.append(family)

    state_hashes = [[row.get("initial_state_sha256") for row in arms.values()] for arms in cells]
    complete_hashes = [values for values in state_hashes if all(values)]
    result = {
        "inputs": {
            "freeze_sha256": sha256(freeze_path.read_bytes()).hexdigest(),
            "assignment_outcomes_sha256": sha256(outcome_path.read_bytes()).hexdigest(),
        },
        "initial_state": {
            "all_five_available": len(complete_hashes),
            "all_five_equal": sum(len(set(values)) == 1 for values in complete_hashes),
        },
        "overall": summarize(cells),
        "by_source_channel": {
            f"{source} | {channel}": summarize(group)
            for (source, channel), group in sorted(by_source_channel.items())
        },
        "leave_one_source_out": {
            source: summarize(list(itertools.chain.from_iterable(
                group for (other, _), group in by_source_channel.items() if other != source
            )))
            for source in sources
        },
        "order": {
            "position": order_stats(cells),
            "relative_order": {
                f"{left}{right}": {
                    "left_first": summarize([a for a in cells if a[left]["position"] < a[right]["position"]])["pairs"][left + right],
                    "right_first": summarize([a for a in cells if a[left]["position"] > a[right]["position"]])["pairs"][left + right],
                }
                for left, right in CONTRASTS
            },
            "terminal_order_disagreements": terminal_order_disagreements,
        },
        "overlays": overlays,
        "pre_overlays": summarize(list(blind.values())),
        "pre_duties": summarize(list(pre_duties.values())),
        "resources": paired_resources(cells),
        "unknowns": {
            field: sorted(row["assignment"] for cell in cells for row in cell.values()
                          if row.get(field) in (None, "UNKNOWN", "INSUFFICIENT"))
            for field in (*ENDPOINTS, *COST_FIELDS)
        },
        "settled_by_kind": {
            kind: {field: sum(row[field] for row in rows if row[field] is not None)
                   for field in ("attempted_executor_cost_usd", "control_cost_usd")}
            for kind, rows in (
                ("main", [row for cell in cells for row in cell.values()]),
                ("planned_repeats", planned_repeats),
                ("technical_retries", read(FINALE / "review/results.json")["technical_retries"]),
            )
        },
    }
    result["revised_policy"] = policy_audit(rows_by_family, frozen)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
