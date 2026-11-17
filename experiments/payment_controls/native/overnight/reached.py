"""Blind the first actual pre-Fraud packet from each selected baseline, before comparison."""
import hashlib
import json
from .provider import HERE, PRIVATE, visible
from .live_batch import folder, ARMS


def collect():
    selected=json.loads((HERE/"live_selection.json").read_text())
    fixtures={f["id"]:f for f in json.loads((HERE/"fixtures.json").read_text())}
    packets,bind={},{}
    for cid in selected:
        dest=folder(fixtures[cid],ARMS[0])
        if not (dest/"summary.json").is_file():raise ValueError("Missing baseline")
        tracefile=dest/"direct-trace.json"
        traces=json.loads(tracefile.read_text())
        attempts=[(t,s,c) for t in traces.values() for s in t["steps"] if s["kind"]=="llm" and s["agent"]=="orchestrator_agent" for c in (s.get("output") or {}).get("tool_calls",[]) if c["name"]=="delegate_to_fraud"]
        raw=dest/"route-packets.jsonl"
        if not raw.exists():
            bind[cid]={"case":cid,"attained":False,"attempts":len(attempts)}
            continue
        first=json.loads(raw.read_text().splitlines()[0])
        packet=first["packet"]; t,s,c=attempts[0]
        matches=packet["proposal"]==c["arguments"] and packet["inv"]["id"]==t["task_data"]["invoice_id"]
        if not matches:
            bind[cid]={"case":cid,"attained":False,"attempts":len(attempts),"reason":"first proposed call differs from first intercepted invocation"}
            continue
        key=hashlib.sha256(("attained/"+cid).encode()).hexdigest()[:14]
        # Store only anonymized fields in the shareable assessor packet. The exact raw input remains local.
        packets[key]=visible(packet)
        bind[key]=dict(case=cid,seq=s["seq"],attained=True,packet_sha=hashlib.sha256(raw.read_bytes()).hexdigest(),
                       trace_sha=hashlib.sha256(tracefile.read_bytes()).hexdigest())
    (HERE/"reached_panel_inputs.json").write_text(json.dumps(packets,indent=2,sort_keys=True)+"\n")
    (HERE/"reached_index.json").write_text(json.dumps(bind,indent=2,sort_keys=True)+"\n")
    print("reached",len(packets),"of",len(selected))
if __name__=="__main__":collect()
