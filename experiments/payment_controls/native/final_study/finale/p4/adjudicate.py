"""Draw exact blind audit rosters and seal independent P4 decisions."""
import argparse
from collections import Counter, defaultdict
import json

from ...archive_p4_sensitivity import DST
from ...archive_review import HERE, boundary_sequences, digest, draw, rows, write
from .recover import OUT

BATCHES = {
    "stock": "blind_stock_preliminary.jsonl",
    "linked": "blind_stock_linked.jsonl",
    "dev": "blind_dev.jsonl",
}
INTERVENTION = {"ALLOW": 0, "BLOCK": 1, "REVIEW": 1, "INSUFFICIENT": None}


def run(batch, finalize):
    packet_path = OUT / BATCHES[batch]
    a_path, b_path = (OUT / f"terra_{side}_{batch}.jsonl" for side in ("a", "b"))
    packets, first, second = map(rows, (packet_path, a_path, b_path))
    needed = draw(packets, first, second, False)
    audit_path = OUT / f"blind_sol_{batch}.jsonl"
    if not finalize:
        write(audit_path, (packets[k] for k in sorted(needed)))
        print(dict(Counter(needed.values())))
        return
    proof_path = OUT / f"sol_{batch}.jsonl"
    proof = rows(proof_path)
    assert set(proof) == set(needed)
    assert rows(audit_path) == {k: packets[k] for k in needed}
    links = rows(HERE / "archive_wave_family_links.jsonl")
    gold = []
    for key, packet in sorted(packets.items()):
        seq = boundary_sequences(packet)
        for review in (first[key], second[key], proof.get(key)):
            if review is not None:
                assert review["label"] in INTERVENTION and review["reason_code"]
                assert set(review["evidence_seq"]) <= seq
        row = proof.get(key, first[key])
        gold.append({**row, "checkpoint": "P4", "group_id": links[key]["obligation_group"],
                     "intervention_required": INTERVENTION[row["label"]],
                     "review_status": needed.get(key, "two_rater_agreement")})
    gold_path = OUT / f"gold_{batch}.jsonl"
    write(gold_path, gold)
    receipt = {
        "labels": dict(Counter(r["label"] for r in gold)),
        "review": dict(Counter(needed.values())),
        "sha256": {p.name: digest(p) for p in (packet_path, a_path, b_path, audit_path, proof_path, gold_path)},
    }
    (OUT / f"receipt_{batch}.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(receipt["labels"])


def publish():
    source_path = OUT / "source_recovery.jsonl"
    ledger = rows(source_path)
    prior_receipt = json.loads((DST / "priority_gold_receipt.json").read_text())
    for name, checksum in prior_receipt["sha256"].items():
        assert digest(DST / name) == checksum
    exact_gold = rows(DST / "priority_gold.jsonl")
    packets = rows(DST / "priority_packets.jsonl")
    gold = dict(exact_gold)
    if set(packets) != set(gold) or len(gold) != 48:
        raise ValueError("Exact prior gold roster mismatch")
    batches = {}
    for batch in ("stock", "linked"):
        receipt = OUT / f"receipt_{batch}.json"
        if receipt.is_file():
            batches[batch] = json.loads(receipt.read_text())
            for name, checksum in batches[batch]["sha256"].items():
                assert digest(OUT / name) == checksum
            packets.update(rows(OUT / BATCHES[batch]))
            gold.update(rows(OUT / f"gold_{batch}.jsonl"))
    certified_families = defaultdict(set)
    labels = defaultdict(Counter)
    result = []
    for key, row in sorted(ledger.items()):
        label = (gold.get(key) or {}).get("label", "INSUFFICIENT")
        count = row.get("prior_completed_target_count")
        certified = key in gold
        status = ("exact_prior_reuse" if key in exact_gold else "newly_adjudicated") if certified else (
            "awaiting_certified_review" if count is not None else "unrecoverable_from_archived_as_of_evidence")
        result.append({**row, "as_of_label": label, "as_of_status": status,
                       "defender_visible_label": row["strict_label"]})
        labels[row["wave"]][label] += 1
        if certified:
            certified_families[label].add(row["group_id"])
    ledger_result = OUT / "recovery_table.jsonl"
    write(ledger_result, result)

    usable = [key for key, row in gold.items() if row["label"] != "INSUFFICIENT"]
    packet_path = OUT / "verified_action_packets.jsonl"
    gold_path = OUT / "verified_action_gold.jsonl"
    write(packet_path, (packets[k] for k in sorted(usable)))
    write(gold_path, (gold[k] for k in sorted(usable)))
    summary = {
        "strict_heldout_target": len(ledger),
        "exact_prior_panel_reused": len(exact_gold),
        "exact_prior_panel_in_target": len(set(exact_gold) & set(ledger)),
        "exact_prior_panel_outside_target": len(set(exact_gold) - set(ledger)),
        "defender_visible_labels": dict(Counter(r["defender_visible_label"] for r in result)),
        "as_of_labels": dict(Counter(r["as_of_label"] for r in result)),
        "as_of_status": dict(Counter(r["as_of_status"] for r in result)),
        "as_of_certified_families_by_label": {k: len(v) for k, v in certified_families.items()},
        "as_of_labels_by_wave": {k: dict(v) for k, v in labels.items()},
        "verified_action_panel_labels": dict(Counter(gold[k]["label"] for k in usable)),
        "batch_receipts_sha256": {batch: digest(OUT / f"receipt_{batch}.json") for batch in batches},
        "sha256": {p.name: digest(p) for p in (source_path, ledger_result, packet_path, gold_path)},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("stage", "finalize", "publish"))
    parser.add_argument("batch", nargs="?", choices=BATCHES)
    args = parser.parse_args()
    if args.mode == "publish":
        publish()
    else:
        run(args.batch, args.mode == "finalize")
