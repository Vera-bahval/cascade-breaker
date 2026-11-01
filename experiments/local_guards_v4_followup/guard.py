"""v4.2 origin validation around the unchanged frozen business evaluator.

The trusted producer, rather than caller-supplied JSON, authenticates evidence.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import FunctionType

from experiments.local_guards_v4 import guard as frozen

_ROOT = Path(__file__).resolve().parent
_REGISTRY = json.loads((_ROOT / "policy.json").read_text())
_SCHEMA = json.loads((_ROOT / "schema.json").read_text())
_ORIGIN_FIELDS = {"evidence_kind", "source_call_id", "snapshot_id", "parent_workflow_id",
                  "delegated_workflow_id", "delegation_call_id"}
_PARENT_FIELDS = ("parent_workflow_id", "delegated_workflow_id", "delegation_call_id")


def origin_valid(key, proof):
    """Origin compatibility only; scope/time/value/version remain separate checks.

    A trace reference is not a signature. This helper assumes an admitted producer.
    """
    if not isinstance(proof, dict):
        return False
    kind, source = proof.get("evidence_kind"), proof.get("source")
    if not isinstance(source, str):
        return False
    if key in {"human_approved", "human_cleared"}:
        return kind == "independent_registry" and source == "independent_registry"
    if kind == "independent_registry":
        return source == "independent_registry"
    if kind == "declared_fixture":
        return source == "initial_fixture" or (key == "invoice_currency" and
            source == "server_context" and proof.get("operation") == "currency_contract_attest")
    # Native Invoice has no currency. Only an explicitly supplied ledger contract
    # or independent authoritative currency record can establish this field.
    if key == "invoice_currency":
        return False
    if kind == "tool_result":
        return source == "native_tool" and frozen._nonempty(proof.get("source_call_id"))
    if kind == "server_snapshot":
        if key in {"fraud_review_completed", "binding_hold"}:
            return False  # Native DB has no substantive review/HOLD fields.
        return source in {"server_context", "native_tool"} and frozen._nonempty(proof.get("snapshot_id"))
    return False


def _shape(obj):
    if not isinstance(obj, dict):
        return False
    projected = deepcopy(obj)
    ctx = projected.get("context")
    if isinstance(ctx, dict):
        child = ctx.pop("delegated_workflow_id", None)
        if child is not None and not frozen._nonempty(child):
            return False
    provenance = projected.get("provenance")
    if isinstance(provenance, dict):
        for records in provenance.values():
            if isinstance(records, list):
                for proof in records:
                    if isinstance(proof, dict):
                        for key in _ORIGIN_FIELDS:
                            proof.pop(key, None)
    return frozen._shape(projected)


def _proofs(obj):
    """Newest same-scope record wins selection even when its origin is invalid."""
    projected = deepcopy(obj)
    ctx = obj.get("context") or {}
    diagnostics = []
    for key in _SCHEMA["properties"]["facts"]["properties"]:
        candidates = [p for p in obj["provenance"].get(key, [])
            if frozen._integer(p.get("event_seq")) and p["event_seq"] < obj["event_seq"]
            and all(k in p and p[k] == ctx.get(k) for k in frozen._SCOPE)
            and (key == "session_valid" or all(p.get(k) == ctx[k]
                for k in ("vendor_id", "invoice_id") if ctx.get(k) is not None))]
        latest = max((p["event_seq"] for p in candidates), default=None)
        newest = [p for p in candidates if p["event_seq"] == latest]
        valid = bool(newest) and all(origin_valid(key, p) for p in newest)
        if key == "delegation_subject_matches":
            valid = valid and all(frozen._nonempty(ctx.get(k)) and
                all(p.get(k) == ctx[k] for p in newest) for k in _PARENT_FIELDS)
            valid = valid and all(p.get("evidence_kind") == "server_snapshot" and
                p.get("source") == "server_context" for p in newest)
        if newest and not valid:
            diagnostics.append(dict(fact=key, status="latest_origin_or_parent_invalid",
                                    checkpoint=obj["checkpoint"], event_seq=latest))
        projected["provenance"][key] = deepcopy(newest) if valid else []
        for p in projected["provenance"][key]:
            if (p["evidence_kind"] == "server_snapshot" and p["source"] == "server_context"
                    and p["source"] not in frozen._sources(key)):
                # Representation-only bridge after direct server origin validation.
                p["source"] = "native_tool"
    values, accepted, evidence = frozen._proofs(projected)
    for entry in evidence:
        key = entry["fact"]
        if key in accepted and "record_id" in entry:
            original = next(p for p in obj["provenance"][key]
                if p.get("record_id") == entry["record_id"] and p.get("event_seq") == entry["event_seq"])
            for field in ("evidence_kind", "source_call_id", "snapshot_id"):
                if field in original:
                    entry[field] = original[field]
    return values, accepted, evidence + diagnostics


# Each function sees a private globals view: no monkeypatching frozen modules or
# process-global policy state, including when A/B evaluations run concurrently.
_globals = dict(vars(frozen), _REGISTRY=_REGISTRY, _SCHEMA=_SCHEMA,
                _shape=_shape, _proofs=_proofs)
_selection = FunctionType(frozen._selection.__code__, _globals)
_globals["_selection"] = _selection
guard = FunctionType(frozen.guard.__code__, _globals, "guard", frozen.guard.__defaults__)
