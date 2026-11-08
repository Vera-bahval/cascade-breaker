# FinBot v4.2 deterministic contract

Revision 4.2 is an evidence-origin and native-parent clarification of frozen v4.1.
`policy.json` retains its A01–A09 and B01–B03 requirement registry, actor/callable
matrix, native enums, payment limits and applicability. `schema_version` remains 4.
`schema.json` describes the envelope; this document describes semantic validity.
No corpus, gold, attack phrase, case identifier, learned feature, model call, new
operational approval registry or native invoice-currency field is used.

## Decision and trust boundary

The pure API is `guard(observation, policy=None)`. Policy may be `A` (default), `B`,
or the immutable registry plus profile/explicit predeclared requirement ablation.
An invalid envelope or invalid policy is UNKNOWN before evaluating requirements.
For a valid envelope, each applicable requirement is satisfied, violated or
unknown; inapplicable requirements are not_applicable. Any known violation gives
BLOCK; otherwise any unknown gives UNKNOWN; otherwise ALLOW. An invalid proof is
local missing evidence and does not hide another independently proven violation.
At P0–P4 BLOCK and UNKNOWN stop the whole admitted execution. They cannot become
recoverable tool messages or retries. UNKNOWN is unresolved, never a correct
successful autonomous action. P5 is detection only: UNKNOWN, stop=false.

Only a trusted native adapter or explicitly declared isolated fixture producer
may supply this envelope. JSON schema, source labels, snapshot IDs and call IDs
are not authentication or signatures. Model/user JSON, summaries, role names,
notes, descriptions, claimed parent relationships and archived outcomes cannot
establish any trusted context, fact or proof. Runtime observation uses actual
SessionContext, concrete agent classes, native callable mappings, native arguments,
scoped repositories and actual instantiated parent/child objects. No text parsing
can create human approval, clearance, review, no-HOLD, currency or authority.

## Envelope and applicability

Required fields are checkpoint, nonnegative integer event_seq, proposal, facts and
provenance. Context and schema_version=4 are structurally optional for legacy shape
compatibility; absent applicable context or proof remains UNKNOWN. Unknown fields
are rejected. Boolean is not an integer. Amounts are finite Decimal strings,
never float arithmetic in the guard. Currency comparison is uppercase. Native
status values outside policy enums are unavailable evidence, never safe values.

Proposal fields are tool, target_status, trust_level, risk_level, amount and
currency, each optional nullable string. Native status maps to target_status;
process_payment has no target_status argument. Context includes immutable record,
session, user, namespace and origin portal; admitted workflow owner; concrete
technical_actor and delegated_actor; referenced vendor/invoice/attachments; current
call; material versions and account equality token; payment reference; optional
approval and claim records; and native delegation fields described below. Context
attachment_file_ids=[] means no referenced attachment only when actual native
arguments or an explicit fixture establish that fact. Null does not mean false
or inapplicable. No referenced entity makes its relation inapplicable; a referenced
entity without its proof makes the relation unknown.

P0 is entry before model. P1 is before every native/MCP tool, including delegation,
start_workflow and complete_task. P2 is after delegated completion and before any
continuation; P2b after fraud is represented as P2/delegated_actor=fraud. P3 is
immediately before state mutation; P4 only immediately before
finstripe__create_transfer. Mutation runs P1 then P3; transfer runs P1 then P4.
Early ALLOW does not require future payment readiness or guarantee later safety.

## Proof origin and binding

Every proof retains source, prior event_seq, subject_matches, operation, immutable
record_id, value, namespace, session_id and workflow_id, plus every referenced
vendor/invoice ID. Applicable material versions and target call linkage remain
required. A proof value must equal the supplied fact after Decimal/currency
normalization. Its integer sequence is nonnegative and strictly less than the
observation cut. Subject_matches must be true. Namespace/session/workflow and
referenced subject IDs must match exactly. A producer may explicitly rebind initial
fixture evidence to an admitted child only after checking those scopes.

The additional origin field evidence_kind has exactly these semantic alternatives:

| evidence_kind | source compatibility | Additional obligation |
| --- | --- | --- |
| server_snapshot | server_context or native_tool | Nonempty snapshot_id; actual direct native DB/server read or dispatcher observation, taken before cut. No invented producing tool invocation is required. |
| tool_result | native_tool only | Nonempty source_call_id identifying the actual native invocation which produced the successful structured result. |
| declared_fixture | initial_fixture; alternatively server_context only for invoice_currency/currency_contract_attest | Explicit isolated initial fixture or explicit immutable fixture currency contract, never inferred from a policy constraint or unavailable archive fact. |
| independent_registry | independent_registry only | Independently authenticated same-subject authoritative record; synthetic human actions require an explicitly declared synthetic independent registry. |

Only independent_registry evidence can establish human_approved or human_cleared.
A declared fixture does not directly become human authority through initial_fixture.
Independent registry evidence may also attest native state where the frozen fact
family permits it. Legacy proofs without evidence_kind remain unproven in v4.2.
An external representation adapter may explicitly declare synthetic evidence for
an already synthetic fixture without changing its value/time/scope or using gold;
the guard performs no such upgrade itself. A source_call_id is the producing
invocation, distinct in purpose from context.call_id and proof.call_id, which bind
the current target invocation where required. Equality of strings alone authenticates
neither invocation.

For every fact first select the newest prior record among records with matching
namespace/session/workflow and referenced subject IDs, before origin, value or
version validation. A newest same-scope origin-invalid record makes that fact
unknown; never discard it and revive an older accepted fact. Every record tied at
the newest sequence must have valid origin; conflicting normalized values are
unknown. Foreign-scope and future records cannot establish a fact. Next apply
frozen attester-family, subject_matches, operation, record and target-call checks,
then value and material-version checks. Missing origin/source-call/snapshot linkage
is semantic unknown for that fact. Malformed enclosing JSON structure is UNKNOWN
for the envelope.

server_snapshot is admitted only for actual directly observable session/access/scope,
invoice amount/status, vendor status, amount/recipient comparisons, complete transfer
count and payment-reference/retained-argument comparison. The native DB has no
substantive fraud_review_completed or binding_hold fields: these require actual
tool_result history, declared_fixture or independent_registry, and cannot become
server_snapshot by changing the source label. Human fields remain registry-only;
invoice currency remains declared/independent-only.

A server_snapshot can truthfully contain those recorded native fields without pretending
that the DB read was a tool call. After validating its origin, the wrapper projects
server_context to frozen native_tool only where the frozen fact-family validator
requires that representation. This changes no value, sequence, scope or version.
Origin restrictions above and the frozen attester-family rules must BOTH hold;
neither rule grants a broader origin. The frozen family checks remain: session_valid requires server_context or declared
initial fixture with operation=session_validate; tool_scope_matches and
delegation_subject_matches require server_context; relation/comparison facts allow
server_context, native_tool or declared initial fixture; transfer count/reference
require native_tool or declared initial fixture; invoice/vendor state and review/HOLD
allow native_tool, declared initial fixture or independent registry. Human facts
allow only independent_registry. Dispatcher facts cannot gain permission from a
model string claiming to be a server.

Native Invoice has no currency field. invoice_currency therefore cannot be
established by server_snapshot or tool_result in this adapter. It requires explicit
fixture currency evidence or an independent authoritative record. A declared
immutable fixture ledger contract may be freshly attested as
source=server_context/evidence_kind=declared_fixture/operation=currency_contract_attest.
It must be bound to current subject and both material versions. A non-USD declared
currency is a known payment-policy violation. Missing native/archive currency stays
UNKNOWN. The USD payment constraint is not evidence of the invoice's currency.

All payment state, review, amount, currency, matching and human-approval facts, plus
payment_reference_matches_transfer, retain frozen v4.1 material-version semantics:
when context has invoice_id, invoice_version must be present and match; when
context has vendor_id, vendor_version must be present and match. BOTH contextual
versions apply even to vendor_status when both subject IDs are present. Do not
substitute narrower fact-family versions. binding_hold and human_cleared are invoice
history and exempt from BOTH material-version checks, while scope/subject/attester/
newest-event checks remain required. A material edit does not clear a HOLD. A known
HOLD requires independent clearance strictly after the newest hold; a later hold
invalidates earlier clearance. No unobserved history gap proves no HOLD.

## Requirements retained from v4.1

| ID | Applicable requirement |
| --- | --- |
| A01 | P0–P4: valid server session, nonempty record/session/user/namespace, known vendor/admin origin. |
| A02 | P0–P4: native access for every referenced vendor/invoice/attachment, invoice-vendor equality when both referenced. Required tool subject or actual attachment shape unavailable is unknown. Same-namespace cross-vendor native reads are preserved; current_vendor selection alone adds no new prohibition. |
| A03 | P1/P3/P4: concrete actor must have the exact tool in its native registry or a source-registered MCP server tool; tool_scope_matches binds actual typed arguments to envelope. A known disallowed/unknown tool is violated; absent actor/map is unknown. Prefix alone is insufficient. |
| A04 | P2: successful technical child completion and corresponding server proof of actual scoped parent/child/delegation linkage. Completion alone proves no fraud review. |
| A05 | P3/update_invoice_status: invoice actor, canonical current status, target processing/approved/rejected. Approved target requires proven positive amount <=50000, active vendor and no uncleared HOLD. Existing approved/rejected/paid status alone adds no reprocessing ban. Human threshold, review and transfer-count readiness are not universal P3 approval prerequisites. |
| A06 | P3/vendor mutation: only onboarding updates vendor status+trust+risk together with native enums; fraud updates risk only with no invented status/trust fields. No merit classifier or trust/history threshold. |
| A07 | P3/process_payment: payments actor, approved invoice, nonempty reference and exactly one matching completed transfer with retained authorized recipient argument; no target_status. Missing evidence is unknown; a proven mismatch is violated. |
| A08 | P4/finstripe__create_transfer: unchanged pure v3 payment obligations on validated facts, described below. |
| A09 | P2/delegate_to_fraud and P3/update_invoice_status: retain unchanged pure v3 HOLD and approval checks/reasons. P2 HOLD veto is continuation-only after delegated work already completed. |
| B01 | P4 transfer: current unrevoked ordinary approval binding matches invoice/vendor IDs, amount, currency, authorized account and both material versions; approved_seq precedes cut. Missing binding is unknown; known mismatched binding is violated. |
| B02 | P0–P4 workflow admission/continuation: active atomic sidecar claim for invoice or overlapping vendor-wide subject, exact admitted owner and valid prior acquired_seq. Descendants share admitted owner. Missing claim is unknown; foreign/released/uncertain/mismatched claim is violated. |
| B03 | P1/SystemUtils or delegate_to_system_maintenance: immutable vendor-origin execution, including descendants, is violated; admin still needs A03. Missing portal is unknown. |

P4 requires invoice_amount, invoice_currency, invoice_status, vendor_status,
fraud_review_completed, binding_hold, prior_completed_transfers,
amount_matches_invoice and recipient_matches_authorized. Invoice must be approved;
vendor active; invoice/proposed amount equal, positive and <=50000; invoice/proposed
currency USD; recipient authorized; completed fraud review true; zero completed
prior transfers; no uncleared HOLD. Each known negation is a violation. Independent
human approval is required only when invoice amount exceeds 10000: missing approval
is unknown and proven false is violated. For amount <=10000 an absent human approval
is inapplicable. A known unresolved HOLD blocks even if clearance is unavailable.
Missing applicable facts remain unknown unless another known violation blocks.

B01 ordinary native invoice approval does not satisfy independent human approval.
The binding amount/currency are compared with the proposed transfer, independently
of A08 validation of current invoice facts. Missing/unparseable proposal comparison
inputs or absent current ID/version/account inputs make B01 unknown. With comparison
inputs present, approved_seq at or after the cut is a known violation. A present
B02 claim acquired at or after the cut is likewise violated. A same-owner vendor-wide
claim [namespace, "vendor", vendor_id] covers that vendor and its invoices; an invoice
claim covers only that invoice. A present claim with missing current namespace has
a mismatched subject and is violated; an absent claim remains unknown.
Every covered amount/currency/account/subject change invalidates its binding, even
if later restored after both changes are observed. No wall-clock TTL is added.
B02 claim acquisition distinguishes same invoice and overlapping vendor-wide work;
different invoices can coexist unless a vendor-wide claim overlaps. Successful
root completion releases its claim; uncertain outcome keeps it uncertain. A durable
STOP is irreversible for that admitted owner, including subsequent process retries.

## Native parent semantics and runtime

context.workflow_id remains the admitted evidence-store owner used by B02. It is
not repurposed as a native agent identity. At P2, parent_workflow_id is the actual
parent agent.workflow_id, delegated_workflow_id is the actual completed child
agent.workflow_id, and delegation_call_id is the native producing delegation
invocation captured through frozen _INVOKING. Native parent and child often share
the same workflow_id; distinctness is not required. All three values must be
nonempty. The server_snapshot/server_context proof of delegation_subject_matches
must carry these exact three values as well as current target proof.call_id. A
missing/wrong tuple is unknown; a correctly attested false subject relation or
unsuccessful completion is violated. Child summary fields never supply this tuple.
The adapter compares actual child task arguments/session to the admitted parent
scope and attachment linkage; missing captured child entry cannot manufacture true.

The Runtime subclasses frozen v4 Runtime through finbot.probe.v4._CURRENT and keeps
that subclass when forking start_workflow. It preserves frozen callable hooks,
claim/approval/HOLD/STOP/store behavior and does not edit FinBot. Native DB/server
observations get fresh snapshot IDs and actual observation sequences; the final
snapshot cut follows all reads and working proof construction. Typed tool history
stores the actual producing runtime invocation ID and keeps it when replayed into
a later snapshot. A later snapshot cannot invent a missing historical source call.
Currency, no-HOLD/review initial state and synthetic human actions remain explicit
fixture configuration; defaults do not manufacture them.

`Runtime(..., profile="A", policy=None, diagnostics=False, check_observer=None)` accepts
the same profile plus predeclared enabled_requirements mask as the pure guard; the
provided policy profile must equal the requested constructor profile. Configuration
is copied and frozen for descendants; B claim enforcement and vendor SystemUtils
filtering are enabled only with their corresponding B02/B03 requirements.
The runtime keeps necessary reads, store
writes, claim/approval/HOLD/STOP and working proof construction enabled. Full per-check
observations/results are appended only when diagnostics=True, to diagnostic_records
(and its compatibility alias decisions). `check` returns the observation regardless
of diagnostics. Optional check_observer(observation,result,timings) receives timings
for snapshot_ms, decision_ms, diagnostics_ms and whole_check_ms without forcing a
full diagnostic copy. Snapshot includes necessary DB/store work; whole_check timing
excludes observer and STOP persistence, so whole-chain benchmarks must time the
native call externally and measure store/STOP as required. Observer is measurement
instrumentation and must be trusted not to mutate records or raise exceptions.

Sidecar and native DB are not one atomic transaction. Guarantees cover protected
runtime writers and observed pre-effect changes; external writers, unobserved
ABA restoration, source-DB races and provenance authenticity beyond the adapter
remain limitations. This is source-only research instrumentation, not production
authorization or a replacement for all fraud assessment.
