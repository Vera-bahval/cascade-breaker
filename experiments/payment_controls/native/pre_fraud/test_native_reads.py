from experiments.payment_controls.native.pre_fraud.native_reads import assess, NATIVE
import json


def example():
    return {
        "inv": dict(id=6,namespace="x",amount=650,invoice_number="n",invoice_date="2026-11-16",
                    description="rental",status="approved",attachments=[]),
        "vendor":dict(id=1,company_name="Example",bank_account_holder_name="Example",
                      bank_name="Example Bank",bank_account_number="987654321",bank_routing_number="121000358",
                      industry="Film Production",agent_notes=""),
        "profile":dict(total_invoices=1,status="active",risk_level="low"),
        "paid":[], "transactions":[], "tin_ok":True,
        "config":json.loads((NATIVE/"build_freeze.json").read_text())["static_defaults"]["agents"]["FraudComplianceAgent"]["default_config"],
    }


def test_real_stop_needs_exact_settlement():
    ex = example()
    inv = ex["inv"]
    inv["status"] = "paid"
    ex["paid"] = [inv]
    assert assess(**ex)[0] == "DEFER"
    tx = dict(invoice_id=6,vendor_id=1,namespace="x",amount=650,currency="usd",status="completed",transfer_id="t")
    ex["transactions"] = [tx]
    assert assess(**ex)[0] == "CLOSE_STOP"
    for k,v in (("invoice_id",5),("namespace","elsewhere"),("amount",651),("currency","eur"),("status","pending")):
        ex["transactions"] = [{**tx,k:v}]
        assert assess(**ex)[0] == "DEFER"


def test_bank_and_invoice_signals():
    ex = example()
    assert assess(**ex)[0] == "CLOSE_ALLOW"
    assert assess(**{**ex,"tin_ok":False})[0] == "DEFER"
    for field,value in (("bank_account_holder_name","Other holder"), ("agent_notes","Bank information warrants assessment.")):
        assert assess(**{**ex,"vendor":{**ex["vendor"],field:value}})[0] == "DEFER"
    prior = {**ex["inv"],"id":5,"status":"paid"}
    ex["profile"]["total_invoices"] = 2
    ex["paid"] = [prior]
    assert "possible_same_obligation" in assess(**ex)[1]


def test_observability_counterexample():
    # Two locally consistent destinations with the same holder have no change evidence in a single snapshot.
    ex = example()
    alt = {**ex["vendor"],"bank_account_number":"123456789"}
    assert assess(**ex)[0] == assess(**{**ex,"vendor":alt})[0] == "CLOSE_ALLOW"
