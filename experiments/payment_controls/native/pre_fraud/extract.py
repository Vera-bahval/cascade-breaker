"""Reconstruct a pre-call observation; keep later Fraud tool reads in a separate audit."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LIVE = ROOT / ".runtime/payment-controls-chp3/study-live"
PRIVATE = LIVE.parent / "pre-fraud-review"
NATIVE = HERE.parent
HIDDEN = {"namespace", "email", "phone", "contact_name", "created_at", "updated_at"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def clean(row):
    return {k: v for k, v in row.items() if k not in HIDDEN}


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def extract():
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    packets, later, index = {}, {}, {}
    for r in json.loads((NATIVE/"diagnostic_results.json").read_text()):
        folder = LIVE / f"{r['channel']}-{r['arm']}-{r['case']}-native1"
        intake_path = folder/"native-intake.jsonl"
        intake, = map(json.loads, intake_path.read_text().splitlines())
        direct = folder/"direct-trace.json"
        traces = [(direct, t) for t in json.loads(direct.read_text()).values()] if direct.exists() else [
            (p, json.loads(p.read_text())) for p in (folder/"traces").glob("*.json")]
        (path, trace), = [(p,t) for p,t in traces if t.get("task_data",{}).get("invoice_id")==intake["invoice"]["id"]
                          and any(s.get("target")=="fraud" for s in t["steps"])]
        steps = trace["steps"]
        inv = clean(intake["invoice"])
        vendor = clean(intake["vendor"])
        assert inv["vendor_id"] == vendor["id"] == trace["task_data"]["vendor_id"]
        call, proposal = next((s, c) for s in steps if s["kind"]=="llm" and s["agent"]=="orchestrator_agent"
                              for c in (s.get("output") or {}).get("tool_calls",[]) if c["name"]=="delegate_to_fraud")
        before = [s for s in steps if s["seq"] < call["seq"]]
        assert not any(s.get("target")=="fraud" or s.get("agent")=="fraud_agent" for s in before)
        sources = {"invoice_and_vendor":"native-intake before execution", "transactions_and_history":"same namespace intake"}
        reads = []
        for s in before:
            if s["kind"]!="tool" or s["agent"]!="invoice_agent":
                continue
            name, args, out = s["name"], s["arguments"], s["output"]
            if name == "update_invoice_status" and not s["error"] and isinstance(out,dict) and out.get("updated") is True:
                assert args["invoice_id"] == out["invoice_id"] == inv["id"] and args["status"]==out["status"]
                inv["status"] = out["status"]
                sources["invoice_status"] = f"update_invoice_status receipt seq {s['seq']}"
            if name.startswith("findrive__") or name.startswith("taxcalc__"):
                reads.append(dict(seq=s["seq"], tool=name, args=args, output=out,error=s["error"]))
        inv.pop("agent_notes",None)  # free-text updates are not reconstructed from final DB
        snapshots = [s for s in before if s["kind"]=="guard_context" and s["point"]=="P2.invoice_agent"]
        if snapshots:
            latest=snapshots[-1]["db_snapshot"]
            assert latest["invoice"]["id"]==inv["id"] and latest["invoice"]["status"]==inv["status"]
            sources["snapshot_crosscheck"]=snapshots[-1]["seq"]
        key = digest(("pre-fraud/"+r["trace_id"]).encode())[:14]
        packets[key] = dict(invoice=inv,vendor=vendor,history=intake["other_invoices"],
                            transactions=[clean(t) for t in intake["transactions"]],proposal=proposal["arguments"],
                            cut=call["seq"],before_reads=reads,provenance=sources,
                            limits="Free-text Invoice updates omitted. Vendor notes are recorded claims. Unread documents and Fraud results excluded.")
        after=[s for s in steps if s["seq"]>call["seq"] and s.get("agent")=="fraud_agent" and s["kind"]=="tool"]
        later[key]=[dict(seq=s["seq"],name=s["name"],error=bool(s["error"] or
                    (isinstance(s.get("output"),dict) and s["output"].get("error"))),
                    output_keys=sorted(s["output"]) if isinstance(s["output"],dict) else [],
                    returned_count=(s["output"].get("count",s["output"].get("total_invoices"))
                                    if isinstance(s["output"],dict) else None)) for s in after]
        index[key]=dict(family=r["case"],arm=r["arm"],channel=r["channel"],source=folder.name,
                        intake_sha=digest(intake_path.read_bytes()),trace_sha=digest(path.read_bytes()),cut=call["seq"],
                        first_call_well_formed=set(proposal["arguments"])=={"vendor_id","task_description"})
    save(PRIVATE/"packets.json",packets)
    save(PRIVATE/"later.json",later)
    save(HERE/"index.json",index)


if __name__=="__main__":
    extract()
