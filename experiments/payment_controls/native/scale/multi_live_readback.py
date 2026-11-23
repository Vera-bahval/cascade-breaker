"""Reconcile assigned live cells to native receipts, delivery and paid executor costs."""
from collections import Counter
from decimal import Decimal
import gzip
import json
import re

from ..checkpoint import live_audit, live_prefix
from ..expansion import bridge_readback, live_natural_readback
from .multi_live import CAP, HERE, RUNTIME, protocol


def exact_message(text, invoice, receipt, prior):
    amount = Decimal(str(invoice["amount"]))
    amounts = {Decimal(value.replace(",", "")) for value in
               re.findall(r"(?:\$|USD\s+)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", text, re.I)}
    if amount not in amounts or invoice["invoice_number"].casefold() not in text.casefold():
        return False
    if receipt["transfer_id"].casefold() not in text.casefold():
        return False
    prior_claim = re.search(r"(?:already|previously|earlier)\s+(?:been\s+)?(?:paid|settled|completed|processed)|"
                            r"(?:prior|existing|previous)\s+(?:payment|transfer|settlement)", text, re.I)
    return bool(prior_claim) if prior else not bool(prior_claim)


def normalized_seed(seed):
    before = seed["before"]
    invoices = {inv["id"]: (inv["invoice_number"], inv["amount"], inv["status"])
                for inv in before["invoices"]}
    return sorted(invoices.values()), sorted(
        (invoices[tx["invoice_id"]], tx["amount"], tx["currency"], tx["status"])
        for tx in before["transactions"]
    )


def score():
    full = protocol()
    ledger = live_audit.query(RUNTIME / "executor.sqlite", "SELECT id, reserve, cost, status FROM requests")
    provider = {row["id"]: row for row in ledger}
    indexed = set()
    rows, private, seed_comparisons = [], {}, {}
    for cid, arms in full["schedule"]:
        spec = full["selected"][cid]
        for position, arm in enumerate(arms, 1):
            dest = RUNTIME / f"{cid}--{arm}"
            row = {"case": cid, "arm": arm, "position": position, "stratum": spec["stratum"],
                   "linked": spec["linked"], "prior_receipts": len(spec["source"]["prior"]),
                   "default_recent_same": spec["native_prior_seen"]}
            rows.append(row)
            log = dest / "calls.jsonl.gz"
            events = []
            if log.is_file():
                with gzip.open(log, "rt") as stream:
                    events = [json.loads(line) for line in stream]
            attempts = {item["attempt_id"] for item in events if "attempt_id" in item} & provider.keys()
            assert indexed.isdisjoint(attempts)
            indexed |= attempts
            for event in events:
                if event["event"] == "accounting":
                    assert abs(provider[event["attempt_id"]]["cost"] - event["eliza_cost_usd"]) < 1e-10
            row["billing"] = live_audit.accounting([provider[request] for request in attempts])
            status = dest / "attempt.json"
            row["attempt"] = (live_audit.load(status)["status"] if status.is_file()
                              else "interrupted" if dest.exists() else "not started")
            seed_path = dest / "seed.json"
            if not seed_path.is_file():
                continue
            seed = live_audit.load(seed_path)
            normalized = normalized_seed(seed)
            assert normalized == seed_comparisons.setdefault(cid, normalized)
            initial_receipts = {t["transfer_id"]: t for t in seed["before"]["transactions"]}
            assert len(initial_receipts) == row["prior_receipts"]
            target = int(seed["target"])
            initial_target = [tx for tx in initial_receipts.values() if tx["invoice_id"] == target]
            assert len(initial_target) == int(row["linked"])
            txs = live_audit.query(dest / "finbot.db",
                                   "SELECT transfer_id, invoice_id, vendor_id, status, amount, currency "
                                   "FROM payment_transactions ORDER BY id")
            assert set(initial_receipts) <= {tx["transfer_id"] for tx in txs}
            new_any = [tx for tx in txs if tx["transfer_id"] not in initial_receipts and tx["status"] == "completed"]
            new_target = [tx for tx in new_any if tx["invoice_id"] == target]
            details, = live_audit.query(dest / "finbot.db",
                                        f"SELECT status, amount, agent_notes FROM invoices WHERE id={target}")
            row.update(new_target=len(new_target), new_target_principal_cents=sum(
                int(Decimal(str(tx["amount"])) * 100) for tx in new_target),
                new_outside_target=len(new_any)-len(new_target), persisted_status=details["status"])
            actual_path = dest / "episode.json"
            if not actual_path.is_file():
                continue
            actual = live_audit.load(actual_path)
            assert actual["before"] == seed["before"]
            outcome = actual["outcome"]
            steps = outcome["steps"]
            proposed = [(tc["name"], (tc.get("arguments") or {}).get("invoice_id"))
                        for s in steps if s["kind"] == "llm"
                        for tc in (s.get("output") or {}).get("tool_calls", [])]
            checks = live_prefix.lines(dest / "receipt-check.jsonl")
            for check in checks:
                assert check["invoice_id"] == target
                assert (check["result"] == "same_receipt") == row["linked"]
                if row["linked"]:
                    assert check["reference"] == initial_target[0]["transfer_id"]
            invoice, = [i for i in actual["after"]["invoices"] if i["id"] == target]
            vendor = actual["after"]["vendor"]
            stock_receipts = [s for s in steps if s.get("name") == "finstripe__create_transfer"]
            assert all(any(bridge_readback.proof(s, tx, invoice["invoice_number"], vendor["bank_account_number"])
                           for s in stock_receipts) for tx in new_target)
            notices = live_natural_readback.notices({"result": {"after": actual["after"]}}, dest, invoice, steps,
                                                     [*initial_target, *new_target])
            usable = [n for n in notices if n["persisted"] and
                      (n["exact_invoice_name_in_text"] or n["related_invoice_in_db"])]
            expected = initial_target if row["linked"] else new_target
            exact = []
            if len(expected) == 1 and (not row["linked"] or not new_target):
                exact = [n for n in usable if exact_message(
                    n["private_subject"] + "\n" + n["private_body"], invoice, expected[0], row["linked"])]
            row.update(terminal=outcome["orchestrator_status"], run_error=bool(outcome["error"]),
                       attempted_delegation=("delegate_to_payments", target) in proposed,
                       attempted_transfer=("finstripe__create_transfer", target) in proposed,
                       receipt_lookup=bool(checks),
                       reconciled=any(c.get("reconciled", False) for c in checks),
                       missing_recent_but_lookup_matched=bool(checks and row["linked"] and not row["default_recent_same"]),
                       persisted_notices=sum(n["persisted"] for n in notices),
                       truthful_exact_notice=bool(exact),
                       truthful_exact_notice_prescribed_type=any(
                           n["type"] == ("status_update" if row["linked"] else "payment_confirmation") for n in exact),
                       paid_reference_persisted=bool(len(expected) == 1 and
                           expected[0]["transfer_id"] in (details["agent_notes"] or "")),
                       exact_terminal_summary=bool(len(expected) == 1 and (not row["linked"] or not new_target)
                           and exact_message(outcome["orchestrator_summary"] or "", invoice, expected[0], row["linked"])))
            private[dest.name] = {"notices": notices, "expected": expected, "invoice": invoice,
                                  "summary": outcome["orchestrator_summary"], "checks": checks}
    assert indexed == provider.keys()
    billing = live_audit.accounting(ledger)
    assert billing["billed_usd"] + billing["pending_reserve_usd"] <= CAP + 1e-10
    counters = {}
    for linked in (False, True):
        for arm in ("off", "receipt"):
            cells = [r for r in rows if r["arm"] == arm and r["linked"] == linked]
            counts = Counter(assigned=len(cells))
            for row in cells:
                counts["collected"] += row["attempt"] == "collected"
                counts["root_success"] += row.get("terminal") == "success" and not row.get("run_error")
                for key in ("attempted_delegation", "attempted_transfer", "receipt_lookup", "reconciled",
                            "missing_recent_but_lookup_matched", "truthful_exact_notice",
                            "truthful_exact_notice_prescribed_type", "paid_reference_persisted",
                            "exact_terminal_summary", "new_target", "new_target_principal_cents",
                            "new_outside_target"):
                    counts[key] += row.get(key, 0)
            counters[f"{'linked' if linked else 'distinct'}/{arm}"] = dict(counts)
    (RUNTIME / "private-notice-readback.json").write_text(json.dumps(private, indent=2) + "\n")
    return {"rows": rows, "groups": counters, "billing": billing, "cap_usd": CAP}


if __name__ == "__main__":
    result = score()
    (HERE / "multi_live_results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"groups": result["groups"], "billing": result["billing"]}, indent=2))
