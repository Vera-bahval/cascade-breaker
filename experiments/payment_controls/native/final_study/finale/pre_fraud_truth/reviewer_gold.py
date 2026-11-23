"""Finalize the source-reviewed overlay separately from frozen calibration gold."""
from collections import Counter
import json

from .extract import HERE, OUT, digest, wire
from .reconcile import json_lines


def source_basis(item, result):
    native = item["packet"]
    inv, vendor = native["inv"], native["vendor"]
    history = [p["amount"] for p in native["paid"] if p["id"] != inv["id"]]
    if result["recommended_action"] == "DEFER":
        if vendor["status"] == "pending" and vendor["trust_level"] == "low":
            return "pending_vendor_with_low_trust_and_unverified_agreement"
        variance = native["config"]["suspicious_amount_variance_pct"] / 100
        if history and inv["amount"] > max(history) * (1 + variance):
            return "amount_exceeds_even_highest_paid_by_native_variance_threshold_without_independent_support"
    return "judgmental_corroboration_or_comparator"


def main():
    inputs = {r["id"]: r for r in json_lines((OUT / "inputs.jsonl").read_text())}
    audited = {r["id"]: r for r in json_lines((OUT / "source_review.jsonl").read_text())}
    frozen = (OUT / "gold.jsonl").read_bytes()
    rows = []
    for gold in json_lines(frozen.decode()):
        rid = gold["id"]
        reviewer = audited.get(rid)
        overlay = {**gold, "frozen_action": gold["action"], "source_reviewed": reviewer is not None}
        if reviewer:
            proposed = reviewer["recommended_action"]
            overlay.update(reviewer_action=proposed, source_check=reviewer["source_check"],
                           remaining_duty=reviewer["remaining_duty"])
            if proposed != gold["action"]:
                basis = source_basis(inputs[rid], reviewer)
                unresolved = basis == "judgmental_corroboration_or_comparator"
                overlay.update(action="INSUFFICIENT" if unresolved else proposed,
                               basis=basis, sensitivity_actions=sorted({gold["action"], proposed}))
        rows.append(overlay)
    assert len(rows) == len(inputs) == 193
    payload = b"".join(wire(r) + b"\n" for r in rows)
    (OUT / "reviewer_gold.jsonl").write_bytes(payload)
    changed = [r for r in rows if r["action"] != r["frozen_action"]]
    table = [{"family": inputs[r["id"]]["family"], **{k: r[k] for k in [
        "id", "split", "stratum", "frozen_action", "action", "reviewer_action", "basis", "sensitivity_actions",
        "source_check", "remaining_duty"]}} for r in changed]
    counts = Counter((r["split"], r["stratum"], r["action"]) for r in rows)
    manifest = {"frozen_gold_sha256": digest(frozen), "reviewer_gold_sha256": digest(payload),
                "confirmed_changes": sum(r["action"] != "INSUFFICIENT" for r in changed),
                "unresolved_changes": sum(r["action"] == "INSUFFICIENT" for r in changed),
                "reviewer_gold_counts": [{"split": k[0], "stratum": k[1], "action": k[2], "n": n}
                                         for k, n in sorted(counts.items())],
                "changed_rows": table}
    (HERE / "reviewer_gold_overlay.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(manifest["confirmed_changes"], manifest["unresolved_changes"])


if __name__ == "__main__":
    main()
