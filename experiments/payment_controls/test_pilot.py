from collections import Counter
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.payment_controls.pilot import ledger_packets, packets
from experiments.payment_controls.probe_models import request_body


def test_factorial_inputs_and_reference():
    data = list(ledger_packets())
    assert len(data) == 48
    assert list(Counter(r["case_id"] for r in data).values()) == [4] * 12
    for r in data:
        inp = r["input"]
        records = inp["state"]["authenticated_ledger"]
        if records is None:
            decision = "REVIEW"
        else:
            active = False
            for e in records:
                if e["invoice"] == "A" and e["event"] in {"hold", "clearance"}:
                    active = e["event"] == "hold"
            decision = "BLOCK" if active else "ALLOW"
        assert decision == r["expected"]
        assert ("agent_summary" in inp["state"]) == r["summary"]
        assert set(inp) == {"state", "options", "question"}
        assert request_body("jev", inp)["state"] == inp["state"]
        assert set(request_body("jev", inp)["questions"]["check"]["criteria"]) == set(inp["options"])
        assert len(request_body("eliza", inp)["messages"]) == 2


def test_semantic_packets_are_label_blind():
    rows = list(packets())
    assert len(rows) == 48 and len({r["family"] for r in rows}) == 6
    for row in rows:
        state = row["input"]["state"]
        assert set(state) <= {"policy", "invoice", "next_action", "authenticated_review_note", "agent_summary"}
        assert ("agent_summary" in state) == row["summary"]
        assert set(row["input"]) == {"state", "question", "options"}
