"""Bounded factorial SecJev size x prefix-history-format diagnostic.

Reuses frozen 0.8B current-state rows, then scores new 0.8B formats serially,
then loads the security-trained 2B once and scores the identical payloads.
No training, thresholds, future episode state or paid API calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from .mps_diagnostics import aa_summary
from .secjev import canonical_hash
from .secjev_batch import inference_input_hash
from .secjev2b_probe import SecJev2BScorer


def payload_hash(payload: dict) -> str:
    """Model-independent hash preserving the insertion order Kev renders."""
    encoded=json.dumps(payload,sort_keys=False,ensure_ascii=False,separators=(",",":"),allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def http_json(url: str, payload: dict | None = None) -> dict:
    req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None,
                               headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=300) as response:return json.load(response)


def is_current(row: dict) -> bool:
    return row["format"] in ("current","current_state")


def frozen_ablation(view: str) -> str:
    return {"with_explanation":"plus_rationale","plus_rationale":"plus_rationale",
            "facts_action":"facts_action","without_explanation":"facts_action"}[view]


def validate_rows(rows: list[dict]) -> None:
    grouped={}
    for row in rows:
        grouped.setdefault(row["case_id"],[]).append(row)
        if set(row["payload"]) != {"state","questions"}:
            raise ValueError("Only state and unchanged questions may be inference inputs")
    if not 1 <= len(grouped) <= 9 or len(rows) != 3*len(grouped):
        raise ValueError("Bounded diagnostic expects at most nine cases with three formats each")
    for case,items in grouped.items():
        if len(set(r["format"] for r in items))!=3 or sum(is_current(r) for r in items)!=1:
            raise ValueError(f"Case {case} needs exactly one current and two distinct history formats")
        reference=items[0]["payload"]["questions"]
        if len(reference)!=4 or any(payload_hash({"questions":r["payload"]["questions"]})!=payload_hash({"questions":reference}) for r in items):
            raise ValueError(f"Case {case} must retain the same four questions")
        if len(set(r["prefix_id"] for r in items))!=1 or len(set(r["group_id"] for r in items))!=1:
            raise ValueError(f"Case {case} must retain its prefix and base group across formats")


def as_result(row: dict) -> dict:
    return {"status":"UNKNOWN" if row.get("unknown") else "OK","probabilities":row["distributions"],
            "timing_ms":row["timing_ms"],"token_counts":row["token_counts"],
            "model_metadata":row["model_metadata"],"memory":row.get("memory",{}),"error":row.get("error")}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",type=Path,default=Path(__file__).resolve().parents[3])
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--mps08-url",default="http://127.0.0.1:8012")
    parser.add_argument("--frozen08",type=Path,default=Path("experiments/local_guards/results/secjev-mps-scores.jsonl"))
    args=parser.parse_args()
    rows=[json.loads(line) for line in args.input.read_text().splitlines()]
    validate_rows(rows)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    baseline=[json.loads(line) for line in args.frozen08.read_text().splitlines()]
    by_prefix={(r["prefix_id"],r["ablation"]):r for r in baseline}
    health=http_json(args.mps08_url+"/health")
    manifest={"input_sha256":hashlib.sha256(args.input.read_bytes()).hexdigest(),
              "frozen08_sha256":hashlib.sha256(args.frozen08.read_bytes()).hexdigest(),
              "diagnostic_source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "cases":len(set(r["case_id"] for r in rows)),"payloads":len(rows),"model08_health":health,
              "models":{},"actual_calls":{"SecJev-0.8B":0,"SecJev-2B":0},"status":"RUNNING",
              "scope":"Question-specific probability diagnostic. No fitted thresholds, statistical detector comparison or training."}
    outputs=[]
    def save():
        (args.output_dir/"scores.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False,allow_nan=False)+"\n" for r in outputs))
        (args.output_dir/"manifest.json").write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n")
    def record(row,model,result,fingerprint,origin,http_wall_ms=None):
        outputs.append({"case_id":row["case_id"],"prefix_id":row["prefix_id"],"group_id":row["group_id"],
                        "format":row["format"],"model":model,"payload_hash":payload_hash(row["payload"]),
                        "scorer_input_hash":inference_input_hash(row["payload"],fingerprint),
                        "scorer_fingerprint":fingerprint,"origin":origin,"http_wall_ms":http_wall_ms,
                        "analysis":row.get("analysis",{}),"provenance":row.get("provenance",{}),"result":result})
        save();print(json.dumps({"case_id":row["case_id"],"format":row["format"],"model":model,
                                 "status":result["status"],"compute_ms":result["timing_ms"]["compute"],
                                 "tokens":result.get("token_counts",{}).get("state")}),flush=True)
    for row in rows:
        if is_current(row):
            old=by_prefix[(row["prefix_id"],frozen_ablation(row["current_view"]))]
            expected=inference_input_hash(row["payload"],health["fingerprint"])
            if old["input_hash"]!=expected:
                raise ValueError(f"Frozen current payload/order differs for {row['case_id']}")
            record(row,"SecJev-0.8B",as_result(old),health["fingerprint"],"frozen_current")
        else:
            start=time.perf_counter();result=http_json(args.mps08_url+"/score",row["payload"])
            manifest["actual_calls"]["SecJev-0.8B"]+=1
            record(row,"SecJev-0.8B",result,health["fingerprint"],"new_prefix_format",(time.perf_counter()-start)*1000)
    scorer=SecJev2BScorer(args.workspace,"mps",1,"sdpa","solver_block")
    from . import mps_diagnostics
    scorer.metadata={**scorer.metadata,"solver_patch_sha256":hashlib.sha256(Path(mps_diagnostics.__file__).read_bytes()).hexdigest(),
                     "history_diagnostic_source_sha256":manifest["diagnostic_source_sha256"]}
    scorer.fingerprint=canonical_hash({k:v for k,v in scorer.metadata.items() if k!="model_load_ms"})
    manifest["models"]["SecJev-2B"]={"fingerprint":scorer.fingerprint,"metadata":scorer.metadata}
    for row in rows:
        result=scorer.score(row["payload"])
        manifest["actual_calls"]["SecJev-2B"]+=1
        record(row,"SecJev-2B",result,scorer.fingerprint,"new_model_same_payload")
    # One bounded repeatability check, including full raw probability distributions.
    repeated=next(r for r in rows if not is_current(r))
    aa=[scorer.score(repeated["payload"]) for _ in range(3)]
    manifest["actual_calls"]["SecJev-2B"]+=3
    manifest["aa"]={"case_id":repeated["case_id"],"format":repeated["format"],
                    "payload_hash":payload_hash(repeated["payload"]),"results":aa,"summary":aa_summary(aa)}
    manifest["status"]="COMPLETE"
    manifest["valid_rows"]=sum(r["result"]["status"]=="OK" for r in outputs)
    manifest["unknown_rows"]=sum(r["result"]["status"]!="OK" for r in outputs)
    save()


if __name__ == "__main__":main()
