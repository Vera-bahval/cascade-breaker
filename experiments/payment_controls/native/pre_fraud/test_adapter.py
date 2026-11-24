from experiments.payment_controls.native.pre_fraud.score import evaluate, closure


def test_heldout_operands():
    config = {"prohibited_industries": []}
    invoice = dict(id=7, vendor_id=1, invoice_number="X", amount=650, status="paid")
    vendor = dict(id=1, company_name="A", bank_account_holder_name="A", industry="Film", risk_level="low")
    packet = dict(invoice=invoice, vendor=vendor, history=[], transactions=[])
    settled = dict(invoice_id=7, vendor_id=1, amount=650, currency="usd", status="completed")
    assert evaluate({**packet, "transactions":[settled]},config)["monetary_gate"]=="prior_settlement"
    assert evaluate({**packet, "transactions":[{**settled,"invoice_id":8}]},config)["monetary_gate"]!="prior_settlement"
    assert evaluate({**packet, "transactions":None},config)["monetary_gate"]=="unknown"
    assert evaluate({**packet, "invoice":{**invoice,"amount":50001}},config)["monetary_gate"]=="over_ceiling"
    assert evaluate({**packet, "invoice":{**invoice,"amount":None}},config)["monetary_gate"]=="unknown"

def test_routes_when_obligations_are_independently_satisfied():
    clean = {"fraud_assessment": "no_flag_indicated"}
    assert closure(clean, "none_established") == "CLOSE_ALLOW"
    assert closure(clean, "prior_settlement") == "CLOSE_STOP"
    assert closure(clean, "unknown") == "DEFER"
    assert closure({"fraud_assessment": "review"}, "over_ceiling") == "DEFER"
