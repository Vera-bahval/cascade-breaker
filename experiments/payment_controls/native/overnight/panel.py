"""Matched single-decision panel on adjudicated open pre-Fraud packets."""
import argparse
import asyncio
import csv
import hashlib
import json
from .provider import PRIVATE, HERE, choose
from experiments.local_guards_archive_comparison import eliza
from experiments.payment_controls.probe_models import INPUT_MAX, OUTPUT_MAX


async def run(series):
    prefix = "" if series=="seed" else "reached_"
    src=HERE/(prefix+"panel_inputs.json")
    packets=json.loads(src.read_text())
    audit=HERE/(prefix+"gold.json")
    gold=json.loads(audit.read_text())
    if not isinstance(packets,dict) or set(packets)!=set(gold):
        raise ValueError("Panel and reference IDs differ")
    model,=eliza.metadata()["model"]["data"]
    if model.get("disabled") or model["prices"]["input_tokens"]>INPUT_MAX or model["prices"]["output_tokens"]>OUTPUT_MAX:
        raise ValueError("Executor release/price unavailable")
    files=[src,audit,HERE/"provider.py",HERE/"PROTOCOL.md"]
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    freeze=HERE/(prefix+"panel_freeze.json")
    if freeze.exists() and json.loads(freeze.read_text())!=manifest:raise ValueError("Frozen panel changed")
    freeze.write_text(json.dumps(manifest,indent=2)+"\n")
    for i,key in enumerate(sorted(packets)):
        for provider in (("jev","eliza") if i%2==0 else ("eliza","jev")):
            await choose(provider,packets[key],series+"-panel/"+key)
    rows=[]
    for provider in ("jev","eliza"):
        for p in sorted((PRIVATE/provider).glob("*.json")):
            row=json.loads(p.read_text())
            if row["owner"].startswith(series+"-panel/"):
                rows.append({k:row[k] for k in ("owner","provider","model","choice","valid","decision","usd","seconds","packet_sha")})
    if len(rows)!=2*len(packets):raise ValueError("Panel receipts incomplete")
    with (HERE/(prefix+"panel_results.csv")).open("w",newline="") as stream:
        w=csv.DictWriter(stream,fieldnames=rows[0],lineterminator="\n")
        w.writeheader();w.writerows(rows)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--series",choices=("seed","reached"),default="seed")
    asyncio.run(run(parser.parse_args().series))
