"""Unit tests for the probe usage ledger."""

import pytest

from finbot.probe import ledger as probe_ledger

MODEL = "openai/gpt-4o-mini-2024-07-18"


def _metadata(model=MODEL, **usage):
    return {"model": model, "usage": usage}


@pytest.mark.unit
def test_hooks_are_noops_without_open_ledger():
    assert probe_ledger.active_ledger() is None
    probe_ledger.raise_if_halted()
    probe_ledger.record_error(RuntimeError("boom"))


@pytest.mark.unit
def test_api_cost_is_preferred_over_price_card():
    with probe_ledger.open_ledger({"input": 0.15, "output": 0.6}) as led:
        led.record_response("a", MODEL, _metadata(input_tokens=10, output_tokens=2, cost=0.5), 7)
        led.record_response("a", MODEL, _metadata(input_tokens=1_000_000, output_tokens=0), 3)
    totals = led.totals()
    assert totals["cost_usd"] == pytest.approx(0.65)
    assert totals["cost_sources"] == ["api", "price_card"]
    assert totals["by_agent"]["a"]["calls"] == 2
    assert totals["halt_reason"] is None


@pytest.mark.unit
def test_model_mismatch_halts_run():
    with probe_ledger.open_ledger() as led:
        led.record_response("a", MODEL, _metadata(model="openai/gpt-4o-mini"), 1)
        with pytest.raises(probe_ledger.ProbeHalt):
            probe_ledger.raise_if_halted()
    assert led.halt_reason.startswith("model_mismatch")


@pytest.mark.unit
@pytest.mark.parametrize("status, halts", [(402, True), (403, True), (429, False)])
def test_http_errors(status, halts):
    err = RuntimeError("provider error")
    err.status_code = status
    with probe_ledger.open_ledger() as led:
        probe_ledger.record_error(err)
    assert (led.halt_reason is not None) is halts
    assert led.totals()["failed_calls"] == 1
