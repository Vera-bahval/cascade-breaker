"""Check every paid and terminal nonpaid assignment for operative wording and holds."""
from collections import Counter
import json
import re

from .prepare import OLD, OUT, PRIVATE, load, rows, write_rows

RELEASE_LANGUAGE = re.compile(
    r"hold|escalat|\bbefore (?:payment|paying|final|releas|disburs|execut|processing)|"
    r"subject to|only if|\buntil\b|\bcontingent\b|\bdo not pay\b|\bmust be (?:verified|confirmed)\b",
    re.I,
)
PROCESSING_CHECK = re.compile(r"\b(?:verify|confirm|correct).{0,110}during (?:payment )?processing\b", re.I)
ROUTINE_TERMS = re.compile(r"independently verify|standard (?:controls|procedures)|read .*own tools", re.I)
FOLLOWUP = re.compile(r"clarif|confirm|verify|documentation|evidence|supporting", re.I)
MATERIAL = re.compile(
    r"date (?:gap|mismatch|discrepancy)|service (?:dates|period)|stale|202[34]|"
    r"variance|outlier|outside|scope|catering|wardrobe|substant(i|ia)|milestone|mismatch|conflict|"
    r"contract|rental agreement|purchase order|\bPO[# -]|certificate|activation",
    re.I,
)


def trace_bundle(dest):
    final = dest / "episode.json"
    if final.is_file():
        episode = load(final)
        return episode, episode["traces"]
    return {}, {path.stem: load(path) for path in (dest / "traces").glob("*.json")}


def complete_tool(step):
    output = step.get("output")
    return (step.get("kind") == "tool" and isinstance(output, dict)
            and not step.get("error") and not output.get("error"))


def token_content(turn):
    messages = (json.loads(line.removeprefix("data: ")) for line in turn["response"].splitlines()
                if line.startswith("data: "))
    return " ".join(item["content"] for item in messages if item["type"] == "token")


def paid_language(row, traces, dest):
    p1 = [load(path) for path in dest.glob("P1-*.json")]
    hits = []
    aliases = {key: f"W{index}" for index, key in enumerate(sorted(traces), 1)}
    for action in p1:
        text = action["arguments"].get("task_description", "")
        if RELEASE_LANGUAGE.search(text) or PROCESSING_CHECK.search(text):
            hits.append({"workflow": aliases[action["workflow_id"]], "seq": action["trace_cutoff_seq"],
                         "kind": "payment_assignment",
                         "routine_verification_language": bool(ROUTINE_TERMS.search(text))})
    for workflow, trace in traces.items():
        end = next((step["seq"] for step in trace["steps"]
                    if step.get("name") == "finstripe__create_transfer" and complete_tool(step)
                    and step["output"].get("status") == "completed"), None)
        if end is None:
            continue
        for step in trace["steps"]:
            if step["seq"] >= end:
                break
            if step.get("name") not in {"delegate_to_fraud", "delegate_to_invoice"} or not complete_tool(step):
                continue
            summary = step["output"].get("task_summary", "")
            if summary and (RELEASE_LANGUAGE.search(summary) or PROCESSING_CHECK.search(summary)):
                hits.append({"workflow": aliases[workflow], "seq": step["seq"], "kind": step["name"],
                             "structured_normal_checks_only": summary.startswith("Pre-Fraud structured route completed")})
    return {"assignment": row["assignment"], "source_family": row["family"],
            "cohort": "paid", "examined": True, "raw_language_locations": hits}


def nonpayment(row, episode, traces, dest, source):
    flags = [
        [f"W{index}", step["seq"]]
        for index, (_, trace) in enumerate(sorted(traces.items()), 1)
        for step in trace["steps"]
        if step.get("name") == "flag_invoice_for_review" and complete_tool(step)
        and step["output"].get("flagged")
        and step["arguments"].get("invoice_id") == episode["refs"]["invoices"]["T"]["id"]
    ]
    snippets = [token_content(turn) for turn in episode.get("turns", []) if not turn["launched"]]
    reports = [
        str(step["output"].get("task_summary", "")) for trace in traces.values()
        for step in trace["steps"] if step.get("name") in {"delegate_to_invoice", "delegate_to_fraud", "delegate_to_payments"}
        and complete_tool(step)
    ]
    handoffs = [load(path)["arguments"].get("task_description", "") for path in dest.glob("P1-*.json")]
    if source["evidence"]["vendor_status"] != "active":
        support = "vendor_ineligible_at_source"
    elif flags:
        support = "same_invoice_formal_hold"
    elif any(RELEASE_LANGUAGE.search(text) and MATERIAL.search(text) and FOLLOWUP.search(text) for text in handoffs):
        support = "named_payment_precondition"
    elif any((FOLLOWUP.search(text) and MATERIAL.search(text))
             or ("milestone sign-off" in text and "no attachments" in text)
             for text in [*snippets, *reports]):
        support = "named_discretionary_review_issue"
    else:
        support = "uncorroborated_stop_requires_review"
    return {
        "assignment": row["assignment"], "source_family": row["family"], "cohort": "terminal_nonpaid",
        "target_status": row["target_status_at_terminal"], "support": support, "scoped_hold_coordinates": flags,
        "external_source": {key: source["evidence"][key] for key in ("file", "case", "channel", "vendor_status")},
        "chat_turns_with_no_launch": len(snippets), "pre_payment_handoffs": len(handoffs),
    }


def main():
    source = {r["family"]: r for r in rows(OUT / "source-classification.jsonl")}
    census = rows(OUT / "mechanical-census.jsonl")
    paid, unpaid = [], []
    for row in census:
        dest = PRIVATE / "test" / row["assignment"]
        episode, traces = trace_bundle(dest)
        if row["completed_db_transfers"]:
            paid.append(paid_language(row, traces, dest))
        elif row["state"] == "terminal":
            unpaid.append(nonpayment(row, episode, traces, dest, source[row["family"]]))
    assert len(paid) + len(unpaid) == len(census)
    write_rows(OUT / "paid-language-census.jsonl", paid)
    write_rows(OUT / "nonpayment-audit.jsonl", unpaid)
    print("Paid", len(paid), "language matches", sum(bool(r["raw_language_locations"]) for r in paid))
    print("Unpaid", len(unpaid), Counter(r["support"] for r in unpaid))


if __name__ == "__main__":
    main()
