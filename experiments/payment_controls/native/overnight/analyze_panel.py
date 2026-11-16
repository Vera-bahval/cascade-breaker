"""Describe coverage and selective errors, leaving unresolved references unscored."""
import csv
import json
from collections import Counter
from .provider import HERE
from .route import evaluate


def summarize(series):
    prefix="" if series=="seed" else "reached_"
    gold=json.loads((HERE/(prefix+"gold.json")).read_text())
    results=list(csv.DictReader((HERE/(prefix+"panel_results.csv")).open()))
    methods={"jev":{},"eliza":{},"rules":{}}
    for row in results:
        key=row["owner"].split("/")[-1];methods[row["provider"]][key]=row["decision"]
    if series=="seed":
        raw=json.loads((HERE/"panel_inputs.json").read_text())
        for key,packet in raw.items():
            p=dict(packet,inv=packet["invoice"])
            methods["rules"][key]=evaluate(p)[0]
    else:
        from .live_batch import ARMS,folder
        indices=json.loads((HERE/"reached_index.json").read_text())
        fixtures={f["id"]:f for f in json.loads((HERE/"fixtures.json").read_text())}
        for key,r in indices.items():
            if not r["attained"]:continue
            f=folder(fixtures[r["case"]],ARMS[0])/"route-packets.jsonl"
            packet=json.loads(f.read_text().splitlines()[0])["packet"]
            methods["rules"][key]=evaluate(packet)[0]
    stats={}
    detail=[]
    for method,values in methods.items():
        if set(gold)!=set(values):raise ValueError("Incomplete "+method)
        c=Counter()
        for k,d in sorted(values.items()):
            g=gold[k]["action"]
            c["n"]+=1;c["auto"]+=d!="DEFER"
            if g=="INSUFFICIENT":c["reference_unknown"]+=1
            else:
                c["known"]+=1;c["correct"]+=d==g
                c["false_auto"]+=d!="DEFER" and d!=g
                c["excess_defer"]+=d=="DEFER" and d!=g
            detail.append(dict(id=k,method=method,decision=d,gold=g))
        stats[method]=dict(c)
    (HERE/(prefix+"panel_metrics.json")).write_text(json.dumps(stats,indent=2)+"\n")
    with (HERE/(prefix+"panel_scored.csv")).open("w",newline="") as out:
        w=csv.DictWriter(out,fieldnames=detail[0],lineterminator="\n");w.writeheader();w.writerows(detail)
if __name__=="__main__":
    import sys
    summarize(sys.argv[1])
