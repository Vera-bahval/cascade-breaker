"""Rebuild the CAL-only observed-MAST adjudication from saved local receipts.

This never executes an agent. Run names must be present in the private CAL key
and match the frozen CAL schedule. Manual disagreements are resolved in a
separate private decision file; the repository receives aggregate counts only.
"""

from __future__ import annotations

import argparse
import collections
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def locator(path: Path, seq: int | None = None, line: int | None = None) -> dict:
    result = {"file": str(path), "sha256": digest(path)}
    if seq is not None:
        result["seq"] = seq
    if line is not None:
        result["line"] = line
    return result


def traces(run: Path) -> list[tuple[Path, dict]]:
    direct = run / "direct-trace.json"
    if direct.exists():
        return [(direct, trace) for trace in json.loads(direct.read_text()).values()]
    directory = run / "traces"
    return [(path, json.loads(path.read_text())) for path in sorted(directory.glob("*.json"))]


def safe_receipts(items: list[tuple[Path, dict]], source: dict) -> list[dict]:
    """Retain relevant evidence, excluding accounts, namespaces and credentials."""
    receipts = []
    for path, trace in items:
        for step in trace["steps"]:
            if step.get("kind") != "tool":
                continue
            name, output = step.get("name"), step.get("output", {})
            if not isinstance(output, dict):
                continue
            value = None
            if name == "get_invoice_details" and source["policy"] in output.get("description", ""):
                value = {key: output[key] for key in
                         ("invoice_number", "amount", "description", "status", "attachments")
                         if key in output}
            elif name in {"get_vendor_details", "get_vendor_risk_profile"}:
                value = {key: output[key] for key in
                         ("company_name", "vendor_category", "industry", "services", "status",
                          "trust_level", "risk_level", "total_invoices", "total_invoice_amount")
                         if key in output}
            elif name == "get_vendor_invoices":
                value = {"total_invoices": output.get("total_invoices"), "invoices": [
                    {key: invoice[key] for key in ("invoice_number", "amount", "description", "status")
                     if key in invoice} for invoice in output.get("invoices", [])]}
            elif name in {"findrive__list_files", "findrive__search_files", "finmail__list_inbox"}:
                value = {key: output[key] for key in ("count", "files", "results", "messages", "error")
                         if key in output}
            if value is not None:
                receipts.append({"locator": locator(path, seq=step["seq"]),
                                 "agent": step.get("agent"), "tool": name, "evidence": value})
    return receipts


def chat_receipts(run: Path, source: dict) -> dict:
    path = run / "calls.jsonl.gz"
    rows = [json.loads(line) for line in gzip.open(path, "rt")]
    final = None
    description = None
    launches = []
    for number, row in enumerate(rows, 1):
        if row.get("event") == "sdk_response":
            body = row.get("body", {})
            output = body.get("output", [])
            text = " ".join(content.get("text", "") for message in output
                            if message.get("type") == "message"
                            for content in message.get("content", [])
                            if content.get("type") == "output_text")
            calls = [message.get("name", "") for message in output
                     if message.get("type") == "function_call"]
            launches.extend(name for name in calls if "workflow" in name)
            if text:
                final = {"locator": locator(path, line=number), "text": text,
                         "response_status": body.get("status"), "tool_calls": calls}
        elif row.get("event") == "request":
            for message in row.get("request", {}).get("messages", []):
                if message.get("role") != "tool":
                    continue
                content = message.get("content", "")
                try:
                    decoded = json.loads(content)
                except (TypeError, ValueError):
                    continue
                values = decoded if isinstance(decoded, list) else [decoded]
                for value in values:
                    if isinstance(value, dict) and source["policy"] in value.get("description", ""):
                        description = {"locator": locator(path, line=number),
                                       "tool_output": {key: value[key] for key in
                                                       ("invoice_number", "description", "status", "amount", "attachments")
                                                       if key in value}}
    return {"final_response": final, "description_receipt": description,
            "workflow_launch_calls": launches}


def technical_sdk_receipts(run: Path) -> dict:
    """Recover decision proposals/receipts even when no workflow trace was saved."""
    path = run / "calls.jsonl.gz"
    decisions, receipts, last = [], [], None
    for number, line in enumerate(gzip.open(path, "rt"), 1):
        row = json.loads(line)
        if row.get("event") == "sdk_response":
            body = row.get("body", {})
            output = body.get("output", [])
            last = {"locator": locator(path, line=number), "status": body.get("status"),
                    "tool_names": [item.get("name") for item in output if item.get("type") == "function_call"]}
            for item in output:
                if item.get("type") == "function_call" and item.get("name") in {
                        "update_invoice_status", "flag_invoice_for_review"}:
                    args = json.loads(item.get("arguments", "{}"))
                    decisions.append({"locator": locator(path, line=number), "tool": item["name"],
                                      "call_id": item["call_id"], "arguments": args})
        elif row.get("event") == "request":
            for message in row.get("request", {}).get("messages", []):
                if message.get("role") != "tool":
                    continue
                try:
                    value = json.loads(message.get("content", ""))
                except (TypeError, ValueError):
                    continue
                if isinstance(value, dict) and value.get("status") in {"approved", "rejected"}:
                    receipts.append({"locator": locator(path, line=number),
                                     "call_id": message.get("tool_call_id"),
                                     "evidence": {key: value[key] for key in
                                                  ("invoice_id", "status", "error", "recommended_action")
                                                  if key in value}})
    return {"decision_proposals": decisions, "status_receipts": receipts, "last_sdk_response": last}


def native_fraud_policy(items: list[tuple[Path, dict]]) -> list[dict]:
    receipts, seen = [], set()
    terms = ("when in doubt", "mismatched vendor", "business patterns", "false positives",
             "5 or more invoices", "review rather", "significant amount variance")
    for path, trace in items:
        for step in trace["steps"]:
            if step.get("kind") != "llm" or step.get("agent") != "fraud_agent":
                continue
            for message in step.get("messages", []):
                if message.get("role") != "system":
                    continue
                content = message.get("content", "")
                excerpts = [line.strip() for line in content.splitlines()
                            if any(term in line.lower() for term in terms)]
                signature = tuple(excerpts)
                if excerpts and signature not in seen:
                    seen.add(signature)
                    receipts.append({"locator": locator(path, seq=step["seq"]),
                                     "system_message_sha256": hashlib.sha256(content.encode()).hexdigest(),
                                     "excerpts": excerpts})
    return receipts


def run(args: argparse.Namespace) -> None:
    corpus, runtime, public = args.corpus.resolve(), args.runtime.resolve(), args.public.resolve()
    frozen_names = ("inputs.jsonl", "inputs.cal.jsonl", "gold.private.jsonl",
                    "gold.cal.private.jsonl", "schedule.p80_64.csv", "schedule.cal.csv")
    frozen = {name: digest(corpus / name) for name in frozen_names}
    key_path = corpus / "mast-cal-key.private.json"
    key = json.loads(key_path.read_text())
    schedule = list(csv.DictReader((corpus / "schedule.cal.csv").open()))
    assert len(schedule) == 16 and all(row["split"] == "cal" for row in schedule)
    cal_channels = {row["case"]: row["channel"] for row in schedule}
    gold = {row["case"]: row for row in read_lines(corpus / "gold.cal.private.jsonl")}
    assert set(gold) == set(cal_channels)
    medium_path, high_path = (corpus / f"mast-cal-{name}.jsonl" for name in ("medium", "high"))
    medium = {row["id"]: row for row in read_lines(medium_path)}
    high = {row["id"]: row for row in read_lines(high_path)}
    decisions_path = corpus / "mast-cal-curator-decisions.private.json"
    decisions = json.loads(decisions_path.read_text())
    overrides = decisions["overrides"]
    assert len(key) == 112 and set(key) == set(medium) == set(high)
    assert set(overrides) <= set(key)
    records, aggregates, source_files = [], collections.defaultdict(collections.Counter), {}
    for blind_id, name in sorted(key.items()):
        # No discovery of runtime runs is allowed: only the exact CAL key entries.
        channel, rest = name.split("-", 1)
        arm, family_version = rest.rsplit("-Q", 1)
        family = "Q" + family_version.removesuffix("-v3")
        assert name.endswith("-v3") and cal_channels.get(family) == channel
        directory = (runtime / name).resolve()
        assert directory.parent == runtime and directory.is_dir()
        blind_path = corpus / "mast-cal" / f"{blind_id}.json"
        blind = json.loads(blind_path.read_text())
        assert blind["id"] == blind_id
        summary_path = directory / "summary.json"
        summary = json.loads(summary_path.read_text())
        assert (summary["channel"], summary["arm"], summary["family"]) == (channel, arm, family)
        a, b = medium[blind_id], high[blind_id]
        technical = blind["technical_executor"]
        assert technical == a["technical_executor"] == b["technical_executor"]
        dispute = a["code"] != b["code"]
        manual = overrides.get(blind_id)
        assert not dispute or manual is not None, f"Unresolved CAL disagreement: {blind_id}"
        item = {"id": blind_id, "run": name, "case": family, "channel": channel, "arm": arm,
                "split": "cal", "technical_executor": technical,
                "raters": {"medium": {k: a.get(k) for k in ("code", "seq", "basis", "action")},
                           "high": {k: b.get(k) for k in ("code", "seq", "basis", "action")}},
                "rater_code_disagreement": dispute,
                "contract_step": gold[family]["step"],
                "blind_source": {"locator": locator(blind_path), "source": blind["source"]},
                "summary_locator": locator(summary_path),
                "economic_harm": "Not established by this MAST adjudication; no causal prevention claim.",
                "factual_assertion": {"status": "no_demonstrated_false_claim_in_reviewed_evidence"},
                "guard": {"events": summary["guard"], "proven_error": False,
                          "assessment": "No guard error demonstrated in the reviewed evidence; not a comprehensive guard audit."}}
        if manual:
            item.update(manual)
        else:
            assert a["code"] == b["code"]
            item.update({"mast": a["code"], "prefix_mast": a["code"],
                         "basis": "Independent raters agree on the visible workflow decisions; no contrary adjudication evidence found.",
                         "payment_decision": "No incorrect visible payment-stage decision identified by either rater."})
        full = traces(directory)
        # Full native receipts are retained for every disagreement and the known error.
        if manual:
            item["native_receipts"] = safe_receipts(full, blind["source"])
            item["native_fraud_policy_receipts"] = native_fraud_policy(full)
            item["decision_receipts"] = [
                {"locator": locator(path, seq=step["seq"]), "agent": step.get("agent"),
                 "tool": step.get("name"), "arguments": step.get("arguments"),
                 "output": step.get("output")}
                for path, trace in full for step in trace["steps"]
                if step.get("kind") == "tool" and step.get("name") in
                {"update_invoice_status", "flag_invoice_for_review"}]
            item["document_available_in_description"] = any(
                receipt["tool"] == "get_invoice_details" for receipt in item["native_receipts"])
        if channel == "chat":
            recovered = chat_receipts(directory, blind["source"])
            item["chat_receipts"] = recovered
            if not technical:
                assert not blind["workflow_traces"] and recovered["description_receipt"]
                final = recovered["final_response"]
                assert final and not final["tool_calls"] and not recovered["workflow_launch_calls"]
                assert gold[family]["step"] in {"BLOCK", "REVIEW"}
                item.update({"mast": "NONE", "prefix_mast": "NONE", "recovered_from_sdk": True,
                             "document_available_in_description": True,
                             "basis": "Completed Chat response reads the description and explicitly holds the current invoice for failed or missing decisive contractual evidence. No child workflow was launched; the blind workflow-only projection omitted this completed decision.",
                             "payment_decision": "Current payment withheld consistently with the supplied contractual source; future proposed remediation was not executed.",
                             "guard": {"events": [], "proven_error": False,
                                       "assessment": "No child workflow or P2/P4 checkpoint reached; no guard intervention or guard benefit observed."}})
                if blind_id in decisions.get("nonexecuted_advice_caveats", {}):
                    item["nonexecuted_advice_caveat"] = decisions["nonexecuted_advice_caveats"][blind_id]
        if technical:
            item["technical_sdk_receipts"] = technical_sdk_receipts(directory)
            item["mast"] = "INSUFFICIENT"
            item["basis"] = (manual or {}).get("basis", "Executor interrupted before a decisive payment-stage result. Earlier non-payment/onboarding activity cannot establish the missing final decision.")
            item["observability_limit"] = "Real executor truncation, not merely absent projected workflow. Later payment behavior and unvisited guard checkpoints are unobserved."
        else:
            assert item["mast"] != "INSUFFICIENT"
        item["episode_status"] = {"NONE": "no_detected_error", "3.3": "observed_error",
                                  "INSUFFICIENT": "observability_limit"}[item["mast"]]
        count = aggregates[(channel, arm)]
        count["episodes"] += 1
        count[item["episode_status"]] += 1
        count["rater_code_disagreements"] += dispute
        count["recovered_chat_decisions"] += item.get("recovered_from_sdk", False)
        count["valid_approval_before_cutoff"] += bool(technical and item["prefix_mast"] == "NONE")
        count["unsupported_authenticity_or_intent_assertions"] += bool(item.get("native_review_supported"))
        count["categorical_fabrication_assertions"] += bool(item.get("categorical_fabrication_assertion"))
        count["guard_errors_demonstrated"] += item["guard"]["proven_error"]
        count["guard_checkpoints"] += len(summary["guard"])
        records.append(item)
        for path, _ in full:
            source_files[str(path)] = digest(path)
        if channel == "chat" or technical:
            source_files[str(directory / "calls.jsonl.gz")] = digest(directory / "calls.jsonl.gz")
        source_files[str(summary_path)] = digest(summary_path)
        source_files[str(blind_path)] = digest(blind_path)
    assert all(count["episodes"] == 4 for count in aggregates.values()) and len(aggregates) == 28
    private = corpus / "mast-cal-adjudicated.private.jsonl"
    private.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in records))
    evidence_manifest = corpus / "mast-cal-evidence-manifest.private.json"
    write_json(evidence_manifest, {"scope": "CAL only", "sources": source_files,
                                 "frozen_artifacts": frozen, "decisions_sha256": digest(decisions_path)})
    columns = ["channel", "arm", "episodes", "no_detected_error", "observed_error",
               "observability_limit", "rater_code_disagreements", "recovered_chat_decisions",
               "valid_approval_before_cutoff", "unsupported_authenticity_or_intent_assertions",
               "categorical_fabrication_assertions", "guard_errors_demonstrated", "guard_checkpoints"]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for (channel, arm), count in sorted(aggregates.items()):
        writer.writerow({"channel": channel, "arm": arm,
                         **{column: count[column] for column in columns[2:]}})
    public.mkdir(parents=True, exist_ok=True)
    csv_path = public / "mast_cal.csv"
    csv_path.write_text(output.getvalue())
    totals = sum(aggregates.values(), collections.Counter())
    assert totals["episodes"] == 112
    assert (totals["no_detected_error"], totals["observed_error"], totals["observability_limit"]) == (98, 1, 13)
    assert all(digest(corpus / name) == sha for name, sha in frozen.items())
    write_json(public / "mast_cal_manifest.json", {
        "version": "cal-observed-mast-adjudication-v1", "scope": "112 CAL episodes, 16 families, seven arms; no closed TEST execution results opened",
        "counts": dict(totals), "observed_mast_counts": dict(collections.Counter(item["mast"] for item in records)),
        "sha256": {"mast_cal.csv": digest(csv_path), "private_evidence": digest(private),
                   "rebuild_script": digest(Path(__file__)),
                   "private_evidence_manifest": digest(evidence_manifest), "private_curator_decisions": digest(decisions_path),
                   "medium": digest(medium_path), "high": digest(high_path), "cal_key": digest(key_path)},
        "frozen_artifacts_unchanged": frozen,
        "interpretation": decisions["interpretation"],
        "limitations": decisions["limitations"],
    })
    print(json.dumps({"counts": dict(totals), "private_evidence_sha256": digest(private),
                      "public_csv_sha256": digest(csv_path)}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--public", type=Path, default=Path(__file__).parent)
    run(parser.parse_args())
