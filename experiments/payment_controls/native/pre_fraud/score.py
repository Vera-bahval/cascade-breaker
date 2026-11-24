"""Score only pre-Fraud facts; join family and annotation after decisions."""
import hashlib
import json
from .extract import HERE, PRIVATE, ROOT, NATIVE, save
from .rules import assess, payment_amount_gate


def closure(result, monetary_gate):
    """Candidate assessment only; native bookkeeping would still be required in a live route."""
    if result["fraud_assessment"] != "no_flag_indicated" or monetary_gate == "unknown":
        return "DEFER"
    if monetary_gate in ("prior_settlement", "over_ceiling"):
        return "CLOSE_STOP"
    return "CLOSE_ALLOW"


def evaluate(packet, config):
    inv, vendor = packet["invoice"], packet["vendor"]
    history = packet["history"]
    assert all(row["id"] != inv["id"] for row in history)
    transactions = packet.get("transactions")
    amount = inv.get("amount")
    settled = amount is not None and any(row["invoice_id"] == inv["id"] and row["vendor_id"] == vendor["id"]
                  and row["status"]=="completed" and row["amount"]==amount and row["currency"]=="usd"
                  for row in (transactions or []))
    possible_duplicate = any(row["invoice_number"]==inv["invoice_number"] and row["amount"]==amount
                             for row in history)
    same_name = vendor["company_name"]==vendor["bank_account_holder_name"]
    industry = vendor.get("industry")
    evidence = dict(industry="unknown" if not industry else
                    "prohibited" if industry.casefold() in config["prohibited_industries"] else "other",
                    tin="unknown", bank_details="unknown", bank_change="unknown",
                    duplicate_invoice="suspected" if possible_duplicate else "unknown" if history else "none",
                    same_invoice_completed_payment="yes" if settled else "no" if transactions == [] else "unknown",
                    amount_or_frequency_anomaly="unknown", history_review="incomplete" if history else "complete",
                    current_risk=vendor["risk_level"])
    # Equal names do not verify authority. A different holder requires checking the relationship.
    result = assess(evidence)
    over_limit = payment_amount_gate(amount)["payment_gate"]=="block" if amount is not None else None
    gate = "prior_settlement" if settled else "over_ceiling" if over_limit else "unknown" if over_limit is None or evidence["same_invoice_completed_payment"]=="unknown" else "none_established"
    if result["fraud_investigation"] != "proceed":
        raise ValueError("Unexpected routing contract for frozen pre-fraud-v2")
    return dict(evidence=evidence, monetary_gate=gate, routing=closure(result, gate), frozen_baseline="DEFER",
                holder_names_match=same_name, possible_duplicate=possible_duplicate,
                risk_assessment=result, amount_gate=over_limit)


def main():
    for filename, sha in json.loads((HERE/"freeze.json").read_text())["sha256"].items():
        if hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()!=sha:
            raise ValueError("Changed frozen input: "+filename)
    config=json.loads((NATIVE/"build_freeze.json").read_text())["static_defaults"]["agents"]["FraudComplianceAgent"]["default_config"]
    packets=json.loads((PRIVATE/"packets.json").read_text())
    output={k:evaluate(v,config) for k,v in packets.items()}
    save(HERE/"decisions.json",output)


if __name__=="__main__": main()
