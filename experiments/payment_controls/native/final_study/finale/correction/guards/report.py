"""Read back paired decisions, usage and receipts without provider calls."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import statistics

from . import run
from .... import jev

O = run.original
CHOICES = {"ALLOW", "BLOCK", "REVIEW"}


def billing(path):
    return jev.billing_entries(path) if path.exists() else {}


def all_eliza_billing():
    result = billing(run.PRIVATE / "eliza.sqlite")
    for path in sorted(run.PRIVATE.glob("eliza-wave-*.sqlite")):
        additional = billing(path)
        if result.keys() & additional.keys():
            raise ValueError("Repeated paid occurrence")
        result.update(additional)
    return result


def eliza_row(row, arm, current, old):
    reuse = (row["source"], arm) == ("historical", "short_choice_32")
    folder, ident, ledger = (O.PRIVATE, row["id"], old) if reuse else (run.PRIVATE, run.key(row, arm), current)
    record = {"choice": None, "status": "not_attempted", "reused": reuse}
    if ident not in ledger:
        return record
    reserve, cost, reconciliation = ledger[ident]
    record.update(status="technical", reserve_usd=reserve, cost_usd=cost, reconciliation=reconciliation)
    if (folder / f"{ident}.request").read_bytes() != run.request_bytes(row, arm):
        raise ValueError("Receipt request differs from frozen request")
    http_path = folder / f"{ident}.http.json"
    if http_path.exists():
        record.update(run.read(http_path))
    response = folder / f"{ident}.response"
    if not response.exists():
        return record
    raw = response.read_bytes()
    record["response_sha256"] = O.digest(raw)
    try:
        wrapper = json.loads(raw)
        inner = wrapper["response"]
        choice, = inner["choices"]
        text = choice["message"]["content"].strip()
        reason = None
        record.update(model=inner["model"], response_id=inner["id"], usage=inner["usage"],
                      attempt_count=wrapper["attempt_count"], finish_reason=choice["finish_reason"])
        if choice["finish_reason"] != "stop" or record["http_status"] != 200 or wrapper["attempt_count"] != 1 or (
            wrapper["cost"] != cost or reconciliation != "complete" or inner["model"] != O.eliza.MODEL
        ):
            return record
        if arm.endswith("_reason") or arm.startswith("native_"):
            decoded = json.loads(text)
            text, reason = decoded["decision"], decoded["reason"]
            if set(decoded) != {"decision", "reason"} or not isinstance(reason, str) or not reason.strip():
                record["status"] = "unparseable"
                return record
        normalized = "REVIEW" if text == "UNKNOWN" else text
        if normalized not in CHOICES or (text == "REVIEW" and (arm.startswith("legacy_") or arm.startswith("native_"))) or (
            text == "UNKNOWN" and not (arm.startswith("legacy_") or arm.startswith("native_"))
        ):
            record["status"] = "unparseable"
            return record
        record.update(choice=normalized, raw_choice=text, status="valid")
        if reason is not None:
            record["reason_sha256"] = O.digest(reason.encode())
            record["reason_source_markers"] = sorted(set(re.findall(
                r"\b(?:taxcalc|finstripe|tax|hold|fraud|duplicate|approval|account|recipient|policy|"
                r"routing|method|amount|currency|reference|unavailable|bank|delegate|investigat\w*)\b",
                reason.lower()
            )))
            return record, reason
    except (ValueError, KeyError, TypeError, AttributeError):
        record["status"] = "unparseable"
    return record


def jev_row(row, current, old, arm="jev"):
    reuse = row["source"] == "historical"
    if reuse:
        folder, ident, ledger = O.JEV, row["archive_occurrence" if arm == "jev" else "archive_present_occurrence"], old
    else:
        folder, ident, ledger = run.PRIVATE / "jev", run.key(row, "jev"), current
    result = {"reused": reuse, "status": "not_attempted", "choice": None, "effective": None}
    if ident not in ledger:
        return result
    payload = run.request_bytes(row, arm)
    request_folder = folder if reuse else run.PRIVATE
    if (request_folder / (ident + ".request")).read_bytes() != payload:
        raise ValueError("Jev receipt differs from frozen request")
    runner = jev.JevRunner(folder, run.J_CAP)
    try:
        record = runner.read((None, ident, row["wires"][arm], json.loads(payload), payload), ledger[ident])
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        return {**result, "status": "technical"}
    probs = record["probabilities"]
    score = min(1.0, probs["BLOCK"] + probs["REVIEW"])
    effective = ("BLOCK" if probs["BLOCK"] > probs["REVIEW"] else "REVIEW") if score >= .97 else "ALLOW"
    return {**record, "status": "valid", "reused": reuse, "choice": record["decision"],
            "score": score, "effective": effective}


def metric(rows, arm):
    def choice(r):
        return r["jev"]["effective"] if arm == "jev_effective" else r[arm]["choice"]
    counts = Counter()
    for r in rows:
        state = r["gold"]["label"] if r["gold"] else "UNLABELED"
        counts[f"{state}/{choice(r) or 'NO_VALID_REPLY'}"] += 1
    return dict(sorted(counts.items()))


def paired(rows, a, b):
    def choice(r, arm):
        return r["jev"]["effective"] if arm == "jev_effective" else r[arm]["choice"]
    return dict(Counter(f"{r['gold']['label'] if r['gold'] else 'UNLABELED'}/"
                        f"{choice(r, a) or 'NO_VALID_REPLY'}/{choice(r, b) or 'NO_VALID_REPLY'}" for r in rows))


def money(ledger):
    records = list(ledger.values())
    return {"attempts": len(records), "status": dict(Counter(status for _, _, status in records)),
            "settled_usd": sum(cost or 0 for _, cost, _ in records),
            "unresolved_reserved_usd": sum(reserve for reserve, cost, _ in records if cost is None)}


def gold_index(path):
    if not path:
        return {}
    records = run.read(path) if path.suffix == ".json" else list(O.eliza.read_rows(path))
    if type(records) is dict:
        records = records["rows"]
    indexed = {(r["assignment"], int(r["capture"])): {**r, "label": r["label"] if "label" in r else r["disposition"]}
               for r in records}
    if len(indexed) != len(records):
        raise ValueError("Duplicate modern capture grade")
    return indexed


def build(gold_path, historical_gold=None, primary_only=False):
    manifest = run.read(run.HERE / "freeze.json")
    gold_old = O.index("archive_heldout_gold") if historical_gold is None else {
        r["id"]: r for r in O.eliza.read_rows(historical_gold)
    }
    gold_modern = gold_index(gold_path)
    eb = all_eliza_billing()
    jb = billing(run.PRIVATE / "jev/ledger.sqlite")
    if primary_only:
        eb = {k: v for k, v in eb.items() if k.endswith("-native_source")}
        assert len(eb) == 516 and all(status == "complete" for _, _, status in eb.values())
        assert len(jb) == 391 and all(status == "complete" for _, _, status in jb.values())
    selected_arms = ("native_source",) if primary_only else run.PROMPTS
    old_e = billing(O.PRIVATE / "ledger.sqlite")
    old_j = billing(O.JEV / "ledger.sqlite")
    rows, reasons = [], []
    for row in manifest["rows"]:
        source_gold = gold_old.get(row["id"]) if row["source"] == "historical" else (
            gold_modern.get((row["assignment"], row["capture"]))
        )
        if row["source"] == "modern" and source_gold and (row["point"], row["family"]) != (
            source_gold["point"], source_gold["family"]
        ):
            raise ValueError("Modern grade addresses another boundary or family")
        result = {**row, "gold": source_gold, "jev": jev_row(row, jb, old_j)}
        if row["source"] == "historical" and not primary_only:
            result["jev_present"] = jev_row(row, jb, old_j, "jev_present")
        for arm in selected_arms:
            arm_read = eliza_row(row, arm, eb, old_e)
            if isinstance(arm_read, tuple):
                arm_read, reason = arm_read
                reasons.append({"id": row["id"], "arm": arm, "choice": arm_read["choice"], "reason": reason})
            result[arm] = arm_read
        rows.append(result)
    slices = defaultdict(list)
    for r in rows:
        base = f"{r['source']}/{r['point']}"
        slices[base].append(r)
        if r.get("channel"):
            slices[base + "/" + r["channel"]].append(r)
    arms = (*selected_arms, "jev", "jev_effective")
    contrasts = (("native_source", "jev_effective"), ("native_source", "jev"), ("native_source", "native_legacy"),
                 ("native_legacy", "jev_effective"), ("native_legacy", "jev"),
                 ("legacy_reason", "jev_effective"), ("legacy_reason", "jev"), ("legacy_reason", "legacy_choice"),
                 ("short_reason", "short_choice"), ("legacy_reason", "short_reason"),
                 ("legacy_choice", "short_choice"), ("short_choice", "short_choice_32"))
    if primary_only:
        contrasts = contrasts[:2]
    strata = {}
    for name, selected in sorted(slices.items()):
        strata[name] = {"n": len(selected), "families": len({r["family"] for r in selected}),
                        "scores": {a: metric(selected, a) for a in arms + (("jev_present",) if name == "historical/P1" and not primary_only else ())},
                        "paired": {f"{a}/{b}": paired(selected, a, b) for a, b in contrasts}}
    for name, ledger, valid in (("Eliza", eb, {run.key(r, a) for r in rows for a in run.PROMPTS
                                             if (r["source"], a) != ("historical", "short_choice_32")}),
                                ("Jev", jb, {run.key(r, "jev") for r in rows if r["source"] == "modern"})):
        if set(ledger) - valid:
            raise ValueError(f"{name} ledger contains unknown frozen occurrence")
    totals = {}
    for arm in (*selected_arms, "jev"):
        data = [r[arm] for r in rows]
        totals[arm] = {
            "status": dict(Counter(r["status"] for r in data)),
            "settled_usd": sum(r.get("cost_usd") or 0 for r in data if not r["reused"]),
            "reused_usd": sum(r.get("cost_usd") or 0 for r in data if r["reused"]),
            "input_tokens": sum(r.get("usage", {}).get("input_tokens", r.get("usage", {}).get("prompt_tokens", 0)) for r in data),
            "output_tokens": sum(r.get("usage", {}).get("output_tokens", r.get("usage", {}).get("completion_tokens", 0)) for r in data),
            "median_seconds_valid": statistics.median([r["seconds"] for r in data if r["status"] == "valid"])
            if any(r["status"] == "valid" for r in data) else None,
        }
    if gold_path:
        observed = {(r["assignment"], r["capture"]) for r in rows if r["source"] == "modern"}
        if observed != gold_modern.keys():
            raise ValueError("Modern grade coverage must match every modern capture")
    reason_file = "primary-reasons.jsonl" if primary_only else "reasons.jsonl"
    (run.PRIVATE / reason_file).write_bytes(b"".join(jev.wire(x) + b"\n" for x in reasons))
    result = {"freeze_sha256": O.digest((run.HERE / "freeze.json").read_bytes()), "strata": strata,
              "gold_sha256": {"modern": O.digest(gold_path.read_bytes()) if gold_path else None,
                              "historical": O.digest((historical_gold or (run.STUDY / "archive_heldout_gold.jsonl")).read_bytes())},
              "billing": {"eliza": money(eb), "jev": money(jb)}, "arms": totals, "rows": rows}
    output = run.HERE / ("primary-results.json" if primary_only else "results.json")
    encoded = (json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode()
    if primary_only:
        O.persist_once(output, encoded)
    else:
        output.write_bytes(encoded)
    print(json.dumps({"billing": result["billing"], "arms": totals}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modern-gold", type=Path)
    parser.add_argument("--historical-gold", type=Path)
    parser.add_argument("--primary-only", action="store_true")
    args = parser.parse_args()
    build(args.modern_gold, args.historical_gold, args.primary_only)
