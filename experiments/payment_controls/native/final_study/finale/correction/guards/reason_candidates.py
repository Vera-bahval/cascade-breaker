"""Select a deterministic blinded-to-wording manual reason audit panel."""
from collections import defaultdict
import json

from . import run, tables


def panel():
    results = run.read(run.HERE / "results.json")
    by = defaultdict(list)
    for row in results["rows"]:
        for arm in ("native_source", "legacy_reason", "short_reason"):
            decision = tables.decision(row, arm)
            if row[arm].get("reason_sha256"):
                by[row["source"], row["point"], tables.kind(row), decision, arm].append(row)
    result = []
    for (origin, point, expected, prediction, arm), rows in sorted(by.items()):
        ranked = sorted(rows, key=lambda r: run.original.digest(run.jev.wire(["guard-reason-audit-v1", r["id"], arm])))
        for row in ranked[:2]:
            state = json.loads(run.request_bytes(row, "jev"))["state"]
            result.append({"id": row["id"], "source": origin, "point": point, "gold": expected,
                           "choice": prediction, "arm": arm, "reason_sha256": row[arm]["reason_sha256"],
                           "records": state["records"]})
    answers = {(r["id"], r["arm"]): r["reason"] for r in run.original.eliza.read_rows(run.PRIVATE / "reasons.jsonl")}
    for row in result:
        row["reason"] = answers[row["id"], row["arm"]]
        assert run.original.digest(row["reason"].encode()) == row["reason_sha256"]
    return result


if __name__ == "__main__":
    (run.PRIVATE / "reason-audit-panel.json").write_text(json.dumps(panel(), ensure_ascii=False, indent=2) + "\n")
