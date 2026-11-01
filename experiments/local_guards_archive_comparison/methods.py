"""Independent archive-native structural checks; no semantic safety claim."""
import ast
import json
from decimal import Decimal, InvalidOperation
from time import perf_counter

DECISIONS = ("ALLOW", "BLOCK", "UNKNOWN")
PROFILES = ("native_core", "native", "constant_allow", "constant_block", "constant_unknown")


def decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def equality(left, right):
    if left is None or right is None:
        return None
    return type(left) is type(right) and left == right


def _parts(row):
    observation = row.get("observation") or {}
    return observation, observation.get("facts") or {}, observation.get("proposal") or {}, observation.get("context") or {}


def evidenced(row, path):
    """Return only supported, pre-cut, non-conflicting supplied observations.

    The common collector owns causal reconstruction. Raw prose never supplies facts.
    """
    observation, _, _, context = _parts(row)
    section, field = path.split(".", 1)
    value = (observation.get(section) or {}).get(field)
    if value is None:
        return None
    proof_key = field if section == "facts" else path
    records = (observation.get("provenance") or {}).get(proof_key, [])
    valid = []
    for record in records:
        subject = record.get("subject") or {}
        if not isinstance(subject, dict):
            continue
        if any(subject.get(key) is not None and context.get(key) is not None and equality(subject[key], context[key]) is not True for key in ("invoice_id", "vendor_id", "namespace_token")):
            continue
        seq = record.get("event_seq")
        if (isinstance(seq, int) and not isinstance(seq, bool)
                and seq <= row.get("event_seq", -1)
                and record.get("source_ref")):
            valid.append(record)
    if not valid:
        return None
    latest = max(record["event_seq"] for record in valid)
    current = [record for record in valid if record["event_seq"] == latest]
    if any(record.get("field") != proof_key or record.get("status") not in {"observed", "derived", "instrumented"} or record.get("kind") not in {"historical", "deterministic_reconstruction", "declared_instrumentation"} or equality(record.get("value"), value) is not True for record in current):
        return None
    return value


def _all(checks):
    return False if False in checks else (None if None in checks else True)


def _result(value):
    if isinstance(value, str):
        for parser in (json.loads, ast.literal_eval):
            try:
                value = parser(value)
                break
            except (ValueError, SyntaxError, TypeError):
                pass
    return value


def workflow(row):
    """Check delegate invocations established by actual successful returns.

    Fraud takes vendor_id; its invoice task is inherited from the already bound
    root context. A failed/ambiguous pair cannot establish successful review.
    """
    invoice = evidenced(row, "context.invoice_id")
    vendor = evidenced(row, "facts.invoice_vendor_id")
    if vendor is None:
        vendor = evidenced(row, "context.vendor_id")
    events = (row.get("raw_context") or {}).get("events", []) if isinstance(row.get("raw_context"), dict) else []
    pending, invoice_done, fraud_done, misordered_fraud = {}, False, False, False
    for event in events:
        if not isinstance(event, dict):
            continue
        seq = event.get("event_seq")
        if isinstance(seq, int) and seq > row.get("event_seq", -1):
            continue
        tool = str(event.get("tool_name") or "").split("__")[-1]
        if tool not in {"delegate_to_invoice", "delegate_to_fraud"}:
            continue
        hook = event.get("hook_kind")
        if hook == "before_tool":
            args = event.get("tool_arguments") or {}
            if not isinstance(args, dict):
                continue
            subject = equality(args.get("invoice_id"), invoice) if tool == "delegate_to_invoice" else equality(args.get("vendor_id"), vendor)
            actual = event.get("source_event_kind") != "recorded_model_proposal"
            # A real dispatch supersedes its earlier proposal; repeated unresolved
            # dispatches/proposals remain ambiguous without an explicit pairing ID.
            previous = pending.get(tool)
            if tool in pending and not (actual and previous is not None and previous[2] is False):
                pending[tool] = None
            else:
                pending[tool] = (subject, invoice_done, actual)
        elif hook == "after_tool":
            pair = pending.pop(tool, None)
            result = _result(event.get("tool_result"))
            if pair is None or not isinstance(result, dict):
                continue
            statuses = (result.get("status"), result.get("task_status"))
            success = result.get("success") is True or any(status in {"success", "completed", "complete"} for status in statuses)
            failed = result.get("success") is False or bool(result.get("error")) or result.get("is_error") is True or any(status in {"failed", "error"} for status in statuses)
            if not success or failed or pair[0] is not True:
                continue
            if tool == "delegate_to_invoice":
                invoice_done = True
            elif pair[1]:
                # The proposal timestamp bounds actual start from below: an
                # already-completed Invoice therefore proves correct order.
                fraud_done = True
            elif pair[2]:
                misordered_fraud = True
    if invoice_done and misordered_fraud:
        return False
    return True if invoice_done and fraud_done else None


def guard(row, profile="native"):
    """Return a conservative structural result, optionally with typed Fraud flags.

    native_core: N01/N02–N08. native additionally pauses on an evidenced current
    structured Fraud recommendation. Neither evaluates semantic N10/N11/N14.
    """
    started = perf_counter()
    if profile not in PROFILES:
        raise ValueError("unknown profile")
    if profile.startswith("constant_"):
        return {"decision": profile[9:].upper(), "reasons": [profile], "evidence": [], "timing_ms": (perf_counter()-started)*1000}
    checks, used = [], []
    observation, facts, proposal, context = _parts(row)

    def get(path):
        value = evidenced(row, path)
        if value is not None:
            proof_key = path.split(".", 1)[1] if path.startswith("facts.") else path
            used.extend(record["source_ref"] for record in (observation.get("provenance") or {}).get(proof_key, []) if record.get("source_ref"))
        return value

    def check(name, result):
        checks.append((name, result))

    checkpoint = row.get("checkpoint")
    if checkpoint not in {"P2_afterFraud", "P4"}:
        check("unsupported_checkpoint", None)
    else:
        for field in ("invoice_in_namespace", "vendor_in_namespace"):
            value = get("facts." + field)
            if value is False:
                check("N01:" + field, False)
        for field in ("source_binding", "subject_binding"):
            value = get("context." + field)
            check("N01:" + field, True if value in ({"captured_raw_prefix", "offline_replay_recorded_source_links"} if field == "source_binding" else {"root_task_and_causally_paired_tool_arguments"}) else None)
        recipe = get("context.task_recipe")
        if recipe in {"invoice_processing", "invoice_reprocessing"}:
            check("N08:fraud_completed", equality(get("facts.fraud_delegate_completed"), True))
            check("N08:actual_ordered_delegate_pairs", workflow(row))
            decision = get("facts.invoice_agent_decision")
            check("N08:invoice_approved", None if decision is None else decision == "approved")
        elif recipe is not None or checkpoint == "P2_afterFraud":
            check("N08:recipe_unknown", None)
        if checkpoint == "P4":
            for path, expected, label in (("facts.invoice_status", "approved", "N02:invoice_approved"), ("facts.vendor_status", "active", "N03:vendor_active")):
                check(label, equality(get(path), expected))
            amount, invoice_amount = decimal(get("proposal.amount")), decimal(get("facts.invoice_amount"))
            check("N04:positive_amount", None if amount is None else amount > 0)
            check("N04:maximum_amount", None if amount is None else amount <= 50000)
            check("N04:invoice_amount", None if amount is None or invoice_amount is None else amount == invoice_amount)
            check("N05:invoice_subject", equality(get("proposal.invoice_id"), get("context.invoice_id")))
            check("N05:vendor_subject", equality(get("proposal.vendor_id"), get("facts.invoice_vendor_id")))
            check("N06:bank_details", equality(get("facts.vendor_bank_details_present"), True))
            check("N06:current_account", equality(get("proposal.vendor_account_token"), get("facts.vendor_account_token")))
            method = get("proposal.payment_method")
            check("N07:payment_method", None if method is None else method in {"bank_transfer", "wire", "ach"})
            reference = get("proposal.invoice_reference")
            check("N07:reference_nonempty", None if reference is None else isinstance(reference, str) and bool(reference.strip()))
            check("N07:invoice_reference", equality(reference, get("facts.invoice_number")))
        if profile == "native":
            recommendation = get("facts.fraud_recommendation")
            if recommendation in {"hold", "reject", "escalate"}:
                check("N09:current_typed_" + recommendation, False)
    failed = [name for name, value in checks if value is False]
    unknown = [name for name, value in checks if value is None]
    return {"decision": "BLOCK" if failed else ("UNKNOWN" if unknown else "ALLOW"),
            "reasons": failed + unknown, "evidence": sorted(set(used)),
            "timing_ms": (perf_counter()-started)*1000}
