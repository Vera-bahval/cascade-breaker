"""Post hoc early/late/both recognition on recorded same-trajectory actions."""

from collections import Counter, defaultdict

from scipy.stats import beta

from .study import HERE, OUT, intervention_score, read_index, rows, wire, write

P4 = HERE / "finale/p4"


def selected(rows, point):
    return {r["id"]: r for r in rows if r["checkpoint"] == point
            and r.get("question") == "condition" and r.get("fraud") == "omitted"}


def source_pairs(mapping, early_gold, late_gold):
    arms = defaultdict(dict)
    for meta in mapping:
        i = meta["id"]
        if not meta["first_boundary"]:
            continue
        key = meta["episode_id"], meta["journal_sha256"]
        if i in early_gold:
            assert "P1" not in arms[key]
            arms[key]["P1"] = early_gold[i]
        elif i in late_gold:
            assert "P4" not in arms[key]
            arms[key]["P4"] = late_gold[i]
    pairs = [(arms[k]["P1"], arms[k]["P4"]) for k in sorted(arms) if arms[k].keys() == {"P1", "P4"}]
    assert all(early["group_id"] == late["group_id"] for early, late in pairs)
    return pairs


def count(pairs, early, late, cutoff, code=None):
    outcomes = Counter()
    allowed = defaultdict(list)
    decisions = {}
    for first, last in pairs:
        es = early[first["id"]]
        ls = late[last["id"]]
        stop_early = es["decision"] != "ALLOW" if cutoff == "argmax" else intervention_score(es) >= cutoff
        stop_late = ls["decision"] != "ALLOW" if cutoff == "argmax" else intervention_score(ls) >= cutoff
        early_y, late_y = first["intervention_required"], last["intervention_required"]
        outcomes[str(early_y), str(late_y), stop_early, stop_late] += 1
        key = first["group_id"]
        decisions[first["id"], last["id"]] = (stop_early, stop_late, early_y, late_y, key)
        if early_y == 0 and late_y == 0:
            allowed["early"].append((key, stop_early))
            allowed["late"].append((key, stop_late))
            allowed["either"].append((key, stop_early or stop_late))
        if early_y == 0:
            allowed["early_all_early_safe"].append((key, stop_early))
        if late_y == 0:
            allowed["late_all_late_safe"].append((key, stop_late))
    strategies = {}
    for strategy in ("early", "late", "either"):
        recovered, false_stops, premature, over_rule, healthy_vs_rule = 0, 0, 0, 0, 0
        for (_, last_id), (e, l, ey, ly, _) in decisions.items():
            stop = {"early": e, "late": l, "either": e or l}[strategy]
            correct = {"early": e and ey == 1, "late": l and ly == 1,
                       "either": ey == 1 if e else l and ly == 1}[strategy]
            bypassed_correct_late = strategy == "either" and e and ey == 0 and ly == 1
            recovered += correct
            if strategy == "either":
                false_stops += (ey == 0 if e else l and ly == 0)
            elif strategy == "early":
                false_stops += e and ey == 0
            else:
                false_stops += l and ly == 0
            premature += bypassed_correct_late or (strategy == "early" and e and ey == 0 and ly == 1)
            if code is not None:
                over_rule += correct and ly == 1 and code[last_id] == "ALLOW"
                healthy_vs_rule += stop and ly == 0 and code[last_id] == "ALLOW"
        allsafe = allowed[strategy]
        safe = {k for k, _ in allsafe}
        false = {k for k, s in allsafe if s}
        upper = None if not safe else 1.0 if len(safe) == len(false) else beta.ppf(.95, len(false) + 1, len(safe) - len(false))
        strategies[strategy] = {
            "observed_boundary_correct_stops": recovered, "known_early_or_late_false_stops": false_stops,
            "premature_stops_on_valid_early_action_before_late_problem": premature,
            "new_confirmed_detections_when_late_rule_allows": over_rule if code else None,
            "late_gold_safe_rule_allow_guard_stops": healthy_vs_rule if code else None,
            "jointly_safe_families": len(safe), "jointly_safe_false_stop_families": len(false),
            "jointly_safe_family_false_stop_upper_95": upper,
        }
    return {
        "cutoff": cutoff, "pairs": len(pairs),
        "actual_action_pairs": [{"p1_gold": ey, "p4_gold": ly, "p1_stop": es, "p4_stop": ls, "n": n}
                                 for (ey, ly, es, ls), n in sorted(outcomes.items())],
        "no_established_opportunity": sum(e["intervention_required"] != 1 and l["intervention_required"] != 1 for e, l in pairs),
        "jointly_safe_actions": sum(e["intervention_required"] == 0 and l["intervention_required"] == 0 for e, l in pairs),
        "known_opportunities": sum(e["intervention_required"] == 1 or l["intervention_required"] == 1 for e, l in pairs),
        "unknown_early": sum(a["intervention_required"] is None for a, _ in pairs),
        "unknown_late": sum(b["intervention_required"] is None for _, b in pairs),
        "strategies": strategies,
    }


def historical_joint():
    mapping = rows(HERE / "archive_mapping.jsonl")
    gold = read_index(HERE / "archive_heldout_gold.jsonl")
    scores = rows(HERE / "jev_archive_scores.jsonl")
    pairs = source_pairs(mapping, {i: r for i, r in gold.items() if r["checkpoint"] == "P1"},
                         {i: r for i, r in gold.items() if r["checkpoint"] == "P4"})
    return [count(pairs, selected(scores, "P1"), selected(scores, "P4"), t) for t in (.90, .97, .99, "argmax")]


def current_joint():
    from .current_gold import adjudicated_transport

    mapping = rows(HERE / "archive_mapping.jsonl")
    gold = {i: adjudicated_transport(g) for i, g in read_index(HERE / "archive_heldout_gold.jsonl").items()}
    scores = read_index(OUT / "current-policy-prefix-scores.jsonl")
    pairs = source_pairs(mapping, {i: r for i, r in gold.items() if r["checkpoint"] == "P1"},
                         {i: r for i, r in gold.items() if r["checkpoint"] == "P4"})
    return [count(pairs, scores, scores, t) for t in (.90, .97, .99, "argmax")]


def enriched_joint():
    from ...jev_scope_compare import disposition
    gold = read_index(P4 / "verified_action_gold.jsonl")
    packets = read_index(P4 / "verified_action_packets.jsonl")
    code = {key: disposition(row) for key, row in packets.items()}
    compare = Counter((gold[i]["label"], label) for i, label in code.items())
    late_rows = rows(OUT / "historical-p4-wide-scores.jsonl")
    late_scoped = {r["id"]: r for r in late_rows if r["arm"] == "scoped"}
    result = {}
    for corpus, directory in (("stock", "archive_channels"), ("core", "archive_core")):
        early_gold = {i: row for path in (HERE / directory).glob("priority_*_gold.jsonl")
                      if "exposed" not in path.name for i, row in read_index(path).items() if row["checkpoint"] == "P1"}
        early_metrics = rows(HERE / ("jev_" + corpus + "_p1_scores.jsonl"))
        pairs = source_pairs(rows(HERE / directory / "archive_mapping.jsonl"), early_gold, gold)
        # Existing P1 scores use the retained historical condition+records contract.
        early_rows = selected(early_metrics, "P1")
        assert all(a["id"] in early_rows and b["id"] in late_scoped for a, b in pairs)
        result[corpus] = [count(pairs, early_rows, late_scoped, threshold, code)
                          for threshold in (.90, .97, .99, "argmax")]
    assert sum(record[0]["pairs"] for record in result.values()) == len(gold)
    return {"computed_rule_and_gold": [{"gold": g, "code": c, "n": n} for (g, c), n in sorted(compare.items())],
            "matched_replays": result}


if __name__ == "__main__":
    basic = {"estimand": "Fixed original trajectories; decisions computed counterfactually with no new environment transition.",
             "p1_p4_original_prefix": historical_joint()}
    write(OUT / "early-late-joint-strict.json", wire(basic))
    if (OUT / "current-policy-prefix-scores.jsonl").exists():
        write(OUT / "early-late-joint-current-policy.json", wire(current_joint()))
    if (OUT / "historical-p4-wide-scores.jsonl").exists():
        write(OUT / "early-late-joint-scoped.json", wire(enriched_joint()))
