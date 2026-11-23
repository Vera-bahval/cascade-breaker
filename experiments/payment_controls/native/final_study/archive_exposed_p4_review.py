"""Re-adjudicate the unscored exposed P4 panel using the frozen strict policy."""
import argparse
from collections import Counter
import json

from .archive_review import HERE, boundary_sequences, digest, draw, rows, write

ROOT = HERE / "archive_extended"
PREFIX = ROOT / "exposed_p4_policy_reread"
EXPECTED = "8db0340007995d7e3c3fa102fd2223bd1240d0dbb36733e77b2ef41601d3115b"
BINARY = {"ALLOW": 0, "BLOCK": 1, "REVIEW": 1, "INSUFFICIENT": None}


def main(mode):
    src = PREFIX.with_name(PREFIX.name + "_blind.jsonl")
    if digest(src) != EXPECTED:
        raise ValueError("Exact pre-release exposed P4 roster changed")
    packets = rows(src)
    a, b, t = [PREFIX.with_name(PREFIX.name + f"_{suffix}.jsonl")
               for suffix in ("a", "b", "adjudication")]
    first, second = rows(a), rows(b)
    needed = draw(packets, first, second, False)
    if mode == "prepare":
        write(PREFIX.with_name(PREFIX.name + "_adjudication_packets.jsonl"),
              (packets[key] for key in sorted(needed)))
        print(dict(Counter(needed.values())))
        return
    third = rows(t)
    if set(third) != set(needed):
        raise ValueError("Third review must cover all disagreements and sampled agreements")
    for batch in ("01", "02"):
        base = ROOT / f"priority_exposed_{batch}"
        inputs = rows(ROOT / "exposed_blind_batches" / f"priority_{batch}.jsonl")
        original = rows(base.with_name(base.name + "_gold.jsonl"))
        if set(inputs) != set(original):
            raise ValueError("Prior gold and exact exposed input differ")
        merged = []
        for key, row in original.items():
            if inputs[key]["checkpoint"] == "P1":
                merged.append(row)
                continue
            if inputs[key] != packets[key]:
                raise ValueError(f"Exposed packet {key} differs from reread")
            mark = third.get(key, first[key])
            evidence = mark["evidence_seq"]
            if set(evidence) - boundary_sequences(packets[key]):
                raise ValueError(f"Review contains unverified evidence coordinate: {key}")
            if mark["label"] == "ALLOW" and packets[key]["state"]["records"]["prior_transfer_history_complete"] is not True:
                raise ValueError(f"Unsupported strict P4 ALLOW: {key}")
            merged.append({**row, **mark, "review_status": needed.get(key, "two_rater_agreement"),
                           "intervention_required": BINARY[mark["label"]]})
        output = base.with_name(base.name + "_strict_gold.jsonl")
        write(output, merged)
        receipt = {"n": len(merged), "sha256": {p.name: digest(p) for p in (src, a, b, t, output)},
                   "labels": dict(Counter(row["label"] for row in merged))}
        output.with_name(output.stem + "_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "finalize"))
    main(parser.parse_args().mode)
