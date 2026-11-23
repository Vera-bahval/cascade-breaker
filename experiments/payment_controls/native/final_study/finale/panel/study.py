"""Pinned TypeSafe factorial panel on independently rated ordinary invoices."""

import argparse
from collections import Counter, defaultdict
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import fcntl
from hashlib import sha256
from itertools import batched
import json
from pathlib import Path
from statistics import mean

from ...jev import BOUND, JevRunner, Ledger, PINNED_MODEL, PRICE, WORKERS, billing_entries, jev_client, packet_body, registry, retain, wire
from ...archive_prepare import HERE
from ..live.adapter import LIVE_POLICY

ROOT = HERE.parents[3]
PRIVATE = ROOT / ".runtime/finbot-final-study/jev"
LIVE_SELECTION = HERE / "jev_live_selection.json"


def digest(value):
    return sha256(value).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def read_index(path):
    return {r["id"]: r for r in rows(path)}


def write(path, content):
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Immutable artifact differs: {path}")
    else:
        retain(path, content)


def intervention_score(row):
    return min(1.0, row["probabilities"]["BLOCK"] + row["probabilities"]["REVIEW"])


OUT = Path(__file__).resolve().parent
PRIVATE_OUT = PRIVATE / "finale-panel-v1"
CAP = 1.20
CHOICE = {"question": "condition", "fraud": "present"}


def pair(source_packets, source_gold):
    packets, gold = (read_index(HERE / path) for path in (source_packets, source_gold))
    assert packets.keys() == gold.keys()
    return [(packets[key], gold[key]) for key in sorted(packets)]


def dev_panels():
    p1 = pair("archive_development_packets.jsonl", "archive_development_gold.jsonl")
    legacy_groups = read(LIVE_SELECTION)["development_groups"]
    calibration_p1 = [(p, g) for p, g in p1 if p["checkpoint"] == "P1" and legacy_groups[g["group_id"]] == "cal"]
    return p1, calibration_p1


def original(packet):
    result = {key: packet[key] for key in ("id", "checkpoint", "policy", "proposed_action", "actual_fraud")}
    return {**result, "state": {"records": packet["state"]["records"]}}


def make_current(packet):
    result = deepcopy(packet)
    result["policy"] = LIVE_POLICY
    if "prior_snapshot" in packet["state"]:
        prior = packet["state"]["prior_snapshot"]
        assert prior["transaction_view_exhausted"] is True
        records = result["state"]["records"]
        records["prior_transfer_history_complete"] = True
        records["observed_completed_transfers_in_prefix"] = prior["target_prior_completed_transfer_count"]
    return result


def make_item(identity, body, key=None):
    request = wire(body)
    request_hash = digest(request)
    occurrence = key or digest(wire([identity, request_hash]))
    return ({}, occurrence, request_hash, body, request)


def read_retained(transport, identity, body, occurrence):
    item = make_item(identity, body, occurrence)
    assert (transport.directory / (occurrence + ".request")).read_bytes() == item[4]
    entry = billing_entries(transport.directory / "ledger.sqlite")[occurrence]
    return transport.read(item, entry)


def rates(rows, threshold):
    assert all(g["intervention_required"] in (0, 1) for _, g in rows)
    positives, negatives = ([ (r, g) for r, g in rows if g["intervention_required"] == value ]
                             for value in (1, 0))
    detected = [g for r, g in positives if intervention_score(r) >= threshold]
    stopped = [g for r, g in negatives if intervention_score(r) >= threshold]
    safe_groups = {g["group_id"] for _, g in negatives}
    false_groups = {g["group_id"] for g in stopped}
    assert safe_groups and positives
    return {"actions": len(rows), "safe": len(negatives), "false_stops": len(stopped),
            "intervention": len(positives), "detected": len(detected), "safe_groups": len(safe_groups),
            "false_stop_groups": len(false_groups), "family_fpr": len(false_groups) / len(safe_groups),
            "family_fpr_upper_95": 1 - .05 ** (1 / len(safe_groups)) if not false_groups else None}


def freeze_selection():
    original_dev, p1 = dev_panels()
    p4_path = HERE / "finale/p4/gold_dev.jsonl"
    p4_packets = p4_path.with_name("blind_dev.jsonl")
    scoped_p4 = pair(p4_packets, p4_path)
    p4 = [(p, g) for p, g in scoped_p4 if g["intervention_required"] == 0]
    p4 += [(p, g) for p, g in original_dev if p["checkpoint"] == "P4" and g["label"] == "BLOCK"]
    old_heldout = {r["group_id"] for r in rows(HERE / "archive_p4_sensitivity/priority_gold.jsonl")}
    assert not {gold["group_id"] for _, gold in p4}.intersection(old_heldout)
    assert len(p4) == 18
    jobs = [(packet, gold, arm, request) for packet, gold in p1 + p4
            for arm, request in variants(make_current(packet), extra=False).items()]
    results, _ = dispatch("bc-development", jobs)
    by_id = {gold["id"]: gold for _, gold in p1 + p4}
    cache = {k: [(r, by_id[r["id"]]) for r in results if r["checkpoint"] == k and r["arm"] == "fraud"]
             for k in ("P1", "P4")}
    evidence = [{key: r[key] for key in ("id", "group_id", "checkpoint", "request_sha256", "response_sha256")}
                for r in results if r["arm"] == "fraud"]
    candidates = [{"threshold": threshold, "checkpoints": {k: rates(v, threshold) for k, v in cache.items()}}
                  for threshold in (.90, .97)]
    best = min(candidates, key=lambda r: (
        max(m["family_fpr"] for m in r["checkpoints"].values()),
        -sum(m["detected"] for m in r["checkpoints"].values()), -r["threshold"]))
    freeze = {"model": PINNED_MODEL, **CHOICE, "threshold": best["threshold"],
              "boundary": {"B": "P1", "C": "P4"}, "score": "P(BLOCK)+P(REVIEW)",
              "state_projection": "finale.live.adapter.project and final_study.jev.packet_body under current FinStripe policy.",
              "p4_label_scope": "Development-only confirmed HOLD blocks and independently verified ALLOW. Historical missing Payments TaxCalc reviews are excluded under current native FinStripe’s internal tax contract.",
              "method": "Minimize maximum empirical family false-stop rate across P1/P4, then maximize detections, then prefer .97.",
              "candidates": candidates, "calibration_receipts": evidence,
              "factorial_scores_sha256": digest((OUT / "bc-development-scores.jsonl").read_bytes()),
              "template_sha256": digest((HERE / "jev.py").read_bytes()),
              "projection_sha256": digest((HERE / "finale/live/adapter.py").read_bytes()),
              "gold_sha256": {path: digest((HERE / path).read_bytes()) for path in (
                 "archive_development_gold.jsonl", str(p4_path.relative_to(HERE)))}}
    write(OUT / "bc_selection.json", wire(freeze))
    return freeze


def rows(path):
    with path.open() as source:
        return list(map(json.loads, source))


def plain_state(state):
    """Render identical keyed facts as quotations and plain lines, preserving all values."""
    def lines(path, value):
        if isinstance(value, Mapping) and value:
            for key, child in value.items():
                yield from lines((*path, key), child)
        else:
            yield ".".join(path) + " = " + wire(value).decode()

    return "\n".join(lines((), state))


def variants(packet, extra=True):
    sanitized = original(packet)
    full = packet_body(sanitized, **CHOICE)
    structural = packet_body(sanitized, CHOICE["question"], "omitted")
    literal = {**structural, "state": {k: v for k, v in structural["state"].items() if k != "records"}}
    variants = {
        "action_policy": literal,
        "records": structural,
        "fraud": full,
        "prose": {**full, "state": plain_state(full["state"])},
        "direct": packet_body(sanitized, "direct", "present"),
    }
    facts_arm = "fraud"
    if extra and "request_scope" in packet:
        prior = packet["state"]["prior_snapshot"]
        assert prior["transaction_view_exhausted"] is True
        assert type(prior["target_prior_completed_transfer_count"]) is int
        variants["scoped"] = {**full, "state": {
            **full["state"], "prior_snapshot": prior, "request_scope": packet["request_scope"],
            "additional_evidence_scope": packet["additional_evidence_scope"],
        }}
        facts_arm = "scoped"
    masked = deepcopy(variants[facts_arm])
    records = masked["state"]["records"]
    if sanitized["checkpoint"] == "P1":
        # The written restriction can appear in both the linked result and its structured flag.
        masked["state"].pop("actual_fraud", None)
        for field in ("fraud_flags", "observed_hold_release"):
            records.pop(field, None)
    else:
        records.pop("tax_verifications", None)
        # Mask the availability/mandate and its verification jointly.
        masked["state"].pop("request_scope", None)
    variants["masked"] = masked
    assert "records" not in literal["state"]
    assert wire(variants["fraud"]["questions"]) == wire(variants["prose"]["questions"])
    return variants


def cache_records():
    history = [*HERE.glob("jev*_scores.jsonl")]
    old = defaultdict(list)
    for path in history:
        for row in rows(path):
            if all(key in row for key in ("id", "request_sha256", "occurrence", "response_sha256")):
                old[row["id"], row["request_sha256"]].append((row["occurrence"], row["response_sha256"], path.name))
    wire_paths = {}
    for path in PRIVATE.rglob("*.request"):
        if not path.is_relative_to(PRIVATE_OUT) and path.with_suffix(".response").is_file():
            wire_paths[path.stem] = path
    return old, wire_paths


def dispatch(stage, jobs):
    PRIVATE_OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    runner = JevRunner(PRIVATE_OUT / "transport", CAP)
    old, wire_paths = cache_records()
    planned = []
    for packet, gold, arm, request in jobs:
        ident = gold["id"]
        item = make_item(ident, request)
        planned.append((item, {"id": ident, "checkpoint": packet["checkpoint"], "group_id": gold["group_id"], "arm": arm,
                               "request_sha256": item[2]}))
    freeze = {"stage": stage, "model": PINNED_MODEL, "panel_cap_new_usd": CAP, "price_usd_per_input_token": PRICE,
              "code_sha256": digest(Path(__file__).read_bytes()), "jobs": [metadata for _, metadata in planned]}
    freeze_file = OUT / f"{stage}-freeze.json"
    write(freeze_file, wire(freeze))
    observed, sources, pending = {}, {}, {}
    with (runner.directory / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = Ledger(runner.directory / "ledger.sqlite", CAP)
        prior = billing_entries(ledger.path)
        if any(entry[2] != "complete" for entry in prior.values()):
            raise RuntimeError("Unreconciled TypeSafe attempt remains reserved")
        before = set(prior)
        old_ledgers = {}
        for item, metadata in planned:
            _, key, dig, body, encoded = item
            if key in observed or key in pending:
                continue
            if key in prior:
                assert (runner.directory / (key + ".request")).read_bytes() == encoded
                observed[key] = runner.read(item, prior[key])
                continue
            for occurrence, response_digest, source in old[metadata["id"], dig]:
                saved = wire_paths.get(occurrence)
                if saved is None or saved.read_bytes() != encoded:
                    continue
                parent = saved.parent
                old_ledger = old_ledgers.setdefault(parent, billing_entries(parent / "ledger.sqlite"))
                if old_ledger.get(occurrence, (None, None, None))[2] != "complete":
                    continue
                readback = JevRunner(parent, CAP).read(make_item(metadata["id"], body, occurrence), old_ledger[occurrence])
                assert readback["response_sha256"] == response_digest
                observed[key] = readback
                sources[key] = source
                break
            else:
                request = runner.directory / (key + ".request")
                if request.exists():
                    assert request.read_bytes() == encoded
                else:
                    retain(request, encoded)
                pending[key] = item
        if pending:
            with jev_client() as client, ThreadPoolExecutor(WORKERS) as pool:
                served = registry(client)
                write(PRIVATE_OUT / "registry.json", wire(served))
                for batch in batched(pending.values(), WORKERS):
                    if ledger.summary()["cost_usd"] + len(batch) * BOUND > CAP:
                        raise RuntimeError("TypeSafe panel budget would be exceeded")
                    for item in batch:
                        ledger.reserve(item[1], BOUND)
                    batch_results = {item[1]: pool.submit(runner.post, client, ledger, item) for item in batch}
                    observed.update({key: future.result() for key, future in batch_results.items()})
        accounting = billing_entries(ledger.path)
    result = [dict(observed[item[1]], **meta, occurrence=item[1],
                   historical_cache_record=sources.get(item[1])) for item, meta in planned]
    write(OUT / f"{stage}-scores.jsonl", b"".join(wire(row) + b"\n" for row in result))
    paid_ids = set(accounting) & {item[1] for item, _ in planned}
    cost = {"stage": stage, "projected_cells": len(result), "unique_old_reuses": len(sources),
            "unique_panel_paid": len(paid_ids), "stage_paid_input_tokens": sum(observed[key]["usage"]["input_tokens"] for key in paid_ids),
            "stage_paid_or_reserved_usd": sum(accounting[key][1] if accounting[key][2] == "complete"
                                              else accounting[key][0] for key in paid_ids),
            "all_panel_paid_input_tokens": round(sum(v[1] / PRICE for v in accounting.values() if v[2] == "complete")),
            "all_panel_charged_usd": sum(v[1] for v in accounting.values() if v[2] == "complete"),
            "all_panel_outstanding_reserved_usd": sum(v[0] for v in accounting.values() if v[2] != "complete")}
    write(OUT / f"{stage}-meter.json", wire(cost))
    return result, cost


def diagnostic_p1_development():
    p1, _ = dev_panels()
    return dispatch("p1-factorial-development", [(p, g, arm, body) for p, g in p1 if p["checkpoint"] == "P1"
                     for arm, body in variants(p).items()])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze-bc", "p1-dev"))
    args = parser.parse_args()
    if args.stage == "freeze-bc":
        result = freeze_selection()
        print(json.dumps({"threshold": result["threshold"], "candidates": result["candidates"]}))
    else:
        _, cost = diagnostic_p1_development()
        print(json.dumps(cost))
