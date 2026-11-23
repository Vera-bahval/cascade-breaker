"""Export policy-adjudication evidence from the frozen finale; no providers."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
FINALE = OUT.parents[1]
ROOT = FINALE.parents[4]
PRIVATE = ROOT / ".runtime/payment-controls-chp3/final-study-payment-finale"
DECK = PRIVATE / "correction-policy"
OLD = FINALE / "review/assignment_outcomes.json"
POLICY_PATHS = (
    "finbot/finbot/agents/orchestrator.py",
    "finbot/finbot/agents/specialized/invoice.py",
    "finbot/finbot/agents/specialized/fraud.py",
    "finbot/finbot/agents/specialized/payments.py",
    "finbot/finbot/probe/policy.py",
)


def load(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_rows(path, data):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data))


def review_needed(row):
    return (
        row["source_disposition"] == "verify_material_source_issue_before_settlement"
        or row["financial"] != "MET"
        or row["wrong_stop"] is not False
        or row["procedural"] != "MET"
        or any(item["disposition"] != "ADMISSIBLE" for item in row.get("candidate_actions", []))
    )


def main():
    DECK.mkdir(exist_ok=True, mode=0o700)
    freeze = load(PRIVATE / "freeze.json")
    permitted = {
        path: sha256((ROOT / path).read_bytes()).hexdigest() for path in POLICY_PATHS
    }
    assert all(digest == freeze["files"][str(ROOT / path)] for path, digest in permitted.items())
    source = load(FINALE.parent / "live_source_audit.json")["rows"]
    source_rows = []
    for group in freeze["groups"]:
        cell = group["cell"]
        if cell["kind"] != "main":
            continue
        old = source[cell["source_cell"]]
        case, = (item for item in load(ROOT / cell["source_path"]) if item["id"] == cell["case_id"])
        source_rows.append({
            "family": cell["family"], "cell": cell["source_cell"], "channel": cell["channel"],
            "source_path": cell["source_path"], "case_id": cell["case_id"],
            "old_disposition": old["source_only_disposition"], "prior_concern": old["source_issue"],
            "trigger": case["trigger"], "setup": case["setup"],
        })
    assert len(source_rows) == 221
    write_rows(DECK / "source.jsonl", source_rows)
    candidates = {
        row["blind_id"]: row for row in load(OLD)
        if row["kind"] == "main" and review_needed(row)
    }
    counts = Counter()
    index = {}
    for folder in ("blind", "blind-structured-review", "blind-mandatory-duties"):
        for directory in (PRIVATE / folder).glob("wave-*"):
            packets = {r["id"]: r for r in rows(directory / "packets.jsonl")}
            for key in candidates.keys() & packets.keys():
                index[key] = (directory, packets[key])
    assert index.keys() == candidates.keys(), candidates.keys() - index.keys()
    with (DECK / "review-index.jsonl").open("w") as result:
        for key, (directory, packet) in sorted(index.items()):
            row = candidates[key]
            blind_path = directory.relative_to(PRIVATE)
            counts[row["arm"]] += 1
            result.write(json.dumps({
                "id": key, "packet_dir": str(blind_path),
                "technical": row["state"] != "terminal", "source_family": row["family"],
                "candidate_captures": [item["capture"] for item in packet.get("candidate_actions", [])],
            }) + "\n")
    write(DECK / "mapping.json", {key: row["assignment"] for key, row in candidates.items()})
    write(OUT / "input-receipt.json", {
        "policy_sha256_at_frozen_live_execution": permitted,
        "old_gold_sha256": sha256(OLD.read_bytes()).hexdigest(),
        "total_primary_families": len(source_rows),
        "candidate_assignments": dict(counts),
    })
    print(len(candidates), counts)


if __name__ == "__main__":
    main()
