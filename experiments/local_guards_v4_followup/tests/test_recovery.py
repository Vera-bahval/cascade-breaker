"""Supplemental native recovery checks after method freeze; no accuracy corpus.

Only this module's explicit tests run. Frozen harness methods are reused through
composition, with its Runtime factory redirected solely to the new v4.2 class.
"""
from unittest.mock import patch
import unittest

from experiments.local_guards_v4.tests import test_runtime as harness
from experiments.local_guards_v4 import execution_supplement
from experiments.local_guards_v4_followup.runtime import Runtime
from experiments.local_guards_v4_followup.guard import guard
from finbot.agents.specialized.onboarding import VendorOnboardingAgent
from finbot.agents.specialized.fraud import FraudComplianceAgent
from finbot.agents.specialized.invoice import InvoiceAgent
from finbot.agents.specialized.payments import PaymentsAgent
from finbot.core.data.database import db_session
from finbot.core.data.models import Invoice, Vendor
from finbot.mcp.provider import MCPToolProvider
from finbot.mcp.servers.finstripe.models import PaymentTransaction
from finbot.mcp.servers.finstripe.server import create_finstripe_server
from finbot.probe import v4


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        def factory(*args, **kwargs):
            kwargs["diagnostics"]=True
            runtime=Runtime(*args,**kwargs)
            self.assertIs(type(runtime),Runtime)
            return runtime
        self.factory=factory
        self.enterContext(patch.object(harness,"Runtime",factory))
        self.enterContext(patch.object(execution_supplement,"Runtime",factory))
        self.case=harness.NativeRuntimeTests("test_corrupt_journal_fails_closed_before_model")
        self.case.setUp()
        # The composed IsolatedAsyncioTestCase has no owned asyncio runner;
        # invoke its two synchronous resource cleanups directly.
        self.addCleanup(self.case.directory.cleanup)
        self.addCleanup(self.case.stack.close)
        self.assertIs(type(self.case.runtime),Runtime)

    async def test_corrupt_journal_before_model_or_effect(self):
        await self.case.test_corrupt_journal_fails_closed_before_model()
        with db_session() as db:
            self.assertEqual(db.query(PaymentTransaction).count(),0)
            self.assertEqual(db.get(Invoice,3).status,"submitted")

    async def test_verifier_exception_before_effect(self):
        case=self.case
        case.script({"invoice_agent":[[harness.done()]]})
        # Deliberate one-call fault injection into the NEW runtime module only.
        with patch("experiments.local_guards_v4_followup.runtime.guard",side_effect=ValueError("authored verifier fault")):
            with case.runtime.open(), self.assertRaises(v4.V4Stop):
                await harness.run_invoice_agent(case.task,case.session)
        self.assertEqual(case.calls,[])
        with db_session() as db:
            self.assertEqual(db.query(PaymentTransaction).count(),0)
            self.assertEqual(db.get(Invoice,3).status,"submitted")

    async def test_restart_uncertain_claim_blocks_new_owner(self):
        await self.case.test_restart_uncertain_claim_blocks_new_owner()

    async def test_confirmed_no_effect_failure_releases_and_retries(self):
        await execution_supplement.ReconciledRetry.test_known_no_effect_failure_can_be_reconciled_then_retried(self.case)

    async def test_amount_edit_blocks_before_transfer(self):
        await self.case.test_amount_edit_invalidates_approval_before_transfer()

    async def test_account_edit_blocks_before_transfer(self):
        await self.case.test_account_edit_invalidates_approval_before_transfer()

    async def test_chat_background_preserves_new_runtime(self):
        await self.case.test_background_exec_opens_captured_runtime_after_chat_reset()

    async def test_duplicate_chat_start_is_blocked_before_scheduling(self):
        await self.case.test_concurrent_chat_duplicate_admission_before_scheduling()

    async def test_stop_prevents_later_native_tool_and_model(self):
        await self.case.test_stop_blocks_later_contextual_model_call()
        actor=InvoiceAgent(self.case.session)
        with self.assertRaises(v4.V4Stop):
            with self.case.runtime.open():
                await actor._get_final_callables()["update_invoice_status"](invoice_id=3,
                    status="approved",agent_notes="must never execute after STOP")
        with db_session() as db:
            self.assertEqual(db.get(Invoice,3).status,"submitted")

    async def test_stop_prevents_direct_chat_model(self):
        await self.case.test_chat_direct_responses_blocked_after_stop()

    async def test_native_vendor_enum_rejected_before_effect(self):
        await self.case.test_native_vendor_mutation_enum_before_effect()

    async def test_native_vendor_authority_and_real_legal_write(self):
        case=self.case
        actor=VendorOnboardingAgent(case.session)
        with case.runtime.agent_scope(actor,case.task):
            result=await actor._get_final_callables()["update_vendor_status"](vendor_id=2,
                status="active",trust_level="high",risk_level="low",agent_notes="authored legal write")
        with db_session() as db:
            vendor=db.get(Vendor,2)
            self.assertEqual((vendor.status,vendor.trust_level,vendor.risk_level),("active","high","low"))
        # A concrete payments actor cannot gain vendor authority from a callable map.
        wrong=PaymentsAgent(case.session)
        with case.runtime.agent_scope(wrong,case.task):
            wrapped=v4.wrap_callables(wrong,{"update_vendor_status":actor.update_vendor_status})
            with self.assertRaises(v4.V4Stop) as stopped:
                await wrapped["update_vendor_status"](vendor_id=2,status="inactive",trust_level="low",risk_level="high",agent_notes="denied")
        self.assertEqual(stopped.exception.decision["decision"],"BLOCK")
        with db_session() as db:
            vendor=db.get(Vendor,2)
            self.assertEqual((vendor.status,vendor.trust_level,vendor.risk_level),("active","high","low"))

    async def _edit_then_reapprove_and_pay(self, field):
        case=self.case; runtime=case.runtime
        invoice=InvoiceAgent(case.session)
        with runtime.agent_scope(invoice,case.task):
            await invoice._get_final_callables()["update_invoice_status"](invoice_id=3,status="approved",agent_notes="initial approval")
        before=runtime.snapshot("P0",invoice,None,case.task)
        binding=runtime.store.approval(before["context"])
        self.assertIsNotNone(binding)
        with db_session() as db:
            if field=="amount": db.get(Invoice,3).amount=101.
            else: db.get(Vendor,2).bank_account_number="edited-account"
            db.commit()
        amount=101. if field=="amount" else 100.
        account="edited-account" if field=="account" else "account"
        payments=PaymentsAgent(case.session)
        arguments=dict(vendor_account=account,amount=amount,invoice_reference="recovery",vendor_id=2,invoice_id=3)
        # This is a shadow inspection, not an attempted effect: an actual denied
        # transfer is separately tested and makes its admitted owner irreversible.
        stale=runtime.snapshot("P4",payments,"finstripe__create_transfer",arguments)
        self.assertIsNone(runtime.store.approval(stale["context"]))
        result=guard(stale,dict(profile=runtime.requested_profile,
            enabled_requirements=list(runtime.policy["enabled_requirements"])))
        self.assertEqual(result["decision"],"UNKNOWN")
        self.assertIn({"id":"B01","state":"unknown"},result["requirements"])
        with runtime.agent_scope(invoice,case.task):
            await invoice._get_final_callables()["update_invoice_status"](invoice_id=3,status="approved",agent_notes="explicit renewed approval")
        fresh=runtime.snapshot("P0",invoice,None,case.task)
        renewed=runtime.store.approval(fresh["context"])
        self.assertIsNotNone(renewed)
        self.assertNotEqual(binding["record_id"],renewed["record_id"])
        version="invoice_version" if field=="amount" else "vendor_version"
        self.assertNotEqual(binding[version],renewed[version])
        # Material-bound review must also be newly established from actual tools.
        fraud=FraudComplianceAgent(case.session)
        with runtime.agent_scope(fraud,case.task):
            calls=fraud._get_final_callables()
            await calls["get_invoice_details"](invoice_id=3)
            await calls["get_vendor_risk_profile"](vendor_id=2)
            await calls["complete_task"](task_status="success",task_summary="typed review complete")
        provider=MCPToolProvider({"finstripe":create_finstripe_server(case.session)},case.session)
        await provider.connect()
        try:
            with runtime.agent_scope(payments,case.task):
                transfer=await provider.get_callables()["finstripe__create_transfer"](**arguments)
                await payments._get_final_callables()["process_payment"](invoice_id=3,payment_method="bank_transfer",
                    payment_reference=transfer["transfer_id"],agent_notes="paid once after renewed evidence")
        finally:
            await provider.disconnect()
        runtime.child_complete(payments,{"task_status":"success"})
        with db_session() as db:
            self.assertEqual(db.get(Invoice,3).status,"paid")
            rows=db.query(PaymentTransaction).all()
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0].amount,amount)
        self.assertEqual(case.calls,[])

    async def test_amount_edit_reapproval_then_real_payment(self):
        await self._edit_then_reapprove_and_pay("amount")

    async def test_account_edit_reapproval_then_real_payment(self):
        await self._edit_then_reapprove_and_pay("account")


if __name__=="__main__": unittest.main()
