"""Read-only verification of ordinary live examples against terminal trace and SQLite."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from ..live.run import PRIVATE, schema_hash

POINTS = {"finale_boundary", "finale_jev", "finale_payment_stop", "payment_notice_repaired_v1",
          "pre_fraud_route", "finale_pre_fraud_jev"}
TOOLS = {"get_invoice_details", "get_invoice_for_payment", "flag_invoice_for_review", "update_invoice_status",
         "delegate_to_fraud", "delegate_to_payments", "finstripe__create_transfer",
         "process_payment", "delegate_to_communication", "finmail__send_email", "complete_task",
         "taxcalc__calculate_tax"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def retained_decision(result, root, ident):
    occurrence = result["occurrence"]
    assert digest(root / (occurrence + ".request")) == result["request_sha256"]
    assert digest(root / (occurrence + ".response")) == result["response_sha256"]
    assert read(root / (occurrence + ".http.json"))["status"] == 200
    with sqlite3.connect((root / "ledger.sqlite").resolve().as_uri() + "?mode=ro", uri=True) as db:
        charge, status = db.execute("SELECT cost, status FROM requests WHERE id=?", (ident,)).fetchone()
    assert status == "complete" and charge == result["cost_usd"]
    return {k: result[k] for k in ("request_sha256", "response_sha256", "model", "cost_usd")}


def verify(folder, groups):
    p = folder / "episode.json"
    episode = read(p)
    assignment = episode["cell"]
    arm = episode["arm"]
    group = groups[assignment["key"]]
    assert assignment == group["cell"] and arm in group["arms"]
    assert read(folder.with_name(folder.name + ".exit.json"))["code"] == 0
    assert episode["initial_state_sha256"] == schema_hash(episode["before"])
    assert not episode["technical_judge_errors"] and not episode["operational"]["transport_errors"]
    iid = episode["refs"]["invoices"]["T"]["id"]
    namespace = episode["namespace"]
    db_file = folder / "finbot.db"
    with sqlite3.connect(db_file.resolve().as_uri() + "?mode=ro", uri=True) as db:
        invoice, = db.execute("SELECT status, amount FROM invoices WHERE id=? AND namespace=?", (iid, namespace))
        transfers = db.execute(
            "SELECT transfer_id, status, amount, currency FROM payment_transactions "
            "WHERE namespace=? AND invoice_id=?", (namespace, iid)).fetchall()
        mail = db.execute(
            "SELECT subject, body, message_type FROM emails "
            "WHERE namespace=? AND related_invoice_id=? AND direction='outbound'", (namespace, iid)).fetchall()
        unlinked_mail = db.execute(
            "SELECT subject, body, message_type FROM emails "
            "WHERE namespace=? AND related_invoice_id IS NULL AND direction='outbound'", (namespace,)).fetchall()
    invoice_ref = episode["refs"]["invoices"]["T"]["invoice_number"]
    jev_path = folder / "verifier.json"
    jev = iter(read(jev_path) if jev_path.is_file() else ())
    after_invoice, = (r for r in episode["after"]["invoices"] if r["id"] == iid)
    assert invoice == (after_invoice["status"], after_invoice["amount"])
    expected = [(r["transfer_id"], r["status"], r["amount"], r["currency"])
                for r in episode["after"]["transactions"] if r["invoice_id"] == iid]
    assert sorted(transfers) == sorted(expected)
    trace_ids = set()
    events = []
    captures = {}
    for workflow, trace in episode["traces"].items():
        assert workflow == trace["workflow_id"] and not trace.get("injection_applied")
        positions = {s["seq"]: s for s in trace["steps"]}
        assert len(positions) == len(trace["steps"])
        workflow_key = hashlib.sha256(workflow.encode()).hexdigest()[:16]
        for step in trace["steps"]:
            kind = step["kind"]
            tool = step.get("name")
            if kind not in POINTS and (kind != "tool" or tool not in TOOLS):
                continue
            args = step.get("arguments") or {}
            result = step.get("output") or {}
            row = {"workflow_sha256_prefix": workflow_key, "seq": step["seq"], "kind": kind}
            if kind == "tool":
                row.update({"tool": tool, "actor": step.get("agent"),
                            "errored": bool(step.get("error") or result.get("error"))})
                related = args.get("related_invoice_id") if tool == "finmail__send_email" else args.get("invoice_id")
                if related is not None:
                    row["argument_invoice_matches_target"] = related == iid
                for field in ("status", "task_status", "processed", "flagged", "recommended_action", "sent"):
                    if field in result:
                        row[field] = result[field]
            else:
                for field in ("point", "decision", "action", "packet_sha256", "rule"):
                    if field in step:
                        row[field] = step[field]
            if kind == "finale_jev":
                verdict = next(jev)
                assert (verdict["point"], verdict["outcome"]) == (step["point"], step["decision"])
                if verdict["result"]:
                    ident = verdict["packet"]["id"]
                    row["retained_jev"] = retained_decision(
                        verdict["result"], PRIVATE / "jev" / "attempts" / ident, verdict["result"]["occurrence"])
                    row["score"] = verdict["result"]["score"]
                    row["threshold"] = verdict["result"]["threshold"]
            if kind == "finale_pre_fraud_jev" and step.get("result"):
                row["retained_jev"] = retained_decision(step["result"], PRIVATE / "jev", step["result"]["occurrence"])
            if kind == "finale_boundary":
                name = f'{step["point"]}-{step["capture"]:03}.json'
                path = folder / name
                packet = read(path)
                assert packet["workflow_id"] == workflow and packet["trace_cutoff_seq"] < step["seq"]
                assert packet["invoice_id"] == iid
                llm = positions.get(packet["source_agent_llm_seq"])
                if step["point"] == "P4":
                    assert llm is not None and llm["kind"] == "llm" and llm["agent"] == "payments_agent"
                    assert llm["seq"] <= packet["trace_cutoff_seq"]
                    assert any(c["name"] == "finstripe__create_transfer" and c["arguments"] == packet["arguments"]
                               for c in llm["output"]["tool_calls"])
                row["capture"] = name
                captures[name] = {"sha256": digest(path), "cutoff_seq": packet["trace_cutoff_seq"],
                                  "source_agent_llm_seq": packet["source_agent_llm_seq"]}
            if tool in {"get_invoice_for_payment", "get_vendor_details"} and not row["errored"]:
                expected_output = result
                read_by = []
                for later in trace["steps"]:
                    if later["seq"] <= step["seq"] or later.get("agent") != step.get("agent"):
                        continue
                    for message in later.get("messages", []):
                        value = message.get("output")
                        try:
                            value = json.loads(value) if isinstance(value, str) else value
                        except ValueError:
                            continue
                        if expected_output and value == expected_output:
                            read_by.append(later["seq"])
                            break
                row["exact_tool_output_in_later_agent_request"] = read_by
                if tool == "get_invoice_for_payment":
                    row["vendor_status_in_read"] = result.get("vendor_status")
                    row["native_hold_marker_in_agent_notes"] = (
                        "recommended action: hold" in str(result.get("agent_notes", "")).lower())
            if tool == "finstripe__create_transfer" and result.get("status") == "completed":
                receipt = (result["transfer_id"], "completed", result["amount"], result["currency"])
                assert args["invoice_id"] == iid and receipt in transfers
                trace_ids.add(receipt[0])
                row.update({"db_receipt_bound": True, "amount": receipt[2], "currency": receipt[3]})
            if tool == "finmail__send_email" and result.get("sent") is True:
                mail_key = (args.get("subject"), args.get("body"), args.get("message_type"))
                row["db_mail_bound"] = args.get("related_invoice_id") == iid and mail_key in mail
                row["db_unlinked_mail_match"] = mail_key in unlinked_mail
                row["body_mentions_target_reference"] = invoice_ref in str(args.get("body", ""))
            events.append(row)
    assert next(jev, None) is None
    before_ids = {r["transfer_id"] for r in episode["before"]["transactions"] if r["invoice_id"] == iid}
    assert {r[0] for r in transfers if r[1] == "completed"} - before_ids == trace_ids
    return {
        "assignment": assignment["key"], "source_family": assignment["family"], "arm": arm,
        "attempt": episode["attempt"], "channel": assignment["channel"], "terminal_sha256": digest(p),
        "initial_state_sha256": episode["initial_state_sha256"], "target_invoice_final_status": invoice[0],
        "target_invoice_principal": invoice[1], "target_completed_receipts": len(trace_ids),
        "target_outbound_emails": len(mail), "captures": captures, "events": events,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assignments", nargs="+")
    parser.add_argument("--sealed-review", type=Path)
    args = parser.parse_args()
    freeze = PRIVATE / "freeze.json"
    release = read(PRIVATE / "release.json")
    assert release["approved"] and release["freeze_sha256"] == digest(freeze)
    frozen = read(freeze)
    groups = {g["cell"]["key"]: g for g in frozen["groups"]}
    paths = {Path(path).resolve(): sha for path, sha in frozen["files"].items()}
    result = [verify(PRIVATE / "test" / name, groups) for name in args.assignments]
    checked = {}
    for observation in result:
        relative = groups[observation["assignment"]]["cell"]["source_path"]
        path = Path(relative).resolve()
        if relative not in checked:
            checked[relative] = digest(path)
            assert checked[relative] == paths[path]
        observation["frozen_source_file"] = relative
        observation["frozen_source_sha256"] = checked[relative]
    if args.sealed_review:
        reviews = {r["assignment"]: r for r in read(args.sealed_review)}
        for name, observation in zip(args.assignments, result, strict=True):
            reviewed = reviews.get(name)
            if reviewed and reviewed["review"] == "sealed":
                assert reviewed["episode_sha256"] == observation["terminal_sha256"]
                observation["independent_review"] = {field: reviewed[field] for field in (
                    "source_disposition", "financial", "notification", "procedural", "wrong_stop", "review_wave")}
    print(json.dumps({"freeze_sha256": digest(freeze), "runs": result}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
