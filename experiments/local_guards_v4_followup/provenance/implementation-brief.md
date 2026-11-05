# v4.2 implementation brief — source-only development

Own guard.py,runtime.py,policy.json,schema.json,POLICY.md,tests/test_guard.py,
tests/test_runtime.py, implementation-report.md in THIS experiment. No git commits.
No API/model calls or dependencies installed. No old reports, tests, data/gold/results,
ML worktree, old rules v2 or history reads. Allowed frozen dependencies: old v4
POLICY.md,policy.json,schema.json,guard.py,runtime.py,store.py; old v3 rules_v3.py;
FinBot native hook/runner/base/chat/contextual_client/MCP source when needed.
Record source reads. Shared filesystem is procedural isolation only.

Implement by reuse/subclass/wrapper; old files unchanged. v4.2 same business A/B
requirements and BLOCK>UNKNOWN>ALLOW; malformed envelope UNKNOWN first. Preserve
UNKNOWN, per-stage applicability, B01/02/03 semantics. No phrase/case-ID rules.

Proof clarification:
- add proof evidence_kind enum server_snapshot/tool_result/declared_fixture/independent_registry.
- target invocation remains context.call_id and proof.call_id where applicable.
- tool_result requires source_call_id (actual producing tool invocation), source native_tool.
- server_snapshot requires snapshot_id and prior event_seq, same scope/subject/value/
versions as existing contract. It is an actual direct native DB/server read; no invented
source tool call required. Trusted server_snapshot may supply native recorded fields;
projection to v4.1 validation is representation-only after validating new origin.
- declared_fixture is explicit initial fixture or server currency_contract_attest;
independent_registry exclusively supplies human approval/clearance. Human absence stays
UNKNOWN as before. No new operational registry/currency field.
- latest same-scope origin-invalid proof invalidates fact; never drop newest and resurrect
an older accepted value. Origin missing/invalid is semantic unknown for that fact, so
other independent known violations still BLOCK. Invalid structure ->UNKNOWN.
- legacy proof input without new origin fields stays explicitly unproven in v4.2, unless
representation adapter outside guard supplies declared synthetic evidence (not gold).

Parent semantics:
- context.workflow_id retains admitted owner identity for existing B02.
- parent_workflow_id is actual parent native agent.workflow_id;
  delegated_workflow_id is actual completed child's agent.workflow_id.
- context delegation_call_id is producing native delegation invocation; A04 requires
nonempty parent+child+delegation IDs, successful completion and corresponding server
proof of delegation_subject_matches bound to these exact three values.
- Do not accept actor role or parent relationship from model summary/text.

Native subclass of frozen Runtime via existing finbot.probe.v4._CURRENT bridge. Override
fork_workflow to preserve subclass. Existing runtime.snapshot reads DB; enrich origin
metadata as part of real production-of-test-observation, not from labels. Make snapshot
cut after reads, so observed evidence event time precedes cut. Distinguish typed tool
result events from later server reads. Store original source call ID with typed history.
Populate parent/child relation in child_complete from actual native objects/_INVOKING.
No repository FinBot or frozen v4 source changes. Initial fixtures remain explicit.

Diagnostics opt-in constructor argument diagnostics=False; recording full per-check
observations/verbose results is diagnostic. Necessary store writes, HOLD/version/claim/
STOP and working proof construction remain enabled. Disable diagnostic record append
when off; guard decisions/effects unchanged. Provide diagnostic_records separately,
check observer hook for benchmark timing. Runtime.check must return observation for
native invoke machinery even when optional diagnostics disabled.

Tests independently from contract on authored tiny fixtures, not old closed examples.
Cover all new origins, missing/source call, DB snapshot no-call acceptance, missing/wrong
parent tuple and valid delegation, mixed violation/unknown precedence, stale/newest
conflict, required vs optional human evidence, currency, STOP+no later client/tool.
If direct native tests need fixture data author own tiny fixtures and ScriptClient (do
not read old tests before freeze). Use installed native Python in cascades experiments
local_guards/.venv-finbot/bin/python. FinBot source on sys.path ROOT/finbot, temporary
DATABASE_URL before imports, no external sockets. Explain limits; never invent authority.
