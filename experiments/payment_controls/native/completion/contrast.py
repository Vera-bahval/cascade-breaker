"""Paired Jev settlement-linkage audit against retained, SQLite-verified states."""
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
import fcntl
from hashlib import sha256
from itertools import combinations, product
import json
import math
import os
from pathlib import Path
import random
import re
import sqlite3
import sys
from time import monotonic

from ..expansion import register_panel as prior
from ..expansion.register_panel_projection import instant, project, visible_rule

ROOT = prior.panel.ROOT
DATA = ROOT / ".runtime/register-newbritain-v1"
RUNTIME = ROOT / ".runtime/payment-controls-chp3"
CT = RUNTIME / "expansion-register-panel-ct"
PRIVATE = RUNTIME / "contrast-v1"
LABELS = prior.LABELS
LETTERS = "ABC"
CAP = 0.035
PRICE = prior.panel.PRICE
MODEL = prior.checkpoint.MODELS["jev"]
REGISTRY = "https://api.typesafe.ai/v1/models"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
FOCUSED = (
    "Classify the observed prior completed settlement linkage at this pre-Fraud checkpoint. "
    "Start with the current invoice ID and vendor ID. Within the supplied receipt view, use "
    "completed receipts with explicit invoice and vendor links. Distinguish a link to that invoice "
    "from a link to a distinct invoice of that vendor. A matching vendor or amount and a paid invoice "
    "status alone do not establish a receipt link. Use the completeness flag when ruling out a "
    "current-invoice receipt. If necessary identity, settlement, linkage or coverage is missing or "
    "ambiguous, use DEFER. Scope your answer to observed prior settlement."
)
POLICY = {
    "selection": "3 families per status_fixture x SQLite linkage cell; fixed hash rank; exclude prior panel selections",
    "design": "Within family all three cyclic letter mappings x original/focused x full/without_finstripe",
    "primary": ["family mean total variation between rotation pairs",
                "family mean focused minus original log loss, overall and by receipt exposure"],
    "secondary": ["accuracy", "multiclass Brier", "semantic choice flips", "DEFER transitions",
                  "chosen-option and separate confidence against accuracy", "ledger effect on gold log loss"],
    "uncertainty": "10000 percentile bootstrap replicates, family resampling within four selection cells",
    "probability_floor": 1e-12,
    "seed": 515307,
}


def save(path, row):
    prior.save(path, row)


def read(path):
    return prior.panel.load(path)


def digest(path):
    return prior.sha(path)


def fingerprint(value):
    return prior.panel.fingerprint(value)


def keyed(name):
    rows = [json.loads(line) for line in (DATA / name).read_text().splitlines()]
    keyed_rows = {row["case_id"]: row for row in rows}
    assert len(keyed_rows) == len(rows)
    return keyed_rows


def sqlite_gold(db, ident, raw):
    current = raw["current_invoice"]
    book = raw["added_native_finstripe_ledger"]
    cutoff = instant(book["cutoff_utc"])
    assert book["scope"] == "complete mock FinStripe vendor register for this fixture at cutoff"
    target, = db.execute("SELECT vendor_id, status FROM invoices WHERE namespace=? AND id=?",
                         ("register-" + ident, current["id"])).fetchall()
    assert target == (current["vendor_id"], current["status"])
    reads = db.execute(
        """SELECT transfer_id, invoice_id, vendor_id, status, amount, created_at
           FROM payment_transactions WHERE namespace=? AND vendor_id=? ORDER BY transfer_id""",
        ("register-" + ident, current["vendor_id"]),
    ).fetchall()

    def record(rid, invoice, vendor, status, amount, created):
        return rid, invoice, vendor, status, Decimal(str(amount)), instant(created, sqlite_utc=True)

    active = [record(*row) for row in reads if instant(row[-1], sqlite_utc=True) <= cutoff]
    projected = [record(*(row[key] for key in ("transfer_id", "invoice_id", "vendor_id", "status", "amount",
                                             "created_at"))) for row in book["transfers"]]
    assert sorted(active) == sorted(projected)
    prior_links = {r[1] for r in active if r[0] and r[1] and r[3] == "completed"}
    return "SAME" if current["id"] in prior_links else "OTHER" if prior_links else "DEFER"


def alias_shape(state):
    aliases = {}
    def replace(match):
        alias = match.group(1)
        if alias not in aliases:
            aliases[alias] = "".join(filter(str.isalpha, alias)) + str(len(aliases))
        return json.dumps(aliases[alias])
    return prior.ALIAS_PATTERN.sub(replace, prior.panel.canonical(state))


def prior_panel():
    archives = [RUNTIME / "expansion-register-panel", CT]
    exclusions, bodies, inputs = set(), set(), []
    for archive in archives:
        snapshot_path = archive / "freeze.json"
        results_path = archive / "results.json"
        snapshot = read(snapshot_path)
        by_id = {job["case_id"]: job for job in snapshot["jobs"]}
        for item in snapshot["paid_schedule"]:
            ident = item["case_id"]
            exclusions.add(ident)
            bodies.add(by_id[ident][item["phase"]]["request_sha256"]["jev"])
        for item in read(results_path)["rows"]:
            if item["provider"] == "jev":
                assert item["request_hash"] in bodies
        inputs.extend([snapshot_path, results_path])
    return exclusions, bodies, inputs


def prepare():
    os.umask(0o077)
    PRIVATE.mkdir(mode=0o700)
    exclusions, old_bodies, inputs = prior_panel()
    sources, plan = keyed("register_packets.jsonl"), keyed("plan.jsonl")
    ct_freeze = read(CT / "freeze.json")
    ct_jobs = {r["case_id"]: r for r in ct_freeze["jobs"]}
    assert ct_freeze["source_sha256"] == digest(DATA / "register_packets.jsonl")
    assert sources.keys() == plan.keys() == ct_jobs.keys()
    old_gold = read(CT / "gold.json")
    exp = prior.HERE
    audited = read(exp / "register_ct_audit.json")
    rating_paths = [exp / f"register_ct_terra_{r}.json" for r in ("a", "b")]
    previous_index = CT / "rater-index.private.json"
    previous_packet = CT / "rater-packet.json"
    for path in [previous_index, previous_packet, *rating_paths, DATA / "register_packets.jsonl"]:
        assert digest(path) == audited["inputs_sha256"][path.name]
    previous_states = read(previous_packet)["states"]
    previous_full = {r["case_id"]: key for key, r in read(previous_index)["index"].items() if r["phase"] == "full"}
    old_ratings = [read(path) for path in rating_paths]
    strata = defaultdict(list)
    assert digest(DATA / "plan.jsonl") == read(DATA / "freeze.json")["plan_sha256"]
    packet_db = DATA / "packets.db"
    with sqlite3.connect(packet_db.as_uri() + "?mode=ro", uri=True) as db:
        for ident, job in ct_jobs.items():
            if ident in exclusions or job["source_pair_kind"] != "authentic_prior_sibling":
                continue
            row = plan[ident]
            gold = sqlite_gold(db, ident, sources[ident])
            assert gold == old_gold[ident] == ("SAME" if row["linked_prior"] else "OTHER")
            strata[row["status_fixture"], gold].append(ident)
    assert set(strata) == set(product(("paid", "stale"), ("SAME", "OTHER")))
    jobs, blind, index, families = [], {}, {}, {}
    for (status, gold), candidates in sorted(strata.items()):
        for ident in sorted(candidates, key=lambda x: fingerprint(["jev-contrast-v1", x]))[:3]:
            row = sources[ident]
            archived = ct_jobs[ident]
            assert fingerprint(row) == archived["source_row_sha256"]
            family = fingerprint(["jev-contrast-v1-family", plan[ident]["source_vendor_group"]])
            assert family not in families
            state = archived["full"]["bodies"]["jev"]["state"]
            assert alias_shape(state) == alias_shape(project(row, 0))
            old_key = previous_full[ident]
            # The rater state was independently re-aliased. Compare equality structure, including links.
            previous_state = json.loads(prior.panel.canonical(previous_states[old_key]))
            aliases = {}
            def replace(match):
                alias = match.group(0).strip('"')
                if alias not in aliases:
                    stem = next(stem for stem in ("invoice", "receipt", "vendor") if alias.startswith(stem))
                    aliases[alias] = f"{stem}{len(aliases):05d}"
                return json.dumps(aliases[alias])
            previous_normalized = json.loads(re.sub(r'"(?:invoice|receipt|vendor)[a-f0-9]{10}"', replace,
                                                    prior.panel.canonical(previous_state)))
            assert alias_shape(previous_normalized) == alias_shape(state)
            assert all(rating[old_key]["label"] == gold and rating[old_key]["evidence"] for rating in old_ratings)
            without = archived["without_finstripe"]["bodies"]["jev"]["state"]
            assert all(state[k] == without[k] for k in state if k != "added_finstripe_vendor_receipt_view")
            assert without["added_finstripe_vendor_receipt_view"] == {
                "available": False, "complete_at_checkpoint": False, "receipts_visible_at_checkpoint": []}
            families[family] = {"case_id": ident, "stratum": [status, gold], "source_sha256": fingerprint(row),
                                "full_gold": gold, "without_finstripe_gold": "DEFER",
                                "previous_full_ratings_key": old_key}
            key = fingerprint(["blind-without-v1", family])[:24]
            blind[key], index[key] = without, family
            for phase, question, rotation in product(prior.PHASES, ("original", "focused"), range(3)):
                labels = LABELS[rotation:] + LABELS[:rotation]
                view = state if phase == "full" else without
                assert visible_rule(view) == families[family][phase + "_gold"]
                body = {"model": "jev-latest", "state": view, "questions": {"check": {
                    "type": "choice", "instructions": prior.QUESTION if question == "original" else FOCUSED,
                    "criteria": {letter: prior.CRITERIA[label] for letter, label in zip(LETTERS, labels)}
                }}}
                request_hash = fingerprint(body)
                assert request_hash not in old_bodies
                jobs.append(dict(family=family, phase=phase, question=question, rotation=rotation,
                                 labels=labels, body=body, request_sha256=request_hash))
    assert len(families) == 12 and len({job["request_sha256"] for job in jobs}) == len(jobs) == 144
    jobs.sort(key=lambda job: fingerprint(["jev-contrast-run-v1", job["request_sha256"]]))
    sources = [*inputs, *rating_paths, previous_index, previous_packet, CT / "gold.json", CT / "jev-registry.json",
               exp / "register_ct_audit.json", DATA / "plan.jsonl", DATA / "freeze.json",
               DATA / "register_packets.jsonl", DATA / "register_binding.json", packet_db, Path(__file__),
               Path(prior.__file__), exp / "register_panel_projection.py"]
    save(PRIVATE / "rater-packet.json", {"question": prior.QUESTION, "labels": prior.CRITERIA, "states": blind})
    save(PRIVATE / "freeze.json", {
        "created_utc": datetime.now(UTC).isoformat(), "endpoint": ENDPOINT, "model": MODEL, "price": PRICE, "cap": CAP,
        "source_sha256": {str(path.relative_to(ROOT)): digest(path) for path in sources},
        "policy": POLICY, "families": families, "jobs": jobs, "blind_index": index,
        "rater_packet_sha256": digest(PRIVATE / "rater-packet.json"),
        "eligible_per_cell": {"|".join(cell): len(ids) for cell, ids in sorted(strata.items())},
    })
    print(digest(PRIVATE / "freeze.json"))


if __name__ == "__main__":
    globals()[sys.argv[1]]()
