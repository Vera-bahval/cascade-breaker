import sys
from experiments.payment_controls.live_smoke import ROOT
sys.path.insert(0,str(ROOT/"finbot"))
from types import SimpleNamespace

from experiments.payment_controls.native.verifier import inputs,rules


def fixture():
    from finbot.mcp.servers.taxcalc.server import DEFAULT_CONFIG
    invoice=dict(amount=1400,status="approved",id=18,vendor_id=3,description="Camera rental",invoice_number="N6",
                 tax_category="goods",tax_jurisdiction="US-CA")
    vendor=dict(id=3,status="active",risk_level="low",trust_level="high",services="Camera rental",bank_account_number="A")
    ctx=SimpleNamespace(point="P4.finstripe__create_transfer",family="P4",
                        payload={"arguments":{"amount":1400,"invoice_id":18,"vendor_id":3,"vendor_account":"A","invoice_reference":"N6"}},
                        db_snapshot={"invoice":invoice,"vendor":vendor,"transactions":[],"tax_configuration":{"enabled":True,"config":DEFAULT_CONFIG},"other_invoices":[]},
                        trace_so_far=[dict(kind="summary",agent="fraud_agent",seq=10,task_status="success",task_summary="Done")])
    return ctx


def test_composite_violation_dominates_review():
    ctx=fixture()
    assert rules(inputs(ctx))[0]=="allow"
    ctx.db_snapshot["tax_configuration"]["enabled"]=False
    assert rules(inputs(ctx))[0]=="review"
    ctx.payload["arguments"]["amount"]=999
    ctx.trace_so_far.append(dict(kind="tool",seq=3,name="flag_invoice_for_review",arguments=dict(invoice_id=18)))
    assert rules(inputs(ctx))[0]=="block"


def test_future_arguments_absent_after_fraud():
    ctx=fixture()
    ctx.point="P2.fraud_agent"
    ctx.family="P2"
    ctx.payload={"task_status":"success","task_summary":"Done"}
    values=inputs(ctx)["state"]["records"]
    assert "proposed_account" not in values and "proposed_amount" not in values
