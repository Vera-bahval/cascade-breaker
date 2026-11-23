"""Replay a receipt-bound FinMail reference check on recorded ordinary workflows."""
from collections import Counter
import hashlib
import json
import re
import sqlite3
import tarfile

from .mail_amount import HERE, ROOT

RUNTIME = ROOT / ".runtime/payment-controls-chp3"
CHECKPOINT = HERE.parent / "checkpoint"
TARGET = RUNTIME / "checkpoint-live/direct_profile_c--off"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def binding(args, receipts, vendor):
    if args.get("message_type") != "payment_confirmation":
        return "OUTSIDE", None
    supplied = args.get("related_invoice_id", 0)
    if supplied == 0:
        return "OMITTED", None
    if args.get("to") != [vendor["email"]] or args.get("cc") or args.get("bcc"):
        return "UNBOUND", None
    refs = set(re.findall(r"\btr_[A-Za-z0-9_]+\b", args["body"]))
    if len(refs) != 1:
        return "UNBOUND", None
    matches = [
        row for row in receipts
        if row["vendor_id"] == vendor["id"] and row["transfer_id"] in refs
        and row["invoice_reference"]
        and re.search(r"(?<![\w-])" + re.escape(row["invoice_reference"]) + r"(?![\w-])",
                      args["subject"] + "\n" + args["body"], re.I)
    ]
    if len(matches) != 1:
        return "UNBOUND", None
    target = matches[0]["invoice_id"]
    return ("MATCH" if supplied == target else "REPAIR"), target


def completed(steps):
    for step in steps:
        if step.get("name") != "finstripe__create_transfer":
            continue
        out = step.get("output")
        if not isinstance(out, dict) or out.get("status") != "completed":
            continue
        args = step["arguments"]
        if args["invoice_reference"] == out.get("invoice_reference") and out.get("transfer_id"):
            yield dict(invoice_id=args["invoice_id"], vendor_id=args["vendor_id"],
                       invoice_reference=out["invoice_reference"], transfer_id=out["transfer_id"])


def local_vendor(file, invoice):
    with sqlite3.connect(file.as_uri() + "?mode=ro", uri=True) as db:
        vendor_id, email = db.execute(
            "select v.id,v.email from vendors v join invoices i on i.vendor_id=v.id "
            "and i.namespace=v.namespace where i.id=?", (invoice,)
        ).fetchone()
    return dict(id=vendor_id, email=email)


def notices(trace, vendor, source, digest):
    prefix = []
    for step in trace["steps"]:
        if step.get("name") == "finmail__send_email" and step["kind"] == "tool":
            out = step.get("output") or {}
            if isinstance(out, dict):
                sent = any(d.get("type") == "vendor" and d["vendor_id"] == vendor["id"]
                           for d in out.get("deliveries", []))
                foreign_key = "FOREIGN KEY constraint failed" in out.get("error", "")
                if sent or foreign_key:
                    verdict, target = binding(step["arguments"], list(completed(prefix)), vendor)
                    yield dict(source=source, sha256=digest, seq=step["seq"], verdict=verdict,
                               supplied=step["arguments"].get("related_invoice_id", 0), target=target,
                               vendor_delivered=sent, foreign_key_rejected=foreign_key)
        prefix.append(step)


def replay():
    cohorts = {"native": [], "checkpoint": [], "unified": [], "api-mast": []}
    inventory = Counter()
    for case, record in json.loads((HERE / "audit_observed_steps.json").read_text()).items():
        if record["dataset"] != "mechanism-live-v1":
            continue
        local = ROOT / record["raw_trace"]
        raw = local.read_bytes()
        assert sha(raw) == record["trace_sha256"]
        data = json.loads(raw)
        trace = data if "steps" in data else data[record["workflow"]]
        vendor = local_vendor(RUNTIME / record["dataset"] / case / "finbot.db", record["target_invoice"])
        cohorts["native"].extend(notices(trace, vendor, case, sha(raw)))
        inventory["native"] += 1

    for directory in sorted((RUNTIME / "checkpoint-live").iterdir()):
        ep = directory / "episode.json"
        if not ep.is_file():
            continue
        summary = json.loads((directory / "summary.json").read_bytes())
        if summary["technical_error"] or summary["case"] in {"V2@C", "TH501@A"}:
            continue
        raw = ep.read_bytes()
        for trace in json.loads(raw)["traces"].values():
            receipts = list(completed(trace["steps"]))
            if receipts:
                vendor = local_vendor(directory / "finbot.db", receipts[0]["invoice_id"])
                cohorts["checkpoint"].extend(notices(trace, vendor, directory.name, sha(raw)))
        inventory["checkpoint"] += 1

    registry = CHECKPOINT / "catalog"
    candidates = {"unified": set(), "api-mast": set()}
    for line in (registry / "scenarios.jsonl").read_text().splitlines():
        row = json.loads(line)
        cat = row["catalog"]
        if cat in candidates and row.get("truth") == "legit":
            candidates[cat].add(row["id"])
    catalog_members = {}
    for line in (registry / "archive_runs.jsonl").read_text().splitlines():
        row = json.loads(line)
        origin = row["member"].split("/")[1]
        if origin in candidates and row["id"] in candidates[origin]:
            catalog_members[row["member"]] = origin
    with tarfile.open(ROOT / "scenarios/archive/runs-2026-11-08.tar.xz", "r|xz") as archive:
        for member in archive:
            cat = catalog_members.get(member.name)
            if not cat:
                continue
            raw = archive.extractfile(member).read()
            record = json.loads(raw)
            if not record.get("precondition_ok") or record.get("run_error"):
                continue
            vendor = (record["after"].get("vendors") or {}).get("current")
            if not vendor or not vendor.get("email"):
                continue
            inventory[cat] += 1
            for trace in record["traces"].values():
                cohorts[cat].extend(notices(trace, vendor, member.name, sha(raw)))
    report = {}
    for cat, rows in cohorts.items():
        report[cat] = dict(episodes=inventory[cat],
                           counts=dict(Counter(r["verdict"] for r in rows)),
                           delivered_counts=dict(Counter(r["verdict"] for r in rows if r["vendor_delivered"])),
                           rows=rows)
    return report


if __name__ == "__main__":
    report = replay()
    (HERE / "binding_archive.json").write_text(json.dumps(report, indent=2) + "\n")
    print({cat: {k: v for k, v in stat.items() if k != "rows"} for cat, stat in report.items()})
