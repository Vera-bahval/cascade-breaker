"""Native v4.2 adapter through the frozen FinBot v4 bridge; no model client.

Sidecar state remains limited to covered runtime writers, not DB atomicity.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from time import perf_counter
from types import MappingProxyType
from uuid import uuid4

from finbot.probe import v4
from experiments.local_guards_v4 import runtime as frozen
from .guard import guard, _REGISTRY, _selection

_DELEGATION_MATCH = ContextVar("v42_delegation_match", default=None)


class Runtime(frozen.Runtime):
    def __init__(self, path, profile="A", *, fixture_contract=None, owner=None,
                 diagnostics=False, check_observer=None, policy=None):
        configured = {"profile": profile} if policy is None else deepcopy(policy)
        if isinstance(configured, str):
            configured = {"profile": configured}
        if not isinstance(configured, dict):
            raise ValueError("invalid policy")
        configured.setdefault("profile", profile)
        selected = _selection(configured)
        if selected is None or configured["profile"] != profile:
            raise ValueError("invalid policy or profile mismatch")
        self.requested_profile = profile
        self.policy = MappingProxyType(dict(profile=profile, enabled_requirements=tuple(
            key for key in _REGISTRY["profiles"][profile] if key in selected)))
        # The frozen bridge uses profile only to filter vendor SystemUtils servers.
        compatibility_profile = "B" if "B03" in selected else "A"
        super().__init__(path, compatibility_profile, fixture_contract=fixture_contract, owner=owner)
        self.diagnostics = bool(diagnostics)
        self.diagnostic_records = []
        self.decisions = self.diagnostic_records
        self.check_observer = check_observer
        self._agent_subjects = {}

    @contextmanager
    def agent_scope(self, agent, task_data):
        # These are the arguments actually handed to the instantiated native agent.
        # Their claimed authority is never accepted; linkage is compared separately.
        self._agent_subjects[agent] = {key: deepcopy(task_data[key])
            for key in ("vendor_id", "invoice_id", "attachment_file_ids") if key in task_data}
        with super().agent_scope(agent, task_data):
            yield self

    def _put(self, obj, key, value, source="native_tool", operation="native_snapshot", **extra):
        if key == "delegation_subject_matches":
            value = _DELEGATION_MATCH.get()
        if value is None:
            return
        if "event_seq" not in extra:
            extra["event_seq"] = self.tick()
        super()._put(obj, key, value, source, operation, **extra)
        proof = obj["provenance"][key][-1]
        if source == "independent_registry":
            proof["evidence_kind"] = "independent_registry"
        elif source == "initial_fixture" or operation == "currency_contract_attest":
            proof["evidence_kind"] = "declared_fixture"
        else:
            proof.update(evidence_kind="server_snapshot", snapshot_id=obj["context"]["record_id"])
        if key == "delegation_subject_matches":
            for field in ("parent_workflow_id", "delegated_workflow_id", "delegation_call_id"):
                proof[field] = obj["context"].get(field)

    def acquire(self):
        if "B02" not in self.policy["enabled_requirements"] or self.admitted:
            return
        try:
            self.store.acquire_claim(self.session.namespace, self.envelope["vendor_id"],
                self.envelope["invoice_id"], self.owner, self.tick())
        except frozen.ClaimConflict:
            self.stop(dict(decision="BLOCK", reasons=["B02:violated", "workflow_claim_conflict"],
                stop=True, evidence=[], timing_ms=0., requirements=[{"id":"B02","state":"violated"}]))
        except Exception:
            self.fail("workflow_claim_unavailable")
        self.admitted = True

    def snapshot(self, checkpoint, agent, tool, arguments, **extra_context):
        obj = super().snapshot(checkpoint, agent, tool, arguments, **extra_context)
        ctx = obj["context"]
        if ("B02" in self.policy["enabled_requirements"] and
                (ctx["technical_actor"] not in {"vendor_chat", "admin_chat"} or tool == "start_workflow")):
            ctx["claim"] = self.store.claim(self.owner)
        else:
            ctx.pop("claim", None)
        # Stored typed results retain the invocation that produced the observation.
        # A later server read does not turn an unbound historical result into proof.
        recorded = {event["payload"]["record_id"]: event["payload"]
            for event in self.store.events(self.subject_key(ctx["invoice_id"], ctx["vendor_id"]))
            if event["kind"] == "typed_fact"}
        for records in obj["provenance"].values():
            for proof in records:
                payload = recorded.get(proof["record_id"])
                if payload is not None:
                    proof.update(evidence_kind="tool_result", source_call_id=payload.get("source_call_id"))
                    proof.pop("snapshot_id", None)
        # The cut follows all native reads and working evidence/store construction.
        obj["event_seq"] = self.tick()
        return obj

    def check(self, checkpoint, agent, tool, arguments, **extra):
        self.raise_if_stopped()
        started = perf_counter()
        try:
            obj = self.snapshot(checkpoint, agent, tool, arguments, **extra)
            snapshot_done = perf_counter()
            result = guard(obj, dict(profile=self.requested_profile,
                enabled_requirements=list(self.policy["enabled_requirements"])))
            decision_done = perf_counter()
            if self.diagnostics:
                self.diagnostic_records.append(dict(checkpoint=checkpoint, tool=tool,
                    observation=deepcopy(obj), **deepcopy(result)))
            diagnostics_done = perf_counter()
            timings = dict(snapshot_ms=(snapshot_done-started)*1000,
                decision_ms=(decision_done-snapshot_done)*1000,
                diagnostics_ms=(diagnostics_done-decision_done)*1000,
                whole_check_ms=(diagnostics_done-started)*1000)
            if self.check_observer is not None:
                self.check_observer(obj, result, timings)
            if result["stop"]:
                self.stop(result)
            return obj
        except v4.V4Stop:
            raise
        except Exception:
            self.fail("verifier_exception")

    def typed_fact(self, obj, key, value, operation):
        self.store.record_event(self.subject_key(obj["context"]["invoice_id"], obj["context"]["vendor_id"]),
            "typed_fact", dict(key=key, value=value, operation=operation,
                context=obj["context"], record_id=uuid4().hex,
                source_call_id=obj["context"]["call_id"]), self.tick())

    def child_complete(self, agent, result):
        parent = frozen._INVOKING.get()
        if not parent or not parent[1].startswith("delegate_to_"):
            return super().child_complete(agent, result)
        source, name, args, parent_obj = parent
        parent_id = getattr(source, "workflow_id", None)
        child_id = getattr(agent, "workflow_id", None)
        call_id = parent_obj["context"]["call_id"]
        actual = self._agent_subjects.get(agent)
        matches = None
        if actual is not None:
            matches = all(getattr(agent.session_context, key) == getattr(source.session_context, key)
                == getattr(self.session, key) for key in ("session_id", "user_id", "namespace", "portal_type"))
            matches = matches and all(actual.get(key, self.envelope[key]) == args.get(key, self.envelope[key])
                for key in ("vendor_id", "invoice_id"))
            matches = matches and actual.get("attachment_file_ids", self.envelope["attachment_file_ids"]) == self.envelope["attachment_file_ids"]
        succeeded = result.get("task_status") == "success"
        self.store.record_event(self.owner, "technical_delegation", dict(
            actor=frozen.technical_actor(agent), succeeded=succeeded,
            parent_workflow_id=parent_id, delegated_workflow_id=child_id,
            delegation_call_id=call_id, context=parent_obj["context"]), self.tick())
        token = _DELEGATION_MATCH.set(matches)
        try:
            self.check("P2", source, name, args, delegated_actor=frozen.technical_actor(agent),
                delegation_succeeded=succeeded, delegation_call_id=call_id,
                parent_workflow_id=parent_id, delegated_workflow_id=child_id)
        finally:
            _DELEGATION_MATCH.reset(token)

    def fork_workflow(self, session, task_data, owner):
        child = type(self)(self.store.path, self.requested_profile, fixture_contract=self.fixture, owner=owner,
            diagnostics=self.diagnostics, check_observer=self.check_observer,
            policy=dict(profile=self.requested_profile, enabled_requirements=list(self.policy["enabled_requirements"])))
        child.initialize(session, task_data)
        child.acquire()
        return child
