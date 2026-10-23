"""Unit tests for the probe guard runtime and trace recorder."""

import pytest

from finbot.probe import trace as probe_trace
from finbot.probe.guards import runtime as probe_guards
from finbot.probe.guards.base import GuardResult


class _Fixed:
    def __init__(self, name, decision, families=("P1", "P4")):
        self.name = name
        self.families = frozenset(families)
        self.decision = decision

    async def check(self, ctx):
        return GuardResult(decision=self.decision, reason=f"{self.name} at {ctx.point}")


def _runtime(mode, enforce=None):
    return probe_guards.GuardRuntime(
        mode=mode,
        run_id="r1",
        verifiers=[_Fixed("allow_all", "allow"), _Fixed("block_all", "block")],
        snapshot=lambda: {"invoice": {"status": "approved"}},
        enforce=enforce or {},
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hooks_are_noops_without_runtime():
    await probe_guards.before_tool("payments_agent", "finstripe__create_transfer", {})
    await probe_guards.check_input({"amount": 1})
    probe_guards.raise_if_stopped()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shadow_records_every_verdict_and_never_blocks():
    with probe_trace.open_recorder() as rec, probe_guards.open_runtime(_runtime("shadow")):
        await probe_guards.before_tool("payments_agent", "finstripe__create_transfer", {"amount": 5})
        await probe_guards.before_tool("payments_agent", "get_vendor_details", {})
        probe_guards.raise_if_stopped()
    guards = [s for s in rec.steps if s["kind"] == "guard"]
    assert {g["verifier"] for g in guards} == {"allow_all", "block_all"}
    assert all(g["point"] == "P4.finstripe__create_transfer" for g in guards)
    assert [s["kind"] for s in rec.steps].count("guard_context") == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enforce_runs_only_configured_pair_and_stops():
    runtime = _runtime("enforce", {"P4": "block_all"})
    with probe_trace.open_recorder() as rec, probe_guards.open_runtime(runtime):
        await probe_guards.before_tool("orchestrator_agent", "delegate_to_invoice", {})
        with pytest.raises(probe_guards.GuardStop):
            await probe_guards.before_tool("payments_agent", "finstripe__create_transfer", {})
        with pytest.raises(probe_guards.GuardStop):
            await probe_guards.before_tool("payments_agent", "get_vendor_details", {})
        with pytest.raises(probe_guards.GuardStop):
            probe_guards.raise_if_stopped()
    assert runtime.stopped_by == {"point": "P4.finstripe__create_transfer", "verifier": "block_all"}
    assert [s["verifier"] for s in rec.steps if s["kind"] == "guard"] == ["block_all"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enforce_accepts_a_single_point():
    runtime = _runtime("enforce", {"P4.process_payment": "block_all"})
    with probe_trace.open_recorder(), probe_guards.open_runtime(runtime):
        await probe_guards.before_tool("payments_agent", "finstripe__create_transfer", {})
        with pytest.raises(probe_guards.GuardStop):
            await probe_guards.before_tool("payments_agent", "process_payment", {})


@pytest.mark.unit
@pytest.mark.parametrize(
    "agent, tool, point",
    [
        ("orchestrator_agent", "delegate_to_fraud", "P1.delegate_to_fraud"),
        ("orchestrator_agent", "complete_task", "P5.final"),
        ("invoice_agent", "update_invoice_status", "P3.update_invoice_status"),
        ("payments_agent", "process_payment", "P4.process_payment"),
        ("invoice_agent", "get_invoice_details", None),
        ("invoice_agent", "complete_task", None),
    ],
)
def test_point_mapping(agent, tool, point):
    assert probe_guards._point_before_tool(agent, tool) == point  # pylint: disable=protected-access
