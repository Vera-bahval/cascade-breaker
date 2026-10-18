"""Strict tokenizer-only admission for frozen ledger payloads; no model inference."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from .structured_ledger import ordered_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--input", type=Path, default=Path("experiments/local_guards/results/diagnostics/structured-ledger/inputs.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("experiments/local_guards/results/diagnostics/structured-ledger/token-preflight.json"))
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    sys.path.insert(0, str(args.workspace / ".runtime/secjev/source/kev"))
    from transformers import AutoTokenizer
    from kev.api import SystemOneRequest, to_record
    from kev.model import encode, rows_of

    payloads = [json.loads(line) for line in args.input.read_text().splitlines()]
    paths = {"SecJev-0.8B": args.workspace / "models/Qwen3.5-0.8B-Base",
             "SecJev-2B": args.workspace / ".runtime/mps-diagnostics/models/Qwen3.5-2B-Base"}
    report = {"input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(), "model_inferences": 0,
              "limit_per_question_row": 8192, "strict": True, "no_truncation": True, "cases": []}
    for model, path in paths.items():
        tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
        for item in payloads:
            began = time.perf_counter()
            record, metadata = to_record(SystemOneRequest.model_validate(item["payload"]))
            result = {"model": model, "case_id": item["case_id"], "format": item["format"],
                      "payload_hash": ordered_hash(item["payload"])}
            try:
                encoded = encode(tokenizer, record, max_state=8192, max_branch=8192, strict=True, option_isolation=False)
                state, _, branches = rows_of(encoded)
                result.update(status="OK", state_tokens=len(state),
                              question_rows={m["id"]: len(state) + len(b["ids"]) for m, b in zip(metadata, branches)},
                              total_model_row_tokens=sum(len(state) + len(b["ids"]) for b in branches),
                              state_truncated=encoded["state_truncated"])
            except ValueError as exc:
                result.update(status="UNKNOWN", error=str(exc))
            result["tokenize_ms"] = (time.perf_counter() - began) * 1000
            report["cases"].append(result)
    report["summary"] = {model: {fmt: {
        "rows": len(items := [r for r in report["cases"] if r["model"] == model and r["format"] == fmt]),
        "unknown": sum(r["status"] != "OK" for r in items),
        "state_tokens_min": min((r["state_tokens"] for r in items if r["status"] == "OK"), default=None),
        "state_tokens_max": max((r["state_tokens"] for r in items if r["status"] == "OK"), default=None),
        "largest_question_row": max((max(r["question_rows"].values()) for r in items if r["status"] == "OK"), default=None),
        } for fmt in sorted(set(r["format"] for r in payloads))} for model in paths}
    report["passed"] = all(r["status"] == "OK" and not r["state_truncated"] and max(r["question_rows"].values()) <= 8192 for r in report["cases"])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "summary": report["summary"], "model_inferences": 0}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
