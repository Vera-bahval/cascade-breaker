"""Native DB and hook tests on authored tiny fixtures; no external sockets."""
import asyncio
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

_ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(_ROOT/"finbot"))
_DB=tempfile.TemporaryDirectory(prefix="v42-native-")
os.environ["DATABASE_URL"]="sqlite:///"+str(Path(_DB.name)/"native.db")
os.environ["DATABASE_TYPE"]="sqlite"
os.environ["OPENAI_API_KEY"]="local-no-network"
os.environ.pop("FINBOT_V4_PROFILE",None)

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import Base, db_session, engine
from finbot.core.data.models import Invoice, Vendor
from finbot.mcp.servers.finstripe.models import PaymentTransaction
from finbot.mcp.servers.findrive.models import FinDriveFile
from finbot.agents.specialized.invoice import InvoiceAgent
from finbot.agents.specialized.payments import PaymentsAgent
from finbot.agents.specialized.fraud import FraudComplianceAgent
from finbot.agents.orchestrator import OrchestratorAgent
from finbot.agents.runner import run_agent_with_retry
from finbot.core.llm.contextual_client import ContextualLLMClient
from finbot.probe import v4
from experiments.local_guards_v4_followup.runtime import Runtime as SubjectRuntime

Base.metadata.create_all(engine)


class ScriptClient:
    default_model="local-script"
    default_temperature=0
    def __init__(self, steps=()):
        self.steps=list(steps); self.calls=0
    async def chat(self,request):
        self.calls+=1
        if not self.steps: raise AssertionError("unexpected script request")
        calls=[dict(call,call_id="script-"+str(self.calls)+"-"+str(i)) for i,call in enumerate(self.steps.pop(0))]
        return SimpleNamespace(content=None,messages=None,tool_calls=calls,success=True,metadata={},
            model_dump_json=lambda:json.dumps({"tool_calls":calls}))


class RuntimeContract(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="v42-sidecar-")
        self.addCleanup(self.tmp.cleanup)
        self.namespace="tiny-"+uuid4().hex
        now=datetime.now(UTC)
        self.session=SessionContext("session-"+uuid4().hex,"user",False,self.namespace,
            now,now+timedelta(hours=1),portal_type="admin")
        with db_session() as db:
            vendor=Vendor(namespace=self.namespace,company_name="Tiny",vendor_category="services",
                industry="services",services="plain",contact_name="Person",email=self.namespace+"@example.test",
                tin="test",bank_account_number="fixture-account",bank_name="test",bank_routing_number="test",
                bank_account_holder_name="Tiny",status="active")
            db.add(vendor); db.flush()
            invoice=Invoice(namespace=self.namespace,vendor_id=vendor.id,amount=80,
                invoice_date=now,due_date=now+timedelta(days=1),status="approved")
            db.add(invoice); db.commit(); self.vendor_id=vendor.id; self.invoice_id=invoice.id
        self.task=dict(vendor_id=self.vendor_id,invoice_id=self.invoice_id,description="plain fixture")
        self.client=ScriptClient()
        self.patch=patch("finbot.core.llm.contextual_client.get_llm_client",return_value=self.client)
        self.patch.start(); self.addCleanup(self.patch.stop)
        # Redis event publication is telemetry outside the guard/effect contract.
        for method in ("emit_agent_event","emit_business_event"):
            telemetry=patch("finbot.core.messaging.event_bus."+method,new=AsyncMock())
            telemetry.start(); self.addCleanup(telemetry.stop)
        # Any attempted network operation fails before a connection can leave the process.
        network=patch.object(socket.socket,"connect",side_effect=AssertionError("external socket forbidden"))
        network.start(); self.addCleanup(network.stop)

    def runtime(self, **kw):
        return SubjectRuntime(Path(self.tmp.name)/(uuid4().hex+".db"),
            fixture_contract=dict(invoice_currency="USD",binding_hold=False,fraud_review_completed=True),**kw)

    def agent(self,cls=PaymentsAgent,workflow="native-workflow"):
        return cls(session_context=self.session,workflow_id=workflow)

    def test_snapshot_has_real_origin_and_after_read_cut(self):
        rt=self.runtime(); agent=self.agent(); rt.initialize(self.session,self.task)
        obj=rt.snapshot("P4",agent,"finstripe__create_transfer",dict(self.task,amount=80,currency="usd",vendor_account="fixture-account"))
        p=obj["provenance"]["invoice_amount"][0]
        self.assertEqual(p.get("evidence_kind"),"server_snapshot")
        self.assertTrue(p.get("snapshot_id")); self.assertNotIn("source_call_id",p)
        self.assertLess(p["event_seq"],obj["event_seq"])

    def test_fork_keeps_subclass(self):
        rt=self.runtime(); child=rt.fork_workflow(self.session,self.task,"child-owner")
        self.assertIs(type(child),type(rt))
        self.assertFalse(child.diagnostics)

    def test_diagnostics_do_not_change_effects(self):
        effects=[]
        async def run(enabled):
            seen=[]; rt=self.runtime(diagnostics=enabled,check_observer=lambda o,r,t:seen.append((o,r,t)))
            agent=self.agent(); rt.initialize(self.session,self.task)
            async def execute():
                effects.append(enabled); return {"status":"completed","transfer_id":"test-"+str(enabled)}
            with rt.open():
                await rt.invoke(agent,"finstripe__create_transfer",dict(self.task,amount=80,currency="usd",vendor_account="fixture-account"),execute)
            self.assertEqual(len(rt.diagnostic_records),len(seen) if enabled else 0)
            self.assertEqual(len(rt.decisions),len(rt.diagnostic_records))
            self.assertTrue(all("decision_ms" in t for _,_,t in seen))
            return [r["decision"] for _,r,_ in seen],len(rt.store.events(rt.subject_key(self.invoice_id,self.vendor_id)))
        off=asyncio.run(run(False)); on=asyncio.run(run(True))
        self.assertEqual(off,on); self.assertEqual(effects,[False,True])

    def test_diagnostics_preserve_hold_and_stop_effects(self):
        outcomes=[]
        for enabled in (False,True):
            seen=[]; effects=[]
            rt=self.runtime(diagnostics=enabled,check_observer=lambda o,r,t:seen.append(r["decision"]))
            fraud=self.agent(FraudComplianceAgent); payments=self.agent()
            rt.initialize(self.session,self.task)
            async def flag(): return {"recommended_action":"hold"}
            async def transfer(): effects.append("transfer"); return {}
            async def run():
                with rt.open():
                    await rt.invoke(fraud,"flag_invoice_for_review",{"invoice_id":self.invoice_id},flag)
                    with self.assertRaises(v4.V4Stop):
                        await rt.invoke(payments,"finstripe__create_transfer",dict(self.task,amount=80,currency="usd",vendor_account="fixture-account"),transfer)
            asyncio.run(run())
            typed=[(e["payload"]["key"],e["payload"]["value"]) for e in rt.store.events(rt.subject_key(self.invoice_id,self.vendor_id)) if e["kind"]=="typed_fact"]
            outcomes.append((seen,effects,typed,rt.store.stopped(rt.owner)["decision"]))
        self.assertEqual(outcomes[0],outcomes[1])
        self.assertEqual(outcomes[0][1],[])
        self.assertEqual(outcomes[0][-1],"BLOCK")

    def test_typed_history_preserves_producing_call(self):
        rt=self.runtime(); agent=self.agent(FraudComplianceAgent); rt.initialize(self.session,self.task)
        async def execute(): return {"recommended_action":"hold"}
        with rt.open():
            asyncio.run(rt.invoke(agent,"flag_invoice_for_review",{"invoice_id":self.invoice_id,"recommended_action":"hold"},execute))
        events=[e for e in rt.store.events(rt.subject_key(self.invoice_id,self.vendor_id)) if e["kind"]=="typed_fact"]
        obj=rt.snapshot("P0",agent,None,self.task)
        p=max(obj["provenance"]["binding_hold"],key=lambda p:p["event_seq"])
        self.assertEqual(p["evidence_kind"],"tool_result")
        self.assertEqual(p["source_call_id"],events[0]["payload"]["source_call_id"])
        self.assertNotEqual(p["source_call_id"],obj["context"]["call_id"])

    def test_native_delegation_records_actual_tuple(self):
        rt=self.runtime(diagnostics=True); parent=self.agent(OrchestratorAgent,"actual-parent")
        child=self.agent(InvoiceAgent,"actual-child")
        async def execute():
            with v4.agent_entry(child,self.task):
                rt.child_complete(child,{"task_status":"success","parent_workflow_id":"invented"})
            return {"task_status":"success"}
        with rt.agent_scope(parent,self.task):
            asyncio.run(rt.invoke(parent,"delegate_to_invoice",{"invoice_id":self.invoice_id},execute))
        p2=next(d for d in rt.diagnostic_records if d["checkpoint"]=="P2")
        ctx=p2["observation"]["context"]
        self.assertEqual(ctx["parent_workflow_id"],"actual-parent")
        self.assertEqual(ctx["delegated_workflow_id"],"actual-child")
        self.assertNotEqual(ctx["workflow_id"],"actual-parent")
        p=p2["observation"]["provenance"]["delegation_subject_matches"][-1]
        for key in ("parent_workflow_id","delegated_workflow_id","delegation_call_id"):
            self.assertEqual(p[key],ctx[key])
        self.assertEqual(p2["decision"],"ALLOW")

    def test_masks_control_claim_and_native_server_filter_independently(self):
        for enabled,claim,filtered in ((["B01"],False,False),(["B02"],True,False),(["B03"],False,True)):
            with self.subTest(enabled=enabled):
                policy={"profile":"B","enabled_requirements":list(enabled)}
                rt=self.runtime(profile="B",policy=policy)
                policy["enabled_requirements"].append("B02")
                session=SessionContext(**{**self.session.__dict__,"portal_type":"vendor"})
                agent=self.agent(); agent.session_context=session
                with rt.agent_scope(agent,self.task):
                    self.assertEqual("systemutils" not in v4.filter_servers({"systemutils":object()}),filtered)
                    obj=rt.snapshot("P0",agent,None,self.task)
                self.assertEqual(rt.store.claim(rt.owner) is not None,claim)
                self.assertEqual("claim" in obj["context"],claim)
                child=rt.fork_workflow(session,dict(self.task,invoice_id=None),"fork-"+uuid4().hex) if not claim else None
                if child is not None:
                    self.assertEqual(child.policy,rt.policy)
                    self.assertEqual(child.requested_profile,"B")

    def test_native_delegation_rejects_changed_authenticated_identity(self):
        rt=self.runtime(); parent=self.agent(OrchestratorAgent,"parent")
        child=self.agent(InvoiceAgent,"child")
        child.session_context=SessionContext(**{**self.session.__dict__,"user_id":"other-user"})
        async def execute():
            with v4.agent_entry(child,self.task):
                rt.child_complete(child,{"task_status":"success"})
            return {"task_status":"success"}
        with rt.agent_scope(parent,self.task):
            with self.assertRaises(v4.V4Stop) as stopped:
                asyncio.run(rt.invoke(parent,"delegate_to_invoice",{"invoice_id":self.invoice_id},execute))
        self.assertEqual(stopped.exception.decision["decision"],"BLOCK")

    def test_native_scripted_runner_approval_and_stop(self):
        async def run(hold):
            with db_session() as db:
                db.query(Invoice).filter_by(id=self.invoice_id).one().status="submitted"
                db.commit()
            self.client.steps=[[
                {"name":"update_invoice_status","arguments":{"invoice_id":self.invoice_id,"status":"approved","agent_notes":"plain"}},
                {"name":"complete_task","arguments":{"task_status":"success","task_summary":"plain"}},
            ]]
            self.client.calls=0
            rt=self.runtime(profile="B",diagnostics=True); rt.fixture["binding_hold"]=hold
            with patch.object(InvoiceAgent,"_connect_mcp_servers",new=AsyncMock()):
                with rt.open():
                    if hold:
                        with self.assertRaises(v4.V4Stop):
                            await run_agent_with_retry(InvoiceAgent,self.session,self.task,max_retries=3)
                    else:
                        result=await run_agent_with_retry(InvoiceAgent,self.session,self.task,max_retries=3)
                        self.assertEqual(result["task_status"],"success")
            self.assertEqual(self.client.calls,1)
            self.assertEqual(any(d["tool"]=="complete_task" for d in rt.diagnostic_records),not hold)
            with db_session() as db:
                self.assertEqual(db.query(Invoice).filter_by(id=self.invoice_id).one().status,"submitted" if hold else "approved")
            if hold:
                self.assertIsNone(rt.store.approval(rt.snapshot("P0",self.agent(),None,self.task)["context"]))
                self.assertEqual(rt.store.claim(rt.owner)["state"],"uncertain")
            else:
                context=rt.snapshot("P0",self.agent(),None,self.task)["context"]
                self.assertIsNotNone(rt.store.approval(context))
                self.assertEqual(rt.store.claim(rt.owner)["state"],"released")
        asyncio.run(run(False)); asyncio.run(run(True))

    def test_real_inprocess_finstripe_effect_and_duplicate_stop(self):
        from finbot.mcp.servers.finstripe.server import create_finstripe_server
        async def run():
            rt=self.runtime(); agent=self.agent(); rt.initialize(self.session,self.task)
            server=create_finstripe_server(self.session)
            tool=await server.get_tool("create_transfer")
            args=dict(vendor_id=self.vendor_id,invoice_id=self.invoice_id,amount=80,
                vendor_account="fixture-account",invoice_reference="tiny",currency="usd")
            async def execute(): return tool.fn(**args)
            with rt.open():
                result=await rt.invoke(agent,"finstripe__create_transfer",args,execute)
                self.assertEqual(result["status"],"completed")
                with self.assertRaises(v4.V4Stop):
                    await rt.invoke(agent,"finstripe__create_transfer",args,execute)
            with db_session() as db:
                self.assertEqual(db.query(PaymentTransaction).filter_by(namespace=self.namespace).count(),1)
        asyncio.run(run())

    def test_stop_blocks_tool_client_and_retry(self):
        rt=self.runtime(); agent=self.agent(); rt.initialize(self.session,self.task)
        calls=[]
        async def execute(): calls.append("tool"); return {}
        with rt.open():
            with self.assertRaises(v4.V4Stop):
                asyncio.run(rt.invoke(agent,"finstripe__create_transfer",dict(self.task,amount=80,currency="usd",vendor_account="wrong"),execute))
            with self.assertRaises(v4.V4Stop):
                asyncio.run(rt.invoke(agent,"get_vendor_details",{"vendor_id":self.vendor_id},execute))
            client=ContextualLLMClient(self.session,"payments_agent",llm_client=self.client)
            with self.assertRaises(v4.V4Stop): asyncio.run(client.chat(request=None))
            with self.assertRaises(v4.V4Stop):
                asyncio.run(run_agent_with_retry(InvoiceAgent,self.session,self.task,max_retries=3))
        self.assertEqual(calls,[]); self.assertEqual(self.client.calls,0)
        restored=SubjectRuntime(rt.store.path,owner=rt.owner)
        with self.assertRaises(v4.V4Stop): restored.raise_if_stopped()


if __name__=="__main__": unittest.main()
