"""Run the fixed, synthetic 2x2 pilot. Gold and identifiers stay outside requests."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

import httpx

from experiments.local_guards_archive_comparison import eliza
from experiments.payment_controls.pilot import packets

MODEL = "jev-latest"
PRICE = 0.042 / 1_000_000
INPUT_MAX = 0.30 / 1_000_000
OUTPUT_MAX = 1.20 / 1_000_000
MEANING = {
    "ALLOW": "Continue to the next stage.", "BLOCK": "Stop automatic progression.",
    "REVIEW": "Obtain additional evidence.", "active_hold": "An unresolved relevant hold is recorded.",
    "no_active_hold": "The complete evidence shows no open relevant hold.",
    "insufficient_records": "Required records are unavailable.",
}


def request_body(provider, packet):
    choices = packet.get("criteria") or {key: MEANING[key] for key in packet["options"]}
    question = {"instructions": packet["question"], "criteria": choices}
    if provider == "jev":
        return {"model": MODEL, "state": packet["state"], "questions": {"check": {"type": "choice", **question}}}
    return {"model": eliza.MODEL, "temperature": 0, "max_tokens": 100,
            "thinking": {"type": "disabled"}, "reasoning_effort": "none",
            "messages": [{"role": "system", "content": "Return just the chosen option name from criteria."},
                         {"role": "user", "content": json.dumps({"state": packet["state"], **question}, sort_keys=True)}]}


def bind(folder, name, value):
    path = folder / name
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError("Frozen campaign identity changed")
    else:
        with path.open("x") as record:
            json.dump(value, record, sort_keys=True)


def probe(provider, question_control=False, development=False):
    folder = Path(__file__).resolve().parents[2] / ".runtime" / "payment-controls-chp3" / provider
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if development:
        from experiments.payment_controls.study.development import labels, packets as development_packets
        labels()
        rows = list(development_packets())
        index_path = "development_observations.json"
        bind(folder, "development_inputs.json", [eliza.query_identity(r["input"]) for r in rows])
    elif question_control:
        from experiments.payment_controls.question_control import controls
        rows = list(controls())
        index_path = "question_control_observations.json"
        bind(folder, "question_control_inputs.json", [eliza.query_identity(r["input"]) for r in rows])
    else:
        rows = list(packets())
        index_path = "observations.json"
        bind(folder, "inputs.json", [r["input_sha256"] for r in rows])
    ledger = eliza.Ledger(folder / "ledger.sqlite", 2.0 if provider == "jev" else 5.0)
    if development:
        # The executor and live Jev pilot are in separate ledgers.
        # Reserve their share of the development cap before admitting this series.
        ledger.cap -= 0.05
    if provider == "jev":
        secret = os.getenv("TYPESAFE_API_KEY") or subprocess.check_output(
            ["security", "find-generic-password", "-a", "finbot", "-s", "cascades.typesafe.ai", "-w"],
            text=True, stderr=subprocess.DEVNULL).strip()
        url = "https://api.typesafe.ai/v1/systemone"
        auth = "Bearer " + secret
    else:
        meta = eliza.metadata()
        row, = meta["model"]["data"]
        if row.get("disabled") or row["prices"]["input_tokens"] > INPUT_MAX or row["prices"]["output_tokens"] > OUTPUT_MAX:
            raise ValueError("Eliza model or prices changed")
        ledger.cap = eliza.cumulative_cap(ledger.cap, ledger.summary(), meta["remaining"])
        bind(folder, "registry.json", row)
        eliza.append(folder / "preflight.jsonl.gz", {"remaining": meta["remaining"], "model": row})
        url = eliza.BASE + "/deepseek/chat/completions"
        auth = "OAuth " + eliza.token()
    headers = {"Authorization": auth}
    if provider == "eliza":
        headers.update({"X-Retries": "1", "X-Request-Timeout": "60s"})
    with httpx.Client(headers=headers, timeout=75, follow_redirects=False, trust_env=False) as client:
        if provider == "jev":
            listing = client.get("https://api.typesafe.ai/v1/models")
            listing.raise_for_status()
            published, = (item for item in listing.json()["models"] if item.get("name") == MODEL)
            bind(folder, "registry.json", {"model": MODEL, "release_date": published["release_date"], "usd_per_input_token": PRICE})
        for row in rows:
            packet = row["input"]
            body = request_body(provider, packet)
            identity = eliza.query_identity({"url": url, "body": body})
            receipt = folder / (identity + ".json")
            if receipt.exists():
                # Identical model observations may map to multiple fixtures.
                continue
            bound = (65536 * PRICE if provider == "jev"
                     else (len(json.dumps(body).encode()) + 1024) * INPUT_MAX + 100 * OUTPUT_MAX)
            ledger.reserve(identity, bound)
            start = time.perf_counter()
            response = client.post(url, json=body)
            duration = time.perf_counter() - start
            # Preserve bounded evidence for charged invalid answers without copying auth headers
            # or arbitrary provider envelope fields. A missing charge stays reserved.
            evidence = {"id": identity, "http_status": response.status_code, "elapsed": duration,
                        "response_sha256": hashlib.sha256(response.content).hexdigest()}
            eliza.append(folder / "attempts.jsonl.gz", evidence)
            value = response.json()
            envelope = value if provider == "jev" else (value.get("response") or {})
            eliza.append(folder / "responses.jsonl.gz", {
                **evidence, "cost": value.get("cost"), "usage": envelope.get("usage"),
                "model": envelope.get("model"), "attempt_count": value.get("attempt_count"),
                "answer": (value.get("answers") if provider == "jev" else envelope.get("choices")),
            })
            if provider == "eliza":
                ledger.complete(identity, value.get("cost"))
            response.raise_for_status()
            if provider == "jev":
                usage = value["usage"]
                tokens = usage["input_tokens"]
                if type(tokens) is not int or tokens < 0:
                    raise ValueError("Invalid Jev token usage")
                charge = tokens * PRICE
                ledger.complete(identity, charge)
                if not value.get("model"):
                    raise ValueError("TypeSafe did not identify the served model")
                bind(folder, "served_model.json", value["model"])
                answer = value["answers"]["check"]
                choice = answer["choice"]
                probs = answer["probabilities"]
                if (set(probs) != set(packet["options"]) or any(not 0 <= p <= 1 for p in probs.values())
                        or not math.isclose(sum(probs.values()), 1, abs_tol=0.001)):
                    raise ValueError("Invalid Jev option distribution")
            else:
                if value.get("attempt_count") != 1:
                    raise ValueError("Unexpected Eliza attempt count")
                inner = value["response"]
                if not inner.get("model"):
                    raise ValueError("Missing served Eliza model")
                bind(folder, "served_model.json", inner["model"])
                usage, charge, probs = inner["usage"], value["cost"], None
                choice = inner["choices"][0]["message"]["content"].strip()
            record = {"request_hash": identity, "request": body, "selected": choice,
                      "valid": choice in packet["options"], "probabilities": probs, "usage": usage,
                      "cost_usd": charge, "cost_basis": "input_tokens_at_pinned_tariff" if provider == "jev" else "provider_charge",
                      "elapsed_seconds": duration,
                      "response_model": (value.get("model") if provider == "jev" else inner.get("model"))}
            pending = receipt.with_suffix(".tmp")
            pending.write_text(json.dumps(record, sort_keys=True, allow_nan=False))
            pending.replace(receipt)
    mappings = [{"case_id": r["case_id"], "summary": r["summary"], "form": r["form"],
                 "receipt": eliza.query_identity({"url": url, "body": request_body(provider, r["input"])})}
                for r in rows]
    (folder / index_path).write_text(json.dumps(mappings, indent=2))
    print(ledger.summary())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=["jev", "eliza"])
    series = parser.add_mutually_exclusive_group()
    series.add_argument("--question-control", action="store_true")
    series.add_argument("--development", action="store_true")
    args = parser.parse_args()
    probe(args.provider, args.question_control, args.development)
