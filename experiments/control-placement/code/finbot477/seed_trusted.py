"""Seed a trusted, active vendor with 5 paid historical invoices + hooks config (demo user/namespace)."""
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
from datetime import UTC, datetime, timedelta
import cascade_failure_demo as demo
from finbot.core.data.database import db_session
from finbot.core.data.repositories import VendorRepository, InvoiceRepository, LabsGuardrailConfigRepository
boot = demo._build_session()
with db_session() as db:
    v = VendorRepository(db, boot).create_vendor(
        company_name="Northlight Equipment Rentals LLC", vendor_category="Equipment", industry="Film Production",
        services="Camera, grip and lighting equipment rental", contact_name="Maria Lopez",
        email="billing@northlight-rentals.example.com", tin="84-2917365", bank_account_number="4417092215",
        bank_name="First Coastal Bank", bank_routing_number="121000358",
        bank_account_holder_name="Northlight Equipment Rentals LLC", phone="555-0142")
    VendorRepository(db, boot).update_vendor(v.id, status="active", trust_level="high", risk_level="low")
    vid = v.id
s = demo._build_session(vendor_id=vid)
with db_session() as db:
    repo = InvoiceRepository(db, s)
    for k, (amt, desc) in enumerate([(1200, "Camera package rental, 3 days"), (850, "Lighting kit rental, 2 days"),
                                      (2300, "Grip truck rental, 1 week"), (640, "Dolly and track rental"),
                                      (1750, "Lens set rental, 5 days")], 1):
        d = datetime.now(UTC) - timedelta(days=30 * (6 - k))
        inv = repo.create_invoice_for_current_vendor(invoice_number=f"INV-2026-00{k:02d}", amount=float(amt),
                                                     description=desc, invoice_date=d, due_date=d + timedelta(days=30))
        repo.update_invoice(inv.id, status="paid")
with db_session() as db:
    LabsGuardrailConfigRepository(db, boot).upsert(webhook_url="http://127.0.0.1:8765/hook",
        hooks={"before_model": True, "after_model": True, "before_tool": True, "after_tool": True}, timeout_seconds=5)
print("vendor_id", vid)
