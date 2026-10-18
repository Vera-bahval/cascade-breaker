"""Minimal shared guard interface; BLOCK and UNKNOWN are terminal in enforce mode."""
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Decision = Literal["ALLOW", "BLOCK", "UNKNOWN"]


@dataclass(frozen=True)
class GuardDecision:
    decision: Decision
    scores: dict[str, float] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    timing_ms: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.decision not in {"ALLOW", "BLOCK", "UNKNOWN"}:
            raise ValueError("Unsupported guard decision")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
