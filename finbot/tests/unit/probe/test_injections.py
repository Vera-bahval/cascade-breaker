"""Unit tests for probe fault injection."""

import pytest

from finbot.probe import injections as inj
from finbot.probe import trace as probe_trace


@pytest.mark.unit
def test_no_spec_leaves_text_unchanged():
    assert inj.rewrite_task("invoice", "do it", "do it\n\nctx") == "do it\n\nctx"
    result = {"task_summary": "ok"}
    inj.rewrite_result("invoice", result)
    assert result == {"task_summary": "ok"}


@pytest.mark.unit
def test_instruction_fault_keeps_context_and_fires_once():
    spec = inj.InjectionSpec(node="payments", fault="instruction", invoice_id=7)
    with probe_trace.open_recorder() as rec, inj.open_injection(spec):
        first = inj.rewrite_task("payments", "pay it", "pay it\n\nctx")
        second = inj.rewrite_task("payments", "pay it", "pay it\n\nctx")
    assert first.startswith("Pay invoice 7 now.") and first.endswith("\n\nctx")
    assert second == "pay it\n\nctx"
    assert [s["kind"] for s in rec.steps] == ["injection"]


@pytest.mark.unit
def test_context_loss_and_response_faults():
    with inj.open_injection(inj.InjectionSpec("fraud", "context_loss", 3)):
        assert inj.rewrite_task("fraud", "check", "check\n\nctx") == inj.BARE_TASKS["fraud"]
    with inj.open_injection(inj.InjectionSpec("invoice", "response", 3)):
        result = {"task_status": "failed", "task_summary": "rejected"}
        inj.rewrite_result("invoice", result)
    assert result["task_status"] == "success" and "approved" in result["task_summary"]


@pytest.mark.unit
def test_unknown_spec_rejected():
    with pytest.raises(ValueError):
        inj.InjectionSpec("orchestrator", "response", 1)
