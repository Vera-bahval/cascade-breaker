from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"

VIA_KINDS = {
    "api": {"invoice", "chat", "onboarding"},
    "direct": {"orchestrator"},
}

DEFAULT_VENDOR = {
    "company_name": "Northwind Equipment LLC",
    "vendor_category": "Equipment",
    "industry": "Production",
    "services": "Camera and lighting equipment rental",
    "name": "Jane Doe",
    "email": "jane.doe@northwind.example",
    "phone": "555-0100",
    "tin": "12-3456789",
    "bank_account_number": "1234567890",
    "bank_name": "First Demo Bank",
    "bank_routing_number": "987654321",
    "bank_account_holder_name": "Northwind Equipment LLC",
}


@dataclass
class Scenario:
    id: str
    via: str
    trigger: dict[str, Any]
    vendor: dict[str, Any] = field(default_factory=dict)
    setup_invoices: list[dict[str, Any]] = field(default_factory=list)
    vendor_overrides: dict[str, Any] = field(default_factory=dict)
    onboard: bool = False
    description: str = ""
    path: Path | None = None

    @property
    def kind(self) -> str:
        return self.trigger["kind"]


def invoice_fields(spec: dict[str, Any], number: str) -> dict[str, Any]:
    today = date.today()
    due = today + timedelta(days=int(spec.get("due_in_days", 30)))
    return {
        "invoice_number": spec.get("invoice_number") or number,
        "amount": float(spec["amount"]),
        "description": spec["description"],
        "invoice_date": today.isoformat(),
        "due_date": due.isoformat(),
    }


def resolve_path(name: str) -> Path:
    path = Path(name)
    if path.exists():
        return path
    candidate = CASES_DIR / f"{name}.yaml"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Scenario not found: {name}")


def load(name: str) -> Scenario:
    path = resolve_path(name)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    via = raw.get("via", "api")
    trigger = raw.get("trigger") or {}
    kind = trigger.get("kind")
    if via not in VIA_KINDS:
        raise ValueError(f"{path.name}: via must be one of {sorted(VIA_KINDS)}")
    if kind not in VIA_KINDS[via]:
        raise ValueError(
            f"{path.name}: trigger.kind for via={via} must be one of {sorted(VIA_KINDS[via])}"
        )
    if kind == "chat" and not trigger.get("message"):
        raise ValueError(f"{path.name}: chat trigger needs a message")
    if kind == "invoice" and not trigger.get("invoice"):
        raise ValueError(f"{path.name}: invoice trigger needs an invoice")
    setup = raw.get("setup") or {}
    return Scenario(
        id=raw.get("id") or path.stem,
        via=via,
        trigger=trigger,
        vendor={**DEFAULT_VENDOR, **(setup.get("vendor") or {})},
        setup_invoices=list(setup.get("invoices") or []),
        vendor_overrides=dict(setup.get("vendor_overrides") or {}),
        onboard=bool(setup.get("onboard", False)),
        description=raw.get("description", ""),
        path=path,
    )
