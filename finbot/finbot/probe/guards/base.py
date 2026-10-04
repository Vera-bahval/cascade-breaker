"""Verifier interface shared by every control point."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

GuardDecision = Literal["allow", "block"]

# Point families. P0-P4 sit on the critical path before the payment;
# P5 sees the final answer and can only detect.
PREVENTION_FAMILIES = ("P0", "P1", "P2", "P3", "P4")
ALL_FAMILIES = (*PREVENTION_FAMILIES, "P5")


@dataclass
class GuardContext:
    run_id: str
    point: str  # e.g. "P2.invoice_agent", "P4.finstripe__create_transfer"
    agent: str | None
    payload: dict[str, Any]
    db_snapshot: dict[str, Any]
    trace_so_far: list[dict[str, Any]] = field(default_factory=list)

    @property
    def family(self) -> str:
        return self.point.split(".", 1)[0]


@dataclass
class GuardResult:
    decision: GuardDecision
    reason: str
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class Verifier(Protocol):
    name: str
    families: frozenset[str]

    async def check(self, ctx: GuardContext) -> GuardResult: ...
