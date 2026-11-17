"""Control the simulated payment at the same MCP entry used by the agents."""
from datetime import UTC, datetime
import pytest
from fastmcp import Client
from finbot.core.data.models import Invoice
from finbot.core.data.repositories import MCPServerConfigRepository
from finbot.mcp.servers.finstripe.models import PaymentTransaction
from finbot.mcp.servers.finstripe.server import create_finstripe_server
from finbot.agents.runner import run_orchestrator_agent
from unittest.mock import AsyncMock


@pytest.mark.asyncio
@pytest.mark.parametrize(("category", "region", "disabled", "expected_tax"), [
    ("goods", "US-CA", False, 8.25),
    ("services", "US-CA", False, 0.0),
    ("goods", "unknown", False, None),
    ("goods", "US-CA", True, None),
])
async def test_tax_before_transfer(vendor_pair_setup, category, region, disabled, expected_tax):
    env = vendor_pair_setup
    session, db, vendor = env["s1"], env["db"], env["v1"]
    inv = Invoice(namespace=session.namespace, vendor_id=vendor.id, invoice_number="study",
                  amount=100, invoice_date=datetime.now(UTC), due_date=datetime.now(UTC),
                  tax_category=category, tax_jurisdiction=region)
    db.add(inv)
    db.commit()
    if disabled:
        MCPServerConfigRepository(db, session).upsert("taxcalc", "TaxCalc", enabled=False)
    async with Client(create_finstripe_server(session)) as client:
        reply = await client.call_tool("create_transfer", {
            "amount": 100, "invoice_id": inv.id, "vendor_id": vendor.id,
            "vendor_account": vendor.bank_account_number, "invoice_reference": "study", "payment_method": "ach",
        })
    txs = db.query(PaymentTransaction).all()
    if expected_tax is None:
        assert reply.data.get("requires_review") and txs == []
    else:
        assert reply.data["tax"]["tax_amount"] == expected_tax
        assert len(txs) == 1 and txs[0].amount == inv.amount
        assert txs[0].to_dict()["metadata"]["tax"] == reply.data["tax"]


@pytest.mark.asyncio
async def test_terminal_p0(vendor_pair_setup, monkeypatch):
    env = vendor_pair_setup
    s, db, vendor = env["s1"], env["db"], env["v1"]
    inv = Invoice(namespace=s.namespace, vendor_id=vendor.id, invoice_number="study",
                  amount=0, invoice_date=datetime.now(UTC), due_date=datetime.now(UTC))
    db.add(inv)
    db.commit()
    monkeypatch.setenv("PROBE_ENFORCE", "P0=V1")
    emit = AsyncMock()
    monkeypatch.setattr("finbot.agents.runner.event_bus.emit_agent_event", emit)
    result = await run_orchestrator_agent({"invoice_id": inv.id, "vendor_id": vendor.id}, s)
    assert result["task_status"] == "stopped" and result["guard_stop"]["point"] == "P0.input"
    assert emit.await_args.kwargs["event_type"] == "guard_stop"
    assert db.query(PaymentTransaction).count() == 0


@pytest.mark.asyncio
async def test_p4_stop_survives_background_and_prevents_transfer(vendor_pair_setup, monkeypatch):
    import asyncio
    from finbot.probe import trace
    from finbot.probe.guards import runtime as guards
    from finbot.probe.guards.workflow import workflow_guard

    db, vendor, session = (vendor_pair_setup[k] for k in ("db", "v1", "s1"))
    invoice = Invoice(namespace=session.namespace, vendor_id=vendor.id, invoice_number="pending",
                      amount=100, status="submitted", invoice_date=datetime.now(UTC), due_date=datetime.now(UTC))
    db.add(invoice)
    db.commit()
    task = {"invoice_id": invoice.id, "vendor_id": vendor.id}
    monkeypatch.setenv("PROBE_ENFORCE", "P4=V1")
    ready = asyncio.Event()

    async def delayed_payment():
        await ready.wait()
        await guards.before_tool("payments_agent", "finstripe__create_transfer", task)
        pytest.fail("Stopped workflow reached transfer")

    with trace.open_recorder(), workflow_guard("test-wf", session, task):
        pending = asyncio.create_task(delayed_payment())
        with pytest.raises(guards.GuardStop):
            await guards.before_tool("payments_agent", "finstripe__create_transfer", {**task, "amount": 100})
        ready.set()
        with pytest.raises(guards.GuardStop):
            await pending
    assert db.query(PaymentTransaction).count() == 0
