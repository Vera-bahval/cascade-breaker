"""FinBot is imported from the current environment, so run this from the finbot/ directory."""

from __future__ import annotations

import asyncio
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from runner.scenario import Scenario, invoice_fields
from runner.state import load_state, save_result, save_state

# Same texts the vendor API routes send, so a direct run starts like a portal one.
ONBOARDING_TASK = (
    "A new vendor has registered. Evaluate and onboard the vendor, then notify them of the decision."
)
INVOICE_TASK = (
    "A new invoice has been submitted. Process the invoice and notify the vendor of the decision."
)


def _session(namespace: str, vendor_id: int | None = None):
    from finbot.core.auth.session import SessionContext

    now = datetime.now(UTC)
    return SessionContext(
        session_id=f"sess_{secrets.token_urlsafe(12)}",
        user_id="scenario_runner",
        is_temporary=False,
        namespace=namespace,
        created_at=now,
        expires_at=now + timedelta(hours=2),
        email="scenario-runner@example.com",
        portal_type="vendor",
        current_vendor_id=vendor_id,
    )


async def _ensure_event_bus() -> bool:
    # Agents emit events to Redis on every step; without Redis turn emission off.
    from finbot.core.messaging import event_bus

    try:
        await asyncio.wait_for(event_bus.redis.ping(), timeout=2)
        return True
    except Exception:  # pylint: disable=broad-exception-caught
        async def _noop(*_args: Any, **_kwargs: Any) -> None:
            return None

        event_bus.emit_agent_event = _noop
        event_bus.emit_business_event = _noop
        return False


def _create_vendor(namespace: str, vendor: dict[str, Any], overrides: dict[str, Any]) -> int:
    from finbot.core.data.database import db_session
    from finbot.core.data.repositories import VendorRepository

    fields = dict(vendor)
    fields["contact_name"] = fields.pop("name")
    with db_session() as db:
        repo = VendorRepository(db, _session(namespace))
        created = repo.create_vendor(**fields)
        if overrides:
            repo.update_vendor(created.id, **overrides)
        return created.id


def _create_invoice(namespace: str, vendor_id: int, fields: dict[str, Any],
                    status: str | None = None) -> int:
    from finbot.core.data.database import db_session
    from finbot.core.data.repositories import InvoiceRepository

    row = dict(fields)
    if status:
        row["status"] = status
    for key in ("invoice_date", "due_date"):
        row[key] = datetime.fromisoformat(row[key]).replace(tzinfo=UTC)
    with db_session() as db:
        return InvoiceRepository(db, _session(namespace, vendor_id)).create_invoice_for_current_vendor(**row).id


def snapshot(namespace: str, vendor_id: int) -> dict[str, Any]:
    from finbot.core.data.database import db_session
    from finbot.core.data.repositories import InvoiceRepository, VendorRepository
    from finbot.mcp.servers.finstripe.models import PaymentTransaction

    session = _session(namespace, vendor_id)
    with db_session() as db:
        vendor = VendorRepository(db, session).get_vendor(vendor_id)
        invoices = InvoiceRepository(db, session).list_invoices_for_current_vendor()
        txns = (
            db.query(PaymentTransaction)
            .filter(PaymentTransaction.namespace == namespace,
                    PaymentTransaction.vendor_id == vendor_id)
            .order_by(PaymentTransaction.id)
            .all()
        )
        return {
            "vendor": vendor.to_dict() if vendor else None,
            "invoices": [inv.to_dict() for inv in invoices or []],
            "transactions": [
                {"transfer_id": t.transfer_id, "invoice_id": t.invoice_id, "amount": t.amount,
                 "status": t.status, "payment_method": t.payment_method}
                for t in txns
            ],
        }


async def _orchestrate(namespace: str, vendor_id: int, task_data: dict[str, Any],
                       injection: Any = None) -> dict[str, Any]:
    from finbot.agents.runner import run_orchestrator_agent
    from finbot.probe import injections as probe_injections
    from finbot.probe import trace as probe_trace

    workflow_id = f"wf_scn_{secrets.token_urlsafe(9)}"
    error, result = None, {}
    started = time.perf_counter()
    with probe_trace.open_recorder() as recorder, probe_injections.open_injection(injection):
        try:
            result = await run_orchestrator_agent(
                task_data=task_data,
                session_context=_session(namespace, vendor_id),
                workflow_id=workflow_id,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            error = f"{type(e).__name__}: {str(e)[:500]}"
    return {
        "workflow_id": workflow_id,
        "task_data": task_data,
        "wall_s": round(time.perf_counter() - started, 2),
        "error": error,
        "orchestrator_status": result.get("task_status"),
        "orchestrator_summary": result.get("task_summary"),
        "injection": injection.label() if injection else None,
        "injection_applied": bool(injection and injection.applied),
        "steps": recorder.steps,
        "tool_defs": recorder.tool_defs,
    }


async def _prepare(scenario: Scenario) -> dict[str, Any]:
    redis = await _ensure_event_bus()
    tag = secrets.token_hex(3)
    namespace = f"scn-{scenario.id}-{tag}"
    vendor_id = _create_vendor(namespace, scenario.vendor, scenario.vendor_overrides)
    onboarding = None
    if scenario.onboard:
        onboarding = await _orchestrate(
            namespace, vendor_id, {"vendor_id": vendor_id, "description": ONBOARDING_TASK})
    invoice_ids = [
        _create_invoice(namespace, vendor_id, invoice_fields(spec, f"INV-{tag}-S{n}"),
                        spec.get("status"))
        for n, spec in enumerate(scenario.setup_invoices, start=1)
    ]
    state = {
        "scenario": scenario.id,
        "via": "direct",
        "tag": tag,
        "namespace": namespace,
        "vendor_id": vendor_id,
        "setup_invoice_ids": invoice_ids,
        "redis": redis,
        "prepared_at": datetime.now(UTC).isoformat(),
        "onboarding": onboarding,
    }
    save_state(scenario.id, state)
    return state


async def _run(scenario: Scenario) -> dict[str, Any]:
    from finbot.probe import injections as probe_injections

    state = load_state(scenario.id)
    if state.get("via") != "direct":
        raise RuntimeError(f"State for {scenario.id} was prepared for via={state.get('via')}")
    await _ensure_event_bus()
    namespace, vendor_id = state["namespace"], state["vendor_id"]
    trigger = scenario.trigger
    task_data: dict[str, Any] = {"vendor_id": vendor_id}
    invoice_id = None
    if trigger.get("invoice"):
        invoice_id = _create_invoice(
            namespace, vendor_id, invoice_fields(trigger["invoice"], f"INV-{state['tag']}"))
    elif trigger.get("use_setup_invoice"):
        invoice_id = state["setup_invoice_ids"][int(trigger["use_setup_invoice"]) - 1]
    if invoice_id:
        task_data["invoice_id"] = invoice_id
    task_data["description"] = trigger.get("description") or (
        INVOICE_TASK if invoice_id else ONBOARDING_TASK)
    injection = None
    if trigger.get("injection"):
        spec = trigger["injection"]
        injection = probe_injections.InjectionSpec(spec["node"], spec["fault"], invoice_id or 0)
    before = snapshot(namespace, vendor_id)
    started_at = datetime.now(UTC).isoformat()
    run = await _orchestrate(namespace, vendor_id, task_data, injection)
    result = {
        "scenario": scenario.id,
        "via": "direct",
        "kind": scenario.kind,
        "trigger": trigger,
        "started_at": started_at,
        "namespace": namespace,
        **run,
        "before": before,
        "after": snapshot(namespace, vendor_id),
    }
    result["path"] = str(save_result(scenario.id, result))
    return result


def prepare(scenario: Scenario) -> dict[str, Any]:
    return asyncio.run(_prepare(scenario))


def run(scenario: Scenario) -> dict[str, Any]:
    return asyncio.run(_run(scenario))
