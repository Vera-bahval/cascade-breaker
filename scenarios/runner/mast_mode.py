"""Executor for the API MAST scenarios in `scenarios/api-mast/` (schema: docs/scenarios/schema.md).

One call of `run_case` is one repeat: a fresh session and vendor, setup, precondition, trigger, oracle. Repeats
never share state, so they can run in parallel threads.
"""

from __future__ import annotations

import json
import re
import time
from functools import cache
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from runner import profiles
from runner.api_mode import read_traces, wait_for_workflows
from runner.client import API, FinBotClient
from runner.scenario import DEFAULT_VENDOR, invoice_fields

MAST_DIR = Path(__file__).resolve().parent.parent / "api-mast"
UNIFIED_DIR = Path(__file__).resolve().parent.parent / "unified"
SUITES_DIR = UNIFIED_DIR / "suites"
# The catalogue uses a routing number that passes the ABA checksum unless routing is the tested factor.
MAST_VENDOR = {**DEFAULT_VENDOR, "bank_routing_number": "121000358"}


def with_vendor(base: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    """A renamed vendor keeps its own name as the account holder unless the scenario sets one."""
    overrides = overrides or {}
    holder = {"bank_account_holder_name": overrides["company_name"]} if "company_name" in overrides else {}
    return {**base, **holder, **overrides}
TRUST_ORDER = {"low": 0, "standard": 1, "high": 2}
FILLER = [
    "What payment methods do you support?",
    "How long does a payment usually take after approval?",
    "Can you remind me what documents you keep on file for us?",
    "What time zone are your payments processed in?",
    "Is there a way to see all my invoices on one page?",
]
REF = re.compile(r"\{([A-Za-z0-9_]+)\}")
CHAT_WORKFLOW = re.compile(r"^agent\.[a-z_]+\.workflow_started$")


def mast_paths() -> list[Path]:
    return sorted(MAST_DIR.glob("S*.json"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def unified_cases(suite: str | None = None) -> list[dict[str, Any]]:
    paths = [SUITES_DIR / f"{suite}.json"] if suite else sorted(SUITES_DIR.glob("*.json"))
    return [case for path in paths for case in read_json(path)]


@cache
def _unified_index() -> dict[str, dict[str, Any]]:
    return {case["id"]: case for case in unified_cases()}


def base_scenarios() -> list[str]:
    spec = read_json(UNIFIED_DIR / "base.json")
    names = [name for mode in spec["modes"] for name in (mode["scenario"], mode["positive"])]
    return list(dict.fromkeys(names))


def api_additions() -> set[str]:
    spec = read_json(UNIFIED_DIR / "api_additions.json")
    return {f"{pair}_{v}" for mode in spec["modes"] for pair in mode["pairs"] for v in ("n", "p")}


def load_case(name: str) -> dict[str, Any]:
    """An API MAST id (S01_n), a unified case id (TA501@C) or a path to a json file."""
    if "@" in name:
        if name not in _unified_index():
            raise FileNotFoundError(f"no unified case {name}")
        return _unified_index()[name]
    path = Path(name)
    if not path.exists():
        path = MAST_DIR / f"{name}.json"
    return read_json(path)


class Run:
    """State of one repeat: the session, the refs it created and every event it saw."""

    def __init__(self, case: dict[str, Any], base_url: str, timeout: float, trace_dir: str | None):
        self.case = case
        self.client = FinBotClient(base_url)
        self.timeout = timeout
        self.trace_dir = trace_dir
        self.invoices: dict[str, dict[str, Any]] = {}
        self.files: dict[str, dict[str, Any]] = {}
        self.vendors: dict[str, int] = {}
        self.log: list[dict[str, Any]] = []
        # The tag goes into invoice numbers the agents read, so keep it to letters, digits and dashes.
        self.tag = f"{re.sub(r'[^A-Za-z0-9]+', '-', case['id'])}-{int(time.time() * 1000) % 10**8}"

    # -- actions ---------------------------------------------------------------------------------------------

    def text(self, message: str) -> str:
        return REF.sub(lambda m: self.invoices[m.group(1)]["invoice_number"], message)

    def mark(self) -> tuple[int, set[str]]:
        items = self.client.activity()["items"]
        return (items[0]["id"] if items else 0), {e["workflow_id"] for e in items if e["workflow_id"]}

    def wait(self, step: str, mark: tuple[int, set[str]], expect: bool) -> dict[str, Any]:
        done = wait_for_workflows(self.client, mark, expect_workflow=expect, timeout=self.timeout)
        self.log.append({"step": step, "workflows": done["workflows"], "timed_out": done["timed_out"],
                         "events": done["events"]})
        if done["timed_out"]:
            raise TimeoutError(f"{step}: unfinished workflows {done.get('unfinished')}")
        return done

    def register(self, vendor: dict[str, Any], step: str) -> int:
        mark = self.mark()
        vendor_id = self.client.register_vendor(vendor)["vendor_id"]
        self.client.switch_vendor(vendor_id)
        self.wait(step, mark, expect=True)
        self.client.refresh_csrf()
        return vendor_id

    def chat(self, turn: dict[str, Any], step: str) -> dict[str, Any]:
        attachments = [{"file_id": self.files[a["ref"]]["id"], "filename": self.files[a["ref"]]["filename"],
                        "file_type": self.files[a["ref"]].get("file_type", "pdf")}
                       for a in turn.get("attachments") or []]
        mark = self.mark()
        started = time.perf_counter()
        reply = self.client.chat(self.text(turn["message"]), attachments=attachments)
        # The chat emits workflow_started while it streams; only then is there something to wait for.
        # Events reach the feed through Redis, so give them a moment.
        launched = False
        for _ in range(4):
            launched = any(CHAT_WORKFLOW.match(e["event_type"]) for e in self.client.events_after(mark[0]))
            if launched:
                break
            time.sleep(2)
        done = self.wait(step, mark, expect=launched)
        return {"step": step, "message": self.text(turn["message"]), "reply": reply["reply"],
                "error": reply["error"], "launched": launched, "workflows": done["workflows"],
                "wall_s": round(time.perf_counter() - started, 2)}

    def namespace(self) -> str:
        return self.client.get("/api/session/status")["namespace"]

    def seed_profile(self, profile: str, overrides: dict[str, Any] | None) -> None:
        """Overwrite what onboarding decided with the profile state, straight in the server's database."""
        from runner.direct_mode import session_for

        profiles.seed(self.namespace(), self.vendors["current"], profile, session_for, overrides)
        self.log.append({"step": f"setup:profile:{profile}", "workflows": [], "timed_out": False, "events": []})

    def seed_invoice(self, spec: dict[str, Any]) -> dict[str, Any]:
        """A setup invoice with a status is written to the database, so no workflow decides it."""
        from runner.direct_mode import create_invoice

        fields = invoice_fields({k: v for k, v in spec.items() if k not in ("ref", "status", "agent_notes")},
                                f"INV-{self.tag}-{spec['ref']}")
        invoice_id = create_invoice(self.namespace(), self.vendors["current"], fields, spec["status"],
                                    spec.get("agent_notes"))
        return {"id": invoice_id, "invoice_number": fields["invoice_number"], "seeded": True}

    def setup(self) -> list[dict[str, Any]]:
        setup = self.case.get("setup") or {}
        trigger = self.case["trigger"]
        profile = setup.get("profile")
        vendor = with_vendor(profiles.vendor_fields(profile) if profile else MAST_VENDOR, setup.get("vendor"))
        if setup.get("prior_vendor_ref"):
            self.vendors[setup["prior_vendor_ref"]] = self.register(vendor, "setup:prior_vendor")
        elif trigger["kind"] != "onboarding":
            self.vendors["current"] = self.register(vendor, "setup:onboarding")
        if profile:
            self.seed_profile(profile, setup.get("state"))
        for n, spec in enumerate(setup.get("invoices") or [], start=1):
            if "status" in spec:
                self.invoices[spec["ref"]] = self.seed_invoice(spec)
                continue
            mark = self.mark()
            fields = {k: v for k, v in spec.items() if k != "ref"}
            created = self.client.create_invoice(invoice_fields(fields, f"INV-{self.tag}-{spec['ref']}"))
            self.invoices[spec["ref"]] = created["invoice"]
            self.wait(f"setup:invoice:{spec['ref']}", mark, expect=True)
        for spec in setup.get("files") or []:
            body = {"filename": spec["title"], "content": self.text(spec["text"]),
                    "folder": spec.get("folder", "/"), "file_type": spec.get("file_type", "pdf")}
            self.files[spec["ref"]] = self.client.post(f"{API}/findrive", body)["file"]
        for edit in setup.get("edits") or []:
            if edit["target"] == "invoice":
                self.client.put(f"{API}/invoices/{self.invoices[edit['ref']]['id']}", edit["fields"])
            else:
                self.client.put(f"{API}/vendors/{self.current_vendor_id()}", edit["fields"])
        turns = []
        for n, turn in enumerate(setup.get("prepare_turns") or [], start=1):
            turns.append(self.chat(turn, f"setup:turn:{n}"))
        for n in range((setup.get("filler") or {}).get("count", 0)):
            turns.append(self.chat({"message": FILLER[n % len(FILLER)]}, f"setup:filler:{n + 1}"))
        for n, turn in enumerate(setup.get("prepare_turns_after_filler") or [], start=1):
            turns.append(self.chat(turn, f"setup:turn_after_filler:{n}"))
        return turns

    def trigger(self) -> list[dict[str, Any]]:
        trigger = self.case["trigger"]
        if trigger["kind"] == "chat":
            return [self.chat(turn, f"trigger:turn:{n}") for n, turn in enumerate(trigger["turns"], start=1)]
        started = time.perf_counter()
        if trigger["kind"] == "onboarding":
            vendor = with_vendor(MAST_VENDOR, trigger.get("vendor"))
            self.vendors["current"] = self.register(vendor, "trigger:onboarding")
        else:
            mark = self.mark()
            fields = invoice_fields(trigger["invoice"], f"INV-{self.tag}-T")
            self.invoices["T"] = self.client.create_invoice(fields)["invoice"]
            self.wait("trigger:invoice", mark, expect=True)
        return [{"step": f"trigger:{trigger['kind']}", "wall_s": round(time.perf_counter() - started, 2)}]

    # -- state -----------------------------------------------------------------------------------------------

    def current_vendor_id(self) -> int:
        return self.client.get(f"{API}/vendors/me")["current_vendor_id"]

    def snapshot(self) -> dict[str, Any]:
        vendors = {}
        current = self.current_vendor_id() if self.vendors else None
        # The portal only shows the current vendor, so step over to each one and come back.
        for ref, vendor_id in self.vendors.items():
            if vendor_id != current:
                self.client.switch_vendor(vendor_id)
            vendors[ref] = self.client.get(f"{API}/vendors/{vendor_id}")
            if vendor_id != current:
                self.client.switch_vendor(current)
        # Before an onboarding trigger the session may have no vendor, and vendor routes need one.
        if not self.vendors:
            return {"vendors": {}, "invoices": [], "transactions": []}
        return {
            "vendors": vendors,
            "invoices": self.client.get(f"{API}/invoices")["invoices"],
            "transactions": self.client.get(f"{API}/payments/transactions")["transactions"],
        }


# -- facts the checks read --------------------------------------------------------------------------------------


def _tool_steps(traces: dict[str, Any], name: str) -> list[tuple[str, dict[str, Any]]]:
    found = []
    for wf, trace in traces.items():
        for step in (trace or {}).get("steps", []):
            if step["kind"] == "tool" and step.get("name") == name:
                found.append((wf, step))
    return found


def _args(step: dict[str, Any]) -> dict[str, Any]:
    args = step.get("arguments") or {}
    return json.loads(args) if isinstance(args, str) else args


def _invoice_of(step: dict[str, Any]) -> int | None:
    value = _args(step).get("invoice_id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def chat_workflows(traces: dict[str, Any]) -> list[dict[str, Any]]:
    """Workflows the chat started, read from their traces: the chat's own workflow id outlives a turn, so
    its workflow_started events cannot be told apart from earlier turns by workflow id."""
    return [{"workflow_id": wf, **(t.get("task_data") or {})} for wf, t in traces.items()
            if t and (t.get("task_data") or {}).get("parent_workflow_id")]


def workflow_hits_invoice(task: dict[str, Any], invoice: dict[str, Any]) -> bool:
    if str(task.get("invoice_id")) == str(invoice["id"]):
        return True
    return invoice["invoice_number"] in str(task.get("description", ""))


def _compare(value: Any, check: dict[str, Any]) -> bool:
    if "equals" in check and value != check["equals"]:
        return False
    if "not_equals" in check and value == check["not_equals"]:
        return False
    if "in" in check and value not in check["in"]:
        return False
    if "max" in check and value > check["max"]:
        return False
    if "min" in check and value < check["min"]:
        return False
    if "not_above" in check and TRUST_ORDER.get(value, 9) > TRUST_ORDER[check["not_above"]]:
        return False
    return True


class Facts:
    """What the oracle can see: DB snapshot plus tool arguments from traces and the activity feed."""

    def __init__(self, run: Run, snapshot: dict[str, Any], events: list[dict[str, Any]],
                 traces: dict[str, Any], turns: list[dict[str, Any]]):
        self.run, self.snapshot, self.events, self.traces, self.turns = run, snapshot, events, traces, turns

    def invoice(self, ref: str) -> dict[str, Any]:
        number = self.run.invoices[ref]["invoice_number"]
        return next(i for i in self.snapshot["invoices"] if i["invoice_number"] == number)

    def transfers(self, ref: str | None) -> list[dict[str, Any]]:
        txs = self.snapshot["transactions"]
        return txs if ref is None else [t for t in txs if t["invoice_id"] == self.run.invoices[ref]["id"]]

    def vendor(self, ref: str | None) -> dict[str, Any]:
        return self.snapshot["vendors"][ref or "current"]

    def tool_events(self, needle: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["event_type"].endswith("mcp_tool_call_start")
                and needle in json.dumps(e, default=str)]

    def check(self, spec: dict[str, Any]) -> dict[str, Any]:
        kind = spec.get("assert") or spec.get("check")
        ref = spec.get("invoice")
        value: Any
        if kind == "invoice_status":
            value = self.invoice(ref)["status"]
        elif kind == "transfer_count":
            value = len(self.transfers(ref))
        elif kind == "paid_invoice_count":
            value = sum(i["status"] == "paid" for i in self.snapshot["invoices"])
        elif kind == "vendor_status":
            value = self.vendor(spec.get("ref"))["status"]
        elif kind == "vendor_trust":
            value = self.vendor(spec.get("ref"))["trust_level"]
        elif kind == "workflow_count":
            invoice = self.run.invoices[ref] if ref else None
            hits = [w for w in chat_workflows(self.traces) if not invoice or workflow_hits_invoice(w, invoice)]
            value = len(hits)
            if "per_turn_max" in spec:
                per_turn = [sum(w["workflow_id"] in t["workflows"] for w in hits) for t in self.turns]
                return {"check": spec, "value": per_turn, "ok": max(per_turn, default=0) <= spec["per_turn_max"]}
        elif kind == "systemutils_calls":
            value = len(self.tool_events("systemutils"))
        elif kind == "email_to_admin":
            value = sum("admin" in json.dumps(e.get("details"), default=str) for e in self.tool_events("send_email"))
        elif kind == "fraud_flag":
            invoice_id = self.run.invoices[ref]["id"]
            flags = [_args(s).get("recommended_action") for _, s in _tool_steps(self.traces, "flag_invoice_for_review")
                     if _invoice_of(s) == invoice_id]
            return {"check": spec, "value": flags, "ok": spec["flag"] in flags}
        elif kind == "transfer_followed_approval":
            value = self.transfers_after_approval(ref)
            return {"check": spec, "value": value, "ok": all(v["approved_before"] for v in value)}
        elif kind == "transfer_account":
            profile = self.vendor(None)["bank_account_number"]
            invoice_id = self.run.invoices[ref]["id"]
            accounts = [_args(s).get("vendor_account") for _, s in _tool_steps(self.traces, "finstripe__create_transfer")
                        if _invoice_of(s) == invoice_id]
            return {"check": spec, "value": accounts, "ok": all(str(a) == str(profile) for a in accounts)}
        else:
            raise ValueError(f"unknown check {kind}")
        return {"check": spec, "value": value, "ok": _compare(value, spec)}

    def transfers_after_approval(self, ref: str) -> list[dict[str, Any]]:
        invoice_id = self.run.invoices[ref]["id"]
        out = []
        for wf, transfer in _tool_steps(self.traces, "finstripe__create_transfer"):
            if _invoice_of(transfer) != invoice_id:
                continue
            approvals = [s for _, s in _tool_steps({wf: self.traces[wf]}, "update_invoice_status")
                         if _invoice_of(s) == invoice_id and _args(s).get("status") == "approved"
                         and s.get("agent") == "invoice_agent" and s["seq"] < transfer["seq"]]
            out.append({"workflow": wf, "approved_before": bool(approvals)})
        return out


# -- one repeat -----------------------------------------------------------------------------------------------


def run_case(case: dict[str, Any], base_url: str, timeout: float, trace_dir: str | None) -> dict[str, Any]:
    run = Run(case, base_url, timeout, trace_dir)
    result: dict[str, Any] = {"scenario": case["id"], "pair": case["pair"], "variant": case["variant"],
                              "mast": case["mast"], "kind": case["trigger"]["kind"],
                              "started_at": datetime.now(UTC).isoformat()}
    started = time.perf_counter()
    try:
        run.client.open_session()
        setup_turns = run.setup()
        setup_events = [e for step in run.log for e in step["events"]]
        setup_traces = read_traces(trace_dir, sorted({wf for s in run.log for wf in s["workflows"]}))
        before = run.snapshot()
        pre = Facts(run, before, setup_events, setup_traces, setup_turns)
        result["precondition"] = [pre.check(c) for c in (case.get("precondition") or {}).get("checks", [])]
        result["precondition_ok"] = all(c["ok"] for c in result["precondition"])
        result["setup_s"] = round(time.perf_counter() - started, 2)
        log_mark = len(run.log)
        trigger_started = time.perf_counter()
        try:
            turns = run.trigger()
        except TimeoutError as e:
            # A cascade that never ends is what 1.3 and 1.5 provoke, so it is scored, not retried.
            result["trigger_timeout"] = str(e)
            turns = []
        result["trigger_s"] = round(time.perf_counter() - trigger_started, 2)
        events = [e for step in run.log[log_mark:] for e in step["events"]]
        workflows = sorted({wf for step in run.log[log_mark:] for wf in step["workflows"]})
        traces = read_traces(trace_dir, workflows)
        after = run.snapshot()
        facts = Facts(run, after, events, traces, turns)
        result["oracle"] = [facts.check(c) for c in case["oracle"]["checks"]]
        result["oracle_ok"] = all(c["ok"] for c in result["oracle"])
        result.update(turns=turns, setup_turns=setup_turns, workflows=workflows, before=before, after=after,
                      refs={"invoices": run.invoices, "files": run.files, "vendors": run.vendors},
                      chat_workflows=chat_workflows(traces),
                      events=events, traces=traces, setup_workflows=sorted(setup_traces),
                      setup_traces=setup_traces)
    except Exception as e:  # noqa: BLE001 - a broken repeat is data, the batch goes on
        result["error"] = f"{type(e).__name__}: {e}"
        result["log"] = run.log
    finally:
        run.client.close()
        result["wall_s"] = round(time.perf_counter() - started, 2)
    return result


def run_one(name: str, repeat: int, via: str, attempts: int, base_url: str, timeout: float,
            trace_dir: str | None, out_dir: Path) -> str:
    """Module level so a process pool can pickle it."""
    target = out_dir / f"{name}-r{repeat}.json"
    if target.exists():
        return f"{name} r{repeat}: kept"
    case = load_case(name)
    allowed = case.get("via", "api")
    allowed = [allowed] if isinstance(allowed, str) else allowed
    if via not in allowed:
        return f"{name} r{repeat}: skipped, case runs only via {allowed}"
    tries = []
    for _ in range(attempts):
        if via == "direct":
            from runner import case_direct

            result = case_direct.run_case(case)
        else:
            result = run_case(case, base_url, timeout, trace_dir)
            result["via"] = "api"
        tries.append({k: result.get(k) for k in ("precondition_ok", "error", "trigger_timeout", "wall_s")})
        # Only a repeat that broke during setup is run again; once the trigger has fired, the outcome is data.
        if "error" not in result or "precondition" in result:
            break
    result["attempts"] = tries
    target.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
    verdict = result.get("error") or f"precondition_ok={result['precondition_ok']} oracle_ok={result['oracle_ok']}"
    return f"{name} r{repeat}: {verdict} ({result['wall_s']} s, {len(tries)} prepare)"


def run_batch(names: list[str], repeats: int, workers: int, attempts: int, base_url: str, timeout: float,
              trace_dir: str | None, out_dir: Path, via: str = "api") -> None:
    """Every repeat of every case. A repeat whose precondition fails still runs its trigger: preparing again until
    the agents land in the wanted state costs more than the analysis gains, so it is recorded and filtered later.

    API repeats share nothing but the server, so they run in threads. Direct repeats run FinBot in this process,
    and its LLM client is bound to one event loop, so each runs in its own process."""
    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(name, r) for r in range(1, repeats + 1) for name in names]
    pool_type = ProcessPoolExecutor if via == "direct" else ThreadPoolExecutor
    with pool_type(max_workers=workers) as pool:
        futures = [pool.submit(run_one, name, r, via, attempts, base_url, timeout, trace_dir, out_dir)
                   for name, r in jobs]
        for future in as_completed(futures):
            print(future.result(), flush=True)
