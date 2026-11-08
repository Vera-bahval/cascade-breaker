# v4.2 source-only implementation report

Status: implementation ready for independent source review and parent freeze. No
old source edits, commits, inference requests or dependencies installed. Base HEAD
is `81fb02600d1c0944a2d236b9c4405383941c2cd4`. Only the eight assigned new files were
written by this worker. Broader evaluation/archive/new800 work belongs to other
workers; no predictions or labels from those workers were read.

## Implementation

The pure guard reuses the frozen v4 evaluator through a private function-global
view; it never monkeypatches the frozen module. The added proof-origin selection
happens before frozen fact validation, and newest origin-invalid evidence cannot
revive older accepted values. A04 requires exact actual native parent/child/call
linkage. `origin_valid` exposes origin compatibility only for debugging, not gold.
Review/HOLD cannot originate in a nonexistent native DB field; native historical
flags/review are tool_result with retained source_call_id. Human facts remain
registry-only, and currency remains explicit declared/independent evidence.

Runtime subclasses the frozen adapter and keeps that subclass on workflow forks.
DB observations have fresh snapshot IDs and event times before the final cut.
Typed history preserves actual producing invocation IDs, rather than relabeling
later server reads as those invocations. Child tuple/session/subject/attachment
linkage comes from actual native objects and captured typed child-entry arguments,
never task summaries. Required sidecar behavior stays enabled with diagnostics off.
Only optional full per-check observations/results are diagnostic.

The runtime API adds policy, diagnostics and check_observer. requested_profile and
a copied MappingProxyType policy/tuple mask are authoritative for guard selection;
legacy `profile` is a compatibility flag B only with B03, because the frozen FinBot
bridge uses it for vendor SystemUtils filtering. B02 acquisition/claim injection is
independently gated by B02. B01-only, B02-only and B03-only masks cannot accidentally
activate each other's controls. Forks retain the requested profile/frozen mask.
No frozen global is changed. Full A and full B retain their requested behavior.

## Verification and acceptance limits

Command from this worktree:

```text
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python -m unittest experiments.local_guards_v4_followup.tests.test_guard experiments.local_guards_v4_followup.tests.test_runtime
```

Final result: 30 authored tests, zero failures/errors (0.211 seconds in the final
recorded run). The complete scoped suite covers new origins and legacy unknown,
missing/invalid producing call, direct DB snapshot without an invented call,
newest-invalid/stale/conflicting/foreign/future proofs, malformed-envelope priority,
known BLOCK with independent unknown, required/optional human approval, currency,
HOLD persistence, BOTH material versions, A04 tuple/actual authenticated child,
B approval/claim/vendor-SystemUtils controls, P0 applicability and P5 detection.
Native tests include real in-process FinStripe DB effect and duplicate STOP,
scripted native runner approval and pre-mutation HOLD STOP, no next tool/model/retry,
durable STOP readback, subclass forks, independent B masks, and diagnostic parity
for successful effects and typed HOLD/STOP history. Source check
`git diff --exit-code -- experiments/local_guards_v4 experiments/local_guards_v3/rules_v3.py finbot`
was empty. Installed Draft202012Validator accepted the new schema and an authored
complete envelope. Full-repository test discovery was deliberately not run, per
source-isolation and explicit test-scope instructions.

Contract tests were authored from the brief with tiny literal synthetic fixtures;
no old closed examples were opened. A legacy-origin assertion was observed failing
against frozen v4 (ALLOW instead of UNKNOWN) before the wrapper, and native snapshot
origin was observed missing before the subclass. Later source-only contract rulings
were checked with focused failing tests before correction. These are development
checks, not new800 evaluation evidence; no post-gold method changes are authorized.

Native tests use a temporary SQLite DATABASE_URL before imports, a dummy local SDK
initialization key, an authored ScriptClient, and a socket.connect blocker. The
initial native runner attempt exposed Redis event telemetry; its connection was
blocked before leaving the process, then only event emission transport was stubbed
in the tests. InvoiceAgent MCP connection setup is replaced with an async no-op in
the scripted native approval test; FinStripe effect is separately exercised through
the actual in-process server function. Required guard/store/effect code is not
mocked. Test output retains installed Authlib deprecation, development SECRET_KEY
and native missing-invoice-ID completion warnings. No inference API was called.

These tests establish the declared isolated contract, not external-write atomicity,
production readiness, complete provenance authentication or all fraud detection.
Whole-check observer timing excludes its callback and STOP persistence; external
whole-chain timing must include actual required state effects. No old/new800
accuracy, archive recovery or benchmark conclusions are claimed here.

## Explicit source-read log

Before source work, read this experiment's PLAN.md and
provenance/implementation-brief.md, canonical `/Users/proskurin-dmi/Documents/igaming/AGENTS.md`,
and the applicable installed workflow skills. No checkout AGENTS.md or CONTRIBUTING.md
exists at this worktree root or its scanned ancestors. This worker read only the
following existing repository source dependencies, plus its own newly authored
files. Native dependencies were explicitly authorized by the parent; the table
records source inspection, not database/test/result reads. Python imports also
load their normal native dependencies; no broad test discovery was used.

| Repository source path | Purpose / displayed scope |
| --- | --- |
| `experiments/local_guards_v4/POLICY.md` | Frozen business/proof/STOP contract. |
| `experiments/local_guards_v4/policy.json` | Requirement IDs, actor/tool/enums, thresholds and profiles. |
| `experiments/local_guards_v4/schema.json` | Frozen envelope/record shapes reused and extended. |
| `experiments/local_guards_v4/guard.py` | Unchanged evaluator/function globals and pure proof validator. |
| `experiments/local_guards_v4/runtime.py` | Full inherited adapter flow; override only origin/parent/diagnostics/config seams. |
| `experiments/local_guards_v4/store.py` | Full necessary SQLite claim/material/approval/HOLD/STOP/event effects. |
| `experiments/local_guards_v3/rules_v3.py` | Unchanged pure payment evaluation; no v3 policy/data loaded by new code. |
| `finbot/finbot/probe/v4.py` | Full existing default-off bridge, STOP and current-runtime lifecycle. |
| `finbot/finbot/agents/runner.py` | Full native instantiation/completion/retry propagation. |
| `finbot/finbot/agents/base.py` | Constructor, contextual loop, tool dispatch, completion, exception propagation and callable wrapping sections. |
| `finbot/finbot/agents/chat.py` | Actual workflow/session fields, start_workflow/background and STOP sections. |
| `finbot/finbot/core/llm/contextual_client.py` | Native request/response/STOP path and client injection sections. |
| `finbot/finbot/agents/orchestrator.py` | Concrete child task construction/delegation and actual shared workflow IDs. |
| `finbot/finbot/agents/specialized/invoice.py` | Constructor/process/native config and prompt sections needed for own scripted runner fixture. |
| `finbot/finbot/core/data/database.py` | Full DB configuration/session/create-table implementation for isolated fixtures. |
| `finbot/finbot/core/auth/session.py` | SessionContext fields and is_valid; selected session/user definitions. |
| `finbot/finbot/core/data/models.py` | Vendor/Invoice/native DB schema and selected user/session definitions; no database content. |
| `finbot/finbot/core/data/repositories.py` | Vendor/Invoice namespace/getter/mutation sections. |
| `finbot/finbot/mcp/servers/finstripe/models.py` | Native transaction schema; no stored transaction content. |
| `finbot/finbot/mcp/servers/finstripe/server.py` | In-process successful transfer implementation and getter/list sections. |
| `finbot/finbot/mcp/servers/finstripe/repositories.py` | Native complete invoice transaction lookup and create/update implementation. |
| `finbot/finbot/mcp/servers/findrive/models.py` | Native attachment table fields for metadata registration. |
| `finbot/finbot/core/messaging/events.py` | Method/transport lines establishing Redis telemetry dependency; only event transport stubbed in tests. |

No old tests, corpora/data/gold, reports, evaluation results, historical chats,
ML files/worktrees, old rules v2 or corporate knowledge sources were read. Source
restrictions were procedural; all workers share a filesystem, so this is not a
technical blind-isolation guarantee.

## Ready-to-freeze file hashes

Hashes below were computed after the final code/test verification; this report is
excluded from its own digest table. The parent may freeze these together with its
independent method/evaluation manifests after source review.

| Owned file | SHA256 |
| --- | --- |
| `guard.py` | `598e731ba962dbdc677c298fdc3540ef03c60c57e3d2e149d9749ff4db156d1f` |
| `runtime.py` | `68f81b124bb81d5881a5d888881f1a226c398f78229fcee8cab7162cd4484869` |
| `POLICY.md` | `2151b1709e02709d9110e97552216c7c4c35a188eca39425b986a38412173f03` |
| `policy.json` | `a2bef6576e8f598d30a418681b8d8d27a11893d2c23575a5ac3c4fd28b6d8487` |
| `schema.json` | `f8e22af22ea0245e3494d143e2597ff23fbb424ab89a74c4c8e3429dc6be92f1` |
| `tests/test_guard.py` | `d6327cda68abe4e5f3b268dd9aed4179b382818f74bddd7dcdd899dfea42058e` |
| `tests/test_runtime.py` | `8a5e840ef8685d43d1dffafff2d9fbfe6a441572efbdd9c61709b714249f6bd6` |
