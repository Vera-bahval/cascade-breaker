from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from runner.client import FinBotClient
from runner.scenario import Scenario, invoice_fields
from runner.state import load_state, save_result, save_state

ORCHESTRATOR_START = "agent.orchestrator_agent.task_start"
ORCHESTRATOR_DONE = ("agent.orchestrator_agent.task_completion", "agent.orchestrator_agent.agent.failed")


def _last_event_id(client: FinBotClient) -> int:
    items = client.activity(page_size=1)
    return items[0]["id"] if items else 0


def wait_for_workflows(client: FinBotClient, after_id: int, *, expect_workflow: bool,
                       timeout: float, settle: float = 10.0, poll: float = 2.0) -> dict[str, Any]:
    # Events reach the activity feed asynchronously, so a run is only done once
    # it has also stayed quiet for `settle` seconds.
    deadline = time.monotonic() + timeout
    last_count, quiet_since = -1, time.monotonic()
    while True:
        events = [e for e in client.activity() if e["id"] > after_id]
        started = {e["workflow_id"] for e in events if e["event_type"] == ORCHESTRATOR_START}
        finished = {e["workflow_id"] for e in events if e["event_type"] in ORCHESTRATOR_DONE}
        if len(events) != last_count:
            last_count, quiet_since = len(events), time.monotonic()
        all_done = started <= finished and (started or not expect_workflow)
        if all_done and time.monotonic() - quiet_since >= settle:
            return {"timed_out": False, "workflows": sorted(started), "events": events[::-1]}
        if time.monotonic() > deadline:
            return {"timed_out": True, "workflows": sorted(started),
                    "unfinished": sorted(started - finished), "events": events[::-1]}
        time.sleep(poll)


def read_traces(trace_dir: str | None, workflows: list[str], wait_s: float = 10.0) -> dict[str, Any]:
    # A trace file appears when its workflow ends, which can be a moment after the last event.
    if not trace_dir:
        return {}
    deadline = time.monotonic() + wait_s
    paths = {wf: Path(trace_dir) / f"{wf}.json" for wf in workflows}
    while not all(p.exists() for p in paths.values()) and time.monotonic() < deadline:
        time.sleep(0.5)
    return {wf: json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
            for wf, p in paths.items()}


def _tag() -> str:
    return secrets.token_hex(3)


def _register(client: FinBotClient, vendor: dict[str, Any]) -> dict[str, Any]:
    response = client.register_vendor(vendor)
    # Registration does not always make the new vendor current for the session.
    client.switch_vendor(response["vendor_id"])
    return response


def prepare(scenario: Scenario, base_url: str, timeout: float) -> dict[str, Any]:
    client = FinBotClient(base_url)
    try:
        client.open_session()
        tag = _tag()
        vendor_id = None
        prepared: dict[str, Any] = {"onboarding": None, "invoices": []}
        # For an onboarding scenario the registration itself is the trigger.
        if scenario.kind != "onboarding":
            after = _last_event_id(client)
            vendor_id = _register(client, scenario.vendor)["vendor_id"]
            prepared["onboarding"] = wait_for_workflows(
                client, after, expect_workflow=True, timeout=timeout)
            client.refresh_csrf()
            for n, spec in enumerate(scenario.setup_invoices, start=1):
                after = _last_event_id(client)
                created = client.create_invoice(invoice_fields(spec, f"INV-{tag}-S{n}"))
                done = wait_for_workflows(client, after, expect_workflow=True, timeout=timeout)
                prepared["invoices"].append({"invoice": created["invoice"], "wait": done})
        state = {
            "scenario": scenario.id,
            "via": "api",
            "base_url": base_url,
            "tag": tag,
            "vendor_id": vendor_id,
            "prepared_at": datetime.now(UTC).isoformat(),
            "prepared": prepared,
            **client.export(),
        }
        save_state(scenario.id, state)
        return state
    finally:
        client.close()


def _trigger(client: FinBotClient, scenario: Scenario, tag: str) -> tuple[dict[str, Any], bool]:
    """Start the scenario. Returns the API response and whether a workflow must follow."""
    trigger = scenario.trigger
    if scenario.kind == "onboarding":
        vendor = {**scenario.vendor, **(trigger.get("vendor") or {})}
        return _register(client, vendor), True
    if scenario.kind == "invoice":
        return client.create_invoice(invoice_fields(trigger["invoice"], f"INV-{tag}")), True
    return client.chat(trigger["message"]), bool(trigger.get("expect_workflow", False))


def run(scenario: Scenario, timeout: float, base_url: str | None = None,
        trace_dir: str | None = None) -> dict[str, Any]:
    state = load_state(scenario.id)
    if state.get("via") != "api":
        raise RuntimeError(f"State for {scenario.id} was prepared for via={state.get('via')}")
    client = FinBotClient(base_url or state["base_url"], cookies=state["cookies"],
                          csrf_token=state["csrf_token"])
    try:
        before = client.snapshot()
        after = _last_event_id(client)
        started = time.perf_counter()
        response, expect_workflow = _trigger(client, scenario, state["tag"])
        wait = wait_for_workflows(client, after, expect_workflow=expect_workflow, timeout=timeout)
        result = {
            "scenario": scenario.id,
            "via": "api",
            "kind": scenario.kind,
            "trigger": scenario.trigger,
            "started_at": datetime.now(UTC).isoformat(),
            "wall_s": round(time.perf_counter() - started, 2),
            "response": response,
            "error": response.get("error"),
            "timed_out": wait["timed_out"],
            "workflows": wait["workflows"],
            "before": before,
            "after": client.snapshot(),
            "events": wait["events"],
            "traces": read_traces(trace_dir, wait["workflows"]),
        }
        result["path"] = str(save_result(scenario.id, result))
        return result
    finally:
        client.close()
