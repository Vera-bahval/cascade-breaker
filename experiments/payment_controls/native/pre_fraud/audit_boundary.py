"""Index first PROPOSED Fraud calls in explicit raw trace files; no execution."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def value_sha(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def trace_entries(path: Path) -> list[tuple[str | None, dict]]:
    data = json.loads(path.read_text())
    if isinstance(data, dict) and isinstance(data.get("steps"), list):
        return [(data.get("workflow_id"), data)]
    if isinstance(data, dict) and all(isinstance(v, dict) and isinstance(v.get("steps"), list)
                                      for v in data.values()):
        return list(data.items())
    raise ValueError("Expected raw trace.steps or workflow_id -> raw trace; not a projected packet")


def proposals(step: dict) -> list[dict]:
    output = step.get("output", {})
    if not isinstance(output, dict):
        return []
    return [call for call in output.get("tool_calls", [])
            if isinstance(call, dict) and call.get("name") == "delegate_to_fraud"]


def index(path: Path) -> list[dict]:
    source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    result = []
    for workflow_id, trace in trace_entries(path):
        steps = trace["steps"]
        task = trace.get("task_data", {})
        entries = [(n, s) for n, s in enumerate(steps)
                   if s.get("kind") == "llm" and s.get("agent") == "fraud_agent"]
        callers = [(n, s, call) for n, s in enumerate(steps)
                   if s.get("kind") == "llm" and s.get("agent") == "orchestrator_agent"
                   for call in proposals(s)]
        row = {"file": str(path.resolve()), "source_sha256": source_sha,
               "workflow_id": workflow_id, "root_invoice_id": task.get("invoice_id"),
               "root_vendor_id": task.get("vendor_id"), "fraud_llm_requests": len(entries),
               "warnings": []}
        if not callers:
            row.update(status="no_observed_fraud_proposal", binding_ready=False)
            result.append(row)
            continue
        # A malformed first call remains the cut, even if a later retry succeeds.
        number, caller, proposal = callers[0]
        first = entries[0][1] if entries else None
        prefix = steps[:number]
        arguments = proposal.get("arguments", {})
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        prior_fraud_outputs = [s for s in prefix if s.get("agent") == "fraud_agent"
                               and s.get("kind") in {"summary", "tool"}]
        if task.get("invoice_id") is None:
            row["warnings"].append("No root invoice binding; may be onboarding-only or incomplete raw trace")
        if arguments.get("vendor_id") != task.get("vendor_id"):
            row["warnings"].append("Proposed vendor differs from root vendor or one ID is absent")
        if prior_fraud_outputs:
            row["warnings"].append("Fraud-generated output precedes first recorded Fraud LLM request")
        row.update(status="first_proposed_fraud_call_indexed",
                   first_fraud_seq=first.get("seq") if first else None,
                   first_proposed_arguments_sha256=value_sha(arguments),
                   first_proposed_unknown_arguments=sorted(set(arguments) - {"vendor_id", "task_description"}),
                   first_proposed_required_arguments_present={"vendor_id", "task_description"} <= set(arguments),
                   later_proposed_fraud_calls=len(callers) - 1,
                   orchestrator_proposal_seq=caller.get("seq"),
                   orchestrator_call_id=proposal.get("call_id"),
                   proposed_vendor_id=arguments.get("vendor_id"),
                   prefix_sha256=value_sha(prefix), prefix_step_count=len(prefix),
                   binding_ready=not row["warnings"])
        result.append(row)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    records = [item for path in args.trace for item in index(path)]
    args.out.write_text(json.dumps({"schema": "first-proposed-fraud-boundary-index-v2", "records": records},
                                   ensure_ascii=False, indent=2, sort_keys=True) + "\n")
