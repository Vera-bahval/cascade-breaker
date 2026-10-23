"""Per-run accounting of LLM calls for the cascade-control probe.

A runner opens a ledger with `open_ledger()`; while none is open every hook
here is a no-op, so FinBot behaves exactly as before.

The ledger also enforces the pilot's stop conditions: an HTTP 401/402/403
from the provider (bad key, spend limit, moderation) or a served model that
differs from the requested one halts the run, and every later LLM call in it
raises `ProbeHalt` instead of reaching the API.
"""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from typing import Any

HALT_STATUS_CODES = frozenset({401, 402, 403})

_ledger: contextvars.ContextVar[RunLedger | None] = contextvars.ContextVar(
    "probe_ledger", default=None
)
_agent: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "probe_agent", default=None
)


class ProbeHalt(RuntimeError):
    """Raised for LLM calls made after the run ledger has halted."""


@dataclass
class CallRecord:
    agent: str | None
    requested_model: str | None
    served_model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    cost_source: str = "none"  # "api" | "price_card" | "none"
    duration_ms: int = 0
    success: bool = True
    status_code: int | None = None
    error: str | None = None


@dataclass
class RunLedger:
    # USD per million tokens, used only when the API reports no cost
    price_per_mtok: dict[str, float] | None = None
    calls: list[CallRecord] = field(default_factory=list)
    halt_reason: str | None = None

    def record_response(
        self,
        agent: str | None,
        requested_model: str | None,
        metadata: dict[str, Any] | None,
        duration_ms: int,
    ) -> None:
        metadata = metadata or {}
        usage = metadata.get("usage") or {}
        record = CallRecord(
            agent=agent,
            requested_model=requested_model,
            served_model=metadata.get("model"),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cached_tokens=int(usage.get("cached_tokens", 0)),
            duration_ms=duration_ms,
        )
        if "cost" in usage:
            record.cost_usd = float(usage["cost"])
            record.cost_source = "api"
        elif self.price_per_mtok:
            record.cost_usd = (
                record.input_tokens * self.price_per_mtok["input"]
                + record.output_tokens * self.price_per_mtok["output"]
            ) / 1_000_000
            record.cost_source = "price_card"
        self.calls.append(record)
        if requested_model and record.served_model != requested_model:
            self.halt(
                f"model_mismatch: requested {requested_model}, "
                f"served {record.served_model}"
            )

    def record_error(self, status_code: int | None, message: str) -> None:
        self.calls.append(
            CallRecord(
                agent=_agent.get(),
                requested_model=None,
                success=False,
                status_code=status_code,
                error=message[:500],
            )
        )
        if status_code in HALT_STATUS_CODES:
            self.halt(f"http_{status_code}: {message[:200]}")

    def halt(self, reason: str) -> None:
        if self.halt_reason is None:
            self.halt_reason = reason

    def totals(self) -> dict[str, Any]:
        ok = [c for c in self.calls if c.success]
        by_agent: dict[str, dict[str, Any]] = {}
        for c in ok:
            entry = by_agent.setdefault(
                c.agent or "unknown",
                {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
            )
            entry["calls"] += 1
            entry["input_tokens"] += c.input_tokens
            entry["output_tokens"] += c.output_tokens
            entry["cost_usd"] += c.cost_usd
        return {
            "llm_calls": len(ok),
            "failed_calls": len(self.calls) - len(ok),
            "input_tokens": sum(c.input_tokens for c in ok),
            "output_tokens": sum(c.output_tokens for c in ok),
            "cached_tokens": sum(c.cached_tokens for c in ok),
            "cost_usd": sum(c.cost_usd for c in ok),
            "cost_sources": sorted({c.cost_source for c in ok}),
            "served_models": sorted({c.served_model or "?" for c in ok}),
            "llm_time_ms": sum(c.duration_ms for c in ok),
            "by_agent": by_agent,
            "halt_reason": self.halt_reason,
        }

    def call_dicts(self) -> list[dict[str, Any]]:
        return [asdict(c) for c in self.calls]


def active_ledger() -> RunLedger | None:
    return _ledger.get()


@contextlib.contextmanager
def open_ledger(
    price_per_mtok: dict[str, float] | None = None,
) -> Iterator[RunLedger]:
    ledger = RunLedger(price_per_mtok=price_per_mtok)
    token = _ledger.set(ledger)
    try:
        yield ledger
    finally:
        _ledger.reset(token)


@contextlib.contextmanager
def agent_scope(agent_name: str) -> Iterator[None]:
    token = _agent.set(agent_name)
    try:
        yield
    finally:
        _agent.reset(token)


def raise_if_halted() -> None:
    ledger = _ledger.get()
    if ledger is not None and ledger.halt_reason:
        raise ProbeHalt(ledger.halt_reason)


def record_error(exc: BaseException) -> None:
    ledger = _ledger.get()
    if ledger is not None:
        ledger.record_error(getattr(exc, "status_code", None), str(exc))
