"""Recompute pre-pilot audit from the frozen checkpoint-2 archive, offline."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scenarios/replay"))
from sets import GROUPS, outcome


def facts(raw):
    run = json.loads(raw)
    iid = run["refs"]["invoices"]["T"]["id"]
    txs = [tx for tx in run["after"]["transactions"] if tx["invoice_id"] == iid]
    trace, = run["traces"].values()
    steps = trace["steps"]
    t = next(s for s in steps if s.get("name") == "finstripe__create_transfer" and s["arguments"]["invoice_id"] == iid)
    before = [s for s in steps if s["seq"] < t["seq"] and s["kind"] == "tool"]
    inv = next(s["output"] for s in before if s["name"] == "get_invoice_details" and s["arguments"]["invoice_id"] == iid)
    tx, = txs
    out = t["output"]
    return {
        "sha256": hashlib.sha256(raw).hexdigest(), "transfer_seq": t["seq"], "amount": tx["amount"],
        "linked_completed": out["transfer_id"] == tx["transfer_id"] and out["status"] == tx["status"] == "completed",
        "amount_matches": tx["amount"] == inv["amount"] == t["arguments"]["amount"],
        "account_matches": out["vendor_account"] == run["before"]["vendors"]["current"]["bank_account_number"] == t["arguments"]["vendor_account"],
        "fraud_returned": any(s["name"] == "delegate_to_fraud" for s in before),
        "flag_calls": sum(s["name"] == "flag_invoice_for_review" for s in before),
        "first_history_read_seq": next((s["seq"] for s in before if s["name"] == "get_vendor_invoices"), None),
        "first_approval_seq": next((s["seq"] for s in before if s["name"] == "update_invoice_status"
                                    and isinstance(s.get("output"), dict) and s["output"].get("status") == "approved"
                                    and s["arguments"].get("invoice_id") == iid), None),
        "input_description_hash": hashlib.sha256(inv["description"].encode()).hexdigest(),
        "paid_history_count": sum(i["status"] == "paid" for i in run["before"]["invoices"]),
    }


def main():
    replay = json.loads((ROOT / "docs/results/llm-guard-replay-direct.json").read_text())
    missed = [r for r in replay if r["harm_seq"] is not None and not outcome(r, GROUPS)["stopped_harm"]]
    allowed = [r for r in replay if r["variant"] == "positive" and r["oracle_ok"] and r["amount"] is not None]
    pairs = [(r, min(allowed, key=lambda c: (abs(r["amount"] - c["amount"]), c["name"]))) for r in missed]
    needed = {r["name"] for pair in pairs for r in pair}
    evidence = {}
    with tarfile.open(ROOT / "scenarios/archive/runs-2026-11-08.tar.xz", "r|xz") as archive:
        for member in archive:
            p = Path(member.name)
            if p.parent.as_posix() == "results/unified/direct/baseline-ds1" and p.name in needed:
                evidence[p.name] = facts(archive.extractfile(member).read())
    cases = {c["id"]: c for suite in ("core", "honest")
             for c in json.loads((ROOT / f"scenarios/unified/suites/{suite}.json").read_text())}
    for name, ref in evidence.items():
        original = cases[name.rsplit("-r", 1)[0]]["trigger"]["invoice"]
        if (hashlib.sha256(original["description"].encode()).hexdigest() != ref["input_description_hash"]
                or ref["amount"] != original["amount"]):
            raise ValueError(f"Fixture and archived input mismatch: {name}")
    rows = []
    for case, ctrl in pairs:
        name = case["name"]
        scenario = name.rsplit("-r", 1)[0]
        observed = evidence[name]
        control = evidence[ctrl["name"]]
        if not observed["linked_completed"] or observed["transfer_seq"] != case["harm_seq"] or not control["linked_completed"]:
            raise ValueError(f"Archive/replay mismatch: {name}")
        rows.append(dict(run=name, scenario=scenario, author_label=cases[scenario]["source"]["truth"], control=ctrl["name"],
                         control_amount=control["amount"], control_amount_matches=control["amount_matches"],
                         control_account_matches=control["account_matches"], **observed,
                         checks_before_transfer=" ".join(f"{c['group']}@{c['seq']}" for c in case["checks"]
                                                         if c["group"] in GROUPS and c["seq"] <= case["harm_seq"])))
    with (HERE / "archive_audit.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} misses from {len({r['scenario'] for r in rows})} scenarios")


if __name__ == "__main__":
    main()
