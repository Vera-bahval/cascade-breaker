"""Optional per-workflow enforcement. Based on the checkpoint-2 guarded runner."""
from contextlib import nullcontext
import os

from finbot.core.data.database import db_session
from finbot.core.data.repositories import InvoiceRepository, VendorRepository
from finbot.mcp.servers.finstripe.models import PaymentTransaction
from finbot.probe.guards.invariants import InvariantVerifier, TextRuleVerifier
from finbot.probe.guards.llm import ConsistencyVerifier
from finbot.probe.guards.runtime import GuardRuntime, active_runtime, open_runtime


def workflow_guard(workflow_id, session, task):
    spec = os.getenv("PROBE_ENFORCE", "").strip()
    if not spec or active_runtime() is not None:
        return nullcontext()
    classes = {v.name: v for v in (InvariantVerifier, TextRuleVerifier, ConsistencyVerifier)}
    selections = {}
    for entry in spec.split(","):
        point, sep, verifier = entry.strip().partition("=")
        if not sep or verifier not in classes or point.split(".")[0] not in classes[verifier].families:
            raise ValueError("Invalid PROBE_ENFORCE selection")
        selections[point] = verifier

    def snapshot():
        with db_session() as db:
            invoice = InvoiceRepository(db, session).get_invoice(task.get("invoice_id"))
            vendor_id = invoice.vendor_id if invoice else task.get("vendor_id")
            vendor = VendorRepository(db, session).get_vendor(vendor_id)
            txs = db.query(PaymentTransaction).filter_by(
                namespace=session.namespace, invoice_id=invoice.id if invoice else None
            ).all()
            return {"invoice": invoice.to_dict() if invoice else {},
                    "vendor": vendor.to_dict() if vendor else {},
                    "transactions": [tx.to_dict() for tx in txs]}

    return open_runtime(GuardRuntime("enforce", workflow_id,
                                     [classes[name]() for name in sorted(set(selections.values()))],
                                     snapshot, selections))
