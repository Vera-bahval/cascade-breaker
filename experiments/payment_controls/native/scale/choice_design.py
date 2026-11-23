"""Freeze a supplier-paired factorial over independently manipulated Choice key and wire position."""
from collections import Counter, defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from itertools import product
import json
import os
from pathlib import Path
import re
import sqlite3

from ..completion import contrast as old
from ..completion.jev_choice import PINNED_MODEL

HERE = Path(__file__).parent
PRIVATE = old.RUNTIME / "scale-choice-v1"
PACKET = PRIVATE / "rater-packet.json"
CAP = .09
REPLICATES = 24
WORKERS = 8
LABELS = old.LABELS
LETTERS = old.LETTERS
PHASES = old.prior.PHASES
QUESTIONS = {"original": old.prior.QUESTION, "focused": old.FOCUSED}
POLICY = {
    "families": "Six authentic prior-sibling vendor families per status_fixture x SQLite linkage stratum.",
    "wire": "Three cyclic semantic-to-letter assignments crossed with three cyclic semantic insertion orders; independent.",
    "arms": "Original/focused x full/without_finstripe within each family. Only missing-receipt arm targets DEFER.",
    "pairing": "Compare all three level pairs for one factor while holding the others fixed.",
    "effects": [
        "Total variation on semantic distributions, semantic choice flips, absolute paired errors and gold log-loss deltas.",
        "Signed error and log loss by level, full/ablated and focused/original paired differences.",
        "Counts of directional choice transitions; gold correctness gains and losses by factor.",
    ],
    "inference": "Within-family summaries; 10000 percentile bootstrap replicates stratified by four selection cells.",
    "repeats": "One prespecified repeat in each supplier family, balanced across phase and prompt, identical request bytes.",
    "floor": 1e-12,
    "seed": 645185,
    "workers": WORKERS,
}


def wire(body):
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def rotate(sequence, amount):
    return sequence[amount:] + sequence[:amount]


def prepare():
    os.umask(0o077)
    exclusions, _, inputs = old.prior_panel()
    earlier_path = old.PRIVATE / "freeze.json"
    earlier = old.read(earlier_path)
    exclusions.update(row["case_id"] for row in earlier["families"].values())
    source, plan = old.keyed("register_packets.jsonl"), old.keyed("plan.jsonl")
    ct_path = old.CT / "freeze.json"
    ct = old.read(ct_path)
    ct_jobs = {r["case_id"]: r for r in ct["jobs"]}
    assert ct["source_sha256"] == old.digest(old.DATA / "register_packets.jsonl")
    assert source.keys() == plan.keys() == ct_jobs.keys()
    older_plan_path = old.DATA.with_name("register-study-v1") / "plan.jsonl"
    older_plan = {row["case_id"]: row for row in map(json.loads, older_plan_path.read_text().splitlines())}
    all_plans = {**older_plan, **plan}
    assert exclusions <= all_plans.keys()
    excluded_vendors = {all_plans[ident]["source_vendor_group"] for ident in exclusions}
    gold_path = old.CT / "gold.json"
    old_gold = old.read(gold_path)
    exp = old.prior.HERE
    audit_path = exp / "register_ct_audit.json"
    audited = old.read(audit_path)
    rating_paths = [exp / f"register_ct_terra_{reader}.json" for reader in ("a", "b")]
    previous_index, previous_packet = [old.CT / name for name in ("rater-index.private.json", "rater-packet.json")]
    for path in [previous_index, previous_packet, *rating_paths, old.DATA / "register_packets.jsonl"]:
        assert old.digest(path) == audited["inputs_sha256"][path.name]
    previous_states = old.read(previous_packet)["states"]
    previous_keys = {r["case_id"]: key for key, r in old.read(previous_index)["index"].items() if r["phase"] == "full"}
    old_ratings = [old.read(path) for path in rating_paths]
    strata = defaultdict(list)
    assert old.digest(old.DATA / "plan.jsonl") == old.read(old.DATA / "freeze.json")["plan_sha256"]
    db_path = old.DATA / "packets.db"
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as db:
        for ident, job in ct_jobs.items():
            row = plan[ident]
            if row["source_vendor_group"] in excluded_vendors or job["source_pair_kind"] != "authentic_prior_sibling":
                continue
            gold = old.sqlite_gold(db, ident, source[ident])
            assert gold == old_gold[ident] == ("SAME" if row["linked_prior"] else "OTHER")
            strata[row["status_fixture"], gold].append(ident)
    assert set(strata) == set(product(("paid", "stale"), ("SAME", "OTHER")))

    PRIVATE.mkdir(mode=0o700)
    requests = PRIVATE / "requests"
    requests.mkdir()
    families, jobs, blind, index = {}, [], {}, {}
    selected_vendors = set()
    arms = list(product(PHASES, QUESTIONS))
    for cell_number, ((status, gold), candidates) in enumerate(sorted(strata.items())):
        ranked = sorted(candidates, key=lambda ident: old.fingerprint(["jev-choice-crossed-v1", ident]))
        within = 0
        for ident in ranked:
            vendor = plan[ident]["source_vendor_group"]
            if vendor in selected_vendors:
                continue
            selected_vendors.add(vendor)
            source_row = source[ident]
            archived = ct_jobs[ident]
            assert old.fingerprint(source_row) == archived["source_row_sha256"]
            family = old.fingerprint(["jev-choice-crossed-v1-family", vendor])
            full = archived["full"]["bodies"]["jev"]["state"]
            assert old.alias_shape(full) == old.alias_shape(old.project(source_row, 0))
            old_key = previous_keys[ident]
            aliases = {}

            def normalize(match):
                value = match[0].strip('"')
                if value not in aliases:
                    stem = next(stem for stem in ("invoice", "receipt", "vendor") if value.startswith(stem))
                    aliases[value] = f"{stem}{len(aliases):05d}"
                return json.dumps(aliases[value])

            pattern = r'"(?:invoice|receipt|vendor)[a-f0-9]{10}"'
            prior_state = json.loads(re.sub(pattern, normalize, old.prior.panel.canonical(previous_states[old_key])))
            assert old.alias_shape(prior_state) == old.alias_shape(full)
            assert all(rating[old_key]["label"] == gold and rating[old_key]["evidence"] for rating in old_ratings)
            without = archived["without_finstripe"]["bodies"]["jev"]["state"]
            key = "added_finstripe_vendor_receipt_view"
            assert {k: v for k, v in full.items() if k != key} == {k: v for k, v in without.items() if k != key}
            assert without[key] == {"available": False, "complete_at_checkpoint": False,
                                    "receipts_visible_at_checkpoint": []}
            families[family] = {"case_id": ident, "stratum": [status, gold], "source_sha256": old.fingerprint(source_row),
                                "full_gold": gold, "without_finstripe_gold": "DEFER", "previous_full_ratings_key": old_key}
            blind_key = old.fingerprint(["choice-blind-no-receipt-v1", family])[:24]
            aliases = {}
            def relabel(match):
                value = match[1]
                if value not in aliases:
                    aliases[value] = value.rstrip("0123456789") + old.fingerprint([blind_key, value])[:10]
                return json.dumps(aliases[value])
            blind[blind_key] = json.loads(old.prior.ALIAS_PATTERN.sub(relabel, old.prior.panel.canonical(without)))
            index[blind_key] = family
            rep_phase, rep_question = arms[(cell_number + within) % len(arms)]
            for phase, question, label_rot, order_rot in product(PHASES, QUESTIONS, range(3), range(3)):
                by_letter = dict(zip(LETTERS, rotate(LABELS, label_rot)))
                by_label = {label: letter for letter, label in by_letter.items()}
                order = rotate(LABELS, order_rot)
                state = full if phase == "full" else without
                expected = families[family][phase + "_gold"]
                assert old.visible_rule(state) == expected
                body = {"model": PINNED_MODEL, "state": state, "questions": {"check": {
                    "type": "choice", "instructions": QUESTIONS[question],
                    "criteria": {by_label[label]: old.prior.CRITERIA[label] for label in order},
                }}}
                request = wire(body)
                request_hash = sha256(request).hexdigest()
                with (requests / (request_hash + ".json")).open("xb") as handle:
                    handle.write(request)
                item = {"family": family, "phase": phase, "question": question,
                        "label_rotation": label_rot, "order_rotation": order_rot,
                        "by_letter": by_letter, "semantic_order": list(order), "request_sha256": request_hash}
                jobs.append({**item, "occurrence": 0, "request_id": request_hash + "-0"})
                if (phase, question, label_rot, order_rot) == (rep_phase, rep_question, within % 3, cell_number % 3):
                    jobs.append({**item, "occurrence": 1, "request_id": request_hash + "-1"})
            within += 1
            if within == 6:
                break
        assert within == 6, (status, gold, within)
    assert len(families) == len(blind) == 24
    assert len({j["request_sha256"] for j in jobs}) == 864 and len(jobs) == 864 + REPLICATES
    assert Counter((j["phase"], j["question"]) for j in jobs if j["occurrence"]) == dict.fromkeys(arms, 6)
    # Keep repeat calls in a separate randomized block after all primary cells.
    jobs.sort(key=lambda j: (j["occurrence"], old.fingerprint(["jev-choice-crossed-order-v1", j["request_id"]])))
    old.save(PACKET, {"question": old.FOCUSED, "labels": old.prior.CRITERIA, "states": blind})
    from . import choice_run, choice_score
    inputs = [*inputs, *rating_paths, previous_index, previous_packet, gold_path, audit_path, earlier_path,
              *[old.DATA / p for p in ("plan.jsonl", "freeze.json", "register_packets.jsonl", "register_binding.json")],
              db_path, older_plan_path, Path(__file__), Path(choice_run.__file__), Path(choice_score.__file__), Path(old.__file__),
              Path(old.prior.__file__), exp / "register_panel_projection.py",
              HERE / "choice_protocol.md", HERE.parent / "completion/jev_choice.py"]
    old.save(PRIVATE / "freeze.json", {
        "created_utc": datetime.now(UTC).isoformat(), "endpoint": old.ENDPOINT, "model": PINNED_MODEL,
        "price": old.PRICE, "cap": CAP, "policy": POLICY, "families": families, "jobs": jobs, "blind_index": index,
        "rater_packet_sha256": old.digest(PACKET),
        "source_sha256": {str(p.relative_to(old.ROOT)): old.digest(p) for p in inputs},
        "excluded_cases": len(exclusions), "excluded_vendors": len(excluded_vendors),
        "eligible_per_cell": {"|".join(cell): len(ids) for cell, ids in sorted(strata.items())},
    })
    print(f"{old.digest(PRIVATE / 'freeze.json')} {PACKET}")


if __name__ == "__main__":
    prepare()
