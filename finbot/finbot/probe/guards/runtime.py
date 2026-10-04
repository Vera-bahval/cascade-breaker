"""Guard runtime: runs verifiers at control points in shadow or enforce mode.

Inactive unless a runner opens one with `open_runtime()` (and the runner only
does so when CASCADE_GUARD_MODE is not "off"); every hook is a no-op then.

shadow   every applicable verifier runs at every point; verdicts are only
         recorded, execution never changes.
enforce  only the configured (family, verifier) pairs run; the first block
         stops the workflow ("stop and escalate"): the blocked action does not
         run and every later LLM call or tool call raises GuardStop.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from finbot.probe import trace as probe_trace
from finbot.probe.guards.base import GuardContext, GuardResult, Verifier

_runtime: contextvars.ContextVar[GuardRuntime | None] = contextvars.ContextVar(
    "probe_guard_runtime", default=None
)

DELEGATE_PREFIX = "delegate_to_"
STATE_CHANGING_TOOLS = frozenset(
    {"update_invoice_status", "flag_invoice_for_review", "update_vendor_risk"}
)
PAYMENT_TOOLS = frozenset({"finstripe__create_transfer", "process_payment"})
P2_AGENTS = frozenset({"invoice_agent", "fraud_agent", "payments_agent"})


class GuardStop(RuntimeError):
    """The workflow was stopped by a blocking verdict (enforce mode)."""


@dataclass
class GuardRuntime:
    mode: str  # "shadow" | "enforce"
    run_id: str
    verifiers: list[Verifier]
    snapshot: Callable[[], dict[str, Any]]
    # enforce mode: family -> verifier name active at that family
    enforce: dict[str, str] = field(default_factory=dict)
    stopped_by: dict[str, Any] | None = None

    def _applicable(self, family: str) -> list[Verifier]:
        if self.mode == "enforce":
            name = self.enforce.get(family)
            return [v for v in self.verifiers if v.name == name and family in v.families]
        return [v for v in self.verifiers if family in v.families]

    async def check(self, point: str, agent: str | None, payload: dict[str, Any]) -> None:
        if self.stopped_by is not None:
            raise GuardStop(f"workflow stopped at {self.stopped_by['point']}")
        family = point.split(".", 1)[0]
        verifiers = self._applicable(family)
        if not verifiers:
            return
        recorder = probe_trace.active_recorder()
        ctx = GuardContext(
            run_id=self.run_id,
            point=point,
            agent=agent,
            payload=payload,
            db_snapshot=self.snapshot(),
            trace_so_far=list(recorder.steps) if recorder else [],
        )
        started = time.perf_counter()
        results = await asyncio.gather(*(self._timed(v, ctx) for v in verifiers))
        pause_ms = round((time.perf_counter() - started) * 1000, 1)
        context_step = None
        if recorder is not None:
            context_step = recorder.add(
                "guard_context", point=point, family=family, agent=agent,
                payload=payload, db_snapshot=ctx.db_snapshot, pause_ms=pause_ms,
            )["seq"]
        blocking = None
        for verifier, result in zip(verifiers, results):
            probe_trace.record(
                "guard", point=point, family=family, agent=agent,
                verifier=verifier.name, context_seq=context_step,
                decision=result.decision, reason=result.reason,
                latency_ms=result.latency_ms, tokens_in=result.tokens_in,
                tokens_out=result.tokens_out, cost_usd=result.cost_usd,
            )
            if result.decision == "block" and blocking is None:
                blocking = verifier.name
        if self.mode == "enforce" and blocking is not None:
            self.stopped_by = {"point": point, "verifier": blocking}
            probe_trace.record("guard_stop", point=point, verifier=blocking)
            raise GuardStop(f"blocked at {point} by {blocking}")

    @staticmethod
    async def _timed(verifier: Verifier, ctx: GuardContext) -> GuardResult:
        started = time.perf_counter()
        try:
            result = await verifier.check(ctx)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # A verifier failure must not change the run; it fails open and is logged.
            result = GuardResult(decision="allow", reason=f"verifier_error: {e}"[:300])
        result.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return result


def active_runtime() -> GuardRuntime | None:
    return _runtime.get()


@contextlib.contextmanager
def open_runtime(runtime: GuardRuntime) -> Iterator[GuardRuntime]:
    token = _runtime.set(runtime)
    try:
        yield runtime
    finally:
        _runtime.reset(token)


def raise_if_stopped() -> None:
    runtime = _runtime.get()
    if runtime is not None and runtime.stopped_by is not None:
        raise GuardStop(f"workflow stopped at {runtime.stopped_by['point']}")


def _point_before_tool(agent: str, tool_name: str) -> str | None:
    if agent == "orchestrator_agent":
        if tool_name.startswith(DELEGATE_PREFIX):
            return f"P1.{tool_name}"
        if tool_name == "complete_task":
            return "P5.final"
        return None
    if tool_name in PAYMENT_TOOLS:
        return f"P4.{tool_name}"
    if tool_name in STATE_CHANGING_TOOLS:
        return f"P3.{tool_name}"
    return None


async def before_tool(agent: str, tool_name: str, arguments: dict[str, Any]) -> None:
    runtime = _runtime.get()
    if runtime is None:
        return
    point = _point_before_tool(agent, tool_name)
    if point is None:
        raise_if_stopped()
        return
    await runtime.check(point, agent, {"tool": tool_name, "arguments": arguments})


async def after_tool(agent: str, tool_name: str, arguments: dict[str, Any], output: Any) -> None:
    """P2: an agent's summary at the boundary, before the orchestrator passes it on."""
    runtime = _runtime.get()
    if runtime is None or agent != "orchestrator_agent":
        return
    if not tool_name.startswith(DELEGATE_PREFIX) or not isinstance(output, dict):
        return
    target = tool_name[len(DELEGATE_PREFIX):] + "_agent"
    if target not in P2_AGENTS:
        return
    await runtime.check(
        f"P2.{target}",
        target,
        {
            "agent": target,
            "task_status": output.get("task_status"),
            "task_summary": output.get("task_summary"),
        },
    )


async def check_input(payload: dict[str, Any]) -> None:
    """P0: the invoice record before the workflow starts."""
    runtime = _runtime.get()
    if runtime is not None:
        await runtime.check("P0.input", None, payload)
