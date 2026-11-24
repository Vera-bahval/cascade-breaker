"""Score paired document decisions and conditional second-provider use."""
import csv
import json
from collections import defaultdict
from statistics import median

from experiments.payment_controls.probe_models import request_body
from .development import cases, decode, labels, packets, HERE


def results():
    runtime = HERE.parents[2] / ".runtime/payment-controls-chp3"
    for series, index in (("dev","development"), ("confirmation","confirmation")):
        inputs = {(row["case_id"],row["form"]):row["input"] for row in packets(series)}
        targets = labels(series)
        orders = {r["family"]: decode(i) for i,r in enumerate(cases(series))}
        pair = defaultdict(dict)
        for provider in ("jev","eliza"):
            folder = runtime / provider
            ids = json.loads((folder / (index+"_observations.json")).read_text())
            for obs in ids:
                key = obs["case_id"], obs["form"]
                record = json.loads((folder / (obs["receipt"]+".json")).read_text())
                assert record["request_hash"] == obs["receipt"] and record["request"] == request_body(provider, inputs[key])
                assert record["response_model"] == {"jev":"jev-1.14.0","eliza":"deepseek-flash"}[provider]
                result = dict(series=series,family=key[0],form=key[1],method=provider,
                              gold=targets[key[0]]["masked" if key[1]=="masked" else "step"],
                              decision=orders[key[0]].get(record["selected"],"REVIEW"),
                              technical=int(not record["valid"]), second_calls=0,
                              elapsed=record["elapsed_seconds"],usd=record["cost_usd"],receipt=obs["receipt"])
                if provider in pair[key]:
                    raise ValueError("Repeated observation")
                pair[key][provider] = result
                yield result
        assert set(inputs) == set(pair)
        for providers in pair.values():
            jev, deepseek = providers["jev"],providers["eliza"]
            use = jev["decision"] == "REVIEW" and not jev["technical"]
            last = deepseek if use else jev
            yield {**last,"method":"jev_then_deepseek","second_calls":int(use),
                   "elapsed":jev["elapsed"] + use*deepseek["elapsed"],"usd":jev["usd"] + use*deepseek["usd"],
                   "receipt":jev["receipt"] + ("|"+deepseek["receipt"] if use else "")}


def write():
    data = list(results())
    with (HERE / "document_results.csv").open("w") as stream:
        writer = csv.DictWriter(stream,fieldnames=data[0])
        writer.writeheader()
        writer.writerows(data)
    for series in ("dev","confirmation"):
        for method in ("jev","eliza","jev_then_deepseek"):
            for form in ("facts","decision","structured","summary","masked"):
                rows = [r for r in data if (r["series"],r["method"],r["form"])==(series,method,form)]
                if rows:
                    print(series,method,form,len(rows),sum(r["decision"]==r["gold"] for r in rows),
                          sum(r["decision"]=="ALLOW" and r["gold"]!="ALLOW" for r in rows),
                          sum(r["gold"]=="ALLOW" and r["decision"]!="ALLOW" for r in rows),
                          sum(r["second_calls"] for r in rows), round(median(r["elapsed"] for r in rows),3),
                          round(sum(r["usd"] for r in rows),9))


if __name__=="__main__":
    write()
