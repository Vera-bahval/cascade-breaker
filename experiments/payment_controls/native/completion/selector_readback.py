"""Read paid selector evidence without changing the hashed experiment runner."""
import gzip
import json
import re
import sqlite3

from experiments.payment_controls.native.completion.selector import (
    CELLS, ELIZA_CAP, HERE, JEV_CAP, LIVE, TASK, process_chat, verify_freeze,
)


def collect():
    verify_freeze()
    rows, accounting, first_requests, same_invoice_rows = [], {}, {}, {}
    prelabels = json.loads((HERE / "process_chat_inputs.json").read_text())["cases"]
    messages = {case: row["message"] for case, row in zip(("review", "definition"), prelabels, strict=True)}
    expected_invoices = {"review": 5, "definition": 0}
    selected, profile_reads = {}, {}
    for case, arm in CELLS:
        dest = LIVE / f"{case}--{arm}"
        row = json.loads((dest / "chat.json").read_text())
        traces = [json.loads(p.read_text()) for p in (dest / "traces").glob("*.json")]
        children = {t["workflow_id"]: t for t in traces if t["task_data"].get("parent_workflow_id")}
        assert len(children) == len(row["launches"]) <= 1 and row["reply"]
        for launch in row["launches"]:
            task = children[launch["workflow_id"]]["task_data"]
            assert (task["vendor_id"], task["parent_workflow_id"], task["description"]) == (
                row["vendor_id"], launch["parent"], launch["description"])
            assert not task.get("invoice_id") and not task.get("attachment_file_ids")
            if arm == "selector" and row["checks"][0].get("stage_tools"):
                assert task["description"] == TASK
        with sqlite3.connect((dest / "finbot.db").as_uri() + "?mode=ro", uri=True) as db:
            assert db.execute("SELECT id FROM vendors").fetchall() == [(row["vendor_id"],)]
            invoices = db.execute("SELECT * FROM invoices ORDER BY id")
            columns = [column[0] for column in invoices.description]
            semantic = [c for c in columns if c not in {"namespace", "created_at", "updated_at", "uploaded_at"}]
            normalized = [tuple(r[columns.index(c)][:10] if c in {"invoice_date", "due_date"} else r[columns.index(c)] for c in semantic) for r in invoices]
            assert len(normalized) == expected_invoices[case]
            same_invoice_rows[case, arm] = normalized
            assert db.execute("SELECT count(*) FROM payment_transactions").fetchone() == (0,)
        with gzip.open(dest / "calls.jsonl.gz", "rt") as stream:
            journal = list(map(json.loads, stream))
        requests = [r for r in journal if r["event"] == "request"]
        wire = requests[0]["request"]
        assert wire["messages"][-1] == {"role": "user", "content": messages[case]}
        prompt = wire["messages"][0]["content"]
        namespace = re.search(r"admin@(ns_user_[A-Za-z0-9_-]+)\.finbot", prompt).group(1)
        wire["messages"][0]["content"] = prompt.replace(namespace + ".finbot", "[session].finbot")
        first_requests[case, arm] = (requests[0]["request_sha256"], wire)
        if case == "review":
            tool_call, tool_result = requests[1]["request"]["messages"][-2:]
            call, = tool_call["tool_calls"]
            assert call["function"]["name"] == "get_vendor_details"
            assert json.loads(call["function"]["arguments"]) == {"vendor_id": row["vendor_id"]}
            assert tool_result["tool_call_id"] == call["id"]
            profile = json.loads(tool_result["content"])
            expected_profile = prelabels[0]["current_vendor"]
            assert all(profile["vendor_category" if f == "category" else f] == v for f, v in expected_profile.items())
            profile_reads[arm] = {k: v for k, v in profile.items() if k not in {"namespace", "created_at", "updated_at"}}
        receipts = [r for r in journal if r["event"] == "accounting"]
        assert receipts and sorted(r["attempt_id"] for r in receipts) == sorted(
            r["attempt_id"] for r in journal if r["event"] == "request")
        for receipt in receipts:
            assert receipt["attempt_id"] not in accounting
            accounting[receipt["attempt_id"]] = receipt["eliza_cost_usd"]
        row.update(workflow_count=len(children), oracle_ok=len(children) == int(case == "review"),
                   executor_calls=len(receipts), executor_usd=sum(r["eliza_cost_usd"] for r in receipts))
        for check in row["checks"]:
            if "selector" in check:
                selected[check["selector"]["request_sha256"]] = check["selector"]
        assert row["before_status"] == row["after_status"]
        rows.append(row)
    with sqlite3.connect((LIVE / "executor.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        ledger = db.execute("select id,cost,status from requests").fetchall()
    assert {attempt for attempt, _, _ in ledger} == set(accounting)
    assert all(status == "completed" and abs(cost - accounting[attempt]) <= 1e-12 for attempt, cost, status in ledger)
    with sqlite3.connect((LIVE / "jev/ledger.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        jev_ledger = db.execute("SELECT id,cost,status FROM requests").fetchall()
    assert {ident for ident, _, _ in jev_ledger} == set(selected) and len(selected) == 2
    for ident, cost, status in jev_ledger:
        assert status == "complete" and cost == selected[ident]["usd"]
        assert json.loads((LIVE / f"jev/{ident}.json").read_text()) == selected[ident]
    jev_summary = {"requests": len(jev_ledger), "cost_usd": sum(r[1] for r in jev_ledger), "pending": 0}
    assert jev_summary["cost_usd"] <= JEV_CAP
    assert profile_reads["off"] == profile_reads["selector"]
    pairs = {}
    for case in ("review", "definition"):
        a, b = (first_requests[case, arm] for arm in ("off", "selector"))
        assert a[1] == b[1] and same_invoice_rows[case, "off"] == same_invoice_rows[case, "selector"]
        pairs[case] = {"wire_request_sha256": [a[0], b[0]], "first_request_equivalent_after_sandbox_mail_alias_normalization": True,
                       "same_invoice_rows": len(same_invoice_rows[case, "off"]),
                       "same_profile_read": True if case == "review" else None}
    assert sum(accounting.values()) <= ELIZA_CAP
    process_chat.dump(HERE / "selector_results.json", {"cells": rows, "eliza_usd": sum(accounting.values()),
                                                         "jev": jev_summary, "pairs": pairs})


if __name__ == "__main__":
    collect()
