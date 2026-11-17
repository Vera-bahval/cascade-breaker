"""Independent channel repetitions and deliberately edited controls, kept outside the natural sample."""
import argparse
import csv
import json
import sys
from copy import deepcopy
from pathlib import Path

from .fraud_recheck import HERE, ROOT, P2, P4, candidate, frozen_rules, recorded_disposition, revised_packet


def score(packet, series, case, expected):
    baseline = frozen_rules(packet)
    decision, reason = candidate(revised_packet(packet), baseline)
    return dict(series=series, case=case, point=packet["state"]["point"], expected=expected,
                disposition=recorded_disposition(packet["state"]["records"]), baseline=baseline[0].upper(),
                decision=decision, reason=reason)


def controls(episodes, output):
    sys.path.insert(0, str(ROOT / "finbot"))
    rows = []
    base = {}
    readiness = json.loads((HERE / "channel_readiness.json").read_text())
    for trial in readiness:
        channel = trial["channel"]
        if channel == "portal":  # Already included in the primary 44.
            continue
        if not (trial["all_points_reached"] and trial["full_complete"] and trial["source_amount"] == 650):
            raise ValueError("Incomplete valid channel control")
        path = episodes / f"{channel}-off-e04b3edc417640-native1/native-prefix.jsonl"
        packets = [json.loads(line)["packet"] for line in path.read_text().splitlines()]
        if [p["state"]["point"] for p in packets] != [P2, P4]:
            raise ValueError("Unexpected checkpoint sequence")
        for packet in packets:
            rows.append(score(packet, "channel_repeat", channel, "ALLOW"))
            if channel == "direct":
                base[packet["state"]["point"]] = packet
    # Replace the sender's text and exactly its automatic copy. Native amount, flag and all other facts stay fixed.
    edits = [
        (P2, "incorrect_invoice_amount", "No fraud indicators. The current invoice amount is USD 6,500.", "BLOCK"),
        (P4, "explicit_verbal_hold", "No fraud indicators. Do not pay pending beneficiary confirmation.", "DEFER"),
        (P4, "verbal_condition", "No fraud indicators. Obtain beneficiary confirmation before sending funds.", "DEFER"),
    ]
    for point, case, summary, expected in edits:
        packet = deepcopy(base[point])
        facts = packet["state"]["records"]
        prev = facts["fraud_dispositions"][0]["summary"]
        assert prev and facts["vendor_notes"].count(prev) == 1 and facts["invoice_amount"] == 650
        facts["vendor_notes"] = facts["vendor_notes"].replace(prev, summary)
        facts["fraud_dispositions"][0]["summary"] = summary
        if point == P2:
            facts["fraud_handoff"] = summary
        rows.append(score(packet, "edited_control", case, expected))
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=Path, default=ROOT / ".runtime/payment-controls-chp3/study-live")
    parser.add_argument("--output", type=Path, default=HERE / "fraud_recheck_controls.csv")
    args = parser.parse_args()
    controls(args.episodes, args.output)
