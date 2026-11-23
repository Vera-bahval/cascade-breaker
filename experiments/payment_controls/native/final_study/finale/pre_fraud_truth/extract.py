"""Reconstruct the stock first-Fraud boundary using the pre-call prefix only."""
import asyncio
from collections import Counter
import csv
from hashlib import sha256
import json
from pathlib import Path

from ... import live
from ....overnight import route
from ..panel.prefraud import body

HERE = Path(__file__).resolve().parent
OUT = live.PRIVATE.with_name("finale-pre-fraud-truth")
LATEST = live.HERE / "extension/pooled_families.csv"

# Invoice.to_dict stable fields corroborated by the prefix read.
IMMUTABLE = ("amount", "description", "invoice_number", "invoice_date", "due_date", "vendor_id")
PREFIX_TOOLS = {
    "get_vendor_details", "get_invoice_details", "update_invoice_status", "complete_task",
    "delegate_to_invoice", "findrive__list_files", "findrive__search_files",
    "taxcalc__calculate_tax", "taxcalc__validate_tax_id", "taxcalc__get_tax_rates",
}


def digest(data):
    return sha256(data).hexdigest()


def wire(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def reconstruct(episode, config, source_invoice):
    target = episode["refs"]["invoices"].get("T", {}).get("id")
    calls = [(trace, step) for trace in episode["traces"].values() for step in trace["steps"]
             if step.get("kind") == "tool" and step.get("name") == "delegate_to_fraud"]
    if not calls:
        return "no_fraud_boundary", None
    if len(episode["traces"]) != 1:
        return "multiple_workflows", None
    trace, call = calls[0]
    task = trace["task_data"]
    proposal = call.get("arguments") or {}
    vendor = episode["before"]["vendors"]["current"]
    if type(target) is not int or task.get("invoice_id") != target or proposal.get("vendor_id") != vendor["id"]:
        return "unbound", None
    steps = [s for s in trace["steps"] if s.get("kind") == "tool" and s["t_ms"] <= call["t_start_ms"]]
    if any(s["name"] not in PREFIX_TOOLS for s in steps):
        return "unrecognized_prior_tools", None
    records = {row["id"]: row.copy() for row in episode["before"]["invoices"]}
    if target not in records:
        # The new target's insert fields are corroborated by the pre-boundary read.
        terminal = next((i for i in episode["after"]["invoices"] if i["id"] == target), None)
        reads = [s.get("output") or {} for s in steps if s["name"] == "get_invoice_details"
                 and not s.get("error") and s["arguments"].get("invoice_id") == target]
        if (terminal is None or not reads or any(reads[0].get(k) != terminal[k] for k in IMMUTABLE)
                or source_invoice is None or terminal["attachments"]
                or any(terminal[k] != source_invoice.get(k, default)
                       for k, default in (("tax_category", "goods"), ("tax_jurisdiction", ""))
                       if k in source_invoice)):
            return "target_intake_unverified", None
        records[target] = {k: v for k, v in terminal.items() if k not in {"updated_at", "status", "agent_notes"}}
        records[target].update(status=reads[0]["status"], agent_notes=reads[0]["agent_notes"],
                               updated_at=terminal["created_at"])
    for step in steps:
        if step["name"] != "update_invoice_status" or step.get("error"):
            continue
        args = step["arguments"]
        output = step.get("output") or {}
        if output.get("updated") is not True or output.get("status") != args.get("status"):
            return "unverified_status_write", None
        row = records.get(args.get("invoice_id"))
        if row is None:
            return "unknown_invoice_write", None
        row["status"] = args["status"]
        row["agent_notes"] = (row["agent_notes"] or "") + "\n\n" + args["agent_notes"]
        # Trace lacks the persisted timestamp. It is not a routing or rating input.
        row.pop("updated_at", None)
    inv = records[target]
    if inv["vendor_id"] != vendor["id"] or inv["namespace"] != vendor["namespace"]:
        return "unbound_records", None
    transactions = [t for t in episode["before"]["transactions"] if t["invoice_id"] == target]
    if transactions:
        return "receipt_fields_unverified", None
    history = sorted(records.values(), key=lambda row: row["created_at"], reverse=True)
    return "bound", {
        "inv": inv, "vendor": vendor, "profile": {"status": vendor["status"], "risk_level": vendor["risk_level"],
                                                  "total_invoices": len(history)},
        "paid": [r for r in history if r["status"] == "paid"], "transactions": [],
        "config": config, "proposal": proposal,
        "provenance": {"invoice": "get_invoice_details", "vendor": "get_vendor_details",
                       "profile": "get_vendor_risk_profile", "history": "get_vendor_invoices(paid)",
                       "transactions": "workflow_snapshot", "tin": "TaxCalc format only"},
    }


async def main():
    from finbot.agents.specialized.fraud import FraudComplianceAgent
    from finbot.mcp.servers.taxcalc.server import create_taxcalc_server
    from runner.direct_mode import session_for

    config = object.__new__(FraudComplianceAgent)._load_config()
    dev = {row["group_id"].removeprefix("unified:") for row in map(
        json.loads, (live.HERE / "archive_development_gold.jsonl").read_text().splitlines())}
    roster = list(csv.DictReader(LATEST.open()))
    cells = {r["key"]: r for r in live.approved()["cells"]}
    catalogs = {path: {r["id"]: r for r in live.read(live.ROOT / path)}
                for path in {r["source_path"] for r in cells.values()}}
    assert len(roster) == len({r["family"] for r in roster}) == 221
    rows, exclusions = [], {}
    for entry in roster:
        family = entry["family"]
        dest = live.PRIVATE.with_name(entry["tranche"]) / "test" / entry["A_assignment"]
        source = dest / "episode.json"
        if not source.exists():
            exclusions[family] = "no_terminal_episode"
            continue
        raw = source.read_bytes()
        episode = json.loads(raw)
        assert episode["arm"] == "A"
        cell = cells[entry["source_cell"]]
        origin = catalogs[cell["source_path"]][cell["case_id"]]
        assert origin["source"]["truth"] == "legit"
        status, packet = reconstruct(episode, config, origin["trigger"].get("invoice"))
        if packet is None:
            exclusions[family] = status
            continue
        vendor = packet["vendor"]
        session = session_for(vendor["namespace"], vendor["id"])
        tax = await create_taxcalc_server(session).call_tool(
            "validate_tax_id", {"tax_id": vendor["tin"], "country": "US"})
        packet["tin_ok"] = tax.structured_content["format_valid"]
        outcome, reasons, _ = route.evaluate(packet)
        veto = route.mandatory_veto(packet, reasons)
        split = "development" if family in dev or digest(f"finale-pre-fraud-v1/{family}".encode())[0] in "012345" else "heldout"
        blind_id = digest(f"finale-pre-fraud-blind-v1/{family}".encode())[:24]
        rows.append({"id": blind_id, "family": family, "split": split, "source": entry["A_assignment"],
                     "source_sha256": digest(raw), "packet": packet, "d_action": outcome,
                     "reasons": reasons, "mandatory_veto": veto, "blind_packet": body(packet)["state"]})

    unique = {}
    for row in sorted(rows, key=lambda r: (r["split"], r["id"])):
        state = row["blind_packet"]
        signature = digest(wire(state))
        if signature in unique:
            exclusions[row["family"]] = "equivalent_packet:" + unique[signature]["id"]
        else:
            unique[signature] = row
    rows = sorted(unique.values(), key=lambda r: r["id"])
    OUT.mkdir(exist_ok=True, mode=0o700)
    (OUT / "inputs.jsonl").write_bytes(b"".join(wire(r) + b"\n" for r in rows))
    (OUT / "rating_packets.jsonl").write_bytes(b"".join(
        wire({"id": r["id"], "state": r["blind_packet"]}) + b"\n" for r in rows))
    (OUT / "exclusions.json").write_bytes(wire(exclusions) + b"\n")
    print(Counter(e.split(":")[0] for e in exclusions.values()))
    print(Counter((r["split"], r["d_action"], bool(r["mandatory_veto"])) for r in rows))


if __name__ == "__main__":
    asyncio.run(main())
