"""Recheck the immutable amount condition on both native proposals in one observed workflow."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from .controlled import AmountCheck, HERE


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(trace_path):
    trace = json.loads(trace_path.read_text())
    steps = {s["seq"]: s for s in trace["steps"]}
    assert steps[21]["name"] == "get_invoice_for_payment"
    invoice = {key: steps[21]["output"][key] for key in ("id", "vendor_id", "amount")}
    rows = []
    for seq in (25, 27):
        proposal, = steps[seq]["output"]["tool_calls"]
        result = steps[seq+1]
        assert proposal["name"] == result["name"] == "finstripe__create_transfer"
        assert proposal["arguments"] == result["arguments"]
        rows.append(dict(proposal_seq=seq, native_result_seq=seq+1,
                         arguments={k:proposal["arguments"][k] for k in ("invoice_id","vendor_id","amount")},
                         native_result=result["output"].get("error") or result["output"]["status"]))
    return dict(workflow=trace["workflow_id"], trace_sha256=sha(trace_path), invoice_source_seq=21,
                invoice=invoice, proposals=rows)


async def check(data):
    frozen = json.loads((HERE/"controlled_freeze.json").read_text())["sha256"]["controlled.py"]
    if sha(HERE/"controlled.py") != frozen:
        raise ValueError("The checked implementation differs from the frozen implementation")
    data["rule_sha256"] = frozen
    for row in data["proposals"]:
        ctx=SimpleNamespace(db_snapshot={"invoice":data["invoice"]},payload={"arguments":row["arguments"]})
        result=await AmountCheck().check(ctx)
        row["invariant_verdict"]=result.decision
        row["reason"]=result.reason
    return data


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace",type=Path,help="Original natural chat/rules workflow JSON; omit to check the archived projection")
    args=parser.parse_args()
    saved=HERE/"natural_amount_pair.json"
    evidence=extract(args.trace) if args.trace else json.loads(saved.read_text())
    checked=asyncio.run(check(evidence))
    if args.trace:
        saved.write_text(json.dumps(checked,indent=2)+"\n")
    elif checked != json.loads(saved.read_text()):
        raise SystemExit("Recorded result does not reproduce")
    print([(r["proposal_seq"],r["invariant_verdict"]) for r in checked["proposals"]])
