"""Verify natural P1 states and prepare an isolated stock Payments continuation."""
import argparse
import asyncio
from contextlib import closing, redirect_stdout
from datetime import datetime
from hashlib import sha256
import fcntl
import json
from math import isfinite
import os
from pathlib import Path
import re
import sqlite3
from struct import unpack
import subprocess
import sys
from tempfile import TemporaryDirectory

RUNTIME = Path(".runtime/payment-controls-chp3/final-study-payment-finale/test")
ASSIGNMENTS = ("TH626-portal--B", "TH612-chat2--B")



def digest(value):
    return sha256(value).hexdigest()


def record_hash(rows):
    return digest(json.dumps(rows, sort_keys=True, default=str).encode())


def fields_match(row, expected):
    for key, value in expected.items():
        observed = row[key]
        if key in {"created_at", "updated_at", "invoice_date", "due_date"} and value is not None:
            observed = datetime.fromisoformat(observed).isoformat()
            value = datetime.fromisoformat(value).isoformat()
        if key == "attachments":
            observed = json.loads(observed) if observed else []
        if observed != value:
            return False
    return True


def evaluate(source, save_dir=None):
    capture = json.loads((source/"P1-001.json").read_text())
    terminal = json.loads((source/"episode.json").read_text())
    workflow = terminal["traces"][capture["workflow_id"]]
    prefix = workflow["steps"][:capture["trace_cutoff_seq"]+1]
    delegation = prefix[-1]
    assert delegation["kind"] == "delegation" and delegation["target"] == "payments"
    assert delegation["enriched_task"] == capture["arguments"]["task_description"]
    assert not any(x["kind"] == "llm" and x.get("agent") == "payments_agent" for x in workflow["steps"])
    iid, namespace = capture["invoice_id"], capture["namespace"]
    capture_rows = capture["snapshot"]
    assert not capture_rows["transactions"]
    base = (source/"finbot.db").read_bytes()
    wal = (source/"finbot.db-wal").read_bytes()
    magic, version, page_size, _, salt1, salt2, _, _ = unpack(">8I", wal[:32])
    assert magic in {0x377F0682, 0x377F0683} and version == 3007000 and len(base) == page_size
    step = 24+page_size
    assert (len(wal)-32) % step == 0
    matches = []
    endpoints = {}
    seen_tables = set()
    with TemporaryDirectory(prefix='finbot-payments-readback-') as temp:
        for frame, off in enumerate(range(32, len(wal), step), 1):
            page, dbsize, frame_salt1, frame_salt2, _, _ = unpack(">6I", wal[off:off+24])
            assert page and (salt1,salt2) == (frame_salt1,frame_salt2)
            if not dbsize:
                continue
            path = Path(temp) / f"candidate-{frame}.db"
            wal_path = path.with_name(path.name+"-wal")
            path.write_bytes(base)
            wal_path.write_bytes(wal[:off+step])
            try:
                with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True)) as db:
                    db.row_factory = sqlite3.Row
                    tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
                    seen_tables.update(tables)
                    if not {"invoices","vendors","payment_transactions","emails"} <= tables:
                        continue
                    assert db.execute("pragma page_count").fetchone()[0] == dbsize
                    invoice = db.execute("select * from invoices where namespace=? and id=?", (namespace,iid)).fetchone()
                    vendor = db.execute("select * from vendors where namespace=? and id=?",
                                        (namespace,capture_rows["vendor"]["id"])).fetchone()
                    if (not invoice or not vendor or not fields_match(invoice,capture_rows["invoice"])
                        or not fields_match(vendor,capture_rows["vendor"])):
                        continue
                    tx = db.execute("select id from payment_transactions where namespace=? and invoice_id=?", (namespace,iid)).fetchall()
                    if tx:
                        continue
                    outbound = db.execute("select id from emails where namespace=? and direction='outbound'", (namespace,)).fetchall()
                    if outbound:
                        continue
                    assert db.execute("pragma quick_check").fetchone()[0] == "ok"
                    hashes = {t: record_hash([tuple(r) for r in db.execute('select * from "'+t+'" order by rowid')]) for t in tables}
                    audit_suffix = [tuple(r) for r in db.execute(
                        "SELECT id,server_type,direction,method,tool_name FROM mcp_activity_log "
                        "WHERE namespace=? AND workflow_id=? ORDER BY id DESC LIMIT 8",
                        (namespace,capture["workflow_id"]))]
                    matches.append((frame, hashes, audit_suffix))
                    endpoints[frame] = off + step
            finally:
                for candidate in path.parent.glob(path.name+"*"):
                    candidate.unlink()
    assert len(matches) == 3
    differences = {table for table in seen_tables if len({h.get(table) for _, h, _ in matches}) > 1}
    assert differences == {"mcp_activity_log"}
    selected, _, audit = matches[0]
    assert audit[0][2:4] == ("response", "tools/call")
    assert matches[1][2][0][1:] == ("finmail", "request", "tools/list", None)
    assert matches[2][2][0][1:] == ("finmail", "request", "tools/call", "send_email")
    if save_dir is not None:
        save_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        (save_dir / "finbot.db").write_bytes(base)
        (save_dir / "finbot.db-wal").write_bytes(wal[:endpoints[selected]])
    return {
        "assignment":source.name, "episode_sha256":digest((source/"episode.json").read_bytes()),
        "p1_sha256":digest((source/"P1-001.json").read_bytes()),
        "base_sha256":digest(base),"wal_sha256":digest(wal),"page_size":page_size,
        "commit_frames_matching_p1_and_no_outbound":[f for f,_,_ in matches],
        "varied_tables":sorted(differences),
        "mcp_activity_suffix_per_candidate":{f:suffix for f,_,suffix in matches},
        "selected_commit_frame": selected,
        "task_source_seq":delegation["seq"], "historical_payments_request_exists":False,
    }


def normalize_system(message, *, omit_user=False):
    content = message["content"]
    names = "Current Date and Time|User ID" if omit_user else "Current Date and Time"
    content, replaced = re.subn(rf"(?m)^(\s*(?:{names}): ).*$", r"\1[verified-dynamic-field]", content)
    assert replaced == (2 if omit_user else 1)
    return {**message, "content": content}


def request_hash(messages, tools):
    system, user = messages
    return record_hash({"messages": [normalize_system(system), user], "tools": tools})


async def inspect_request(clone, source):
    from finbot.agents.specialized.payments import PaymentsAgent
    from runner.direct_mode import _ensure_event_bus

    await _ensure_event_bus()
    context, p1, task, snapshot = restore_context(clone, source)
    actual = snapshot(context, task)
    assert actual == p1["snapshot"]
    agent = PaymentsAgent(context, p1["workflow_id"])
    invoice_read = await agent.get_invoice_for_payment(task["invoice_id"])
    assert invoice_read["agent_notes"] == actual["invoice"]["agent_notes"]
    assert "recommended action: hold" in invoice_read["agent_notes"].lower()
    assert invoice_read["vendor_status"] == actual["vendor"]["status"]
    await agent._connect_mcp_servers()
    try:
        request = {
            "messages": [
                {"role": "system", "content": agent._get_final_system_prompt()},
                {"role": "user", "content": await agent._get_user_prompt(task)},
            ],
            "tools": agent._get_final_tool_definitions(),
        }
    finally:
        await agent._disconnect_mcp_servers()
    counterpart = source.with_name(source.name[:-1] + "A")
    original = json.loads((source / "episode.json").read_text())
    other = json.loads((counterpart / "episode.json").read_text())
    assert original["initial_state_sha256"] == other["initial_state_sha256"]
    trace, = [t for t in other["traces"].values()
              if any(s.get("agent") == "payments_agent" and s["kind"] == "llm" for s in t["steps"])]
    first = next(s for s in trace["steps"] if s.get("agent") == "payments_agent" and s["kind"] == "llm")
    assert normalize_system(request["messages"][0], omit_user=True) == normalize_system(
        first["messages"][0], omit_user=True)
    assert request["tools"] == trace["tool_defs"][first["tools_sha"]]
    return {
        "request_sha256_excluding_wall_clock": request_hash(request["messages"], request["tools"]),
        "system_and_tools_match_stock_first_request_excluding_session_and_clock": True,
        "scoped_native_orm_read_matches_capture": True,
        "native_payments_read_returns_exact_hold_note": True,
        "stock_actor_llm_seq": first["seq"],
    }


def restore_context(clone, source):
    from finbot.core.auth.session import SessionContext
    from finbot.probe.guards.workflow import workflow_snapshot

    p1 = json.loads((source / "P1-001.json").read_text())
    with closing(sqlite3.connect(clone.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        row, = db.execute(
            "SELECT session_id,user_id,email,is_temporary,namespace,created_at,expires_at,user_agent,"
            "current_vendor_id FROM user_sessions WHERE namespace=?", (p1["namespace"],)).fetchall()
    sid, uid, email, temporary, namespace, created, expires, user_agent, vid = row
    context = SessionContext(session_id=sid, user_id=uid, email=email, is_temporary=bool(temporary),
                             namespace=namespace, created_at=datetime.fromisoformat(created),
                             expires_at=datetime.fromisoformat(expires), user_agent=user_agent,
                             portal_type="vendor", current_vendor_id=vid)
    task = {"invoice_id": p1["invoice_id"], "description": p1["arguments"]["task_description"]}
    return context, p1, task, workflow_snapshot


def native_environment(root, clone):
    sys.path[:0] = [str(root / "finbot"), str(root / "scenarios"), str(root)]
    os.environ.update(DATABASE_URL=f"sqlite:///{clone}", OPENAI_API_KEY="offline-placeholder",
                      LLM_PROVIDER="openai", LLM_DEFAULT_MODEL="deepseek-flash",
                      LLM_DEFAULT_TEMPERATURE="0", PROBE_ENFORCE="", FINBOT_V4_PROFILE="",
                      CASCADE_GUARD_MODE="off", REDIS_URL="redis://127.0.0.1:1")


def preflight():
    results = []
    with TemporaryDirectory(prefix="finbot-continuation-preflight-") as temp:
        for name in ASSIGNMENTS:
            source = (RUNTIME / name).resolve()
            path = Path(temp) / name
            evidence = evaluate(source, save_dir=path)
            native = subprocess.check_output([sys.executable, str(Path(__file__).resolve()),
                "inspect-isolated-request", str(path / "finbot.db"), str(source)])
            evidence["first_native_request_assembled_offline"] = json.loads(native)
            results.append(evidence)
    return results


async def one_paid(source, target, runtime, cap, expected_request):
    from experiments.payment_controls.native.final_study import live, live_meter
    from experiments.payment_controls.native.final_study.finale.live import meter
    from unittest.mock import patch

    ledger = runtime / "test" / "executor.sqlite"
    with patch.object(live_meter, "live_ledger", meter.ledger):
        await _execute_paid(source, target, cap, expected_request, ledger, live)


async def _execute_paid(source, target, cap, expected_request, ledger, live):
    async with live.session(target, ledger, cap, "test"):
        from finbot.agents.specialized.payments import PaymentsAgent
        from finbot.core.llm.contextual_client import ContextualLLMClient
        from finbot.probe import trace
        from unittest.mock import patch

        context, p1, task, snapshot = restore_context(target / "finbot.db", source)
        assert snapshot(context, task) == p1["snapshot"]
        first = True
        original = ContextualLLMClient.chat

        async def match_first(client, request, *args, **kwargs):
            nonlocal first
            if first:
                assert request_hash(request.messages, request.tools) == expected_request
                first = False
            return await original(client, request, *args, **kwargs)

        with patch.object(ContextualLLMClient, "chat", match_first), trace.open_recorder() as recording:
            response = await PaymentsAgent(context, p1["workflow_id"]).process(task)
        assert not first
        final = snapshot(context, task)
        completed = [tx for tx in final["transactions"] if tx["status"] == "completed"]
        receipt_ids = {s["output"]["transfer_id"] for s in recording.steps if s["kind"] == "tool"
                       and s.get("name") == "finstripe__create_transfer" and not s.get("error")
                       and (s.get("output") or {}).get("status") == "completed"}
        assert receipt_ids == {tx["transfer_id"] for tx in completed}
        live.write(target / "continuation.json", {
            "source_assignment": source.name, "stock_result": response, "final_snapshot": final,
            "steps": recording.steps, "completed_receipts": len(completed),
            "first_request_sha256_excluding_wall_clock": expected_request, "scope": "Payments child only",
        })


def paid():
    from experiments.payment_controls.native.final_study.finale.live import run

    runtime = run.PRIVATE
    release_path = runtime / "continuation-release.json"
    release = json.loads(release_path.read_text())
    assert release.get("reviewer") == "root" and release.get("approved") is True
    assert release["freeze_sha256"] == digest((runtime / "freeze.json").read_bytes())
    assert release["code_sha256"] == digest(Path(__file__).read_bytes())
    assert release["assignments"] == list(ASSIGNMENTS)
    allowance = release["eliza_additional_usd"]
    assert type(allowance) in (int, float) and isfinite(allowance) and 0 < allowance <= run.ELIZA_CAP
    receipt_path = Path(__file__).with_name("continuation_preflight.json")
    assert release["preflight_sha256"] == digest(receipt_path.read_bytes())
    preflight_rows = load_json(receipt_path)
    assert [r["assignment"] for r in preflight_rows] == list(ASSIGNMENTS)
    private = runtime / "continuation"
    with (runtime / "dispatch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        data = run.approved()
        archive = run.collect(data)
        for totals in archive["summary"].values():
            assert totals["technical_complete"] == totals["planned_groups"]
        assert not (runtime / "test" / "halt.json").exists()
        before = run.meter(runtime / "test")["eliza"]
        exposure = before["settled_usd"] + before["unresolved_usd"]
        quota = load_json(runtime / "quota.json")["eliza_cap_usd"]
        cap = min(quota, run.ELIZA_CAP, exposure + allowance)
        assert exposure < cap
        private.mkdir(mode=0o700, exist_ok=False)
        try:
            for evidence in preflight_rows:
                name = evidence["assignment"]
                source = runtime / "test" / name
                target = private / name
                actual = evaluate(source, save_dir=target)
                request = evidence["first_native_request_assembled_offline"]["request_sha256_excluding_wall_clock"]
                assert record_hash(actual) == record_hash({k: v for k, v in evidence.items()
                                  if k != "first_native_request_assembled_offline"})
                subprocess.run([sys.executable, "-m", __spec__.name, "paid-child",
                                str(source), str(target), str(runtime), str(cap), request, str(lock.fileno())],
                               check=True, pass_fds=(lock.fileno(),))
        finally:
            after = run.meter(runtime / "test")["eliza"]
            exact = {key: after[key] - before[key] for key in ("settled_usd", "unresolved_usd")}
            (private / "usage.json").write_text(json.dumps({
                "shared_ledger_before": before, "shared_ledger_after": after,
                "continuations_delta": exact, "shared_cap_usd": cap,
            }, indent=2) + "\n")


def load_json(path):
    return json.loads(path.read_text())


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "inspect-isolated-request":
        root = Path(__file__).resolve().parents[6]
        clone, source = map(Path, sys.argv[2:])
        native_environment(root, clone)
        with redirect_stdout(sys.stderr):
            request = asyncio.run(inspect_request(clone, source))
        print(json.dumps(request))
    elif len(sys.argv) >= 2 and sys.argv[1] == "paid-child":
        assert len(sys.argv) == 8
        source, target, runtime = map(Path, sys.argv[2:5])
        cap, expected_request, inherited_lock = sys.argv[5:]
        from experiments.payment_controls.native.final_study.finale.live import run

        assert runtime == run.PRIVATE
        assert os.path.samestat(os.fstat(int(inherited_lock)), (runtime / "dispatch.lock").stat())
        release = load_json(runtime / "continuation-release.json")
        assert release.get("reviewer") == "root" and release.get("approved") is True
        assert release["code_sha256"] == digest(Path(__file__).read_bytes())
        assert source.name in release["assignments"] and target == runtime / "continuation" / source.name
        assert source == runtime / "test" / source.name
        receipt_path = Path(__file__).with_name("continuation_preflight.json")
        assert release["preflight_sha256"] == digest(receipt_path.read_bytes())
        receipt, = (r for r in load_json(receipt_path) if r["assignment"] == source.name)
        assert expected_request == receipt["first_native_request_assembled_offline"]["request_sha256_excluding_wall_clock"]
        assert 0 < float(cap) <= min(run.ELIZA_CAP, load_json(runtime / "quota.json")["eliza_cap_usd"])
        asyncio.run(one_paid(source, target, runtime, float(cap), expected_request))
    else:
        cli = argparse.ArgumentParser(description=__doc__)
        cli.add_argument("action", choices=("preflight", "paid"))
        if cli.parse_args().action == "preflight":
            print(json.dumps(preflight(), indent=2, sort_keys=True))
        else:
            paid()
