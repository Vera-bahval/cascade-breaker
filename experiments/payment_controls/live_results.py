"""Reconcile completed direct workflow pilot evidence with DB, traces and model ledgers."""
import csv
import hashlib
import json
import math
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent


def collect_live():
    folder = HERE.parents[1] / ".runtime/payment-controls-chp3/live"
    rows = []
    for case in ("normal-tax", "unknown-tax", "release-note", "active-note"):
        d = folder / case
        s = json.loads((d / "summary.json").read_text())
        raw = (d / "run.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != s["sha256_trace"]:
            raise ValueError("Trace digest mismatch")
        original = json.loads(raw)
        iid = original["refs"]["invoices"]["T"]["id"]
        with sqlite3.connect(f"file:{d / 'finbot.db'}?mode=ro", uri=True) as db:
            txs = db.execute("select status,amount,metadata_json from payment_transactions where invoice_id=?", (iid,)).fetchall()
        if len(txs) != s["transfers"] or any(o != "completed" or amount != 480 for o,amount,_ in txs):
            raise ValueError("Transaction count or amount mismatch")
        step = (s.get("guard_decisions") or [{}])[0]
        jev = json.loads((d / "jev_receipt.json").read_text()) if (d / "jev_receipt.json").exists() else {}
        rows.append(dict(case=case, milliseconds=round(s["seconds"] * 1000), executor_calls=s["executor_calls"],
                         executor_usd=s["eliza_usd"], guard_usd=jev.get("cost_estimate_usd", 0),
                         guard_ms=round(1000*jev.get("duration_s",0)), guard_decision=step.get("decision",""),
                         guard_reason=step.get("reason",""), guard_point=step.get("point",""),
                         tax_review=s["tax_reviews"], transfer_calls=s["transfer_attempts"], transfers=len(txs),
                         tax_amount=json.loads(txs[0][2])["tax"]["tax_amount"] if txs else None,
                         oracle_ok=s["oracle_ok"], trace_sha256=s["sha256_trace"]))
    for dbname, field in (("executor.sqlite", "executor_usd"), ("live-jev.sqlite","guard_usd")):
        with sqlite3.connect(f"file:{folder / dbname}?mode=ro", uri=True) as db:
            total, incomplete = db.execute("select sum(cost),sum(case when cost is null then 1 else 0 end) from requests").fetchone()
            if incomplete or not math.isclose(total, sum(row[field] for row in rows),abs_tol=1e-10):
                raise ValueError(f"Unreconciled {field} totals")
    with (HERE / "live_pilot_results.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=rows[0],lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    for row in collect_live():
        print(row["case"],row["guard_decision"],row["transfers"],row["oracle_ok"])
