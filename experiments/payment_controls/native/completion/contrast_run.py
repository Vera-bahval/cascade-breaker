"""Execute or score the frozen Jev contrast using exact, resolved API receipts."""
from collections import Counter, defaultdict
import fcntl
from hashlib import sha256
from itertools import combinations
import json
import math
import os
from pathlib import Path
import random
from statistics import mean, median
import sys
from time import monotonic

from .contrast import (
    CAP, CT, ENDPOINT, LABELS, LETTERS, MODEL, POLICY, PRICE, PRIVATE, REGISTRY, ROOT,
    digest, fingerprint, prior, read, save,
)

BOUND = 65536 * PRICE


def verified():
    path = PRIVATE / "freeze.json"
    freeze = read(path)
    assert freeze["policy"] == POLICY
    assert (freeze["endpoint"], freeze["model"], freeze["price"], freeze["cap"]) == (ENDPOINT, MODEL, PRICE, CAP)
    assert digest(PRIVATE / "rater-packet.json") == freeze["rater_packet_sha256"]
    assert all(digest(ROOT / file) == expected for file, expected in freeze["source_sha256"].items())
    blind = freeze["blind_index"]
    ratings = {}
    for reader in ("a", "b"):
        rating_path = PRIVATE / f"terra_{reader}.json"
        scores = read(rating_path)
        assert scores.keys() == blind.keys()
        assert all(row["label"] == "DEFER" and row["evidence"] for row in scores.values())
        ratings[reader] = digest(rating_path)
    assert ratings["a"] != ratings["b"]
    release = {"freeze_sha256": digest(path), "rating_sha256": ratings, "runner_sha256": digest(Path(__file__))}
    return freeze, release


def parse(raw, job):
    value = json.loads(raw)
    if value["model"] != MODEL or value.get("errors"):
        raise ValueError("Unexpected served model or API errors")
    tokens = value["usage"]["input_tokens"]
    if type(tokens) is not int or not 0 < tokens <= 65536:
        raise ValueError("Invalid token usage")
    answer = value["answers"]["check"]
    choice, probs = answer["choice"], answer["probabilities"]
    confidence = answer.get("confidence", value.get("confidence"))
    if (set(probs) != set(LETTERS) or any(type(p) not in (int, float) or not 0 <= p <= 1 for p in probs.values())
            or not math.isclose(sum(probs.values()), 1, rel_tol=0, abs_tol=0.001) or choice not in LETTERS):
        raise ValueError("Invalid choice or probability distribution")
    if confidence is not None and (type(confidence) not in (int, float) or not 0 <= confidence <= 1):
        raise ValueError("Invalid provider confidence")
    by_letter = dict(zip(LETTERS, job["labels"]))
    return {
        "input_tokens": tokens, "cost_usd": tokens * PRICE, "model": MODEL,
        "selected": by_letter[choice], "probabilities": {by_letter[k]: p for k, p in probs.items()},
        "confidence": confidence, "answer_keys": sorted(answer), "response_keys": sorted(value),
    }


def run():
    os.umask(0o077)
    freeze, release = verified()
    (PRIVATE / "receipts").mkdir(exist_ok=True)
    with (PRIVATE / "run.lock").open("a") as lock, prior.jev_client() as client:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prior.bind(PRIVATE, "release.json", release)
        ledger = prior.panel.eliza.Ledger(PRIVATE / "ledger.sqlite", CAP)
        if ledger.summary()["pending"]:
            raise RuntimeError("An earlier request has unresolved billing; stop without retrying.")
        rsp = client.get(REGISTRY)
        rsp.raise_for_status()
        registry, = [r for r in rsp.json()["models"] if r["name"] == "jev-latest"]
        if registry != read(CT / "jev-registry.json"):
            raise RuntimeError("The official registry differs from the earlier panel.")
        prior.bind(PRIVATE, "jev-registry.json", registry)
        for idx, job in enumerate(freeze["jobs"]):
            ident = job["request_sha256"]
            assert ident == fingerprint(job["body"])
            path = PRIVATE / "receipts" / f"{ident}.json"
            raw_path = path.with_suffix(".raw")
            ledger_rows = prior.billing_entries(ledger.path)
            if ident in ledger_rows:
                cost = parse(raw_path.read_bytes(), job)["cost_usd"]
                assert ledger_rows[ident] == (BOUND, cost, "complete") and read(path)["cost_usd"] == cost
                continue
            assert not path.exists() and not raw_path.exists()
            ledger.reserve(ident, BOUND)
            start = monotonic()
            rsp = client.post(ENDPOINT, json=job["body"])
            elapsed = monotonic() - start
            with raw_path.open("xb") as handle:
                handle.write(rsp.content)
                handle.flush()
                os.fsync(handle.fileno())
            rsp.raise_for_status()
            typed = parse(rsp.content, job)
            save(path, {**typed, "request_sha256": ident, "response_sha256": sha256(rsp.content).hexdigest(),
                        "seconds": elapsed, "http_status": rsp.status_code})
            ledger.complete(ident, typed["cost_usd"])
            if (idx + 1) % 24 == 0:
                print(f"{idx + 1}/{len(freeze['jobs'])} resolved", flush=True)


def summary(values, families, event=False):
    strata = defaultdict(list)
    for family, value in values.items():
        strata[tuple(families[family]["stratum"])].append(value)
    rng = random.Random(POLICY["seed"])
    samples = sorted(mean(v for group in strata.values() for v in rng.choices(group, k=len(group)))
                     for _ in range(10000))
    result = {"mean": mean(values.values()), "family_count": len(values),
              "stratified_bootstrap_95": [samples[249], samples[9749]]}
    if event:
        result["families_with_any_nonzero_event"] = sum(v > 0 for v in values.values())
    return result


def score():
    freeze, release = verified()
    assert release == read(PRIVATE / "release.json")
    families = freeze["families"]
    ledger = prior.billing_entries(PRIVATE / "ledger.sqlite")
    assert set(ledger) == {job["request_sha256"] for job in freeze["jobs"]}
    rows = {}
    floor = POLICY["probability_floor"]
    for job in freeze["jobs"]:
        ident = job["request_sha256"]
        path = PRIVATE / "receipts" / f"{ident}.json"
        raw = path.with_suffix(".raw").read_bytes()
        typed = parse(raw, job)
        receipt = read(path)
        assert typed == {k: receipt[k] for k in typed}
        assert (receipt["request_sha256"], receipt["response_sha256"]) == (ident, sha256(raw).hexdigest())
        assert ledger[ident] == (BOUND, typed["cost_usd"], "complete")
        gold = families[job["family"]][job["phase"] + "_gold"]
        probs = typed["probabilities"]
        row = {**receipt, "gold": gold, "correct": typed["selected"] == gold,
               "abstain": typed["selected"] == "DEFER",
               "maximum_tie": sum(p == max(probs.values()) for p in probs.values()) > 1,
               "choice_below_maximum": probs[typed["selected"]] < max(probs.values()),
               "log_loss": -math.log(max(floor, probs[gold])),
               "brier": sum((probs[label] - (label == gold)) ** 2 for label in LABELS)}
        rows[job["family"], job["phase"], job["question"], job["rotation"]] = row

    output = {"release": release, "arms": {}, "contrasts": {}, "families": len(families),
              "requests": len(rows), "cost_usd": sum(row["cost_usd"] for row in rows.values()),
              "input_tokens": sum(row["input_tokens"] for row in rows.values()), "unresolved_reserved_usd": 0,
              "answer_keys": sorted(set(tuple(r["answer_keys"]) for r in rows.values())),
              "response_keys": sorted(set(tuple(r["response_keys"]) for r in rows.values())),
              "server_model": MODEL, "median_latency_s": median(row["seconds"] for row in rows.values())}
    contrasts_all, order_all, flips_all = defaultdict(list), defaultdict(list), defaultdict(list)
    for phase in prior.PHASES:
        loss_diff = {}
        for fam in families:
            loss_diff[fam] = mean(rows[fam, phase, "focused", ix]["log_loss"] -
                                  rows[fam, phase, "original", ix]["log_loss"] for ix in range(3))
            contrasts_all[fam].append(loss_diff[fam])
        output["contrasts"][phase + "_focused_minus_original_log_loss"] = summary(loss_diff, families)
        for prompt in ("original", "focused"):
            arm = {fam: [rows[fam, phase, prompt, ix] for ix in range(3)] for fam in families}
            tv = {fam: mean(sum(abs(a["probabilities"][k] - b["probabilities"][k]) for k in LABELS) / 2
                            for a, b in combinations(group, 2)) for fam, group in arm.items()}
            flips = {fam: mean(a["selected"] != b["selected"] for a, b in combinations(group, 2))
                     for fam, group in arm.items()}
            for fam, value in tv.items():
                order_all[fam].append(value)
                flips_all[fam].append(flips[fam])
            flat = [row for group in arm.values() for row in group]
            calibration = {}
            for correct in (True, False):
                group = [r for r in flat if r["correct"] == correct]
                confidence = [r["confidence"] for r in group if r["confidence"] is not None]
                calibration[str(correct).lower()] = {
                    "count": len(group),
                    "mean_chosen_option_probability": mean(r["probabilities"][r["selected"]] for r in group) if group else None,
                    "provider_confidence_count": len(confidence),
                    "mean_provider_confidence": mean(confidence) if confidence else None,
                }
            output["arms"][phase + "/" + prompt] = {
                "rotation_total_variation": summary(tv, families, event=True),
                "rotation_choice_flip_rate": summary(flips, families, event=True),
                "confusion": {label: dict(Counter(r["selected"] for r in flat if r["gold"] == label)) for label in LABELS},
                "correct": sum(r["correct"] for r in flat), "requests": len(flat),
                "abstentions": sum(r["abstain"] for r in flat), "mean_log_loss": mean(r["log_loss"] for r in flat),
                "mean_multiclass_brier": mean(r["brier"] for r in flat), "by_correctness": calibration,
                "maximum_probability_ties": sum(r["maximum_tie"] for r in flat),
                "choices_below_recorded_maximum": sum(r["choice_below_maximum"] for r in flat),
            }
    for name, values in (("mean_focused_minus_original_log_loss", contrasts_all), ("mean_rotation_total_variation", order_all),
                         ("mean_rotation_choice_flip_rate", flips_all)):
        output["contrasts"][name] = summary({fam: mean(parts) for fam, parts in values.items()}, families,
                                             event=name != "mean_focused_minus_original_log_loss")
    for prompt in ("original", "focused"):
        matched = {fam: [(rows[fam, "full", prompt, ix], rows[fam, "without_finstripe", prompt, ix])
                         for ix in range(3)] for fam in families}
        change = {fam: mean(b["log_loss"] - a["log_loss"] for a, b in pairs) for fam, pairs in matched.items()}
        output["contrasts"][prompt + "_removed_ledger_minus_full_log_loss"] = summary(change, families)
        output["contrasts"][prompt + "_full_to_ablated_choices"] = {
            label: dict(Counter(b["selected"] for pairs in matched.values() for a, b in pairs if a["selected"] == label))
            for label in LABELS}
    save(PRIVATE / "score.json", output)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    {"run": run, "score": score}[sys.argv[1]]()
