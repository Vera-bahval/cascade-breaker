"""Select blinded narrative checks independently of the order of live assignments."""
from hashlib import sha256
from collections import Counter

from .adjudicate import signature
from .prepare import DECK, OLD, OUT, load, rows, write, write_rows

OPERATIVE = "verify whether operative release condition is actually supported"


def narrative_receipt(selected, overlays):
    chosen = {row["id"]: row for row in selected}
    required = {key for key, row in chosen.items() if OPERATIVE in row["tags"]}
    receipt, readings = {}, {}
    for reader in ("terra-a", "terra-b"):
        take = DECK / f"{reader}-narrative.jsonl"
        collected = {row["id"]: row for row in rows(take)}
        assert collected.keys() <= chosen.keys() and required <= collected.keys()
        receipt[reader] = {
            "sha256": sha256(take.read_bytes()).hexdigest(),
            "packets": len(collected),
            "coverage_by_overlapping_tag": dict(Counter(tag for key in collected for tag in chosen[key]["tags"])),
        }
        readings[reader] = collected
    overlap = readings["terra-a"].keys() & readings["terra-b"].keys()
    write(OUT / "narrative-review-receipt.json", {
        "selected": len(selected), "operative_priority": len(required), "both_read": len(overlap),
        "operative_read_by_both": len(required & overlap),
        "scope": "Focused manual reading of relevant retained narrative; some original appendix responses were excerpted.",
        "additional_review_status": "Both Terra readers exhausted their availability after completing all operative priorities.",
        "readers": receipt,
    })
    write_rows(OUT / "operative-narrative-adjudication.jsonl", [
        {"assignment": overlays[key]["assignment"],
         "readers": {reader: {
             "financial": collected[key]["financial"], "wrong_stop": collected[key]["wrong_stop"],
             "reason": collected[key]["reason"], "candidate_actions": collected[key]["candidate_actions"],
         } for reader, collected in readings.items()},
         "adjudicated_financial": overlays[key]["financial"],
         "adjudicated_candidates": overlays[key]["candidate_actions"],
         "adjudicated_reason": overlays[key]["financial_reason"],
         "basis_status": overlays[key]["release_condition_visibility"]}
        for key in sorted(required)
    ])


def main():
    by_id = {r["blind_id"]: r for r in load(OLD) if r["kind"] == "main"}
    index = {r["id"]: r for r in rows(DECK / "review-index.jsonl")}
    source = {r["family"]: r for r in rows(DECK / "source.jsonl")}
    census = {r["assignment"]: r for r in rows(OUT / "mechanical-census.jsonl")}
    left = {r["id"]: r for r in rows(DECK / "terra-a.jsonl")}
    right = {r["id"]: r for r in rows(DECK / "terra-b.jsonl")}
    sample = {r["id"] for r in rows(OUT / "adjudication.jsonl") if r["selection"] == "sampled_agreement"}
    overlays = {r["old_packet_id"]: r for r in rows(OUT / "assignment-overlay.jsonl")}
    selected = []
    for key, info in index.items():
        prior = by_id[key]
        flags = []
        if (overlays[key]["financial"] == "VIOLATED"
                or prior["source_disposition"] == "continue_standard_review" and prior["financial"] == "VIOLATED"):
            flags.append(OPERATIVE)
        if any(c["snapshot_violations"] or c["fraud_text_hold_tokens"]
               for c in census[prior["assignment"]]["capture_evidence"]):
            flags.append("verify review or hold wording and as-of action")
        if signature(left[key]) != signature(right[key]):
            flags.append("narrative policy-role check")
        if key in sample:
            flags.append("hash-ranked agreement control")
        if flags:
            trigger = source[prior["family"]]["trigger"].get("turns") or [
                {"message": "Ordinary new-invoice processing and follow-up notice"}]
            selected.append({**info, "tags": flags, "external_trigger": trigger})
    selected.sort(key=lambda r: (OPERATIVE not in r["tags"], r["id"]))
    write_rows(DECK / "narrative-review-index.jsonl", selected)
    if all((DECK / f"terra-{side}-narrative.jsonl").is_file() for side in "ab"):
        narrative_receipt(selected, overlays)
    print(len(selected), "narrative packets")


if __name__ == "__main__":
    main()
