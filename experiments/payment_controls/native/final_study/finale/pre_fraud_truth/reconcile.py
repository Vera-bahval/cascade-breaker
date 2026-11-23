"""Validate blind assessments and join ratings only after each pass is done."""
from collections import Counter
import json

from .extract import HERE, LATEST, OUT, digest, wire

ACTIONS = {"CLOSE_ALLOW", "CLOSE_STOP", "DEFER", "INSUFFICIENT"}
PROMPT = HERE / "rater_prompt.txt"


def json_lines(text):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def results(prefix):
    records = {}
    for prompt in sorted(OUT.glob(prefix + "[0-9][0-9].prompt")):
        raw = prompt.with_suffix(".result")
        if not raw.is_file():
            continue
        prompts = json_lines(prompt.read_text().split("\n\nPackets\n", 1)[1])
        out = json_lines(raw.read_text())
        if [row["id"] for row in prompts] != [row["id"] for row in out]:
            raise ValueError(f"Unexpected identifiers or order in {raw.name}")
        for row in out:
            if (set(row) != {"id", "action", "checked", "missing"} or row["action"] not in ACTIONS
                    or not row["checked"] or not isinstance(row["checked"], str)
                    or not isinstance(row["missing"], str)
                    or (bool(row["missing"]) != (row["action"] in {"DEFER", "INSUFFICIENT"}))
                    or row["id"] in records):
                raise ValueError(f"Invalid or repeated rating in {raw.name}")
            records[row["id"]] = row
    return records


def stratum(row):
    if row["d_action"] != "DEFER":
        return "D_resolved"
    return "D_veto" if row["mandatory_veto"] else "E_eligible"


def main():
    rows = {r["id"]: r for r in json_lines((OUT / "inputs.jsonl").read_text())}
    a, b, c = (results(phase) for phase in "abc")
    need = [rid for rid in rows if rid in a and rid in b and a[rid]["action"] != b[rid]["action"]]
    gold = []
    for rid, item in rows.items():
        primary, independent, adjudicator = a.get(rid), b.get(rid), c.get(rid)
        if not primary or not independent:
            continue
        rating = primary
        if rid not in need:
            basis = "two_terra_agreement"
        elif adjudicator and adjudicator["action"] in {primary["action"], independent["action"]}:
            rating, basis = adjudicator, "third_terra_majority"
        elif rid in need:
            rating, basis = {"id": rid, "action": "INSUFFICIENT", "checked": "Raters differed.",
                             "missing": "Independent disposition not resolved."}, "unresolved_disagreement"
        gold.append({**rating, "split": item["split"], "basis": basis, "stratum": stratum(item)})

    exclusions = json.loads((OUT / "exclusions.json").read_text())
    manifest = {"archived_roster": len(rows) + len(exclusions),
                "exclusions": dict(Counter(reason.split(":")[0] for reason in exclusions.values())),
                "rater_model": "gpt-6.1-terra",
                "gold_sha256": digest(b"".join(wire(g) + b"\n" for g in gold)),
                "rater_batches": {file.name: {
                    "input_sha256": digest(file.read_bytes()),
                    "result_sha256": digest(file.with_suffix(".result").read_bytes()),
                } for file in sorted(OUT.glob("*.prompt")) if file.with_suffix(".result").is_file()},
                "rating_packets": len(rows), "primary_rated": len(a), "independently_rated": len(b),
                "review_agreements": sum(rid in a and rid not in need for rid in b),
                "adjudicated": len(c), "disagreements_for_adjudication": len(need),
                "source_roster_sha256": digest(LATEST.read_bytes()),
                "primary_prompt_sha256": digest(PROMPT.read_bytes()),
                "private_inputs_sha256": digest((OUT / "inputs.jsonl").read_bytes()),
                "blinded_projected_inputs_sha256": digest((OUT / "rating_packets.jsonl").read_bytes()),
                "counts": [dict(split=k[0], stratum=k[1], action=k[2], n=v)
                           for k, v in sorted(Counter((g["split"], g["stratum"], g["action"]) for g in gold).items())]}
    if gold:
        (OUT / "gold.jsonl").write_bytes(b"".join(wire(g) + b"\n" for g in gold))
    prior = sorted(OUT.glob("c[0-9][0-9].prompt"))
    queued = {r["id"] for p in prior for r in json_lines(p.read_text().split("\n\nPackets\n", 1)[1])}
    pending = [rid for rid in need if rid not in queued]
    for i in range(0, len(pending), 22):
        batch = [{"id": rid, "state": rows[rid]["blind_packet"]} for rid in pending[i:i+22]]
        body = PROMPT.read_text() + "\n\nPackets\n" + "\n".join(wire(row).decode() for row in batch)
        (OUT / f"c{len(prior)+i//22:02}.prompt").write_text(body)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    if len(a) == len(rows) and len(b) == len(rows) and set(c) == set(need):
        (HERE / "audit.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
