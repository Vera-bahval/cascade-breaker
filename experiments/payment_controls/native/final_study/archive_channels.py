"""Extract ordinary archived stock-channel proposals from verified source members."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import tarfile

from . import archive_prepare as ap

ROOT = ap.early.ROOT
HERE = ap.HERE
INVENTORY = HERE / "inventory.json"
ARCHIVE = ROOT / "scenarios/archive/runs-2026-11-08.tar.xz"
DELEGATIONS = {"delegate_to_invoice", ap.FRAUD, ap.PAY, "delegate_to_communication"}
PROPOSAL_TOOLS = ap.TOOLS | DELEGATIONS


def adapted_trace(trace):
    # A tool in the saved LLM response was proposed at that step. Only a
    # uniquely matching later same-actor tool result establishes appearance at the boundary.
    steps = sorted(trace["steps"], key=lambda step: step["seq"])
    if len({step["seq"] for step in steps}) != len(steps):
        raise ValueError("Non-unique stock source step sequence")
    pending = {}
    events = []
    for step in steps:
        seq = step["seq"] * 1024
        kind = step["kind"]
        actor = step.get("agent")
        workflow = trace.get("workflow_id")
        base = {"workflow_id": workflow, "agent_name": actor}
        if kind == "llm":
            calls = step.get("output", {}).get("tool_calls", []) if isinstance(step.get("output"), dict) else []
            # Same-actor invocation supersedes unexecuted earlier proposals.
            pending[actor] = []
            events.append({**base, "hook_kind": "before_model", "event_seq": seq})
            for ordinal, call in enumerate(calls, 1):
                if ordinal >= 1023:
                    raise ValueError("Too many tool calls in one stock source step")
                if call.get("name") in PROPOSAL_TOOLS:
                    pending[actor].append((call, seq + ordinal))
            events.append({**base, "hook_kind": "after_model", "event_seq": seq + 1023})
        if kind != "tool":
            continue
        tool = step.get("name")
        args = step.get("arguments") or {}
        matches = [(call, call_at) for call, call_at in pending.get(actor, [])
                   if call.get("name") == tool and call.get("arguments") == args]
        if len(matches) == 1:
            call, cut = matches[0]
            pending[actor].remove((call, cut))
            events.append({**base, "hook_kind": "before_tool", "event_seq": cut,
                           "tool_name": tool, "tool_arguments": args})
        obj = {"error": step["error"]} if step.get("error") else step.get("output")
        events.append({**base, "hook_kind": "after_tool", "event_seq": seq,
                       "tool_name": tool, "tool_arguments": args, "tool_result": obj})
    return sorted(events, key=lambda e: e["event_seq"])


def emit(destination, name, rows):
    path = destination / name
    path.write_text("".join(json.dumps(r, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n" for r in rows))


def main(cohort):
    destination = HERE / ("archive_channels" if cohort == "ordinary_150" else "archive_core")
    destination.mkdir(exist_ok=True)
    inventory = json.loads(INVENTORY.read_bytes())
    wanted = {}
    for family, row in inventory[cohort].items():
        for channel, sources in row["historical_channel_runs"].items():
            for source in ([sources] if cohort == "ordinary_150" else sources.values()):
                if source["member"] in wanted:
                    raise ValueError("Same source member assigned more than once")
                wanted[source["member"]] = (family, channel, row["obligation"], source)
    expected = {value[3]["archive_sha256"] for value in wanted.values()}
    archive_sha = ap.sha(ARCHIVE)
    if expected != {archive_sha}:
        raise ValueError("Stock archive differs from inventory")
    packets, mapping, trajectories, run_census = [], [], [], []
    seen = set()
    with tarfile.open(ARCHIVE, "r|xz") as archive:
        for member in archive:
            if member.name not in wanted:
                continue
            family, channel, obligation, source = wanted[member.name]
            raw = archive.extractfile(member).read()
            if member.name in seen or sha256(raw).hexdigest() != source["member_sha256"]:
                raise ValueError("Stock archive member duplicated or changed")
            seen.add(member.name)
            run = json.loads(raw)
            traces = run.get("traces") or {}
            target = (run.get("refs", {}).get("invoices", {}).get("T") or {}).get("id")
            values = list(traces.values()) if isinstance(traces, dict) else traces
            selected = [tr for tr in values if tr.get("task_data", {}).get("invoice_id") == target] if target is not None else []
            source_run = {"group_id": obligation, "source_sha256": archive_sha,
                          "raw_hash": source["member_sha256"], "episode_id": ap.opaque("stock-source-v1", member.name)}
            if len(selected) == 1:
                events = adapted_trace(selected[0])
                # Only a trace bound to the exact invoice from this source run enters the frame.
                ap.add_run(source_run, None, None, member.name, "stock_channel_" + channel,
                           packets, mapping, trajectories, run_census, adapted_events=events)
            else:
                run_census.append({"trajectory_id": None, "episode_id": source_run["episode_id"], "group_id": obligation,
                                   "counts": {}, "frame": "stock_channel_" + channel, "source_member": member.name,
                                   "exclusion_reason": "no_unique_target_invoice_trace"})
    if seen != wanted.keys():
        raise ValueError("Missing stock archive member")
    for row in mapping:
        row["primary"] = row["first_boundary"]
    primary = {r["id"] for r in mapping if r["primary"]}
    active = {r["trajectory_id"] for r in mapping if r["primary"]}
    artifacts = {
        "archive_packets.jsonl": [r for r in packets if r["id"] in primary],
        "archive_trajectory_packets.jsonl": [r for r in trajectories if r["id"] in active],
        "archive_mapping.jsonl": mapping,
        "archive_run_census.jsonl": run_census,
        "archive_extended_packets.jsonl": [r for r in packets if r["id"] not in primary],
        "archive_extended_trajectory_packets.jsonl": [r for r in trajectories if r["id"] not in active],
    }
    for name, rows in artifacts.items():
        emit(destination, name, sorted(rows, key=lambda r: r.get("id", r.get("episode_id", ""))))
    counts = Counter((r["frame"], r["checkpoint"]) for r in mapping if r["primary"])
    manifest = {
        "version": "literal-v3-stock-channels", "cohort": cohort, "verified_archive_sha256": archive_sha,
        "inventory_sha256": ap.sha(INVENTORY), "verified_stock_source_members": len(wanted),
        "primary_count": len(primary), "primary_trajectories": len(active), "mapped_actions": len(packets),
        "projection_note": "Matching saved same-actor model proposal and tool result. A result-only anchor is counted in the census, without a pre-action packet.",
        "primary_per_channel_checkpoint": {"|".join(k): v for k, v in sorted(counts.items())},
        "primary_actual_fraud": dict(Counter(r["checkpoint"] for r in packets if r["id"] in primary and r["actual_fraud"])),
        "no_unique_target_trace": sum(r.get("exclusion_reason") == "no_unique_target_invoice_trace" for r in run_census),
        "source_runs_by_channel": dict(Counter(r["frame"] for r in run_census)),
        "sha256": {name: ap.sha(destination / name) for name in artifacts},
    }
    (destination / "archive_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--cohort", choices=("ordinary_150", "core_35"), default="ordinary_150")
    main(cli.parse_args().cohort)
