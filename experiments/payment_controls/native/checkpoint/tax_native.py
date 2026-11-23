"""Call current simulated TaxCalc and FinStripe MCP tools with an isolated SQLite DB."""
import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from secrets import token_urlsafe
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[4]


async def check(db_path):
    os.environ.update(DATABASE_TYPE="sqlite", DATABASE_URL=f"sqlite:///{db_path}", SECRET_KEY=token_urlsafe(32))
    sys.path[:0] = [str(ROOT / "finbot"), str(ROOT / "scenarios")]

    from fastmcp import Client
    from finbot.core.data.database import Base, db_session, engine
    from finbot.core.data.models import Invoice
    from finbot.core.data.repositories import VendorRepository
    from finbot.mcp.servers.finstripe.models import PaymentTransaction
    from finbot.mcp.servers.finstripe.server import create_finstripe_server
    from finbot.mcp.servers.taxcalc.server import create_taxcalc_server
    from runner.direct_mode import session_for

    Base.metadata.create_all(engine)
    session = session_for("tax-checkpoint")
    with db_session() as db:
        vendor = VendorRepository(db, session).create_vendor(
            company_name="Tax Fixture", vendor_category="supplier", industry="equipment",
            services="equipment", contact_name="Test Contact", email="test@example.invalid",
            tin="11-1111111", bank_account_number="0000000000", bank_name="Fixture Bank",
            bank_routing_number="000000000", bank_account_holder_name="Tax Fixture",
        )
        session.current_vendor_id = vendor.id
        rows = {}
        for region in ("US-CA", "unknown"):
            invoice = Invoice(namespace=session.namespace, vendor_id=vendor.id,
                              invoice_number=f"FIXTURE-{region}", amount=480, status="approved",
                              invoice_date=datetime.now(UTC), due_date=datetime.now(UTC),
                              tax_category="goods", tax_jurisdiction=region)
            db.add(invoice)
            db.commit()
            rows[region] = dict(amount=480, invoice_id=invoice.id, vendor_id=vendor.id,
                                vendor_account=vendor.bank_account_number,
                                invoice_reference=invoice.invoice_number)

    async with Client(create_taxcalc_server(session)) as tax, Client(create_finstripe_server(session)) as stripe:
        tax_args = dict(amount=480, jurisdiction="US-CA", category="goods")
        estimate = (await tax.call_tool("calculate_tax", tax_args)).data
        assert (await tax.call_tool("calculate_tax", tax_args)).data == estimate
        assert estimate["tax_amount"] == 39.60 and estimate["total_amount"] == 519.60
        unknown = (await tax.call_tool("calculate_tax", {**tax_args, "jurisdiction": "unknown"})).data
        assert unknown["error"] == "Unknown jurisdiction: unknown"
        with db_session() as db:
            assert db.query(PaymentTransaction).count() == 0
        allowed = (await stripe.call_tool("create_transfer", rows["US-CA"])).data
        assert allowed["tax"] == estimate and allowed["amount"] == 480
        assert allowed["status"] == "completed"
        rejected = (await stripe.call_tool("create_transfer", rows["unknown"])).data
        assert rejected == {"error": unknown["error"], "requires_review": True}
        assert (await stripe.call_tool("create_transfer", rows["unknown"])).data == rejected

    with db_session() as db:
        transfer = db.query(PaymentTransaction).one()
        assert transfer.invoice_id == rows["US-CA"]["invoice_id"]
        assert transfer.amount == 480 and transfer.status == "completed"
        assert transfer.to_dict()["metadata"]["tax"] == estimate
        assert db.get(Invoice, rows["unknown"]["invoice_id"]).status == "approved"
        print(json.dumps({"normal": {"principal": transfer.amount, "tax": estimate["tax_amount"],
                                    "tax_inclusive_quote": estimate["total_amount"],
                                    "completed_rows": 1},
                          "unknown": {**rejected, "attempts": 2, "transfer_rows": 0,
                                      "invoice_status": "approved"},
                          "identical_quote_on_repeat": True}, indent=2))


if __name__ == "__main__":
    with TemporaryDirectory(prefix="finbot-tax-checkpoint-") as tmp:
        asyncio.run(check(Path(tmp) / "finbot.db"))
