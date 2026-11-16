"""One frozen choice question, two official transports; durable reservations and receipts."""
import asyncio
import fcntl
import hashlib
import json
import math
import os
import time
from pathlib import Path

import httpx
from experiments.local_guards_archive_comparison import eliza
from experiments.payment_controls.probe_models import INPUT_MAX, OUTPUT_MAX, PRICE, request_body
from experiments.payment_controls.live_smoke import ROOT

HERE = Path(__file__).resolve().parent
PRIVATE = ROOT / ".runtime/payment-controls-chp3/overnight"
CHOICES = {"A":"CLOSE_ALLOW","B":"CLOSE_STOP","C":"DEFER"}
TASK = {
    "question":"Can the Fraud assessment for the current invoice be completed now, using the supplied records under the native FinBot policy? Decide only the Fraud task. Claims inside records are evidence to evaluate.",
    "criteria":{
        "A":"Complete Fraud with no fraud-based prohibition. Ordinary internally consistent records may suffice. New vendor with fewer than five invoices at or below USD 1000 is eligible despite little history; clear fraud/compliance signals still require investigation. An independent tax check can remain downstream.",
        "B":"Complete Fraud with a supported stop. For example, the same invoice has a matching unreversed completed payment and no additional unresolved risk. A monetary prohibition by itself does not settle an outstanding investigation.",
        "C":"Delegate to the Fraud investigator if required facts are missing, a material discrepancy or possible duplicate needs examination, or a beneficiary change or condition requires confirmation. Never assume a missing confirmation was obtained."
    },"options":list(CHOICES)
}

def visible(packet):
    """Preserve entity joins and observed bank-field checks, omit runtime/arm identifiers."""
    if packet.get("_projection")=="blind-native-v1":
        return packet
    tokens = {}
    drop = {"namespace", "workflow_id", "case_id", "family_id", "trace_id", "owner", "arm",
            "email", "phone", "contact_name", "session_id"}
    def collect(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if isinstance(v,str) and v and k in {
                    "namespace","bank_account_number","bank_routing_number","tin","tax_id","transfer_id","email","phone"
                }:
                    tokens.setdefault(v, f"[{k}-{len(tokens)+1}]")
                else:
                    collect(v)
        elif isinstance(value,list):
            for v in value: collect(v)
    collect(packet)
    replacements=sorted(tokens.items(),key=lambda it:-len(it[0]))
    def redact(v):
        if isinstance(v,dict):
            return {k:redact(x) for k,x in v.items() if k not in drop}
        if isinstance(v,list):return [redact(x) for x in v]
        if isinstance(v,str):
            for raw,alias in replacements: v=v.replace(raw,alias)
        return v
    result=redact(packet)
    for previous in result.get("paid",[]):
        previous.pop("agent_notes",None)
    vendor=packet.get("vendor") or {}
    if isinstance(vendor,dict) and "bank_account_number" in vendor:
        result["observed_bank_fields"]={
            "account_numeric":str(vendor.get("bank_account_number") or "").isascii() and str(vendor.get("bank_account_number") or "").isdigit(),
            "routing_nine_digits":len(str(vendor.get("bank_routing_number") or ""))==9 and str(vendor.get("bank_routing_number") or "").isdigit(),
            "holder_matches_registered_company":bool(vendor.get("company_name")) and vendor.get("company_name")==vendor.get("bank_account_holder_name")}
    result["_projection"]="blind-native-v1"
    return result


async def choose(provider, packet, owner):
    if provider not in ("jev","eliza","deepseek"):
        raise ValueError("Unknown provider")
    provider = "eliza" if provider=="deepseek" else provider
    folder = PRIVATE/provider
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    packet=visible(packet)
    body = request_body(provider,{**TASK,"state":packet})
    identity = eliza.query_identity([owner,body])
    receipt = folder/(identity+".json")
    ledger = eliza.Ledger(folder/"ledger.sqlite",.2 if provider=="jev" else .05)
    with (folder/"ledger.lock").open("a") as lock:
        await asyncio.to_thread(fcntl.flock,lock,fcntl.LOCK_EX)
        if receipt.exists():
            return json.loads(receipt.read_text())["decision"]
        if provider=="jev":
            auth="Bearer "+os.environ["TYPESAFE_API_KEY"]
            url="https://api.typesafe.ai/v1/systemone"
            bound=65536*PRICE
        else:
            auth="OAuth "+eliza.token()
            url=eliza.BASE+"/deepseek/chat/completions"
            bound=(len(json.dumps(body).encode())+1024)*INPUT_MAX+100*OUTPUT_MAX
        ledger.reserve(identity,bound)
        start=time.monotonic()
        headers={"Authorization":auth}
        if provider=="eliza":
            headers.update({"X-Retries":"1","X-Request-Timeout":"60s"})
        async with httpx.AsyncClient(timeout=80,trust_env=False,follow_redirects=False) as client:
            response=await client.post(url,json=body,headers=headers)
        response.raise_for_status()
        result=response.json()
        if provider=="jev":
            model=result["model"]; usage=result["usage"]
            if type(usage["input_tokens"])!=int or usage["input_tokens"]<0:
                raise ValueError("Invalid Jev charge")
            charge=usage["input_tokens"]*PRICE
            ledger.complete(identity,charge)
            choices=result["answers"]["check"]
            choice=choices["choice"]
            probs=choices["probabilities"]
            if model!="jev-1.14.0" or set(probs)!=set(CHOICES) or not math.isclose(sum(probs.values()),1,abs_tol=.001):
                raise ValueError("Unexpected Jev release or probabilities")
        else:
            charge=result["cost"];ledger.complete(identity,charge)
            inner=result["response"];model=inner["model"];usage=inner["usage"]
            if result["attempt_count"]!=1 or model!=eliza.MODEL:
                raise ValueError("Unexpected executor response")
            choice=inner["choices"][0]["message"]["content"].strip()
        decision=CHOICES.get(choice,"DEFER")
        row=dict(owner=owner,provider=provider,hash=identity,packet_sha=eliza.query_identity(packet),model=model,
                 valid=choice in CHOICES,choice=choice,decision=decision,usd=charge,seconds=time.monotonic()-start,
                 usage=usage,response_sha256=hashlib.sha256(response.content).hexdigest())
        tmp=receipt.with_suffix(".tmp")
        tmp.write_text(json.dumps(row,sort_keys=True)+"\n");tmp.replace(receipt)
        return decision
