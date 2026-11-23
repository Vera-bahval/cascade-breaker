"""Select archived ordinary invoice notice handoffs with settled SQLite evidence."""
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from ..completion.mail_full import ROOT, load, dump, digest

HERE = Path(__file__).resolve().parent
RUNTIME = ROOT / ".runtime/payment-controls-chp3"
SCHEDULE = {
    "mechanism-live-v1": ("chat-m1-after-fraud-*", "chat-m1-off-*", "chat-m1-rules-*", "portal-m1-off-*", "direct-m1-off-*"),
    "expansion-natural-live": ("*--off",),
    "expansion-paired-run227-v1": ("TH604--off", "TH610--off", "TH606--off", "TH605--recover", "TH617--recover", "TH668--recover"),
    "checkpoint-live": ("TH602*--off", "direct*--off", "invoice_basic--off", "chat_invoice_status--off"),
    "native-confirmation-live": ("*--off",),
    "study-live": ("direct-off-*", "portal-off-*", "chat-off-*"),
}


def hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


def paths(folder):
    for pattern in ("episode.json", "continuation.json", "direct-trace.json", "traces/*.json"):
        yield from sorted(folder.glob(pattern))


def traces(raw):
    if "steps" in raw:
        yield raw
    elif "traces" in raw:
        yield from raw["traces"].values()
    elif all(isinstance(tr, dict) and "steps" in tr for tr in raw.values()):
        yield from raw.values()


def candidates(folder):
    dbfile = folder / "finbot.db"
    if not dbfile.is_file():
        return
    with sqlite3.connect(dbfile.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        for source in paths(folder):
            for trace in traces(load(source)):
                ss = trace["steps"]
                for item in ss:
                    args = item.get("arguments", {})
                    if item.get("name") != "finmail__send_email" or not args or item["kind"] != "tool":
                        continue
                    out = item.get("output")
                    if not isinstance(out, dict) or not out.get("sent"):
                        continue
                    deliveries = [x for x in out["deliveries"] if x.get("type") == "vendor"]
                    if len(deliveries) != 1:
                        continue
                    delivery, = deliveries
                    rows = db.execute(
                        "select e.*, i.status, i.amount, i.invoice_number, i.description "
                        "from emails e join invoices i on i.id=e.related_invoice_id "
                        "where e.vendor_id=? and e.subject=? and e.body=?",
                        (delivery["vendor_id"], args["subject"], args["body"]),
                    ).fetchall()
                    if len(rows) != 1:
                        continue
                    email, = rows
                    iid, vid = email["related_invoice_id"], email["vendor_id"]
                    refs = set(re.findall(r"\btr_[a-zA-Z0-9_]+\b", args["body"]))
                    fresh_by_reference = [s for s in ss if s.get("kind") == "tool" and s.get("name") == "finstripe__create_transfer"
                                          and s["seq"] < item["seq"] and isinstance(s.get("output"), dict)
                                          and s["output"].get("status") == "completed"
                                          and s["output"].get("transfer_id") in refs]
                    original_link = iid
                    if len(fresh_by_reference) == 1:
                        iid = fresh_by_reference[0]["arguments"]["invoice_id"]
                    inv, = db.execute("select * from invoices where id=? and vendor_id=?", (iid, vid)).fetchall()
                    receipt = [dict(r) for r in db.execute(
                        "select transfer_id, invoice_id, vendor_id, namespace, amount, currency, status, payment_method, metadata_json "
                        "from payment_transactions where invoice_id=? and vendor_id=? and status='completed'",
                        (iid, vid),
                    )]
                    calls = [s for s in ss if s["kind"] == "llm" and s.get("agent") == "communication_agent"
                             and any(c.get("arguments") == args for c in (s.get("output") or {}).get("tool_calls", []))]
                    handoffs = [s for s in ss if s.get("name") == "delegate_to_communication"
                                and s["kind"] == "tool" and s["seq"] > item["seq"]
                                and (s.get("arguments") or {}).get("vendor_id") == vid]
                    if len(calls) != 1 or not handoffs:
                        continue
                    proposal, = calls
                    handoff = handoffs[0]
                    user, = [m["content"] for m in proposal["messages"] if m.get("role") == "user"]
                    if not user.startswith("Task Description: ") or "\n        Communication Details:" not in user:
                        continue
                    desc = user.removeprefix("Task Description: ").split("\n        Communication Details:", 1)[0]
                    archived_type = handoff["arguments"]["notification_type"]
                    if f"notification_type: {archived_type}\n" not in user:
                        continue
                    if len(receipt) > 1 or (receipt and inv["status"] != "paid"):
                        continue
                    archived_transfer = [s for s in ss if s["kind"] == "tool" and s.get("name") == "finstripe__create_transfer"
                                         and s["seq"] < item["seq"] and isinstance(s.get("output"), dict)
                                         and receipt and s["output"].get("transfer_id") == receipt[0]["transfer_id"]]
                    if receipt and abs(receipt[0]["amount"] - inv["amount"]) > .000001:
                        continue
                    parental = [s for s in ss if s["kind"] == "llm" and s.get("agent") == "orchestrator_agent"
                                 and s["seq"] < proposal["seq"] and any(c.get("name") == "delegate_to_communication"
                                     and c.get("arguments") == handoff["arguments"]
                                     for c in (s.get("output") or {}).get("tool_calls", []))]
                    if not parental:
                        continue
                    parent = parental[-1]
                    first_communication = next(s for s in ss if s.get("kind") == "llm"
                                               and s.get("agent") == "communication_agent"
                                               and parent["seq"] < s["seq"] <= proposal["seq"])
                    prior = [s for s in ss if s["seq"] < first_communication["seq"]]
                    config = trace.get("task_data") or {}
                    yield dict(
                        trace=str(source.relative_to(ROOT)), trace_sha256=digest(source), db=str(dbfile.relative_to(ROOT)),
                        invoice_id=iid, vendor_id=vid, email_id=email["id"], recipient=delivery["email"],
                        invoice_status=inv["status"], invoice_amount=inv["amount"], invoice_number=inv["invoice_number"],
                        description=inv["description"], namespace=email["namespace"], receipt=receipt,
                        receipt_age="fresh" if archived_transfer else ("historical" if receipt else "absent"),
                        original_link=original_link, parent_call=parent["seq"], comm_first=first_communication["seq"],
                        archive_draft=args, handoff={**handoff["arguments"], "task_description": desc}, task_data=config,
                        seq=dict(draft=proposal["seq"], send=item["seq"], delegation=handoff["seq"]),
                        archive_handoff_to_send_seconds=(item["t_ms"] - next(s["t_ms"] for s in ss if
                            s.get("agent") == "communication_agent" and s["kind"] == "llm")) / 1000,
                        archive_trace_seconds=(ss[-1]["t_ms"]-ss[0]["t_ms"])/1000,
                        archive_prefix_sha256=hash_bytes(json.dumps(prior, sort_keys=True).encode()),
                    )


def inventory():
    for group, patterns in SCHEDULE.items():
        for pattern in patterns:
            for folder in sorted((RUNTIME / group).glob(pattern)):
                yield from candidates(folder)


if __name__ == "__main__":
    for r in inventory():
        state = r["receipt_age"] if r["receipt"] else r["invoice_status"]
        print(r["trace"].split("/")[3], r["invoice_number"], r["invoice_amount"], state, r["handoff"]["notification_type"],
              r["archive_draft"]["message_type"], r["handoff"]["task_description"][:115])


SELECTION = (
    ("P091-archived-tax-error", "chat-m1-after-fraud-673892a8a5163d"),
    ("P091-principal", "chat-m1-off-673892a8a5163d"),
    ("P091-tax-breakdown", "chat-m1-rules-673892a8a5163d"),
    ("H1-link-drift", "H1@E--off"),
    ("H3", "H3@B--off"),
    ("TH604", "TH604--off"),
    ("TH610", "TH610--off"),
    ("TH606", "TH606--off"),
    ("TH602", "TH602@C+chat--off"),
    ("direct-lighting", "direct_invoice--off"),
    ("TH503", "TH503@B--off"),
    ("TH510", "TH510@B--off"),
    ("study-grip", "direct-off-d9146c468e911a-native1"),
    ("study-dolly", "portal-off-e04b3edc417640-native1"),
    ("historical", "direct-m1-off-ea7a51a1f2f040"),
    ("held", "TH605--recover"),
)
CAP = .25


def freeze():
    import shutil
    data = list(inventory())
    dest = RUNTIME / "scale-mail-v1" / "snapshots"
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    arms = {}
    for label, folder in SELECTION:
        hits = [row for row in data if Path(row["db"]).parent.name == folder]
        row = min(hits, key=lambda row: (row["seq"]["send"], row["trace"]))
        snapshot = dest / f"{label}.sqlite"
        assert not snapshot.exists()
        with sqlite3.connect((ROOT / row["db"]).as_uri() + "?mode=ro", uri=True) as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
            target.execute("PRAGMA journal_mode=DELETE")
            prior = [e[0] for e in target.execute("select id from emails where namespace=? order by id", (row["namespace"],))]
            assert row["email_id"] in prior
            target.execute("delete from emails where id=?", (row["email_id"],))
            target.commit()
        row.update(snapshot=str(snapshot.relative_to(ROOT)), snapshot_sha256=digest(snapshot),
                   retained_email_ids=[e for e in prior if e != row["email_id"]], intervention=None)
        arms[label] = row
    for base, replacement in (("TH604", "$1,697.43"), ("TH610", "$216.89")):
        row = dict(arms[base])
        original = f'${row["invoice_amount"]:,.2f}'
        handoff = row["handoff"]
        assert handoff["task_description"].count(original) == 1
        # Controlled change to the upstream handoff, with the native draft authored after the change.
        row.update(handoff={**handoff, "task_description": handoff["task_description"].replace(original, replacement)},
                   intervention={"field": "handoff_amount", "original": original, "supplied": replacement})
        arms[base + "-amount-contrast"] = row
    independent = {(r["invoice_number"], r["invoice_amount"], r["description"]) for r in arms.values() if r["receipt_age"] == "fresh"}
    assert len(independent) == 12
    schedule = [(label, arm) for i, label in enumerate(arms)
                for arm in (("off", "receipt") if i % 2 == 0 else ("receipt", "off"))]
    design = dict(caps=dict(eliza_usd=CAP, jev_usd=0), snapshot_kind="Archived final SQLite state minus the identified notice",
                  schedule=schedule, cases=arms)
    dump(HERE / "mail_freeze.json", design)
    blind = {}
    id_index = {}
    for label, row in arms.items():
        if row["intervention"]:
            continue
        hid = hash_bytes(("scale-mail-archive-1:" + label).encode())[:10]
        id_index[hid] = label
        blind[hid] = dict(invoice={k: row[k] for k in ("invoice_number", "invoice_amount", "invoice_status", "invoice_id", "vendor_id", "recipient")},
                          receipt_age=row["receipt_age"], receipts=row["receipt"],
                          handoff=row["handoff"], mail=row["archive_draft"],
                          persisted_related_invoice_id=row["original_link"])
    dump(HERE / "mail_archive_blind.json", dict(cases=dict(sorted(blind.items()))))
    dump(dest.parent / "archive_blind_index.json", id_index)
    print(f"Frozen {len(arms)} contexts, {len(independent)} ordinary fresh obligations")
