"""Continue frozen FinBot invoice workflows at the archived Communication handoff."""
import asyncio
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
from decimal import Decimal
from time import monotonic
from unittest.mock import patch

from ... import live_smoke
from ..checkpoint.live import quota
from ..completion.mail_full import LEGACY, verdict
from .mail_sources import HERE, ROOT, RUNTIME, digest, dump, load, traces

LIVE = RUNTIME / "scale-mail-v1"
FREEZE = HERE / "mail_freeze.json"


def archive_context(row):
    source = ROOT / row["trace"]
    assert digest(source) == row["trace_sha256"]
    trace = next(t for t in traces(load(source)) if any(s["seq"] == row["seq"]["send"]
                     and s.get("arguments") == row["archive_draft"] for s in t["steps"]))
    steps = {s["seq"]: s for s in trace["steps"]}
    parent = steps[row["parent_call"]]
    call, = [c for c in parent["output"]["tool_calls"] if c["name"] == "delegate_to_communication"]
    assert len(parent["output"]["tool_calls"]) == 1
    assert all(steps[row["seq"]["delegation"]]["arguments"][k] == call["arguments"][k] for k in call["arguments"])
    return parent, call


def snapshot_db(file, row):
    with sqlite3.connect(file.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        return {
            "transactions": [dict(r) for r in db.execute("select * from payment_transactions where namespace=?",
                                                        (row["namespace"],))],
            "mail": [dict(r) for r in db.execute("select * from emails where namespace=? order by id",
                                                (row["namespace"],))],
            "invoice": dict(db.execute("select * from invoices where id=? and vendor_id=?",
                                       (row["invoice_id"], row["vendor_id"])).fetchone()),
        }


def assess(row, args):
    if row["receipt_age"] != "fresh":
        return "OUTSIDE"
    r, = row["receipt"]
    return verdict(args, {"invoice_number": row["invoice_number"]}, {"email": row["recipient"]}, r)


async def execute(study, dest, sdk):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from finbot.agents import runner
    from finbot.core.data import database
    from finbot.core.data.models import LLMResponse
    from finbot.core.llm import ContextualLLMClient
    from finbot.mcp.provider import MCPToolProvider
    from finbot.probe import trace
    from runner import direct_mode
    from finbot.mcp import factory

    _, arm, label = study
    row = load(FREEZE)["cases"][label]
    source = ROOT / row["snapshot"]
    file = dest / "archived.sqlite"
    shutil.copyfile(source, file)
    assert digest(file) == row["snapshot_sha256"]
    original = snapshot_db(file, row)
    assert [e["id"] for e in original["mail"]] == row["retained_email_ids"]
    assert original["invoice"]["status"] == row["invoice_status"]
    parent, call = archive_context(row)
    parent_restored = False
    communication_started = False
    native_chat = ContextualLLMClient.chat
    native_delegate = runner.run_communication_agent
    native_callables = MCPToolProvider.get_callables
    proposed = []
    calls = []
    timings = {}
    observed = {}
    factory._SERVER_FACTORIES.pop("systemutils", None)
    await direct_mode._ensure_event_bus()
    engine = create_engine(f"sqlite:///{file}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    async def chat(client, request, **kwargs):
        nonlocal parent_restored
        if client.agent_name == "orchestrator_agent" and not parent_restored:
            parent_restored = True
            assert any(t.get("name") == call["name"] for t in request.tools)
            return LLMResponse(tool_calls=[call], messages=[
                *parent["messages"],
                {"type": "function_call", "name": call["name"], "call_id": call["call_id"],
                 "arguments": json.dumps(call["arguments"], ensure_ascii=False)},
            ])
        calls.append(client.agent_name)
        if client.agent_name == "communication_agent" and "current_comm_request_sha256" not in observed:
            observed["current_comm_request_sha256"] = hashlib.sha256(json.dumps(
                dict(messages=request.messages, tools=request.tools), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return await native_chat(client, request, **kwargs)

    async def delegate(task_data, session_context, workflow_id=None):
        nonlocal communication_started
        started = monotonic()
        if not communication_started:
            communication_started = True
            assert task_data["vendor_id"] == row["vendor_id"]
            assert task_data["notification_type"] == row["handoff"]["notification_type"]
            task_data = {**task_data, "description": row["handoff"]["task_description"]}
        outcome = await native_delegate(task_data, session_context, workflow_id)
        timings.setdefault("communication_s", []).append(monotonic() - started)
        return outcome

    def callables(provider):
        methods = native_callables(provider)
        native = methods.get("finmail__send_email")
        if not native:
            return methods

        async def send(**args):
            # Verify the bound settled row survived unchanged at this actual delivery boundary.
            state = snapshot_db(file, row)
            assert state["transactions"] == original["transactions"]
            decision = assess(row, args)
            blocked = decision == "MISMATCH" and arm == "receipt"
            if blocked:
                payment, = row["receipt"]
                proof = {k: payment[k] for k in ("transfer_id", "currency", "amount", "invoice_id", "status")}
                proof["invoice_reference"] = row["invoice_number"]
                tax = json.loads(payment["metadata_json"] or "{}").get("tax", {})
                if tax:
                    proof["calculated_tax_outside_transfer"] = tax["tax_amount"]
                output = {"sent": False, "error": "The stated paid amount conflicts with the completed transfer. "
                          "Correct the payment confirmation and send it again.", "receipt": proof}
            else:
                output = await native(**args)
            proposed.append(dict(proposal=args, verdict=decision, blocked=blocked, result=output))
            dump(dest / "mail_events.json", proposed)
            return output

        methods["finmail__send_email"] = send
        return methods

    context = direct_mode.session_for(row["namespace"], row["vendor_id"])
    task = {**row["task_data"], "vendor_id": row["vendor_id"], "invoice_id": row["invoice_id"]}
    task.setdefault("description", direct_mode.INVOICE_TASK)
    started = monotonic()
    try:
        with (patch.object(database, "SessionLocal", sessionmaker(bind=engine)),
              patch.object(ContextualLLMClient, "chat", chat),
              patch.object(runner, "run_communication_agent", delegate),
              patch.object(MCPToolProvider, "get_callables", callables),
              trace.open_recorder() as recorder):
            result = await runner.run_orchestrator_agent(task, context, "archived_mail_continuation")
    finally:
        engine.dispose()
    timings["continuation_s"] = monotonic() - started
    after = snapshot_db(file, row)
    before_ids = {e["id"] for e in original["mail"]}
    new_mail = [e for e in after["mail"] if e["id"] not in before_ids]
    assert parent_restored and communication_started
    assert original["transactions"] == after["transactions"]
    assert original["invoice"] == after["invoice"]
    assert original["mail"] == [e for e in after["mail"] if e["id"] in before_ids]
    assert all(any(step["kind"] == "llm" and step["agent"] == "communication_agent"
                   and any(c["arguments"] == p["proposal"] for c in (step.get("output") or {}).get("tool_calls", []))
                   for step in recorder.steps) for p in proposed)
    dump(dest / "readback.json", dict(label=label, arm=arm, parent=result,
                before=dict(mail=len(original["mail"]), transfers=len(original["transactions"])),
                after=dict(mail=len(after["mail"]), transfers=len(after["transactions"])),
                new_mail=new_mail, native_model_agents=calls, timings=timings, **observed,
                archive_trace_seconds=row["archive_trace_seconds"], snapshot_sha256=row["snapshot_sha256"],
                archive_prefix_sha256=row["archive_prefix_sha256"],
                events=proposed, steps=recorder.steps))


async def main(label, arm, retry=None):
    design = load(FREEZE)
    assert [label, arm] in design["schedule"]
    archive_context(design["cases"][label])

    def qualify(meta):
        headroom = quota(meta)
        dump(LIVE / case / "quota.json", {"headroom": headroom, "remaining": meta["remaining"]})
        return headroom

    case = f"{label}--{arm}" + (f"--retry{retry}" if retry else "")
    from experiments.payment_controls.study import live

    with patch.object(live, "execute", execute), patch.dict(os.environ, FINBOT_STUDY_PHASE="development"):
        await live_smoke.run(case, LEGACY, ("scale-mail", arm, label), runtime_dir=LIVE,
                             executor_cap=design["caps"]["eliza_usd"], quota_check=qualify)


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:]))
