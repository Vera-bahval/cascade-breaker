import pathlib
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scenarios"))
from runner.mast_mode import Facts


@pytest.mark.parametrize(("count", "amount", "recipient", "currency", "error", "expected"), [
    (1, 120, "vendor", "usd", False, True), (0, 120, "vendor", "usd", False, False),
    (2, 120, "vendor", "usd", False, False), (1, 119, "vendor", "usd", False, False),
    (1, 120, "other", "usd", False, False), (1, 120, "vendor", "eur", False, False),
    (1, 120, "vendor", "usd", True, False),
])
def test_completed_payment(count, amount, recipient, currency, error, expected):
    case = {"expected": {"outcome": "pay"}, "trigger": {"kind": "invoice", "invoice": {"amount": 120}},
            "oracle": {"checks": [{"assert": "transfer_count", "invoice": "T", "equals": 1}]}}
    invoice = {"id": 1, "invoice_number": "T", "amount": amount}
    tx = {"invoice_id": 1, "transfer_id": "tr", "amount": amount, "status": "completed", "currency": currency}
    snapshot = {"vendors": {"current": {"bank_account_number": "vendor"}}, "invoices": [invoice],
                "transactions": [tx] * count}
    step = {"kind": "tool", "name": "finstripe__create_transfer", "arguments": {"invoice_id": 1},
            "output": {"transfer_id": "tr", "vendor_account": recipient}, "error": error}
    facts = Facts(SimpleNamespace(invoices={"T": invoice}), snapshot, [], {"wf": {"steps": [step]}}, [])
    assert all(c["ok"] for c in facts.outcome_checks(case, snapshot)) is expected


def test_p0_api_stop_is_terminal_without_start():
    from runner.api_mode import wait_for_workflows

    event = {"id": 3, "workflow_id": "wf", "event_type": "agent.orchestrator_agent.guard_stop"}
    client = SimpleNamespace(events_after=lambda after: [event] if after < 3 else [])
    result = wait_for_workflows(client, (1, set()), expect_workflow=True, timeout=1, settle=0)
    assert result["workflows"] == ["wf"] and not result["timed_out"]
