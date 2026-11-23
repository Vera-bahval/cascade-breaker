"""Offline preflight for resuming a native parent and, at P4, its Payments child."""

import argparse
import asyncio
from collections import Counter
from contextlib import closing, redirect_stdout
from datetime import datetime
import gzip
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ...examples.continuation import native_environment, normalize_system
from .restore import read, record_hash, restore


def handoff(workflow, capture, point):
    steps = workflow["steps"][:capture["trace_cutoff_seq"] + 1]
    parent = next(step for step in reversed(steps)
                  if step["kind"] == "llm" and step["agent"] == "orchestrator_agent")
    delegates = [s for s in steps if s["kind"] == "delegation" and s["target"] == "payments" and s["seq"] > parent["seq"]]
    if len(delegates) != 1:
        raise ValueError("Archive lacks a uniquely bound Payments invocation")
    args = {"invoice_id": capture["invoice_id"], "task_description": delegates[0]["task_description"]}
    singleton(parent, "delegate_to_payments", args)
    if point == "P1":
        child = None
        if delegates[0]["enriched_task"] != capture["arguments"]["task_description"]:
            raise ValueError("Archived Payments handoff differs from the capture")
    else:
        child = steps[capture["source_agent_llm_seq"]]
        if child["agent"] != "payments_agent":
            raise ValueError("P4 capture does not bind a Payments turn")
        singleton(child, "finstripe__create_transfer", capture["arguments"])
    return parent, child


def singleton(step, name, arguments):
    if step["error"] or len(step["output"]["tool_calls"]) != 1:
        raise ValueError("An exact continuation requires one pending tool call")
    proposal, = step["output"]["tool_calls"]
    if proposal["name"] != name or proposal["arguments"] != arguments:
        raise ValueError("Archived tool call differs from the captured proposal")


def historical_responses(source, selected, workflow):
    requests = {}
    sdk = {}
    with gzip.open(source / "calls.jsonl.gz", "rt") as stream:
        for row in map(json.loads, stream):
            if row["event"] == "request":
                key = record_hash(row["sdk_request"].get("input"))
                if key in requests:
                    requests[key] = None
                else:
                    requests[key] = row
            elif row["event"] == "sdk_response":
                sdk[row["attempt_id"]] = row["body"]
    entries = {}
    for step in selected:
        key = record_hash(step["messages"])
        req = requests.get(key)
        tools = workflow["tool_defs"][step["tools_sha"]]
        if not req or req["sdk_request"]["input"] != step["messages"] or req["sdk_request"]["tools"] != tools:
            raise ValueError("Missing exact native SDK request and tool schemas")
        messages = list(step["messages"])
        reconstructed = []
        body = sdk[req["attempt_id"]]
        for item in body["output"]:
            if item["type"] == "message":
                text = "".join(c["text"] for c in item["content"] if c["type"] == "output_text")
                messages.append({"role": item["role"], "content": text})
            elif item["type"] == "function_call":
                messages.append({k: item[k] for k in ("type", "name", "call_id", "arguments")})
                reconstructed.append({"name": item["name"], "call_id": item["call_id"],
                                      "arguments": json.loads(item["arguments"])})
            else:
                raise ValueError("Unsupported archived response item")
        if reconstructed != step["output"]["tool_calls"]:
            raise ValueError("SDK response and native trace disagree")
        entries[step["agent"]] = (step, messages, tools, reconstructed, req["request_sha256"])
    return entries


def identity(clone, capture, episode):
    from finbot.core.auth.session import SessionContext
    from runner.direct_mode import session_for

    with closing(sqlite3.connect(clone.as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute("SELECT session_id,user_id,email,is_temporary,namespace,created_at,expires_at,"
                          "user_agent,current_vendor_id FROM user_sessions WHERE namespace=?",
                          (capture["namespace"],)).fetchall()
    if episode["cell"]["channel"] == "direct" and not rows:
        return session_for(capture["namespace"], capture["snapshot"]["vendor"]["id"])
    if len(rows) != 1:
        raise ValueError("Archive has no single vendor portal session")
    sid, uid, email, temporary, namespace, created, expires, ua, vid = rows[0]
    return SessionContext(session_id=sid, user_id=uid, email=email, is_temporary=bool(temporary),
                          namespace=namespace, created_at=datetime.fromisoformat(created),
                          expires_at=datetime.fromisoformat(expires), user_agent=ua,
                          portal_type="vendor", current_vendor_id=vid)


async def continue_episode(source, capture_file, clone, decision, offline=False):
    from finbot.agents import runner
    from finbot.agents.orchestrator import OrchestratorAgent
    from finbot.agents.specialized.payments import PaymentsAgent
    from finbot.core.data.models import LLMResponse
    from finbot.core.llm.contextual_client import ContextualLLMClient
    from finbot.probe import trace
    from finbot.probe.guards.runtime import GuardStop
    from finbot.probe.guards.workflow import workflow_snapshot
    from runner.direct_mode import _ensure_event_bus
    from ....notice_repair.run import corrected

    await _ensure_event_bus()
    episode = read(source / "episode.json")
    capture = read(capture_file)
    workflow = episode["traces"][capture["workflow_id"]]
    point = capture_file.name.split("-")[0]
    parent_turn, child_turn = handoff(workflow, capture, point)
    selected = [parent_turn] if child_turn is None else [parent_turn, child_turn]
    responses = historical_responses(source, selected, workflow)
    context = identity(clone, capture, episode)
    iid = capture["invoice_id"]
    task = workflow["task_data"]
    if workflow_snapshot(context, {"invoice_id": iid}) != capture["snapshot"]:
        raise ValueError("Native ORM does not reproduce the captured state")

    class BoundaryReached(GuardStop):
        pass

    class TransferDenied(GuardStop):
        pass

    reached = False
    native_chat = ContextualLLMClient.chat
    native_pay = runner.run_payments_agent
    native_delegate = OrchestratorAgent.delegate_to_payments
    native_callables = PaymentsAgent._get_final_callables
    parent = OrchestratorAgent(context, capture["workflow_id"])
    parent._delegation_attempts = dict(Counter(
        s["name"].removeprefix("delegate_to_") for s in workflow["steps"][:parent_turn["seq"]]
        if s["kind"] == "tool" and s.get("agent") == "orchestrator_agent" and s["name"].startswith("delegate_to_")
    ))
    parent._workflow_context = [(s["agent"], s["task_summary"]) for s in workflow["steps"][:parent_turn["seq"]]
                                if s["kind"] == "summary" and s.get("task_summary")]
    parent_limits = parent._get_max_iterations() - sum(
        s["kind"] == "llm" and s["agent"] == "orchestrator_agent" for s in workflow["steps"][:parent_turn["seq"]]
    )

    async def replay(client, request, *args, **kwargs):
        if client.agent_name in responses:
            step, messages, tools, proposal, wire_hash = responses.pop(client.agent_name)
            if request.tools != tools or normalize_system(request.messages[0]) != normalize_system(step["messages"][0]):
                raise BoundaryReached("Native system prompt or tool schema drifted")
            if request.messages[1] != step["messages"][1]:
                raise BoundaryReached("Native task prompt drifted")
            trace.record("matched_archived_response", agent=client.agent_name, archived_seq=step["seq"],
                         source_request_sha256=wire_hash)
            return LLMResponse(content=step["output"]["content"], provider="openai", success=True,
                               messages=messages, tool_calls=proposal)
        if offline:
            raise BoundaryReached("Offline preflight would otherwise call the provider")
        return await native_chat(client, request, *args, **kwargs)

    def boundary():
        nonlocal reached
        if reached or responses or workflow_snapshot(context, {"invoice_id": iid}) != capture["snapshot"]:
            raise BoundaryReached("The native continuation did not arrive at the same single business state")
        reached = True
        trace.record("matched_policy_boundary", point=point, decision=decision, invoice_id=iid)
        if offline:
            raise BoundaryReached("offline_boundary_verified")

    def denial():
        return corrected({"task_status": "failed", "invoice_id": iid, "payment_processed": False,
                          "finale_stop": point}, capture["snapshot"]["invoice"], capture["snapshot"]["vendor"])

    async def pay(**kwargs):
        if point == "P1" and not reached:
            if kwargs["task_data"] != {"invoice_id": iid, "description": capture["arguments"]["task_description"]}:
                raise BoundaryReached("Unmatched Payments task")
            boundary()
            if decision in {"BLOCK", "REVIEW"}:
                return denial()
        try:
            return await native_pay(**kwargs)
        except TransferDenied:
            return denial()

    async def delegate(agent, invoice_id, task_description):
        result = await native_delegate(agent, invoice_id, task_description)
        if result.get("finale_stop") and result.get("invoice_id") == invoice_id:
            return denial()
        return result

    def callables(agent):
        mapping = native_callables(agent)
        if point != "P4":
            return mapping
        name = "finstripe__create_transfer"
        transfer = mapping[name]

        async def propose(**args):
            if not reached:
                if args != capture["arguments"]:
                    raise BoundaryReached("Unmatched transfer proposal")
                boundary()
                if decision in {"BLOCK", "REVIEW"}:
                    raise TransferDenied()
            return await transfer(**args)

        return {**mapping, name: propose}

    def payment_limits(agent):
        cutoff = child_turn["seq"] if child_turn is not None else 0
        parent_seq = parent_turn["seq"]
        child_used = sum(s["kind"] == "llm" and s["agent"] == "payments_agent"
                         for s in workflow["steps"][parent_seq:cutoff])
        return native_payment_limits(agent) - (child_used if "payments_agent" in responses else 0)

    native_payment_limits = PaymentsAgent._get_max_iterations
    with (patch.object(parent, "_get_max_iterations", return_value=parent_limits),
          patch.object(PaymentsAgent, "_get_max_iterations", payment_limits),
          patch.object(ContextualLLMClient, "chat", replay),
          patch.object(OrchestratorAgent, "delegate_to_payments", delegate),
          patch.object(PaymentsAgent, "_get_final_callables", callables),
          patch.object(runner, "run_payments_agent", pay),
          trace.open_recorder() as recorder):
        # Decorated native methods are registered through their metadata.
        result = None
        try:
            result = await parent.process(task)
        except BoundaryReached as error:
            if str(error) != "offline_boundary_verified" or not offline:
                raise
        if not reached:
            raise ValueError("The selected native boundary was never reached")
        return {"point": point, "decision": decision, "offline": offline, "boundary_reached": reached,
                "source_request_hashes": [s["source_request_sha256"] for s in recorder.steps
                                          if s["kind"] == "matched_archived_response"],
                "orchestrator": result, "steps": recorder.steps,
                "final_snapshot": workflow_snapshot(context, {"invoice_id": iid})}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("capture")
    args = parser.parse_args()
    source = args.source.resolve()
    with TemporaryDirectory(prefix="finbot-resume-") as tmp:
        folder = Path(tmp) / "clone"
        clone = folder / "finbot.db"
        verification = restore(source, source / args.capture, folder)
        root = Path.cwd()
        native_environment(root, clone)
        with redirect_stdout(sys.stderr):
            result = asyncio.run(continue_episode(source, source / args.capture, clone, "ALLOW", offline=True))
        print(json.dumps({"restore": verification, "replay": result}, indent=2))
