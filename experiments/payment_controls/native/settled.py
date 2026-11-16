"""Seed an already completed local transaction before reprocessing the very same invoice."""
import json
from pathlib import Path


def wrap(case_direct, dest):
    orchestrate=case_direct._orchestrate
    async def reprocess(namespace, vid, task):
        from finbot.core.data.database import db_session
        from finbot.core.data.repositories import InvoiceRepository
        from finbot.mcp.servers.finstripe.repositories import PaymentTransactionRepository
        from runner.direct_mode import session_for
        session=session_for(namespace,vid)
        iid=task["invoice_id"]
        with db_session() as db:
            invoices=InvoiceRepository(db,session)
            invoice=invoices.get_invoice(iid)
            tx=PaymentTransactionRepository(db,session).create_transaction(
                invoice_id=iid,vendor_id=vid,transfer_id="tr_native_prior",amount=invoice.amount,
                payment_method="bank_transfer",status="completed")
            invoices.update_invoice(iid,status="paid",agent_notes="Previously settled transfer "+tx.transfer_id)
            assert invoices.get_invoice(iid).status=="paid" and tx.invoice_id==iid and tx.status=="completed"
            (dest/"prior.json").write_text(json.dumps({"invoice_id":iid,"transfer_id":tx.transfer_id,"amount":tx.amount}))
        return await orchestrate(namespace,vid,task)
    case_direct._orchestrate=reprocess
