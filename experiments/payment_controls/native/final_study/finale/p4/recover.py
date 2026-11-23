"""Freeze P4 as-of evidence from authenticated ordinary archive members."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import tarfile

from ... import archive_prepare as ap
from ...archive_p4_sensitivity import ARCHIVE, DST, TAX, adapted_trace, request_scope, scoped_initial
from ...archive_review import HERE, digest, rows, verify_packets, write

OUT = Path(__file__).resolve().parent


def read_native(mapping):
    wanted = defaultdict(list)
    for row in mapping.values():
        wanted[row["episode_id"]].append(row)
    episodes = [r for r in ap.early.read_rows(ap.early.ARCHIVE / "episodes.jsonl.gz")
                if r["episode_id"] in wanted]
    assert {r["episode_id"] for r in episodes} == set(wanted)
    sources = {r["registry_source"]: Path(r["path"]) for r in
               json.loads((ap.early.ARCHIVE / "collector-manifest.json").read_text())["sources"]}
    by_source = defaultdict(list)
    for ep in episodes:
        by_source[ep["source"]].append(ep)
    receipts = {}
    for source, batch in sorted(by_source.items()):
        path = sources[source]
        assert source.endswith(".tar.gz")
        if not path.is_file():
            raw_root = ap.early.ROOT.parent / "finbot-four-model-report"
            artifact_dir = "code/runs" if "/code/runs/" in source else "four-model-comparison/artifacts"
            path = raw_root / "experiments/control-placement" / artifact_dir / path.name
        assert ap.sha(path) == batch[0]["source_sha256"]
        with tarfile.open(path, "r:gz") as archive:
            names = set(archive.getnames())
            for ep in batch:
                for row in wanted[ep["episode_id"]]:
                    assert row["source_sha256"] == ep["source_sha256"]
                    member = row["member"]
                    assert member in names and member.endswith("hooks.jsonl")
                    prefix = member.removesuffix("hooks.jsonl")
                    raw = archive.extractfile(member).read()
                    hook_rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
                    assert ap.early.digest(hook_rows) == row["journal_sha256"] == ep["raw_hash"]
                    cutoff = row["source_seq"] // 2 - 1
                    assert hook_rows[cutoff]["hook_kind"] == "before_tool"
                    transfer_evidence = Counter(
                        event["tool_name"]
                        for event in hook_rows[:cutoff]
                        if event["hook_kind"] == "after_tool" and event.get("tool_name")
                        and any(token in event["tool_name"]
                                for token in ("transfer", "transaction", "payment_history", "list_payments"))
                    )
                    sidecars = sorted(n.removeprefix(prefix) for n in names
                                      if n.startswith(prefix) and n != member)
                    receipts[row["id"]] = {
                        "as_of_history": "no_authenticated_pre_action_transaction_snapshot",
                        "history_visible_in_strict_packet": False,
                        "source_archive": path.name,
                        "native_sidecar_types": sidecars,
                        "native_pre_action_transfer_tools": dict(transfer_evidence),
                    }
    return receipts


def stock_sources(mapping, stock_packets, old_packets):
    by_member = {r["member"]: r for r in mapping.values()}
    missing = {}
    definitions = {}
    recovered = {}
    archive_hash = ap.sha(ARCHIVE)
    assert {r["source_sha256"] for r in mapping.values()} == {archive_hash}
    with tarfile.open(ARCHIVE, "r|xz") as archive:
        for member in archive:
            record = by_member.get(member.name)
            if record is None:
                continue
            raw = archive.extractfile(member).read()
            assert sha256(raw).hexdigest() == record["journal_sha256"]
            run = json.loads(raw)
            traces = run["traces"]
            traces = list(traces.values()) if isinstance(traces, dict) else traces
            for trace in traces:
                for key, tools in (trace.get("tool_defs") or {}).items():
                    actual = sha256(json.dumps(tools, sort_keys=True, default=str).encode()).hexdigest()[:16]
                    if actual == key:
                        if key in definitions:
                            assert definitions[key][0] == tools
                        else:
                            definitions[key] = (tools, record["journal_sha256"])
            if len(traces) != 1:
                continue
            trace = traces[0]
            key = record["id"]
            cut = record["source_seq"]
            prior = scoped_initial(run, trace)
            assert prior is not None
            events = adapted_trace(trace)
            action, = (e for e in events if e["event_seq"] == cut and e["hook_kind"] == "before_tool"
                       and e.get("tool_name") == ap.TRANSFER)
            target = ap.io(action)[0].get("invoice_id")
            assert target == trace["task_data"].get("invoice_id") and target is not None
            prefix = [e for e in events if e["event_seq"] < cut and e.get("tool_name") == ap.TRANSFER]
            # The old sensitivity uses first P4. Demand no earlier execution of this target
            # before calling its pretrigger count a complete as-of count.
            assert not any(ap.io(e)[0].get("invoice_id") == target for e in prefix)
            scope = request_scope(trace, cut)
            if scope is not None:
                assert key in old_packets
                recovered[key] = (old_packets[key], "same_trace_tool_definitions", None)
                continue
            step, = (s for s in trace["steps"] if s["seq"] == cut // 1024)
            missing[key] = (prior, {"steps": [step]}, cut, step["tools_sha"])

    for key, (prior, trace, cut, schema_hash) in missing.items():
        tools, witness = definitions[schema_hash]
        trace["tool_defs"] = {schema_hash: tools}
        scope = request_scope(trace, cut)
        assert scope is not None and scope["taxcalc_available_to_acting_model"]
        packet = stock_packets[key]
        snapshot = {
            "source": "complete_pretrigger_target_vendor_transaction_view",
            "visible_to_executor_prompt": False,
            "target_prior_completed_transfer_count": prior,
            "transaction_view_exhausted": True,
        }
        packet = {**packet, "state": {**packet["state"], "prior_snapshot": snapshot},
                  "request_scope": scope, "additional_evidence_scope":
                  "Alternate guard access to the authenticated pretrigger vendor transaction snapshot; "
                  "the acting request tool names and schema digest are recorded at the source cut."}
        recovered[key] = (packet, "same_archive_matching_tool_definition_digest", witness)
    return recovered


def stage():
    index = rows(HERE / "archive_certified_action_index.jsonl")
    links = rows(HERE / "archive_wave_family_links.jsonl")
    strict = {key: r for key, r in index.items() if (r["scope"], r["checkpoint"], r["label"]) ==
              ("heldout", "P4", "INSUFFICIENT")}
    assert len(strict) == 1261
    old_manifest = json.loads((DST / "manifest.json").read_text())
    assert digest(DST / "packets.jsonl") == old_manifest["packets_sha256"]
    old_receipt = json.loads((DST / "priority_gold_receipt.json").read_text())
    for name, checksum in old_receipt["sha256"].items():
        assert digest(DST / name) == checksum
    old_packets = rows(DST / "packets.jsonl")
    exact = rows(DST / "priority_packets.jsonl")
    assert len(exact) == 48 and all(old_packets[k] == r for k, r in exact.items())
    stock_map, stock_packets = {}, {}
    for name in ("archive_channels", "archive_core"):
        packets, _, mapping = verify_packets(HERE / name)
        stock_map.update({key: r for key, r in mapping.items() if r["checkpoint"] == "P4"})
        stock_packets.update({key: packets[key] for key in mapping if key in stock_map})
    assert len(stock_map) == 846
    recovered = stock_sources(stock_map, stock_packets, old_packets)
    _, _, native_map = verify_packets(HERE)
    native = read_native({key: native_map[key] for key in strict if key not in stock_map})
    ledger = []
    for key, row in sorted(strict.items()):
        mapping = stock_map[key] if key in stock_map else native_map[key]
        evidence = native.get(key)
        if key in recovered:
            packet, method, witness = recovered[key]
            evidence = {
                "as_of_history": "complete_scoped_pretrigger_view_with_no_earlier_target_transfer",
                "history_visible_in_strict_packet": False,
                "prior_completed_target_count": packet["state"]["prior_snapshot"]["target_prior_completed_transfer_count"],
                "request_scope_origin": method,
                "request_scope_witness_journal_sha256": witness,
            }
        assert evidence is not None
        ledger.append({
            "id": key, "group_id": links[key]["obligation_group"], "wave": row["wave"],
            "source_seq": mapping["source_seq"], "journal_sha256": mapping["journal_sha256"],
            "source_sha256": mapping["source_sha256"], "strict_label": row["label"],
            "strict_reason": row["reason_code"], "exact_prior_reuse": key in exact, **evidence,
        })
    direct = {k: recovered[k][0] for k in strict if k in old_packets and k not in exact}
    linked = {k: recovered[k][0] for k in strict if k in recovered and k not in old_packets}
    dev = {k: packet for k, (packet, _, _) in recovered.items() if links[k]["dev_family"]}
    groups = defaultdict(lambda: defaultdict(list))
    for key, packet in dev.items():
        has_tax = any(r["status"] == "success" for r in packet["state"]["records"]["tax_verifications"])
        groups[links[key]["obligation_group"]][has_tax].append(key)
    order = lambda value: sha256(f"finale-p4-dev/{value}".encode()).hexdigest()
    paired = sorted((group for group, strata in groups.items() if len(strata) == 2), key=order)
    # Cap the review here to the existing dev families with an observed tax contrast.
    dev_ids = {min(keys, key=order) for group in paired[:6] for keys in groups[group].values()}
    for filename, values in (
        ("source_recovery.jsonl", ledger),
        ("blind_stock_preliminary.jsonl", [direct[k] for k in sorted(direct)]),
        ("blind_stock_linked.jsonl", [linked[k] for k in sorted(linked)]),
        ("blind_dev.jsonl", [dev[k] for k in sorted(dev_ids)]),
    ):
        write(OUT / filename, values)
    print(json.dumps({"strict": len(strict), "exact": len(set(exact) & strict.keys()),
                      "direct": len(direct), "schema_digest_linked": len(linked), "native_unresolved": len(native),
                      "native_sidecar_types": dict(Counter(s for r in native.values() for s in r["native_sidecar_types"])),
                      "dev": len(dev_ids), "dev_paired_families": len(paired)}, sort_keys=True))


if __name__ == "__main__":
    stage()
