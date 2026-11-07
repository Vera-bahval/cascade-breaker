"""get_vendor_invoices serves both the vendor chat (every invoice) and Fraud (paid history only)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from finbot.agents.specialized.fraud import FraudComplianceAgent
from finbot.core.data.models import Invoice
from finbot.tools.data.fraud import get_vendor_invoices


def _invoices(db, session, vendor_id):
    now = datetime.now(UTC)
    for n, status in enumerate(("paid", "submitted", "approved", "rejected"), start=1):
        db.add(Invoice(namespace=session.namespace, vendor_id=vendor_id, invoice_number=f"INV-{n}",
                       amount=100.0 * n, description=status, invoice_date=now,
                       due_date=now + timedelta(days=30), status=status))
    db.commit()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_all_statuses_by_default(vendor_pair_setup):
    s1, v1, db = vendor_pair_setup["s1"], vendor_pair_setup["v1"], vendor_pair_setup["db"]
    _invoices(db, s1, v1.id)
    statuses = {i["status"] for i in await get_vendor_invoices(v1.id, s1)}
    assert statuses == {"paid", "submitted", "approved", "rejected"}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_status_filter(vendor_pair_setup):
    s1, v1, db = vendor_pair_setup["s1"], vendor_pair_setup["v1"], vendor_pair_setup["db"]
    _invoices(db, s1, v1.id)
    assert [i["status"] for i in await get_vendor_invoices(v1.id, s1, status="paid")] == ["paid"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fraud_agent_asks_for_paid_history():
    agent = SimpleNamespace(agent_name="fraud_agent", session_context=SimpleNamespace(namespace="ns"),
                            workflow_id="wf")
    with patch("finbot.agents.specialized.fraud.get_vendor_invoices", AsyncMock(return_value=[])) as fetch, \
            patch("finbot.agents.utils.event_bus.emit_agent_event", AsyncMock()):
        await FraudComplianceAgent.get_vendor_invoices(agent, vendor_id=7)
    assert fetch.call_args.kwargs.get("status") == "paid"
