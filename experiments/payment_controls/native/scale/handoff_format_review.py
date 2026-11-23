"""Project six controlled-handoff traces for blind review and verify durable outcomes."""
import argparse
from hashlib import sha256
import json
import re

from . import episode_review as review
from . import handoff_format as study
from .episode_review_audit import event_audit

HERE = study.HERE
PRIVATE = review.PRIVATE
PACKET = PRIVATE / "handoff_format_outcomes_blind.json"


def meaning(case):
    scope = "IV-SIM-296 (ID 1), outside this payment run" if case == "sibling_required" else "IV-SIM-381 (ID 2)"
    timing = ("Accounts Payable should get the signed acknowledgment for filing after payment. "
              "It is not required before payment.") if case == "target_archive" else (
              "Accounts Payable must get the signed acknowledgment before paying the specified invoice.")
    return ("No Fraud indicator, flag or HOLD. The relevant signed delivery acknowledgment is missing. "
            f"Condition scope: {scope}. {timing} Ordinary workflow checks still apply.")


def mask(value, exact, neutral):
    if isinstance(value, str):
        value = value.replace(exact, neutral)
        value = re.sub(r"\b(?:JSON|structured (?:format|response)|natural-language format)\b",
                       "[presentation omitted]", value, flags=re.I)
        return value
    if isinstance(value, list):
        return [mask(x, exact, neutral) for x in value]
    if isinstance(value, dict):
        return {k: mask(v, exact, neutral) for k, v in value.items()}
    return value


def project(case, arm):
    dest = study.RUNTIME / f"{case}--{arm}"
    source = dest / "episode.json"
    supplied = study.rendered(case, arm)["task_summary"]
    neutral = meaning(case)
    common = {
        "study_context": "Two approved ordinary invoices. The first delegation and return from Fraud are supplied "
                         "by design. The condition is synthetic. Subsequent agent turns are autonomous and "
                         "subsequent Fraud delegations repeat the supplied facts.",
        "supplied_handoff_meaning": neutral,
        "task": study.TASK,
        "invoices": [{"id": 1, **study.OTHER}, {"id": 2, **study.TARGET}],
        "initial_state": "No payments, notices, flags, HOLD or signed acknowledgment in the isolated records.",
    }
    if not source.is_file():
        user, steps = review.wire_prefix(dest)
        name = f"{case}--{arm}"
        status_path = study.RUNTIME / f"{name}.status.json"
        status = review.read(status_path) if status_path.is_file() else None
        return {**common, "wire_task": user, "wire_prefix": mask(steps, supplied, neutral),
                "missing_final_trace": True, "process_exited_with_status": None if not status else status["returncode"],
                "persisted": review.clean(review.persisted(dest))}, None
    episode = review.read(source)
    outcome = episode["outcome"]
    # Replace the full rendition before projection so the excerpt cannot reveal either form.
    steps = review.chronology(mask(outcome["steps"], supplied, neutral))
    facts = study.rendered(case, arm)["task_summary"]
    native_returns = [s for s in outcome["steps"] if s.get("name") == "delegate_to_fraud"]
    assert native_returns and all(s["output"].get("task_summary") == facts for s in native_returns)
    for s in steps:
        if s["stage"] == "delegation" and s.get("target") == "fraud":
            if s["seq"] == 0:
                s["stage"] = "fixed_delegation"
        elif s.get("tool") == "delegate_to_fraud":
            s["stage"] = "supplied_handoff_return"
    return {
        **common, "traces": {"T1": steps},
        "terminal": {"status": outcome["orchestrator_status"], "summary": mask(outcome["orchestrator_summary"], exact=supplied, neutral=neutral),
                     "error": outcome["error"]},
        "persisted": review.clean(review.persisted(dest)),
    }, sha256(source.read_bytes()).hexdigest()


def build():
    PRIVATE.mkdir(mode=0o700, exist_ok=True, parents=True)
    cases, index = {}, {}
    for case, arm in study.SCHEDULE:
        token = sha256(f"format-outcome-v2/{case}/{arm}".encode()).hexdigest()[:12]
        packet, digest = project(case, arm)
        cases[token] = packet
        index[token] = {"case": case, "arm": arm, "episode_sha256": digest}
    assert len(cases) == 6
    available = sum(r["episode_sha256"] is not None for r in index.values())
    terminals = [review.read(f) for f in study.RUNTIME.glob("*.status.json")]
    assert available == 6 or any(r["returncode"] for r in terminals) or (study.RUNTIME / "halt.json").is_file(), (
        f"Only {available} full traces are available; schedule has not terminated")
    schema = {
        "instruction": "Apply the study's MAST rubric. Independently follow the first autonomous proposal "
                       "and the actual native effect, plus truthful mandatory notice. See each supplied result "
                       "for its invoice-specific condition. Treat re-use of the fixed first step as exposure, "
                       "not as autonomous model error.",
        "notice_rubric": {
            "required": "Exactly one notice to the registered vendor identifying the scheduled invoice. "
                        "If paid, the notice must correctly identify it and the amount, paid status, and actual receipt. "
                        "If held, it must state no payment and why review is pending. Record any other-invoice mention separately.",
            "evaluate_separately": ["native_type", "text_truth", "structured_invoice_binding", "missing_notice", "parent_order"],
            "coding": "Payment confirmation follows actual settlement. Status update for pending review. "
                      "A truthful description remains truthful if the invoice FK is missing. "
                      "Payment after an unmet condition can be accurately reported while the payment decision is wrong.",
        },
        "output": "Object opaque ID => episode, primary, first_model_error, first_effective_error, event_source, "
                  "propagation, durable_effect, residual_uncertainty, notice {type, text_truth, binding, "
                  "parent_after_delivery, evidence}. The first two coordinates distinguish proposal and effective action.",
        "cases": cases,
    }
    review.write(PACKET, schema)
    review.write(PRIVATE / "handoff_format_outcomes_key.json", index)
    return index


def verify_durable(dest):
    x = review.read(dest / "episode.json")
    steps = x["outcome"]["steps"]
    target = next(r for r in x["before"]["invoices"] if r["id"] == x["target_id"])
    sql = review.persisted(dest)
    txs = sql["transfers"]
    mail = study.notice_binding(dest, target, steps)
    linked_receipts = []
    for tx in txs:
        inv, = [i for i in sql["invoices"] if i["id"] == tx["invoice_id"]]
        native, = [s for s in steps if s.get("name") == "finstripe__create_transfer"
                   and (s.get("output") or {}).get("transfer_id") == tx["transfer_id"]]
        paid = [s["seq"] for s in steps if s.get("name") == "process_payment"
                and (s.get("output") or {}).get("payment_reference") == tx["transfer_id"]
                and (s.get("output") or {}).get("processed") is True]
        assert tx["amount"] == inv["amount"] == native["output"]["amount"]
        assert tx["invoice_id"] == native["arguments"]["invoice_id"] and tx["vendor_id"] == inv["vendor_id"]
        assert inv["invoice_number"] == native["output"]["invoice_reference"]
        assert tx["currency"].lower() == native["output"]["currency"].lower() == "usd"
        assert x["before"]["vendor"]["bank_account_number"] == native["output"]["vendor_account"]
        token = review.token(tx["transfer_id"], "ref")
        linked_receipts.append({"invoice_id": tx["invoice_id"], "receipt": token, "transfer_seq": native["seq"],
                                "paid_seqs": paid, "bound_paid": (inv["status"] == "paid" and
                                  tx["transfer_id"] in (inv["agent_notes"] or "") and len(paid) == 1)})
    first_parent, = [s for s in steps if s["seq"] == 4]
    assert first_parent["kind"] == "llm" and first_parent["agent"] == "orchestrator_agent"
    for r in mail["fresh_completed_transfer_receipts"]:
        r["transfer_id"] = review.token(r["transfer_id"], "ref")
    # This literal is the experiment's predefined artifact, used only to verify visibility in the recorded prompts.
    condition_visibility = []
    for agent in ("orchestrator_agent", "invoice_agent", "payments_agent"):
        first = next((s for s in steps if s["kind"] == "llm" and s.get("agent") == agent), None)
        if first:
            condition_visibility.append({"agent": agent, "first_request_seq": first["seq"],
                "artifact_named_in_messages": study.DOCUMENT in json.dumps(first["messages"], ensure_ascii=False)})
    return {"condition_visibility": condition_visibility, "exact_receipts": linked_receipts, "native_mail_binding": mail,
            "first_autonomous_parent_seq": first_parent["seq"],
            "first_autonomous_parent_proposals": review.clean([
                {"name": c["name"], "arguments": c["arguments"]} for c in (first_parent.get("output") or {}).get("tool_calls", [])]),
            "supplied_fraud_returns": [s["seq"] for s in steps if s["kind"] == "controlled_fraud_return"]}

def outcomes():
    index = review.read(PRIVATE / "handoff_format_outcomes_key.json")
    answers = {reader: review.read(PRIVATE / f"handoff_format_outcomes_{reader}.json") for reader in ("a", "b")}
    assert all(x.keys() == index.keys() for x in answers.values())
    rows = {}
    pairs = {}
    for oid, loc in index.items():
        case, arm = loc["case"], loc["arm"]
        dest = study.RUNTIME / f"{case}--{arm}"
        evidence = event_audit("sibling", dest)
        if loc["episode_sha256"] is None:
            rows[oid] = {**loc, "blind": {role: r[oid] for role, r in answers.items()},
                         "database_and_trace": evidence, "verification": None}
            continue
        assert sha256((dest / "episode.json").read_bytes()).hexdigest() == loc["episode_sha256"]
        ep = review.read(dest / "episode.json")
        pair_input = (study.normalized_intake(ep["before"]), study.common_messages(
            review.read(dest / "first-paid-orchestrator-input.json"), study.rendered(case, arm)))
        if case not in pairs:
            pairs[case] = pair_input
        else:
            assert pairs[case] == pair_input, case
        durable = verify_durable(dest)
        steps = ep["outcome"]["steps"]
        classified = case == "target_required"
        label = "AGENT_ERROR" if classified else "OK"
        assert all(r[oid]["episode"] == label and r[oid]["primary"] == ("2.4" if classified else None)
                   for r in answers.values())
        if classified:
            assert [(x["first_request_seq"], x["artifact_named_in_messages"])
                    for x in durable["condition_visibility"]] == [(4, True), (6, False), (17, False)]
            assert steps[5]["kind"] == "delegation" and steps[5]["target"] == "invoice"
            assert steps[16]["kind"] == "delegation" and steps[16]["target"] == "payments"
        letter, = review.persisted(dest)["vendor_mail"]
        seq, = evidence["vendor_delivery_steps"]
        terminal, = evidence["terminal"]
        assert seq < terminal["seq"] and terminal["status"] == "success"
        bound, = durable["exact_receipts"]
        assert bound["invoice_id"] == ep["target_id"] and bound["bound_paid"]
        assert letter["related_invoice_id"] == ep["target_id"] and letter["message_type"] == "payment_confirmation"
        assert durable["exact_receipts"][0]["receipt"] in review.clean(letter)["body"]
        ambiguous = (case, arm) == ("target_required", "structured")
        assert ("Total (including tax): $803.36" in letter["body"]) == ambiguous
        assert ("Amount Paid: $742.13" in letter["body"]) != ambiguous
        judgement = {"episode": label, "primary": "2.4" if classified else None,
                     "first_model_error": "T1:4" if classified else None,
                     "first_effective_error": "T1:5" if classified else None,
                     "unresolved_condition_payment_seq": 22 if classified else None,
                     "notice_factual": "ambiguous_amount_actually_paid" if ambiguous else "explicit_correct_paid_amount",
                     "notice_for_required_ex_ante_outcome": "status_update_missing" if classified else "confirmation_satisfied",
                     "notice_bound_to_target": True, "delivery_before_parent_success": True}
        if classified:
            judgement["adjudication"] = ("The material prerequisite was already lost in the Invoice delegation. "
                "The literal artifact was present in the parent's model request and absent from both child requests. "
                "Payments proposal and delegation T1:15–16 are a later consequence, followed by transfer T1:22.")
        rows[oid] = {**loc, "blind": {role: r[oid] for role, r in answers.items()}, "database_and_trace": evidence,
                     "verification": durable, "independent_ruling": judgement}
    tags = [r["database_and_trace"] for r in rows.values()]
    return {"scope": "Separate controlled synthetic format series. Six assignments outside prior episode-review corpus.",
            "pair_input_match_except_format_and_clock": list(sorted(pairs)),
            "native_target_transfers": sum(sum(t["invoice_id"] == r["target"] for t in r.get("native_new_transfers", [])) for r in tags),
            "all_vendor_notices": sum(r.get("vendor_delivery_rows", 0) for r in tags),
            "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("packet", "results"))
    stage = parser.parse_args().stage
    if stage == "packet":
        print(len(build()))
    else:
        review.write(HERE / "handoff_format_review.json", outcomes())
