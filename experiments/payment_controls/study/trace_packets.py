"""Build private labeler views of observed workflow decisions and actor-visible source summaries."""
import argparse
import hashlib
import json
from pathlib import Path

from .live import ROOT

DATA = ROOT/".runtime/payment-controls-chp3/study-live"


def trajectory(trace):
    labels=[]
    turn={}
    for row in trace["steps"]:
        kind=row["kind"]
        agent=row.get("agent","orchestrator")
        if kind=="llm":
            turn[agent]=row["seq"]
            continue
        item={"seq":row.get("seq"),"kind":kind,"agent":agent,"last_model_turn":turn.get(agent)}
        if kind=="summary":
            item.update(status=row["task_status"],statement=row["task_summary"])
        elif kind=="tool":
            result=row.get("output")
            keep=("success","status","requires_review","error","transfer_id","amount","tax","tax_amount","subtotal","total","total_amount","currency","invoice_amount","decision","recommended_action","agent_notes")
            excerpt={k:result[k] for k in keep if k in result} if isinstance(result,dict) else None
            item.update(name=row["name"],error=bool(row.get("error")),result=excerpt,
                        proposal={k:v for k,v in (row.get("arguments") or {}).items() if k in
                                  ("status","invoice_id","vendor_id","amount","recommended_action","agent_notes")})
        elif kind=="delegation":item.update(target=row["target"],task=row.get("task_description"))
        elif kind in ("guard","guard_stop"):
            item.update(point=row["point"],decision=row.get("decision","stop"))
        else:continue
        labels.append(item)
    return labels


def build(folder,phase):
    corpus={}
    if phase in ("cal","test"):
        with (folder/f"inputs.{phase}.jsonl").open() as stream:
            corpus={r["case"]:r for r in map(json.loads,stream)}
    target=folder/f"mast-{phase}"
    target.mkdir(exist_ok=True)
    ids={}
    for p in sorted(DATA.glob("*-v3/summary.json")):
        r=json.loads(p.read_text())
        if (phase=="open" and r["family"] not in ("stock","inspection","authorized","withheld")) or (phase!="open" and r["family"] not in corpus):
            continue
        trace_files=sorted((p.parent/"traces").glob("*.json"))
        direct=p.parent/"direct-trace.json"
        traces=list(json.loads(direct.read_text()).values()) if direct.exists() else [json.loads(f.read_text()) for f in trace_files]
        blind=hashlib.sha256(p.parent.name.encode()).hexdigest()[:14]
        case=corpus.get(r["family"])
        if not case and r["family"] in ("stock","inspection"):
            from .live import document
            case=document(r["family"])
        if r["channel"] in ("chat-transfer","onboarding-transfer"):
            from .transfer import transfer_case
            policy,_,doc=transfer_case(r["channel"]=="chat-transfer",r["family"]=="authorized")
            case={"policy":policy,**doc}
        ids[blind]=p.parent.name
        bundle=dict(id=blind,source={k:case[k] for k in ("policy","basis","record") if k in case} if case else None,
                    workflow_traces=[trajectory(tr) for tr in traces],terminal={k:r[k] for k in
                    ("transactions","correct_payment","vendor_status","workflow_count","stopped") if k in r},
                    intervention=[{k:v for k,v in g.items() if k in ("decision","action","point")} for g in r["guard"]])
        (target/(blind+".json")).write_text(json.dumps(bundle,ensure_ascii=False))
    (folder/f"mast-{phase}-key.private.json").write_text(json.dumps(ids))
    print(phase,len(ids))


if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("folder",type=Path)
    cli.add_argument("phase",choices=("open","cal","test"))
    a=cli.parse_args()
    build(a.folder,a.phase)
