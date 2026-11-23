"""Prepare and validate blinded scrutiny of source evidence for independent ratings."""
from collections import Counter, defaultdict
import csv
from math import ceil
import json

from .extract import HERE, LATEST, OUT, digest, live, wire
from .reconcile import ACTIONS, json_lines, results, stratum


PROMPT = HERE / "audit_prompt.txt"
SUPPORT = {"supported", "partially_supported", "unsupported"}


def build():
    a, b = (results(p) for p in "ab")
    rows = json_lines((OUT / "inputs.jsonl").read_text())
    groups = defaultdict(list)
    disagreements = []
    for row in rows:
        rid = row["id"]
        if a[rid]["action"] != b[rid]["action"]:
            disagreements.append(row)
        else:
            groups[(row["split"], stratum(row), a[rid]["action"])].append(row)
    matched = []
    for group in groups.values():
        ordered = sorted(group, key=lambda r: digest(f"finale-pre-fraud-source-review-v1/{r['id']}".encode()))
        matched += ordered[:ceil(.20 * len(group))]
    return disagreements, matched, a, b


def packet(item, a, b):
    rid = item["id"]
    p = item["packet"]
    blinded = item["blind_packet"]
    invoice = p["inv"]
    return {
        "id": rid, "state": blinded,
        "preboundary_source_checks": {
            "native_invoice_read": {"issued": invoice["invoice_date"], "due": invoice["due_date"],
                                    "description_and_amount_match_created_target": True,
                                    "bound_to_proposal_vendor_and_workflow_invoice": True},
            "invoice_status": {"post_invoice_update": invoice["status"],
                               "pre_fraud_assessment_and_transfer_outputs_excluded": True},
            "pre_episode_vendor_and_history": {
                "total_invoices_after_inserting_target": p["profile"]["total_invoices"],
                "paid_invoice_dates": [prior["invoice_date"] for prior in p["paid"]],
                "paid_amounts": [prior["amount"] for prior in p["paid"]],
            },
        },
        "label_a": {k: a[rid][k] for k in ("action", "checked", "missing")},
        "label_b": {k: b[rid][k] for k in ("action", "checked", "missing")},
    }


def verify_sources(rows):
    roster = {r["family"]: r for r in csv.DictReader(LATEST.open())}
    for row in rows:
        meta = roster[row["family"]]
        raw = (live.PRIVATE.with_name(meta["tranche"]) / "test" / row["source"] / "episode.json").read_bytes()
        assert digest(raw) == row["source_sha256"]
        episode = json.loads(raw)
        trace, = episode["traces"].values()
        first = next(s for s in trace["steps"] if s.get("kind") == "tool" and s.get("name") == "delegate_to_fraud")
        native = row["packet"]
        iid = native["inv"]["id"]
        assert first["arguments"] == native["proposal"]
        assert trace["task_data"]["invoice_id"] == iid
        assert episode["before"]["vendors"]["current"] == native["vendor"]
        native_read = next(s for s in trace["steps"] if s.get("name") == "get_invoice_details"
                           and s["t_ms"] <= first["t_start_ms"] and s["arguments"]["invoice_id"] == iid
                           and not s.get("error"))
        assert native_read["output"]["description"] == native["inv"]["description"]
        assert native_read["output"]["amount"] == native["inv"]["amount"]
        prior = {i["id"]: i for i in episode["before"]["invoices"]}
        assert all(prior[r["id"]] == r for r in native["paid"] if r["id"] != iid)
        status_write = [s for s in trace["steps"] if s.get("name") == "update_invoice_status"
                        and s["t_ms"] <= first["t_start_ms"] and s["arguments"]["invoice_id"] == iid
                        and (s.get("output") or {}).get("updated") is True]
        status = status_write[-1]["output"]["status"] if status_write else native_read["output"]["status"]
        assert status == native["inv"]["status"]


def main():
    disagreements, matched, a, b = build()
    by_id = {r["id"]: r for r in [*disagreements, *matched]}
    ordered = sorted(by_id.values(), key=lambda r: digest(f"source-review-order-v1/{r['id']}".encode()))
    verify_sources(ordered)
    validated = []
    batches = {}
    for i in range(0, len(ordered), 16):
        batch = [packet(row, a, b) for row in ordered[i:i+16]]
        prompt = OUT / f"source-review-{i//16:02d}.prompt"
        generated = PROMPT.read_text().encode() + b"\n\nPackets\n" + b"\n".join(map(wire, batch))
        if prompt.exists() and prompt.read_bytes() != generated:
            raise ValueError("Retained review prompt differs")
        if not prompt.exists():
            prompt.write_bytes(generated)
        result = prompt.with_suffix(".result")
        if not result.is_file():
            continue
        out = json_lines(result.read_text())
        assert [r["id"] for r in out] == [r["id"] for r in batch]
        for row in out:
            assert set(row) == {"id", "recommended_action", "a_check", "b_check", "source_check", "remaining_duty"}
            assert row["recommended_action"] in ACTIONS and row["a_check"] in SUPPORT and row["b_check"] in SUPPORT
            assert isinstance(row["source_check"], str) and row["source_check"].strip()
            assert isinstance(row["remaining_duty"], str)
        validated += out
        batches[prompt.name] = {"prompt_sha256": digest(generated), "result_sha256": digest(result.read_bytes())}
    print(f"{len(validated)}/{len(ordered)} cross-checked")
    if len(validated) != len(ordered):
        return
    gold = {r["id"]: r for r in json_lines((OUT / "gold.jsonl").read_text())}
    changed = [r for r in validated if r["recommended_action"] != gold[r["id"]]["action"]]
    review = {
        "model": "gpt-6.1-terra",
        "matching_cases_sampled": len(matched),
        "matching_cases_total": len(a) - len(disagreements),
        "matching_sample_cells": [
            {"split": key[0], "stratum": key[1], "action": key[2], "n": count}
            for key, count in sorted(Counter(
                (r["split"], stratum(r), a[r["id"]]["action"]) for r in matched).items())
        ],
        "reviewed_counts": [
            {"stratum": key[0], "gold_action": key[1], "reviewer_agrees": key[2], "n": count}
            for key, count in sorted(Counter(
                (stratum(by_id[r["id"]]), gold[r["id"]]["action"],
                 r["recommended_action"] == gold[r["id"]]["action"]) for r in validated).items())
        ],
        "disagreements_cross_checked": len(disagreements),
        "total_reviewed": len(validated),
        "deterministic_prefix_source_readback": len(ordered),
        "recommended_actions_differing_from_frozen_gold": len(changed),
        "divergence_by_stratum": dict(Counter(stratum(by_id[r["id"]]) for r in changed)),
        "source_check_batches": batches,
        "frozen_gold_sha256": digest((OUT / "gold.jsonl").read_bytes()),
    }
    (HERE / "source_review_audit.json").write_text(json.dumps(review, indent=2, sort_keys=True) + "\n")
    (OUT / "source_review.jsonl").write_bytes(b"".join(wire(r) + b"\n" for r in validated))


if __name__ == "__main__":
    main()
