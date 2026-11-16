"""Export measured outcomes and anonymized reached-step packets for independent adjudication."""
import csv
import gzip
import hashlib
import json
import sqlite3
from pathlib import Path
from .batch import HERE,RUNTIME,VERSION
from experiments.payment_controls.study.score import workflow_evidence,executor_accounting,guard_accounting


def collect(partial=False):
    cases=json.loads((HERE/"fixtures.json").read_text())
    import sys
    from experiments.payment_controls.live_smoke import ROOT
    sys.path.insert(0,str(ROOT/"scenarios"))
    from runner.profiles import vendor_fields
    from experiments.payment_controls.study.enforce import ARMS
    from experiments.payment_controls.study.trace_packets import trajectory
    blind_traces={}
    prefixes={}
    rows=[]
    observed={}
    for case in cases:
        family=case["id"]
        for arm in ARMS:
            folder=RUNTIME/("-".join((case["channel"],arm,family,VERSION)))
            if partial and not (folder/"summary.json").exists():
                continue
            r=json.loads((folder/"summary.json").read_text())
            prior=json.loads((folder/"prior.json").read_text()) if (folder/"prior.json").exists() else {}
            if prior:
                with sqlite3.connect((folder/"finbot.db").resolve().as_uri()+"?mode=ro",uri=True) as db:
                    retained=db.execute("select invoice_id,amount,status from payment_transactions where transfer_id=?",
                                        (prior["transfer_id"],)).fetchall()
                if retained!=[(r["submitted_id"],prior["amount"],"completed")]:
                    raise ValueError("Pre-existing payment changed")
            evidence=workflow_evidence(folder,submitted_id=r["submitted_id"],expected_amount=case["invoice"]["amount"],
                                       registered_account=vendor_fields(case["profile"])["bank_account_number"],
                                       prior_transfer_ids={prior["transfer_id"]} if prior else ())
            acc=executor_accounting(folder)
            guard=r["guard"]
            gacc=guard_accounting(folder,guard)
            if not gacc["guard_accounting_complete"]:
                raise ValueError("Incomplete Jev accounting")
            if not acc["executor_accounting_complete"]:
                raise ValueError("Incomplete executor accounting")
            raw=folder/"native-prefix.jsonl"
            reached=[]
            if raw.exists():
                for line in raw.read_text().splitlines():
                    item=json.loads(line)
                    digest=hashlib.sha256(json.dumps(item["packet"],sort_keys=True).encode()).hexdigest()[:20]
                    prefixes[digest]=item["packet"]
                    reached.append(dict(id=digest,point=item["packet"]["state"]["point"],decision=item["decision"],reason=item["reason"]))
            direct=folder/"direct-trace.json"
            traces=list(json.loads(direct.read_text()).values()) if direct.exists() else [json.loads(x.read_text()) for x in (folder/"traces").glob("*.json")]
            blind=hashlib.sha256(("native-trajectory/"+folder.name).encode()).hexdigest()[:16]
            intake=folder/"native-intake.jsonl"
            blind_traces[blind]={"source":case["invoice"],"vendor_profile":case["profile"],
                               "visible_prefixes":[prefixes[x["id"]] for x in reached],
                               "intake":list(map(json.loads,intake.open())) if intake.exists() else [],
                               "trajectory":[trajectory(t) for t in traces],"terminal":evidence}
            for trace in traces:
                for step in trace["steps"]:
                    if step["kind"]!="llm":continue
                    system=[m for m in (step.get("messages") or []) if isinstance(m,dict) and m.get("role") in ("system","developer")]
                    view={"agent":step["agent"],"system":system,"tools":step.get("tools",[]),"served_model":step.get("served_model")}
                    sha=hashlib.sha256(json.dumps(view,sort_keys=True,default=str).encode()).hexdigest()
                    observed[sha]=view
            # The stateless transport records the request actually submitted, including
            # complete schemas even for direct runs with an in-process trace recorder.
            with gzip.open(folder/"calls.jsonl.gz","rt") as journal:
                for call in map(json.loads,journal):
                    if call["event"]!="request":continue
                    request=call["request"]
                    actual={"system":[m for m in request["messages"] if m.get("role")=="system"],
                            "tools":request.get("tools",[]),"model":request["model"],"layer":"on_wire"}
                    sha=hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest()
                    observed[sha]=actual
            rows.append(dict(trace_id=blind,case=family,arm=arm,channel=case["channel"],seconds=r["seconds"],executor_usd=acc["executor_usd"],
                             executor_calls=r["executor_calls"],guard_usd=gacc["guard_usd"],technical=bool(r.get("technical_executor")) or any(str(g.get("reason")).startswith("verifier_error") for g in guard),
                             guard_ms=[g["latency_ms"] for g in guard if g["reason"]!="outside_study"],reached=reached,**evidence))
    private=RUNTIME.parent/"native-tools"
    (private/"live-traces-blind.json").write_text(json.dumps(blind_traces))
    (private/"reached-blind.json").write_text(json.dumps(prefixes,indent=2))
    (private/"observed-model-inputs.json").write_text(json.dumps(observed,default=str))
    ((private/"inprogress.json") if partial else (HERE/"diagnostic_results.json")).write_text(json.dumps(rows,indent=2)+"\n")


if __name__=="__main__":collect()
