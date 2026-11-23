"""Reconcile all settled TypeSafe panel occurrences with the preceding immutable scores."""

from decimal import Decimal

from .study import OUT, PRIVATE_OUT, billing_entries, read, rows, wire, write

ORDER = (
    "bc-development", "prefraud-development", "prefraud-heldout", "historical-development",
    "historical-p4-balanced", "historical-p1", "current-policy-prefix", "current-policy-scoped-safe",
    "historical-p4-wide", "current-policy-alternative",
)
NANO_USD_PER_TOKEN = 42


def dollars(tokens):
    return str(Decimal(tokens * NANO_USD_PER_TOKEN) / Decimal(10 ** 9))


def audit():
    ledger = billing_entries(PRIVATE_OUT / "transport/ledger.sqlite")
    seen, stages = set(), []
    for stage in ORDER:
        path = OUT / f"{stage}-scores.jsonl"
        if not path.exists():
            continue
        by_key = {r["occurrence"]: r for r in rows(path)}
        cache = {k for k, r in by_key.items() if r["historical_cache_record"] is not None}
        assert not cache.intersection(ledger)
        settled = by_key.keys() & ledger.keys()
        new = settled - seen
        tokens = sum(by_key[key]["usage"]["input_tokens"] for key in new)
        stage_meters = read(OUT / f"{stage}-meter.json")
        assert stage_meters["unique_panel_paid"] == len(settled)
        assert all(ledger[key][2] == "complete" for key in settled)
        stages.append({
            "stage": stage, "cells": stage_meters["projected_cells"],
            "new_calls": len(new), "new_input_tokens": tokens, "new_usd": dollars(tokens),
            "prior_exact_cache_unique": len(cache), "panel_exact_cache_unique": len(settled & seen),
            "within_stage_identical_body_cells": stage_meters["projected_cells"] - len(by_key),
        })
        seen.update(settled)
    outstanding = [entry[0] for entry in ledger.values() if entry[2] != "complete"]
    if set(ledger) - seen or outstanding or len(stages) != len(ORDER):
        raise ValueError("Panel dispatch or score publication remains incomplete")
    total = sum(row["new_input_tokens"] for row in stages)
    assert round(sum(entry[1] for entry in ledger.values()) * 10**9) == NANO_USD_PER_TOKEN * total
    summary = {"stages": stages, "calls": len(ledger), "input_tokens": total, "total_new_usd": dollars(total),
               "outstanding_attempts": 0, "outstanding_reserved_usd": "0", "eliza_usd": "0"}
    write(OUT / "panel_costs_final.json", wire(summary))
    return summary


if __name__ == "__main__":
    print(wire(audit()).decode())
