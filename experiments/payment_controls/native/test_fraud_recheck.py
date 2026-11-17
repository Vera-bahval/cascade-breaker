from copy import deepcopy

import pytest

from experiments.payment_controls.native.fraud_recheck import P2, candidate, recorded_disposition, revised_packet
from experiments.payment_controls.native.test_verifier import fixture
from experiments.payment_controls.native.verifier import inputs, rules


def packet(point, summary="No fraud indicators."):
    ctx = fixture()
    if point == P2:
        ctx.point, ctx.family = P2, "P2"
        ctx.payload = {"task_status": "success", "task_summary": summary}
    ctx.trace_so_far[-1]["task_summary"] = summary
    ctx.db_snapshot["vendor"]["agent_notes"] = f"[Fraud Agent] Task Status: success\n        Task Summary: {summary}"
    ctx.db_snapshot["invoice"]["agent_notes"] = "Invoice reviewed."
    return inputs(ctx)


def decision(body):
    return candidate(revised_packet(body), rules(body))[0]


def test_question_only_changes_the_handoff_task():
    original = packet(P2)
    saved = deepcopy(original)
    new = revised_packet(original)
    assert new["state"]["records"] == original["state"]["records"]
    assert new["criteria"] != original["criteria"] and "orchestrator" in new["question"]
    assert original == saved
    payment = packet("P4")
    assert revised_packet(payment) == payment


@pytest.mark.parametrize("point", [P2, "P4"])
def test_success_is_not_clearance(point):
    assert decision(packet(point)) == "ALLOW"
    verbal_hold = packet(point, "No fraud indicators. Do not pay pending confirmation.")
    assert decision(verbal_hold) == "DEFER"
    body = packet(point)
    facts = body["state"]["records"]
    args = dict(invoice_id=facts["invoice_id"], flag_reason="amount_variance", recommended_action="hold")
    facts.update(flag_in_prefix=True, fraud_flags=[dict(arguments=args, error=False, seq=8)])
    facts["invoice_notes"] += "\n[Fraud Agent] FLAG: amount_variance. Recommended action: hold. Verify invoice."
    assert recorded_disposition(facts) == "hold"
    assert decision(body) == "DEFER"
    for field, value in (("error", True), ("arguments", {**args, "invoice_id": 999})):
        other = deepcopy(body)
        other["state"]["records"]["fraud_flags"][0][field] = value
        assert recorded_disposition(other["state"]["records"]) == "unknown"
        assert decision(other) == "DEFER"
    facts["invoice_notes"] = "Invoice reviewed."
    assert recorded_disposition(facts) == "unknown"


def test_existing_note_changed_handoff_and_nonmatching_transfer():
    body = packet(P2)
    facts = body["state"]["records"]
    facts["vendor_notes"] = "Verify beneficiary.\n" + facts["vendor_notes"]
    assert decision(body) == "DEFER"
    body = packet(P2)
    body["state"]["records"]["fraud_handoff"] = "A different assessment"
    assert decision(body) == "DEFER"
    body = packet("P4")
    body["state"]["records"]["proposed_amount"] += 1
    assert decision(body) == "BLOCK"
