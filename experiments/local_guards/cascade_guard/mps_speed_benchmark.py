"""Matched-input serial benchmark; run only after CPU and MPS batch clients pause."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
import urllib.request

from .secjev import canonical_hash
from .secjev_benchmark import compare
from .secjev2b_probe import SecJev2BScorer


def request(url: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=180) as response:
        return json.load(response)


def median_valid_compute(rows: list[dict]) -> float | None:
    values=[x["result"]["timing_ms"]["compute"] for x in rows if x["result"]["status"]=="OK"]
    return statistics.median(values) if values else None


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",type=Path,default=Path(__file__).resolve().parents[3])
    parser.add_argument("--input",type=Path,default=Path("experiments/local_guards/data/prefixes.jsonl"))
    parser.add_argument("--cpu-url",default="http://127.0.0.1:8011")
    parser.add_argument("--mps08-url",default="http://127.0.0.1:8012")
    parser.add_argument("--case-ids",nargs="*",default=["2154a315fd8101505a96b214","55f3842b959869ca1ab00e1e","baea55b592c4314234ad2bb3"])
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    rows=[json.loads(line) for line in args.input.read_text().splitlines()]
    selected=[next(r for r in rows if r["prefix_id"]==pid) for pid in args.case_ids]
    report={"input_sha256":hashlib.sha256(args.input.read_bytes()).hexdigest(),
            "purpose":"Same full-state + four-question requests, serial warm inference with archive batch clients paused.",
            "pause_prerequisite":"Caller verifies both CPU and MPS archive clients paused and their in-flight requests completed.",
            "health":{"cpu08":request(args.cpu_url+"/health"),"mps08":request(args.mps08_url+"/health")},
            "warmups":[],"cases":[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def save():args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    for row in selected:
        payload={"state":row["state"],"questions":row["questions"]}
        item={"prefix_id":row["prefix_id"],"input_hash":canonical_hash(payload),"cpu08":[],"mps08":[],"mps2b":[]}
        for arm,url in (("cpu08",args.cpu_url),("mps08",args.mps08_url)):
            warmup=request(url+"/score",payload)
            report["warmups"].append({"prefix_id":row["prefix_id"],"arm":arm,"result":warmup})
        for _ in range(args.repeats):
            for arm,url in (("cpu08",args.cpu_url),("mps08",args.mps08_url)):
                start=time.perf_counter();result=request(url+"/score",payload)
                item[arm].append({"http_wall_ms":(time.perf_counter()-start)*1000,"result":result})
        item["cpu08_mps08_parity"]=[compare(item["cpu08"][0]["result"],x["result"]) for x in item["mps08"]]
        report["cases"].append(item);save()
        print(json.dumps({"prefix_id":row["prefix_id"],"phase":"08b_complete"}),flush=True)
    scorer=SecJev2BScorer(args.workspace,"mps",1,"sdpa","solver_block")
    report["mps2b_metadata"]=scorer.metadata
    old2b=json.loads(Path("experiments/local_guards/results/mps-diagnostics/secjev2b/cpu-aa.json").read_text())
    references={c["prefix_id"]:c["results"][0] for c in old2b["cases"]}
    for row,item in zip(selected,report["cases"]):
        payload={"state":row["state"],"questions":row["questions"]}
        report["warmups"].append({"prefix_id":row["prefix_id"],"arm":"mps2b","result":scorer.score(payload)})
        for _ in range(args.repeats):item["mps2b"].append({"result":scorer.score(payload)})
        item["cpu2b_mps2b_parity"]=[compare(references[row["prefix_id"]],x["result"]) for x in item["mps2b"]]
        item["median_compute_ms"]={arm:median_valid_compute(item[arm]) for arm in ("cpu08","mps08","mps2b")}
        numerator,denominator=item["median_compute_ms"]["cpu08"],item["median_compute_ms"]["mps2b"]
        item["mps2b_speedup_vs_cpu08"]=numerator/denominator if numerator is not None and denominator else None
        save();print(json.dumps({"prefix_id":row["prefix_id"],"phase":"2b_complete",**item["median_compute_ms"]}),flush=True)
    report["summary"]={arm:{"median_compute_ms":median_valid_compute([x for c in report["cases"] for x in c[arm]]),
                            "all_valid":all(x["result"]["status"]=="OK" for c in report["cases"] for x in c[arm]),
                            "requests":sum(len(c[arm]) for c in report["cases"])} for arm in ("cpu08","mps08","mps2b")}
    report["timing_limits"]="Single host and three states. All archive clients paused, but both 0.8B services remain loaded; their memory footprint is present. CPU2B timing from the prior contended test is not used here."
    save()


if __name__ == "__main__":main()
