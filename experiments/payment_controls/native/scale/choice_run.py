"""Dispatch only blinded-review-approved frozen request bytes and retain raw and typed receipts."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import fcntl
from hashlib import sha256
from itertools import batched
import json
import os
import sys
from time import monotonic

from .choice_design import CAP, LETTERS, PACKET, PINNED_MODEL, POLICY, PRIVATE, WORKERS, old, wire
from ..completion.jev_choice import receipt_v2

BOUND = 65536 * old.PRICE


def verified():
    path = PRIVATE / "freeze.json"
    freeze = old.read(path)
    assert freeze["policy"] == POLICY
    assert (freeze["endpoint"], freeze["model"], freeze["price"], freeze["cap"]) == (
        old.ENDPOINT, PINNED_MODEL, old.PRICE, CAP)
    assert old.digest(PACKET) == freeze["rater_packet_sha256"]
    assert all(old.digest(old.ROOT / path) == expected for path, expected in freeze["source_sha256"].items())
    ratings = {}
    for reader in ("a", "b"):
        rating = PRIVATE / f"terra_{reader}.json"
        values = old.read(rating)
        assert values.keys() == freeze["blind_index"].keys()
        assert all(v["label"] == "DEFER" and v["evidence"] for v in values.values())
        ratings[reader] = old.digest(rating)
    assert ratings["a"] != ratings["b"]
    release = {"freeze_sha256": old.digest(path), "packet_sha256": old.digest(PACKET),
               "terra_rating_sha256": ratings}
    return freeze, release


def request_bytes(job):
    expected = job["request_sha256"]
    request = (PRIVATE / "requests" / (expected + ".json")).read_bytes()
    assert sha256(request).hexdigest() == expected
    body = json.loads(request)
    assert body["model"] == PINNED_MODEL and request == wire(body)
    criteria = body["questions"]["check"]["criteria"]
    assert set(criteria) == set(LETTERS)
    assert [job["by_letter"][letter] for letter in criteria] == job["semantic_order"]
    assert all(description == old.prior.CRITERIA[job["by_letter"][letter]] for letter, description in criteria.items())
    return request, body


def receipt_path(job):
    return PRIVATE / "receipts" / (job["request_id"] + ".json")


def retain_raw(job, raw):
    with receipt_path(job).with_suffix(".raw").open("xb") as target:
        target.write(raw)
        target.flush()
        os.fsync(target.fileno())


def usage_cost(raw):
    data = json.loads(raw)
    tokens = data["usage"]["input_tokens"]
    if type(tokens) is not int or not 0 < tokens <= 65536:
        raise ValueError("Jev token count outside the reservation")
    return tokens * old.PRICE


def typed(job, body, raw):
    if json.loads(raw).get("errors"):
        raise ValueError("The API reported errors.")
    record = receipt_v2(body, raw)
    choice = record["choice"]
    return {**record, "request_id": job["request_id"], "request_sha256": job["request_sha256"],
            "selected": job["by_letter"][choice], "cost_usd": usage_cost(raw),
            "probabilities": {job["by_letter"][k]: v for k, v in record["answer"]["probabilities"].items()}}


def request_one(client, job, request):
    start = monotonic()
    response = client.post(old.ENDPOINT, content=request, headers={"Content-Type": "application/json"})
    elapsed = monotonic() - start
    retain_raw(job, response.content)
    old.save(receipt_path(job).with_suffix(".http.json"), {"http_status": response.status_code, "seconds": elapsed})
    response.raise_for_status()
    return response.content, elapsed


def run():
    os.umask(0o077)
    freeze, release = verified()
    loaded = {j["request_id"]: request_bytes(j) for j in freeze["jobs"]}
    (PRIVATE / "receipts").mkdir(exist_ok=True)
    with (PRIVATE / "run.lock").open("a") as lock, old.prior.jev_client() as client:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old.prior.bind(PRIVATE, "release.json", release)
        ledger = old.prior.panel.eliza.Ledger(PRIVATE / "ledger.sqlite", CAP)
        existing = old.prior.billing_entries(ledger.path)
        if any(status != "complete" for _, _, status in existing.values()):
            raise RuntimeError("Unresolved frozen request. Reconcile retained evidence before resuming.")
        pending = []
        for job in freeze["jobs"]:
            ident = job["request_id"]
            if ident in existing:
                verify_receipt(job, loaded[ident][1], existing[ident])
            else:
                assert not receipt_path(job).exists() and not receipt_path(job).with_suffix(".raw").exists()
                pending.append(job)
        reply = client.get(old.REGISTRY)
        reply.raise_for_status()
        registry = [r for r in reply.json()["models"] if r["name"] in {PINNED_MODEL, "jev-latest"}]
        # The provider gives a version in the POST response even if the GET lists only the latest alias.
        assert len([r for r in registry if r["name"] == "jev-latest"]) == 1
        registry_path = PRIVATE / "jev-registry.json"
        if registry_path.exists():
            assert old.read(registry_path)["models"] == registry
        else:
            old.save(registry_path, {"models": registry, "checked_utc": datetime.now(UTC).isoformat()})
        resolved = len(existing)
        with ThreadPoolExecutor(WORKERS) as pool:
            for group in batched(pending, WORKERS):
                errors = []
                active = {}
                for job in group:
                    ident = job["request_id"]
                    try:
                        ledger.reserve(ident, BOUND)
                    except Exception as error:
                        errors.append(error)
                        break
                    active[pool.submit(request_one, client, job, loaded[ident][0])] = job
                for future in as_completed(active):
                    job = active[future]
                    ident = job["request_id"]
                    try:
                        raw, elapsed = future.result()
                        ledger.complete(ident, usage_cost(raw))
                        record = typed(job, loaded[ident][1], raw)
                        old.save(receipt_path(job), {**record, "seconds": elapsed, "http_status": 200})
                        resolved += 1
                    except Exception as error:
                        errors.append(error)
                if errors:
                    raise errors[0]
                if resolved % 48 == 0 or resolved == len(freeze["jobs"]):
                    print(f"{resolved}/{len(freeze['jobs'])} resolved, {ledger.summary()['cost_usd']:.6f} USD", flush=True)


def verify_receipt(job, body, entry):
    path = receipt_path(job)
    raw = path.with_suffix(".raw").read_bytes()
    expected = typed(job, body, raw)
    saved = old.read(path)
    transport = old.read(path.with_suffix(".http.json"))
    assert transport["http_status"] == 200 and transport["seconds"] > 0
    assert saved == {**expected, **transport}
    assert entry == (BOUND, expected["cost_usd"], "complete")
    return saved


if __name__ == "__main__":
    {"run": run}[sys.argv[1]]()
