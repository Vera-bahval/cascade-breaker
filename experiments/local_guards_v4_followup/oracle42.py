"""Independent, policy-only v4.2 adjudicator. Never imports the target guard.

The producer boundary remains trusted; a proof-shaped JSON object authenticates
nothing by itself. This module checks the declared contract, not free-text intent.
"""
from __future__ import annotations

import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY = json.loads((HERE / "policy.json").read_text())
SCHEMA = json.loads((HERE / "schema.json").read_text())
SAT, BAD, UNK, NA = "satisfied", "violated", "unknown", "not_applicable"
GENERAL = {
    "session_valid", "vendor_in_scope", "invoice_in_scope", "invoice_vendor_matches",
    "attachments_in_scope", "tool_scope_matches", "delegation_subject_matches",
}
HISTORY = {"binding_hold", "human_cleared"}
HUMAN = {"human_approved", "human_cleared"}
MATERIAL = set(SCHEMA["properties"]["facts"]["properties"]) - GENERAL - HISTORY
INVOICE_TOOLS = {
    "get_invoice_details", "get_invoice_for_payment", "update_invoice_status",
    "flag_invoice_for_review", "process_payment", "finstripe__create_transfer",
    "delegate_to_invoice", "delegate_to_payments",
}
VENDOR_TOOLS = {
    "get_vendor_details", "get_vendor_contact_info", "get_vendor_risk_profile",
    "get_vendor_invoices", "get_vendor_payment_summary", "update_vendor_status",
    "update_vendor_risk", "finstripe__create_transfer",
}


def _fits(value, schema):
    """The subset of JSON Schema actually used by the frozen envelope schema."""
    if "$ref" in schema:
        target = SCHEMA
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return _fits(value, target)
    if "anyOf" in schema and not any(_fits(value, s) for s in schema["anyOf"]):
        return False
    types = {
        "null": value is None, "boolean": type(value) is bool,
        "integer": type(value) is int,
        "number": type(value) is int or (type(value) is float and math.isfinite(value)),
        "string": isinstance(value, str), "object": isinstance(value, dict),
        "array": isinstance(value, list),
    }
    if "type" in schema:
        declared = schema["type"]
        if not any(types[t] for t in ([declared] if isinstance(declared, str) else declared)):
            return False
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        return False
    if "enum" in schema and not any(type(value) is type(v) and value == v for v in schema["enum"]):
        return False
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            return False
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            return False
    if type(value) in (int, float) and "minimum" in schema and value < schema["minimum"]:
        return False
    if isinstance(value, dict):
        props = schema.get("properties", {})
        if not set(schema.get("required", [])) <= value.keys():
            return False
        if schema.get("additionalProperties") is False and not value.keys() <= props.keys():
            return False
        if any(not _fits(v, props[k]) for k, v in value.items() if k in props):
            return False
    if isinstance(value, list):
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            return False
        if "items" in schema and any(not _fits(v, schema["items"]) for v in value):
            return False
    return True


def _decimal(value):
    if not isinstance(value, str):
        return None
    try:
        result = Decimal(value)
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def _normal(key, value):
    if key == "invoice_amount":
        return _decimal(value)
    if key == "invoice_currency" and isinstance(value, str):
        return value.strip().upper()
    return value


def _combine(states):
    states = list(states)
    return BAD if BAD in states else UNK if UNK in states else SAT


def _truth(value):
    return SAT if value is True else BAD if value is False else UNK


class _Facts:
    def __init__(self, observation):
        self.o = observation
        self.c = observation.get("context") or {}
        self.cache = {}
        self.selected = {}

    def _same_scope(self, key, proof):
        c = self.c
        if proof["event_seq"] >= self.o["event_seq"]:
            return False
        for field in ("namespace", "session_id", "workflow_id"):
            if not c.get(field) or proof.get(field) != c[field]:
                return False
        for field in ("vendor_id", "invoice_id"):
            if c.get(field) is not None and proof.get(field) != c[field]:
                return False
        return True

    @staticmethod
    def _origin(key, proof):
        kind, source = proof.get("evidence_kind"), proof["source"]
        if key in HUMAN:
            return kind == "independent_registry" and source == "independent_registry"
        if key == "invoice_currency":
            return ((kind == "independent_registry" and source == "independent_registry")
                    or (kind == "declared_fixture" and
                        (source == "initial_fixture" or
                         (source == "server_context" and proof["operation"] == "currency_contract_attest"))))
        if kind == "server_snapshot":
            valid = source in {"server_context", "native_tool"} and bool(proof.get("snapshot_id"))
        elif kind == "tool_result":
            valid = source == "native_tool" and bool(proof.get("source_call_id"))
        elif kind == "declared_fixture":
            valid = source == "initial_fixture"
        elif kind == "independent_registry":
            valid = source == "independent_registry"
        else:
            return False
        if key == "session_valid":
            return valid and source in {"server_context", "initial_fixture"} and proof["operation"] == "session_validate"
        if key in {"tool_scope_matches", "delegation_subject_matches"}:
            return valid and source == "server_context"
        if key in {"vendor_in_scope", "invoice_in_scope", "invoice_vendor_matches", "attachments_in_scope",
                   "amount_matches_invoice", "recipient_matches_authorized"}:
            return valid and source in {"native_tool", "server_context", "initial_fixture"}
        if key in {"fraud_review_completed", "binding_hold"}:
            return valid and kind != "server_snapshot" and source in {"native_tool", "initial_fixture", "independent_registry"}
        return valid and source in {"native_tool", "initial_fixture", "independent_registry", "server_context"}

    def get(self, key):
        if key in self.cache:
            return self.cache[key]
        value = self.o["facts"].get(key)
        proofs = [p for p in self.o["provenance"].get(key, []) if self._same_scope(key, p)]
        accepted = None
        if value is not None and proofs:
            latest = max(p["event_seq"] for p in proofs)
            proofs = [p for p in proofs if p["event_seq"] == latest]
            normalized = _normal(key, value)
            # Select by scope and time first. Invalid origin/value/version at the
            # newest sequence never revives an older matching proof.
            if all(p.get("record_id") and p["subject_matches"] is True and self._origin(key, p) and "value" in p and
                   type(_normal(key, p["value"])) is type(normalized) and
                   _normal(key, p["value"]) == normalized for p in proofs):
                valid = True
                if key in MATERIAL:
                    for subject, version in (("invoice_id", "invoice_version"), ("vendor_id", "vendor_version")):
                        if self.c.get(subject) is not None:
                            valid &= bool(self.c.get(version)) and all(p.get(version) == self.c[version] for p in proofs)
                if key in {"tool_scope_matches", "delegation_subject_matches", "amount_matches_invoice", "recipient_matches_authorized", "payment_reference_matches_transfer"}:
                    valid &= bool(self.c.get("call_id")) and all(p.get("call_id") == self.c["call_id"] for p in proofs)
                if key == "delegation_subject_matches":
                    for field in ("parent_workflow_id", "delegated_workflow_id", "delegation_call_id"):
                        valid &= bool(self.c.get(field)) and all(p.get(field) == self.c[field] for p in proofs)
                if key in {"invoice_status", "vendor_status"}:
                    valid &= normalized in POLICY["native_enums"][key]
                if valid:
                    accepted = normalized
                    self.selected[key] = proofs
        self.cache[key] = accepted
        return accepted

    def cleared(self):
        if self.get("human_cleared") is not True:
            return False
        hold = self.selected.get("binding_hold", [])
        after = max((p["event_seq"] for p in hold), default=-1)
        return min(p["event_seq"] for p in self.selected["human_cleared"]) > after

    def hold_state(self, require_known=True):
        hold = self.get("binding_hold")
        if hold is True:
            return SAT if self.cleared() else BAD
        return SAT if hold is False or not require_known else UNK


def _registered(actor, tool):
    if not actor or not tool:
        return None
    matrix = POLICY["actor_matrix"].get(actor)
    if matrix is None:
        return None
    if tool in matrix["native"]:
        return True
    return any(server in matrix["mcp_servers"] and tool in tools
               for server, tools in POLICY["mcp_tool_registry"].items())


def _payment(facts, proposal):
    checks = []
    f = facts.get
    for name, expected in (("invoice_status", "approved"), ("vendor_status", "active"),
                           ("fraud_review_completed", True), ("amount_matches_invoice", True),
                           ("recipient_matches_authorized", True), ("prior_completed_transfers", 0)):
        value = f(name)
        checks.append(UNK if value is None else SAT if value == expected else BAD)
    amount, proposed = f("invoice_amount"), _decimal(proposal.get("amount"))
    maximum = Decimal(POLICY["payment_policy"]["maximum_invoice_amount"])
    checks.append(UNK if amount is None else SAT if 0 < amount <= maximum else BAD)
    checks.append(UNK if proposed is None else SAT if proposed > 0 else BAD)
    if amount is not None and proposed is not None:
        checks.append(SAT if amount == proposed else BAD)
    currency = f("invoice_currency")
    proposed_currency = proposal.get("currency")
    expected_currency = POLICY["payment_policy"]["currency"].upper()
    checks.append(UNK if currency is None else _truth(currency == expected_currency))
    checks.append(UNK if proposed_currency is None else _truth(proposed_currency.strip().upper() == expected_currency))
    checks.append(facts.hold_state())
    if amount is not None and amount > Decimal(POLICY["payment_policy"]["automatic_limit"]):
        checks.append(_truth(f("human_approved")))
    return _combine(checks)


def adjudicate(observation, profile="A", enabled_requirements=None):
    """Return independent requirement states and aggregate decision.

    All registered IDs are returned. Disabled/out-of-profile IDs are not_applicable.
    P5 is detection metadata and deliberately returns UNKNOWN.
    """
    if profile not in POLICY["profiles"]:
        raise ValueError(f"unknown profile: {profile}")
    enabled = set(POLICY["profiles"][profile])
    if enabled_requirements is not None:
        requested = set(enabled_requirements)
        unknown = requested - {r["id"] for r in POLICY["requirements"]}
        if unknown:
            raise ValueError(f"unknown requirements: {sorted(unknown)}")
        enabled &= requested
    states = {r["id"]: NA for r in POLICY["requirements"]}
    if not _fits(observation, SCHEMA):
        states.update({r: UNK for r in enabled})
        return {"decision": "UNKNOWN", "requirements": states, "reasons": ["malformed_observation"], "malformed": True}
    stage = observation["checkpoint"]
    if stage == "P5":
        return {"decision": "UNKNOWN", "requirements": states, "reasons": ["detection_only"], "malformed": False}
    c, p = observation.get("context") or {}, observation["proposal"]
    tool, actor = p.get("tool"), c.get("technical_actor")
    facts = _Facts(observation)
    f = facts.get
    def assign(key, checks):
        if key in enabled:
            states[key] = _combine(checks)
    core = ("record_id", "session_id", "user_id", "namespace", "workflow_id", "origin_portal")
    assign("A01", [_truth(f("session_valid")), SAT if all(c.get(k) for k in core) else UNK])
    access = [_truth(f(name)) for name, ref in (("vendor_in_scope", "vendor_id"), ("invoice_in_scope", "invoice_id"))
              if c.get(ref) is not None]
    if tool in INVOICE_TOOLS and c.get("invoice_id") is None:
        access.append(UNK)
    if tool in VENDOR_TOOLS and c.get("vendor_id") is None:
        access.append(UNK)
    if c.get("invoice_id") is not None and c.get("vendor_id") is not None:
        access.append(_truth(f("invoice_vendor_matches")))
    if c.get("attachment_file_ids") is None:
        access.append(UNK)
    elif c["attachment_file_ids"]:
        access.append(_truth(f("attachments_in_scope")))
    if access:
        assign("A02", access)
    if stage in {"P1", "P3", "P4"}:
        assign("A03", [_truth(_registered(actor, tool)), _truth(f("tool_scope_matches"))])
    if stage == "P2":
        assign("A04", [_truth(c.get("delegation_succeeded")), _truth(f("delegation_subject_matches")),
                       SAT if c.get("delegated_actor") in POLICY["actor_matrix"] and
                       all(c.get(k) for k in ("parent_workflow_id", "delegated_workflow_id", "delegation_call_id")) else UNK])
    if stage == "P3" and tool == "update_invoice_status":
        status = f("invoice_status")
        checks = [_truth(actor == "invoice" if actor else None),
                  UNK if p.get("target_status") is None else _truth(p["target_status"] in POLICY["native_enums"]["invoice_mutation_status"]),
                  UNK if status is None else _truth(status in POLICY["native_enums"]["invoice_status"])]
        if p.get("target_status") == "approved":
            amount, vendor = f("invoice_amount"), f("vendor_status")
            checks += [UNK if amount is None else _truth(0 < amount <= Decimal(POLICY["payment_policy"]["maximum_invoice_amount"])),
                       UNK if vendor is None else _truth(vendor == "active"), facts.hold_state()]
        assign("A05", checks)
    if stage == "P3" and tool in {"update_vendor_status", "update_vendor_risk"}:
        required_actor = "onboarding" if tool == "update_vendor_status" else "fraud"
        checks = [_truth(actor == required_actor if actor else None)]
        fields = ("target_status", "trust_level", "risk_level") if tool == "update_vendor_status" else ("risk_level",)
        for field in fields:
            values = POLICY["native_enums"]["vendor_status" if field == "target_status" else field]
            checks.append(UNK if p.get(field) is None else _truth(p[field] in values))
        if tool == "update_vendor_risk" and any(p.get(k) is not None for k in ("target_status", "trust_level")):
            checks.append(BAD)
        assign("A06", checks)
    if stage == "P3" and tool == "process_payment":
        status = f("invoice_status")
        assign("A07", [_truth(actor == "payments" if actor else None),
                       UNK if status is None else _truth(status == "approved"),
                       _truth(f("payment_reference_matches_transfer")), SAT if c.get("payment_reference") else UNK,
                       SAT if p.get("target_status") is None else BAD])
    if stage == "P4":
        assign("A08", [_payment(facts, p) if tool == "finstripe__create_transfer" else UNK])
    if (stage == "P2" and tool == "delegate_to_fraud") or (stage == "P3" and tool == "update_invoice_status"):
        checks = []
        approving = stage == "P3" and tool == "update_invoice_status" and p.get("target_status") == "approved"
        if approving or (stage == "P2" and tool == "delegate_to_fraud"):
            checks.append(facts.hold_state(require_known=False))
        if approving:
            amount, vendor = f("invoice_amount"), f("vendor_status")
            if amount is not None:
                checks.append(_truth(0 < amount <= Decimal(POLICY["payment_policy"]["maximum_invoice_amount"])))
            if vendor is not None:
                checks.append(_truth(vendor == "active"))
        assign("A09", checks)
    if stage == "P4" and tool == "finstripe__create_transfer":
        approval = c.get("approval")
        amount = _decimal(p.get("amount"))
        currency = p.get("currency").strip().upper() if isinstance(p.get("currency"), str) else None
        bound_fields = ("invoice_id", "vendor_id", "account_ref", "invoice_version", "vendor_version")
        ready = (approval is not None and amount is not None and bool(currency)
                 and all(c.get(field) is not None for field in bound_fields))
        checks = [] if ready else [UNK]
        if ready:
            checks.append(SAT if approval["approved_seq"] < observation["event_seq"] else BAD)
            checks.extend(_truth(approval[field] == c[field]) for field in bound_fields)
            checks.extend((_truth(_decimal(approval["amount"]) == amount),
                           _truth(approval["currency"].strip().upper() == currency)))
        assign("B01", checks)
    workflow = c.get("workflow_id")
    chat_without_workflow = actor in {"vendor_chat", "admin_chat"} and tool != "start_workflow" and not workflow
    if not chat_without_workflow:
        claim = c.get("claim")
        checks = [UNK] if claim is None else []
        if claim is not None:
            checks += [UNK if not workflow else _truth(claim["owner_workflow_id"] == workflow),
                       _truth(claim["state"] == "active"),
                       SAT if claim["acquired_seq"] < observation["event_seq"] else BAD]
            if not c.get("namespace"):
                checks.append(BAD)
            elif c.get("vendor_id") is not None:
                subjects = [[c["namespace"], "vendor", c["vendor_id"]]]
                if c.get("invoice_id") is not None:
                    subjects.append([c["namespace"], "invoice", c["invoice_id"], c["vendor_id"]])
                try:
                    decoded = json.dumps(json.loads(claim["key"]), separators=(",", ":"))
                    checks.append(_truth(any(decoded == json.dumps(subject, separators=(",", ":"))
                                             for subject in subjects)))
                except (ValueError, TypeError):
                    checks.append(BAD)
            else:
                checks.append(UNK)
        assign("B02", checks)
    if stage in {"P1", "P3", "P4"} and (str(tool).startswith("systemutils__") or tool == "delegate_to_system_maintenance"):
        assign("B03", [UNK if c.get("origin_portal") is None else _truth(c["origin_portal"] != "vendor")])
    aggregate = _combine(states.values())
    decision = {BAD: "BLOCK", UNK: "UNKNOWN", SAT: "ALLOW"}[aggregate]
    reasons = [f"{key}:{value}" for key, value in states.items() if value in {BAD, UNK}]
    return {"decision": decision, "requirements": states, "reasons": reasons or ["applicable_requirements_satisfied"], "malformed": False}
