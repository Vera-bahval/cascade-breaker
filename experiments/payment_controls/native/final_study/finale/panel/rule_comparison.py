"""Compare the frozen Jev decisions with a literal invoice-scoped HOLD/ESCALATE rule."""

from collections import Counter, defaultdict

from .current_gold import adjudicated_transport
from .study import OUT, intervention_score, pair, read_index, wire, write

THRESHOLD = .97


def invoice_flag(packet):
    records = packet["state"]["records"]
    if records.get("observed_hold_release") is not None:
        return False
    return any(row["recommended_action"] in {"hold", "escalate"} for row in records["fraud_flags"])


def run(include_alternative=False):
    input_pairs = pair("archive_heldout_packets.jsonl", "archive_heldout_gold.jsonl")
    scored = read_index(OUT / "current-policy-prefix-scores.jsonl")
    alternate = read_index(OUT / "current-policy-alternative-scores.jsonl") if include_alternative else {}
    indexed = []
    aggregate = defaultdict(Counter)
    cases = defaultdict(Counter)
    for packet, original_gold in input_pairs:
        gold = adjudicated_transport(original_gold)
        identity = gold["id"]
        point = packet["checkpoint"]
        reference = gold["intervention_required"]
        rule = invoice_flag(packet)
        jev = intervention_score(scored[identity]) >= THRESHOLD
        alt = intervention_score(alternate[identity]) >= THRESHOLD if include_alternative else None
        entry = {"id": identity, "checkpoint": point, "family": gold["group_id"], "gold": reference,
                 "reason_code": gold["reason_code"], "invoice_hold_or_escalate": rule,
                 "jev": jev, "alternative": alt,
                 "selected_score": intervention_score(scored[identity]),
                 "alternative_score": intervention_score(alternate[identity]) if include_alternative else None}
        indexed.append(entry)
        counts = aggregate[point, str(reference)]
        counts.update({"actions": 1, "rule": rule, "selected_jev": jev, "both": rule and jev,
                       "rule_only": rule and not jev, "selected_jev_only": jev and not rule,
                       "neither": not rule and not jev})
        if include_alternative:
            counts.update({"alternative": alt, "alternative_only_vs_rule": alt and not rule,
                           "selected_only_vs_alternative": jev and not alt,
                           "alternative_only_vs_selected": alt and not jev})
        if reference == 1 and jev and not rule:
            cases[point]["selected_jev_only/" + gold["reason_code"]] += 1
        if reference == 1 and rule and not jev:
            cases[point]["rule_only/" + gold["reason_code"]] += 1
    suffix = "with-alternative" if include_alternative else "selected-transferable"
    write(OUT / f"rule-comparison-{suffix}-decisions.jsonl", b"".join(wire(row) + b"\n" for row in indexed))
    result = {
        "definition": "Stop on a currently observed invoice-scoped HOLD or ESCALATE tool flag, excluding release. "
                      "This literal comparator does not read the action's conditional wording or narrative Fraud text. "
                      "The separate historical scoped mechanical TaxCalc rule is evaluated separately.",
        "threshold": THRESHOLD,
        "cells": [dict(counts, checkpoint=p, gold=y) for (p, y), counts in sorted(aggregate.items())],
        "discordant_positive_reasons": cases,
    }
    write(OUT / f"rule-comparison-{suffix}.json", wire(result))
    return result


if __name__ == "__main__":
    print(wire(run()).decode())
    if (OUT / "current-policy-alternative-scores.jsonl").exists():
        print(wire(run(include_alternative=True)).decode())
