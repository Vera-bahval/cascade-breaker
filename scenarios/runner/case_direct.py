"""Unified invoice cases via direct, checked with the same precondition and oracle as via api."""

from __future__ import annotations

import asyncio
import re
import secrets
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from runner import profiles
from runner.direct_mode import (INVOICE_TASK, _ensure_event_bus, _orchestrate, create_invoice, create_vendor,
                                session_for, snapshot)
from runner.scenario import invoice_fields


def _facts_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    return {"vendors": {"current": raw["vendor"]}, "invoices": raw["invoices"], "transactions": raw["transactions"]}


async def _run(case: dict[str, Any]) -> dict[str, Any]:
    from runner.mast_mode import Facts

    if case["trigger"]["kind"] != "invoice" or "profile" not in (case.get("setup") or {}):
        raise ValueError(f"{case['id']}: direct mode runs invoice cases with a vendor profile only")
    redis = await _ensure_event_bus()
    tag = secrets.token_hex(3)
    namespace = f"uni-{re.sub(r'[^A-Za-z0-9]+', '-', case['id'])[:40]}-{tag}"
    profile = case["setup"]["profile"]
    started = time.perf_counter()
    vendor_id = create_vendor(namespace, profiles.vendor_fields(profile), {})
    profiles.seed(namespace, vendor_id, profile, session_for)
    refs = SimpleNamespace(invoices={})
    before = _facts_snapshot(snapshot(namespace, vendor_id))
    pre = Facts(refs, before, [], {}, [])
    precondition = [pre.check(c) for c in (case.get("precondition") or {}).get("checks", [])]
    fields = invoice_fields(case["trigger"]["invoice"], f"INV-{tag}-T")
    invoice_id = create_invoice(namespace, vendor_id, fields)
    refs.invoices["T"] = {"id": invoice_id, "invoice_number": fields["invoice_number"]}
    task_data = {"vendor_id": vendor_id, "invoice_id": invoice_id, "description": INVOICE_TASK}
    setup_s = round(time.perf_counter() - started, 2)
    run = await _orchestrate(namespace, vendor_id, task_data)
    after = _facts_snapshot(snapshot(namespace, vendor_id))
    traces = {run["workflow_id"]: {"steps": run["steps"], "task_data": task_data}}
    facts = Facts(refs, after, [], traces, [])
    oracle = [facts.check(c) for c in case["oracle"]["checks"]]
    return {
        "precondition": precondition, "precondition_ok": all(c["ok"] for c in precondition),
        "oracle": oracle, "oracle_ok": all(c["ok"] for c in oracle),
        "setup_s": setup_s, "trigger_s": run["wall_s"], "namespace": namespace, "redis": redis,
        "workflows": [run["workflow_id"]], "orchestrator_status": run["orchestrator_status"],
        "orchestrator_summary": run["orchestrator_summary"], "run_error": run["error"],
        "before": before, "after": after, "refs": {"invoices": refs.invoices, "vendors": {"current": vendor_id}},
        "traces": traces, "tool_defs": run["tool_defs"],
    }


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"scenario": case["id"], "pair": case["pair"], "variant": case["variant"],
                              "mast": case["mast"], "kind": case["trigger"]["kind"], "via": "direct",
                              "started_at": datetime.now(UTC).isoformat()}
    started = time.perf_counter()
    try:
        result.update(asyncio.run(_run(case)))
        if result["run_error"]:
            # The orchestrator raised; the oracle still read the database, but the run is not a clean repeat.
            result["error"] = result["run_error"]
    except Exception as e:  # noqa: BLE001 - a broken repeat is data, the batch goes on
        result["error"] = f"{type(e).__name__}: {e}"
    result["wall_s"] = round(time.perf_counter() - started, 2)
    return result
