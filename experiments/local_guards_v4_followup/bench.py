"""Offline native benchmark of twelve frozen masks and an inactive guard.

Run with the existing .venv-finbot Python. No provider/model API is used.
The common collector remains enabled for each guarded method; its overcollection
is reported explicitly rather than subtracted from an end-to-end percentile.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import socket
import subprocess
import sys
import tempfile
from time import perf_counter, sleep

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from experiments.local_guards_v4_followup import evaluate as ev


def stats(values):
    values = sorted(values)
    return dict(n=len(values), p50_ms=values[(len(values)-1)//2] if values else None,
        p95_ms=values[math.ceil(.95*len(values))-1] if values else None,
        mean_ms=sum(values)/len(values) if values else None)


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


@contextmanager
def offline():
    from unittest.mock import patch
    original = socket.socket.connect
    def no_external(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("external networking forbidden")
        return original(sock, address)
    with patch.object(socket.socket, "connect", no_external), patch.object(
            socket, "create_connection", side_effect=AssertionError("external networking forbidden")):
        yield


def native_trial(name, diagnostics=False, *, negative=False, repeat=0):
    """The existing tiny scripted native workflow, real in-process FinStripe."""
    import asyncio
    from unittest.mock import patch
    from experiments.local_guards_v4.tests.test_runtime import (
        NativeRuntimeTests, ScriptClient, tool, done, run_orchestrator_agent,
        db_session, PaymentTransaction, Invoice)
    from experiments.local_guards_v4_followup.runtime import Runtime
    import experiments.local_guards_v4_followup.runtime as runtime_module
    from experiments.local_guards_v4.store import EvidenceStore
    from finbot.probe import v4

    config = next((c for c in ev.configurations() if c["name"] == name), None)
    if config is None and name != "off":
        raise ValueError("unknown benchmark method")
    candidate = ev.Candidate(config) if config else None
    case = NativeRuntimeTests("test_safe_full_native_workflow")
    case.setUp()
    try:
        fixture = dict(invoice_currency="USD", binding_hold=negative)
        requested_profile = "B" if config and any(r in ev.B for r in config["requirements"]) else "A"
        policy = dict(profile=requested_profile, enabled_requirements=config["requirements"] if config else [])
        checks, intercepted, proposed, store_spans = [], [], [], []
        last_context = {}
        def observer(obj, result, timings):
            last_context.clear()
            last_context.update(obj["context"])
            selected = bool(candidate and ev.is_eligible({"observation":obj}, config))
            checks.append(dict(checkpoint=obj["checkpoint"], tool=obj["proposal"].get("tool"),
                decision=result.get("decision"), checked=selected, **timings))
        case.runtime = Runtime(case.path, requested_profile, fixture_contract=fixture,
            diagnostics=diagnostics, check_observer=observer, policy=policy)
        def bookkeeping():
            with db_session() as db:
                reference = db.query(PaymentTransaction).one().transfer_id
            return [tool("process_payment", invoice_id=3, payment_method="bank_transfer", payment_reference=reference, agent_notes="paid")]
        case.script({"orchestrator_agent":[
                [tool("delegate_to_fraud", vendor_id=2, task_description="review")],
                [tool("delegate_to_invoice", invoice_id=3, task_description="review")],
                [tool("delegate_to_payments", invoice_id=3, task_description="pay")], [done()]],
            "fraud_agent":[[tool("get_invoice_details", invoice_id=3), tool("get_vendor_risk_profile", vendor_id=2)], [done()]],
            "invoice_agent":[[tool("update_invoice_status", invoice_id=3, status="approved", agent_notes="reviewed")], [done()]],
            "payments_agent":[[tool("finstripe__create_transfer", vendor_account="account", amount=100., invoice_reference="fixture", vendor_id=2, invoice_id=3)], bookkeeping, [done()]]}, mcp=True)
        original_invoke, original_chat = Runtime.invoke, ScriptClient.chat
        original_connection = EvidenceStore._connection
        async def counted_invoke(runtime, agent, tool_name, args, execute):
            intercepted.append(tool_name)
            return await original_invoke(runtime, agent, tool_name, args, execute)
        async def counted_chat(client, request):
            response = await original_chat(client, request)
            proposed.extend(c["name"] for c in response.tool_calls)
            return response
        @contextmanager
        def measured_connection(store, write=False):
            started = perf_counter()
            try:
                with original_connection(store, write=write) as connection:
                    yield connection
            finally:
                store_spans.append(dict(write=write, elapsed_ms=(perf_counter()-started)*1000))
        def selected_guard(obj, _policy):
            result = candidate({"observation":obj})
            return {**result, "evidence":result.get("evidence", [])}
        started = perf_counter()
        status, stopped = "completed", None
        with patch.object(Runtime, "invoke", counted_invoke), patch.object(ScriptClient, "chat", counted_chat), \
             patch.object(EvidenceStore, "_connection", measured_connection), \
             patch.object(runtime_module, "guard", selected_guard) if candidate else nullcontext():
            try:
                with case.runtime.open() if candidate else nullcontext():
                    result = asyncio.run(run_orchestrator_agent(case.task, case.session))
                    if result["task_status"] != "success":
                        raise AssertionError((name, result))
            except v4.V4Stop as exc:
                status, stopped = "stopped", exc.decision
        elapsed = (perf_counter()-started)*1000
        with db_session() as db:
            payments, invoice_status = db.query(PaymentTransaction).count(), db.get(Invoice, 3).status
        if status == "completed" and (payments != 1 or invoice_status != "paid"):
            raise AssertionError((name, payments, invoice_status))
        if status == "stopped" and payments != 0:
            raise AssertionError((name, "stopped after payment", payments))
        if not diagnostics and case.runtime.diagnostic_records:
            raise AssertionError("diagnostic snapshots retained when disabled")
        claim = case.runtime.store.claim(case.runtime.owner)
        state = dict(claim_state=claim["state"] if claim else None,
            invoice_version=last_context.get("invoice_version"), vendor_version=last_context.get("vendor_version"),
            approval_present=bool(last_context and case.runtime.store.approval(last_context)),
            stopped=bool(case.runtime.store.stopped(case.runtime.owner)),
            subject_events=dict(Counter(e["kind"] for e in case.runtime.store.events(case.runtime.subject_key(3, 2)))) if candidate else {},
            owner_events=dict(Counter(e["kind"] for e in case.runtime.store.events(case.runtime.owner))))
        return dict(method=name, repeat=repeat, diagnostics=diagnostics, negative=negative,
            elapsed_ms=elapsed, status=status, stop=stopped, payments=payments, invoice_status=invoice_status,
            model_stub_calls=len(case.calls), proposed_tool_calls=len(proposed), proposed_tools=proposed,
            intercepted_tool_invocations=len(intercepted), intercepted_tools=intercepted,
            checks=checks, diagnostic_records=len(case.runtime.diagnostic_records),
            necessary_store_state=state,
            necessary_collector_ms=sum(c["snapshot_ms"] for c in checks),
            guard_decision_ms=sum(c["decision_ms"] for c in checks),
            diagnostics_ms=sum(c["diagnostics_ms"] for c in checks),
            whole_checks_ms=sum(c["whole_check_ms"] for c in checks),
            unselected_checkpoint_collector_ms=sum(c["snapshot_ms"] for c in checks if not c["checked"]),
            unselected_checkpoint_checks=sum(not c["checked"] for c in checks),
            store_spans=store_spans, store_ms=sum(s["elapsed_ms"] for s in store_spans),
            store_timing_scope="all necessary sidecar connections inside native request; overlaps collector, never subtracted")
    finally:
        case.stack.close()
        case.directory.cleanup()


def _semantic_signature(row):
    return dict(status=row["status"], payments=row["payments"], invoice_status=row["invoice_status"],
        model_stub_calls=row["model_stub_calls"], proposed_tools=row["proposed_tools"],
        intercepted_tools=row["intercepted_tools"],
        necessary_store_state=row["necessary_store_state"],
        decisions=[(c["checkpoint"], c["tool"], c["decision"], c["checked"]) for c in row["checks"]])


def diagnostics_equivalence(names):
    raw = []
    for name in names:
        for negative in (False, True):
            off = native_trial(name, False, negative=negative)
            on = native_trial(name, True, negative=negative)
            if _semantic_signature(off) != _semantic_signature(on):
                raise AssertionError(("diagnostics change decisions/effects", name, negative,
                                      _semantic_signature(off), _semantic_signature(on)))
            raw.append(dict(method=name, negative=negative, equal=True,
                diagnostics_off_signature=_semantic_signature(off), diagnostics_on_signature=_semantic_signature(on)))
    return raw


def native_benchmark(repeats=30, seed=17, names=None, cases=(False, True)):
    names = ["off", *[c["name"] for c in ev.configurations()]] if names is None else names
    rng, raw = random.Random(seed), []
    for repeat in range(repeats):
        order = [(name, diagnostics, negative) for name in names for diagnostics in (False, True) for negative in cases]
        rng.shuffle(order)
        for name, diagnostics, negative in order:
            print("native", repeat, name, "diagnostics=" + str(diagnostics), "negative=" + str(negative), flush=True)
            raw.append(native_trial(name, diagnostics, negative=negative, repeat=repeat))
    summary = []
    for name in names:
        for diagnostics in (False, True):
          for negative in cases:
            rows = [r for r in raw if r["method"] == name and r["diagnostics"] == diagnostics and r["negative"] == negative]
            off = {r["repeat"]:r["elapsed_ms"] for r in raw if r["method"] == "off" and r["diagnostics"] == diagnostics and r["negative"] == negative}
            completed = [r for r in rows if r["status"] == "completed"]
            summary.append(dict(method=name, diagnostics=diagnostics, negative=negative,
                successful_trials=len(completed), stop_trials=len(rows)-len(completed),
                whole_native=stats([r["elapsed_ms"] for r in rows]),
                successful_native=stats([r["elapsed_ms"] for r in completed]),
                stopped_native=stats([r["elapsed_ms"] for r in rows if r["status"] == "stopped"]),
                successful_paired_overhead=stats([r["elapsed_ms"]-off[r["repeat"]] for r in completed if r["repeat"] in off]),
                necessary_collector=stats([r["necessary_collector_ms"] for r in rows]),
                guard_decision=stats([r["guard_decision_ms"] for r in rows]),
                diagnostics_cost=stats([r["diagnostics_ms"] for r in rows]),
                whole_checks=stats([r["whole_checks_ms"] for r in rows]),
                unselected_checkpoint_collector=stats([r["unselected_checkpoint_collector_ms"] for r in rows]),
                sidecar_store_inclusive=stats([r["store_ms"] for r in rows]),
                model_stub_calls=dict(Counter(r["model_stub_calls"] for r in rows)),
                proposed_tool_calls=dict(Counter(r["proposed_tool_calls"] for r in rows)),
                intercepted_tool_invocations=dict(Counter(r["intercepted_tool_invocations"] for r in rows))))
    return dict(seed=seed, repeats_per_case=repeats, cases=["binding_hold" if n else "safe" for n in cases], raw=raw, summary=summary,
        collector_scope="common new runtime collector at all hook checkpoints, even outside each fixed mask; separately measured overcollection",
        percentile_policy="whole-request samples measured directly; no subtraction of component p95 values")


def contention_benchmark(batches=5, hold_ms=50):
    """Real store requests. Rejected responses end immediately, before any barrier."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from experiments.local_guards_v4.store import EvidenceStore, ClaimConflict
    raw = []
    for batch in range(batches):
        for workers in (1, 4, 8):
            for scope in ("different_invoices", "same_invoice", "vendor_wide_overlap"):
                for enabled in (False, True):
                    with tempfile.TemporaryDirectory(prefix="v42-contention-") as td:
                        store = EvidenceStore(Path(td)/"claims.sqlite")
                        if enabled and scope == "vendor_wide_overlap":
                            store.acquire_claim("ns", 2, None, "existing", 1)
                        ready = Barrier(workers)
                        def worker(i):
                            ready.wait()  # Launch coordination is outside request latency.
                            started = perf_counter()
                            invoice = 3 if scope == "same_invoice" else 3+i
                            try:
                                if enabled:
                                    store.acquire_claim("ns", 2, invoice, str(i), 2)
                            except ClaimConflict:
                                elapsed = (perf_counter()-started)*1000
                                return dict(worker=i, outcome="business_rejected", admission_ms=elapsed, response_ms=elapsed)
                            admitted = perf_counter()
                            sleep(hold_ms/1000)
                            if enabled:
                                store.release_claim(str(i), True)
                            return dict(worker=i, outcome="admitted", admission_ms=(admitted-started)*1000,
                                        response_ms=(perf_counter()-started)*1000)
                        started = perf_counter()
                        with ThreadPoolExecutor(max_workers=workers) as pool:
                            attempts = list(pool.map(worker, range(workers)))
                        raw.append(dict(batch=batch, workers=workers, scope=scope, B02_enabled=enabled,
                            batch_ms=(perf_counter()-started)*1000, attempts=attempts))
    summary = []
    for workers in (1, 4, 8):
        for scope in ("different_invoices", "same_invoice", "vendor_wide_overlap"):
            for enabled in (False, True):
                rows = [r for r in raw if (r["workers"], r["scope"], r["B02_enabled"]) == (workers, scope, enabled)]
                attempts = [a for r in rows for a in r["attempts"]]
                admitted = [a for a in attempts if a["outcome"] == "admitted"]
                rejected = [a for a in attempts if a["outcome"] == "business_rejected"]
                summary.append(dict(workers=workers, scope=scope, B02_enabled=enabled, admitted=len(admitted),
                    business_rejected=len(rejected), admission=stats([a["admission_ms"] for a in admitted]),
                    admitted_response=stats([a["response_ms"] for a in admitted]),
                    rejected_response=stats([a["response_ms"] for a in rejected]), batch=stats([r["batch_ms"] for r in rows])))
    return dict(batches=batches, assigned_hold_ms=hold_ms, raw=raw, summary=summary,
        limits="SQLite sidecar admission only; 50ms assigned service hold, no model/DB business-workflow throughput claim")


def cold_start(name, diagnostics):
    started = perf_counter()
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--cold-worker", name,
        *(["--diagnostics"] if diagnostics else [])], capture_output=True, text=True, check=True)
    lines = [line for line in result.stdout.splitlines() if line.startswith("{\"cold_worker\"")]
    if len(lines) != 1:
        raise ValueError("missing unique cold worker result: " + result.stderr[-1000:])
    return dict(**json.loads(lines[0]), parent_wall_ms=(perf_counter()-started)*1000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--native-repeats", type=int, default=30)
    parser.add_argument("--contention-batches", type=int, default=5)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--cold-worker")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="one trial per config/mode, not a final measurement")
    parser.add_argument("--skip-cold", action="store_true")
    parser.add_argument("--positive-only", action="store_true", help="safe fixture only; excludes STOP latency measurements")
    args = parser.parse_args()
    with offline():
        if args.cold_worker:
            started = perf_counter()
            row = native_trial(args.cold_worker, args.diagnostics)
            print(json.dumps(dict(cold_worker=True, method=args.cold_worker, diagnostics=args.diagnostics,
                worker_first_response_ms=(perf_counter()-started)*1000, first_native_response_ms=row["elapsed_ms"],
                process_peak_rss_bytes=peak_rss_bytes(),
                status=row["status"], model_stub_calls=row["model_stub_calls"], payments=row["payments"])))
            return
        if not args.output or not args.manifest:
            parser.error("--manifest and --output required")
        if args.output.exists():
            raise ValueError("benchmark output exists; refusing overwrite")
        ev.verify_manifest(args.manifest)
        names = ["off", *[c["name"] for c in ev.configurations()]]
        # Warm imports/fixtures and verify positive and negative equivalence first.
        equality = diagnostics_equivalence(names)
        cold = [] if args.skip_cold else [cold_start(name, diag) for name in names for diag in (False, True)]
        native = native_benchmark(1 if args.smoke else args.native_repeats, args.seed, names,
            cases=(False,) if args.positive_only else (False, True))
        contention = contention_benchmark(1 if args.smoke else args.contention_batches)
        ev.verify_manifest(args.manifest)
    ev.write_json(args.output, dict(created_at=datetime.now(timezone.utc).isoformat(), phase="smoke" if args.smoke else "frozen_native_measurement",
        python=sys.version, platform=platform.platform(), cpu_count=os.cpu_count(), argv=sys.argv,
        process_peak_rss_bytes=peak_rss_bytes(), rss_units="bytes; Darwin ru_maxrss bytes, Linux ru_maxrss KiB converted",
        benchmark_sha256=ev.digest(Path(__file__)), manifest_sha256=ev.digest(args.manifest),
        base_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        model_api_calls=0, diagnostics_equivalence=equality, cold=cold, native=native, contention=contention))


if __name__ == "__main__":
    main()
