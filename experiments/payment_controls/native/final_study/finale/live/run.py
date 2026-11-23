"""Freeze and execute new, isolated five-arm FinBot assignments."""
import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import UTC, datetime
import fcntl
from hashlib import sha256
import json
from itertools import permutations
import os
from pathlib import Path
from shutil import disk_usage
from statistics import mean
import sys
from time import monotonic
from unittest.mock import patch

from ... import live, live_meter
from ...extension.dispatch import provider_error
from ...v2 import readback, run as v2
from . import adapter, meter as ledger_factory

PRIVATE = live.PRIVATE.with_name("final-study-payment-finale")
MODULE = __spec__.name
HERE = Path(__file__).resolve().parent
ARMS = "ABCDE"
ELIZA_CAP = 15.0
JEV_CAP = .30
RETRY_MAX = 1
DISK_FLOOR = 3 * 1024 ** 3
SEED = "finbot-finale-2026-11-22"
ORDER = tuple(permutations(ARMS))
PLAN = PRIVATE / "freeze.json"
PREFRAUD = PRIVATE.with_name("finale-pre-fraud-truth")


def stable(*items):
    return sha256(json.dumps([SEED, *items], sort_keys=True).encode()).hexdigest()


def schema_hash(snapshot):
    def normalize(item):
        if isinstance(item, dict):
            return {k: normalize(v) for k, v in item.items()
                    if k not in {"namespace", "created_at", "updated_at", "transfer_id"}}
        if isinstance(item, list):
            return [normalize(v) for v in item]
        return item
    return stable(normalize(snapshot))


def source(cell):
    case, = [r for r in live.read(live.ROOT / cell["source_path"]) if r["id"] == cell["case_id"]]
    if case["source"]["id"] != cell["family"] or case["source"]["truth"] != "legit":
        raise ValueError("Assignment is outside the original benign source frame")
    return case


def jsonl(path):
    with path.open() as stream:
        return [json.loads(line) for line in stream]


def select_repeats(primaries):
    import csv
    gold = live.HERE / "extension/pooled_families.csv"
    old = {}
    with gold.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["source_primary_coordinate"] == "True":
                old[row["source_cell"]] = row
    candidates = [c for c in primaries if c["family"] != "TH614" and c["key"] in old
                  and old[c["key"]]["A_financial"] == "MET" and old[c["key"]]["A_procedural"] == "MET"
                  and old[c["key"]]["A_target_handoff"] == "1" and old[c["key"]]["A_exact_target_transfers"] == "1"]
    rows = {
        "condition_lost": {"family": "TH614", "arms": "BC"},
        "correct_action": {"family": min(candidates, key=lambda c: stable("correct_action", c["family"]))["family"],
                           "arms": "BC"},
    }
    references = jsonl(PREFRAUD / "development_eligible_gold.jsonl")
    eligible_families = {c["family"] for c in primaries}
    for category, action in (("sufficient_fraud_evidence", "CLOSE_ALLOW"),
                             ("independent_fraud_read", "DEFER")):
        candidates = [row for row in references if row["action"] == action and
                      row["family"] in eligible_families and row["split"] == "development"
                      and row["stratum"] == "E_eligible"]
        selected = min(candidates, key=lambda row: stable(category, row["family"]), default=None)
        rows[category] = ({"family": selected["family"], "arms": "DE",
                           "development_gold_id": selected["id"], "pre_fraud_stratum": selected["stratum"]} if selected
                          else {"gap": "no supported original-family reference in development"})
    return rows


def locked_paths(primaries, config_path):
    legacy = live.LEGACY
    return {config_path.resolve(), Path(__file__).resolve(), Path(adapter.__file__).resolve(),
            *(HERE.glob("*.py")), PREFRAUD / "development_eligible_gold.jsonl",
            live.HERE / "extension/pooled_families.csv",
            live.HERE / "v2/payment_families.csv", live.PRIVATE / "main-freeze.json",
            live.HERE.parent / "overnight/route.py", live.HERE.parent / "pre_fraud/native_reads.py",
            live.HERE / "notice_repair/run.py", *live.HERE.glob("live*.py"),
            live.HERE / "jev.py", live.HERE / "archive_prepare.py",
            HERE.parent / "panel/prefraud.py", live.HERE.parent / "expansion/register_panel.py",
            HERE.parent / "panel/bc_factorial_selection.json",
            HERE.parent / "panel/prefraud_selection.json", HERE.parent / "PROTOCOL.md",
            live.HERE / "v2/run.py", live.HERE / "v2/receipt.py",
            *(legacy / name for name in live.PINNED),
            *(live.ROOT / c["source_path"] for c in primaries),
            *(live.ROOT / "finbot/finbot").rglob("*.py"),
            *(live.ROOT / "scenarios/runner").glob("*.py")}


def primary_cells():
    old = live.read(live.PRIVATE / "main-freeze.json")
    return [c for c in old["cells"] if c["primary"]]


def provisional():
    return {"groups": [{"cell": c, "arms": ARMS} for c in
                       sorted(primary_cells(), key=lambda c: stable("primary", c["family"]))],
            "jev_cap_usd": JEV_CAP, "model": {}}


def draft(config_path):
    primaries = primary_cells()
    if len(primaries) != 221 or len({c["family"] for c in primaries}) != 221:
        raise ValueError("Frozen original cohort must contain 221 families")
    for cell in primaries:
        source(cell)
    repeats = select_repeats(primaries)
    old_costs = defaultdict(list)
    history = live.PRIVATE.with_name("final-study-payment-v2-extension-02")
    for path in (history / "test").glob("*/episode.json"):
        result = live.read(path)
        ops = result["operational"]
        if ops["requests"] and not ops["transport_errors"]:
            old_costs[result["cell"]["channel"]].append(ops["eliza_usd"])
    channel_estimate = {channel: mean(costs) for channel, costs in old_costs.items()}
    groups = []
    sort = sorted(primaries, key=lambda c: stable("primary", c["family"]))
    for i, cell in enumerate(sort):
        arms = list(ORDER[i % len(ORDER)])
        groups.append({"cell": {**cell, "kind": "main", "source_cell": cell["key"], "order": arms},
                       "arms": arms, "estimated_usd": 5 * channel_estimate[cell["channel"]]})
    by_fam = {c["family"]: c for c in sort}
    for replicate in range(2, 26):
        for stratum, picked in repeats.items():
            if "family" not in picked:
                continue
            cell = by_fam[picked["family"]]
            arms = list(picked["arms"][::(-1 if replicate % 2 else 1)])
            row = {**cell, "kind": "repeat", "source_cell": cell["key"], "primary": False,
                   "repeat_stratum": stratum, "replicate": replicate,
                   "key": f"{cell['key']}-r{replicate:02d}", "order": arms}
            groups.append({"cell": row, "arms": arms, "estimated_usd": 2 * channel_estimate[cell["channel"]]})
    model = live.read(config_path)
    if not isinstance(model.get("P1"), dict) or model.get("P1") != model.get("P4") or (
        set(model.get("pre_fraud", {})) < {"threshold", "allowed_live_classes"}
    ):
        raise ValueError("Placement arms require the same Jev wire decision policy")
    data = {"groups": groups, "repeats": repeats, "model": model, "eliza_cap_usd": ELIZA_CAP,
            "jev_cap_usd": JEV_CAP, "retry_max": RETRY_MAX, "seed": SEED,
            "estimated_eliza_usd": sum(g["estimated_usd"] for g in groups),
            "channel_estimate_usd": channel_estimate, "frozen_at": datetime.now(UTC).isoformat(),
            "files": {str(p): live.digest(p) for p in sorted(locked_paths(primaries, config_path))}}
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if PLAN.exists():
        raise FileExistsError(PLAN)
    live.write(PLAN, data)
    return data


def approved():
    data = live.read(PLAN)
    release = live.read(PRIVATE / "release.json")
    if release != {"freeze_sha256": live.digest(PLAN), "reviewer": "root", "approved": True}:
        raise ValueError("Exact freeze requires root release")
    for path, digest in data["files"].items():
        if live.digest(path) != digest:
            raise ValueError("Frozen dependency changed: " + path)
    return data


def name_for(cell, arm, attempt=0):
    name = live.episode_id(cell, arm)
    return f"{name}.retry-{attempt}" if attempt else name


def status(folder, cell, arm, attempt):
    name = name_for(cell, arm, attempt)
    logfile = folder / (name + ".log")
    exitfile = folder / (name + ".exit.json")
    terminal = folder / name / "episode.json"
    if not (logfile.exists() or terminal.exists() or exitfile.exists()):
        return "unstarted"
    if not exitfile.exists() or not terminal.exists():
        return "interrupted"
    marker = live.read(exitfile)
    return "terminal" if marker["code"] == 0 else "interrupted"


async def episode(cell, arm, attempt, data, offline):
    folder = PRIVATE / ("offline" if offline else "test")
    dest = folder / name_for(cell, arm, attempt)
    dest.mkdir(mode=0o700, parents=True, exist_ok=False)
    cap = 0 if offline else live.read(PRIVATE / "quota.json")["eliza_cap_usd"]
    case = source(cell)
    os.environ.update(FINBOT_V4_PROFILE="", CASCADE_GUARD_MODE="off")
    with patch.object(live_meter, "live_ledger", ledger_factory.ledger):
        await execute(cell, arm, attempt, data, offline, folder, dest, cap, case)


async def execute(cell, arm, attempt, data, offline, folder, dest, cap, case):
    async with live.session(dest, folder / "executor.sqlite", cap, "offline" if offline else "test",
                            offline=offline) as app:
        started = monotonic()
        with adapter.install(arm, cell, dest, PRIVATE, data["model"], data["jev_cap_usd"]):
            result = (await v2.direct(cell, case, dest, offline)
                      if cell["channel"] == "direct" and not case["setup"].get("invoices")
                      else await live.native(app, cell, case, offline=offline))
        from transport import read_records
        receipts = read_records(dest / "calls.jsonl.gz")
        charges = [r for r in receipts if r["event"] == "accounting"]
        stats = {"requests": len(charges), "eliza_usd": sum(r["eliza_cost_usd"] for r in charges),
                 "transport_errors": sum(r["event"] == "error" for r in receipts)}
        projection = dest / "verifier.json"
        technical = [r["reason"] for r in live.read(projection)
                     if (r.get("reason") or "").startswith("verifier_error:")] if projection.exists() else []
        ev = dest / "pre-fraud-jev.jsonl"
        if ev.exists():
            technical += [r["technical_error"] for r in map(json.loads, ev.read_text().splitlines())
                          if "technical_error" in r]
        live.write(dest / "episode.json", {"cell": cell, "arm": arm, "attempt": attempt, **result,
                   "initial_state_sha256": schema_hash(result["before"]), "operational": stats,
                   "technical_judge_errors": technical, "seconds": monotonic() - started,
                   "completed_at": datetime.now(UTC).isoformat()})
        if not offline and (not charges or stats["transport_errors"] or technical):
            raise RuntimeError("Interrupted independent attempt retained")


def meter(folder):
    return {"eliza": readback.measure(folder / "executor.sqlite"),
            "jev": readback.measure(PRIVATE / "jev/ledger.sqlite")}


def verify_budget():
    _, config = live.quota_cap(ELIZA_CAP)
    remaining = config["remaining"]
    daily = ELIZA_CAP if remaining["daily_usd"] < 0 else remaining["daily_usd"]
    current = meter(PRIVATE / "test")["eliza"]
    cap = min(ELIZA_CAP, current["settled_usd"] + min(daily, remaining["monthly_usd"]))
    if cap <= current["settled_usd"] + current["unresolved_usd"]:
        raise ValueError("No verified Eliza room above settled exposure and open reserves")
    from ...jev import jev_client, registry
    with jev_client() as client:
        model = registry(client)
    if model.get("version", model.get("name")) is None:
        raise ValueError("Could not verify the Jev account and registry")
    live.write(PRIVATE / "quota.json", {"eliza_cap_usd": cap, "remaining": remaining,
        "jev_cap_usd": JEV_CAP, "jev_registry": model})
    return cap


def collect(data):
    folder = PRIVATE / "test"
    rows = []
    for group in data["groups"]:
        cell = group["cell"]
        assign = {}
        for arm in group["arms"]:
            assign[arm] = [status(folder, cell, arm, a) for a in range(RETRY_MAX + 1)]
        rows.append({"key": cell["key"], "family": cell["family"], "kind": cell["kind"],
                     "replicate": cell["replicate"], "attempts": assign,
                     "itt_complete": all(v[0] == "terminal" for v in assign.values()),
                     "technical_complete": all("terminal" in v for v in assign.values())})
    return {"groups": rows, "meter": meter(folder), "summary": {
        kind: {"planned_groups": sum(r["kind"] == kind for r in rows),
               "itt_complete": sum(r["kind"] == kind and r["itt_complete"] for r in rows),
               "technical_complete": sum(r["kind"] == kind and r["technical_complete"] for r in rows),
               "first_attempts": dict(Counter(a[0] for r in rows if r["kind"] == kind for a in r["attempts"].values())),
               "retry_attempts": dict(Counter(a[1] for r in rows if r["kind"] == kind for a in r["attempts"].values()))}
        for kind in ("main", "repeat")}}


async def dispatch(data, cap, workers, pilot=False):
    folder = PRIVATE / "test"
    folder.mkdir(mode=0o700, exist_ok=True)
    held = 0.0
    error_count = 0
    paused = None

    async def attempt(cell, arm, retry):
        nonlocal error_count, paused
        name = name_for(cell, arm, retry)
        with (folder / (name + ".log")).open("xb") as logfile:
            process = await asyncio.create_subprocess_exec(sys.executable, "-m", MODULE, "episode",
                cell["key"], arm, str(retry), cwd=live.ROOT, stdout=logfile, stderr=asyncio.subprocess.STDOUT)
            code = await process.wait()
        error = provider_error(folder / name / "calls.jsonl.gz") if code else None
        live.write(folder / (name + ".exit.json"), {"code": code, "transient_provider_error": error})
        if error:
            error_count += 1
            if error_count >= 5:
                paused = "five transient provider interruptions during dispatch"
        efile = folder / name / "episode.json"
        if code == 0 and efile.exists():
            seen = live.read(efile)["initial_state_sha256"]
            for other in ARMS:
                prior = cell["source_cell"] + "--" + other
                ref = next((p for p in (folder / prior / "episode.json",
                                        folder / (prior + ".retry-1") / "episode.json") if p.exists()), None)
                if ref is not None and live.read(ref)["initial_state_sha256"] != seen:
                    paused = "matched initial business state mismatch"
                    break

    async def wave(groups, arms_per_group):
        nonlocal held, paused
        work = iter(groups)
        capacity = asyncio.Condition()
        budget_exhausted = False

        async def worker():
            nonlocal held, paused, budget_exhausted
            for group in work:
                if paused or budget_exhausted or (folder / "halt.json").exists():
                    return
                if disk_usage(folder).free < DISK_FLOOR:
                    paused = "less than 3 GiB available for evidence"
                    return
                cell = group["cell"]
                todo = arms_per_group(group)
                if not todo:
                    continue
                estimate = data["channel_estimate_usd"][cell["channel"]] * len(todo)
                async with capacity:
                    while not paused and not budget_exhausted:
                        paid = meter(folder)["eliza"]
                        exposure = paid["settled_usd"] + paid["unresolved_usd"]
                        if exposure + held + estimate <= cap:
                            held += estimate
                            break
                        if not held:
                            budget_exhausted = True
                            capacity.notify_all()
                            return
                        await capacity.wait()
                    else:
                        return
                try:
                    for arm, retry in todo:
                        if paused or (folder / "halt.json").exists():
                            return
                        await attempt(cell, arm, retry)
                finally:
                    async with capacity:
                        held -= estimate
                        capacity.notify_all()

        await asyncio.gather(*(worker() for _ in range(workers)))
        if budget_exhausted:
            paused = "insufficient budget for the next matched group estimate"

    main = [g for g in data["groups"] if g["cell"]["kind"] == "main"]
    extra = [g for g in data["groups"] if g["cell"]["kind"] == "repeat"]
    if pilot:
        picks = {row["family"] for row in data["repeats"].values() if "family" in row}
        main = [group for group in main if group["cell"]["family"] in picks]
    first = lambda g: [(arm, 0) for arm in g["arms"] if status(folder, g["cell"], arm, 0) == "unstarted"]
    retry = lambda g: [(arm, 1) for arm in g["arms"] if status(folder, g["cell"], arm, 0) == "interrupted"
                       and status(folder, g["cell"], arm, 1) == "unstarted"]
    await wave(main, first)
    await wave(main, retry)
    if not pilot and not paused and not (folder / "halt.json").exists():
        coverage = collect(data)["summary"]["main"]
        if coverage["technical_complete"] == coverage["planned_groups"]:
            await wave(extra, first)
            await wave(extra, retry)
        else:
            paused = "initial cohort has unrecovered independent attempts; repeats not opened"
    outcome = collect(data)
    outcome["dispatch_paused"] = paused
    outcome["halt_reason"] = (folder / "halt.json").read_text() if (folder / "halt.json").exists() else None
    live.write(PRIVATE / "progress.json", outcome)
    print(json.dumps({k: v for k, v in outcome.items() if k != "groups"}), flush=True)


async def offline_check(data):
    choices = {}
    for group in data["groups"]:
        cell = group["cell"]
        choices.setdefault(cell["channel"], cell)
    with (PRIVATE / "offline.log").open("wb") as output:
        jobs = []
        for cell in choices.values():
            for arm in ARMS:
                path = PRIVATE / "offline" / name_for(cell, arm) / "episode.json"
                if not path.exists():
                    jobs.append(await asyncio.create_subprocess_exec(sys.executable, "-m", MODULE, "offline",
                        cell["key"], arm, cwd=live.ROOT, stdout=output, stderr=asyncio.subprocess.STDOUT))
        codes = await asyncio.gather(*(p.wait() for p in jobs))
    if any(codes):
        raise ValueError("Offline replay preflight failed")
    verify = {}
    for cell in choices.values():
        paths = [PRIVATE / "offline" / name_for(cell, arm) / "episode.json" for arm in ARMS]
        digests = {live.read(path)["initial_state_sha256"] for path in paths}
        if len(digests) != 1 or any(live.read(path)["operational"]["requests"] for path in paths):
            raise ValueError("Five treatments do not share the same initial state")
        verify[cell["channel"]] = {"cell": cell["key"], "initial_state_sha256": digests.pop(),
                                   "episodes": {arm: live.digest(path) for arm, path in zip(ARMS, paths, strict=True)}}
    live.write(PRIVATE / "offline-check.json", {"freeze_sha256": live.digest(PLAN) if PLAN.exists() else None,
               "channels": verify})


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("command", choices=("draft", "check", "quota", "dispatch", "episode", "offline", "progress"))
    cli.add_argument("args", nargs="*")
    cli.add_argument("--workers", type=int, default=20, choices=range(1, 33))
    cli.add_argument("--pilot", action="store_true")
    args = cli.parse_args()
    os.umask(0o077)
    if args.command == "draft":
        plan = draft(Path(args.args[0]))
        print(json.dumps({"freeze_sha256": live.digest(PLAN), **{k: v for k, v in plan.items()
                           if k in {"estimated_eliza_usd", "repeats", "channel_estimate_usd"}}}))
        return
    if args.command in {"check", "offline"} and not PLAN.exists():
        data = provisional()
    else:
        data = live.read(PLAN) if args.command in {"check", "offline", "progress", "quota"} else approved()
    if args.command == "quota":
        print(json.dumps({"cap": verify_budget(), "provider": live.read(PRIVATE / "quota.json")["remaining"]}))
    elif args.command == "progress":
        print(json.dumps({k: v for k, v in collect(data).items() if k != "groups"}))
    elif args.command == "check":
        asyncio.run(offline_check(data))
    elif args.command in {"episode", "offline"}:
        key, arm, *retries = args.args
        retry = int(retries[0]) if retries else 0
        if retry not in range(RETRY_MAX + 1):
            raise ValueError("Retry number outside frozen range")
        group, = [g for g in data["groups"] if g["cell"]["key"] == key and arm in g["arms"]]
        asyncio.run(episode(group["cell"], arm, retry, data, args.command == "offline"))
    else:
        with (PRIVATE / "dispatch.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            approved_check = live.read(PRIVATE / "offline-check.json")
            if approved_check["freeze_sha256"] != live.digest(PLAN) or len(approved_check["channels"]) != 4:
                raise ValueError("Five-way initial-state preflight missing")
            asyncio.run(dispatch(data, verify_budget(), min(args.workers, 4) if args.pilot else args.workers, args.pilot))


if __name__ == "__main__":
    main()
