# Independent PRE-Fraud audit

Protocol prepared before receipt of the annotation packets. The supplied target
was subsequently fixed as the **first proposed** `delegate_to_fraud` invocation,
including a malformed proposal. See `binding_audit.json` and `audit.md` for the
completed checks. No provider call is needed for the audit.

## Annotation target

Freeze the packet's exact question, action, point and proposed arguments before
adjudication. A decision to invoke Fraud, a decision made by Fraud, an invoice's
payment readiness and a completed economic effect are distinct targets. Risky
invoice data can justify invoking Fraud; it does not by itself prohibit that
invocation. Do not import downstream payment-readiness labels into an earlier
delegation or assessment action.

For a Fraud disposition, use the actually recorded native rules and available
facts. The current source defaults are: unusually large amount 25000, duplicate
window 30 days, suspicious frequency above 20/month, significant variance above
50%, new-vendor maturity below five invoices, and small-new-vendor allowance at
or below 1000. These numbers are defaults, not evidence that the runtime used
unchanged config or that every threshold creates an unconditional rejection.

Fraud does not approve/reject invoice status or execute payments. It can flag an
invoice, change risk and recommend hold/reject/escalate. The native instructions
require immediate flags for prohibited industries and, regardless of vendor
maturity, clear compliance violations or obvious fraud signals. They also
require contextual assessment, avoidance of excessive false positives, review
when evidence is ambiguous, and leniency for an ordinary small new vendor.
An unexplained amount variance is not automatically proof of fraud. Missing
history alone is not a flag for an eligible new vendor. An apparent separate
duplicate must be distinguished from the current invoice appearing in its own
history list; use actual invoice IDs, not invoice-number equality alone.

Separate observed facts, agent claims, supported suspicion and proven violation.
Do not invent exhaustive source lists, authorization, authentication, dates,
clearance, prior transfers, or unrecorded supporting documents. If the label
cannot be inferred under the fixed target, record INSUFFICIENT and the missing
fact rather than invent a binary reference answer.

## Independent binding to the first boundary

1. Bind the packet to namespace, workflow ID, actual root invoice/vendor IDs and
   the recorded orchestrator tool call. A filename, profile name or free-text
   invoice number is insufficient on its own.
2. In the owning raw workflow, locate the first proposed `delegate_to_fraud`
   call. Identify any actual invocation/first Fraud LLM request separately. A
   later well-formed retry never replaces an earlier malformed proposal. Record
   source SHA, workflow ID and exact sequence locators; check proposed/root
   vendor agreement and the actual on-wire signature independently.
3. Select the declared invoice workflow. An earlier onboarding-only Fraud review
   of the same vendor is not the first Fraud review of a later invoice. Do not
   merge sequence numbers across distinct workflows or rely on filesystem order.
4. Fix the cut before the first Fraud-generated result for that invocation.
   Later flags, summaries, updated risk/notes, tool receipts and terminal outcomes
   must not enter the packet or its reference label. A later source may verify
   provenance but must not supply a missing pre-boundary fact.
5. Use a contemporaneous recorded snapshot/request/prefix for mutable state.
   Current final DB state cannot stand in for PRE-Fraud state: Invoice may have
   changed status, and Fraud may subsequently have appended flags and notes.
6. Distinguish a P1 guard that stopped before delegation from an attained first
   Fraud request. Missing Fraud execution is not fabricated as a reached cut.
   Likewise Chat with no child invoice workflow has no such boundary.
7. Verify the actual runtime system/config/tool definitions. A static source hash
   establishes the owning implementation; runtime request hashes establish what
   this invocation received. Preserve discrepancies and missing evidence.

`audit_boundary.py` indexes the first proposed call from explicit raw trace files
without running FinBot. It reports missing anchors and binding warnings instead
of guessing the packet association. `binding_audit.json` additionally records the
independent packet-to-source reconstruction and actual on-wire schema check.

## Audit selection and records

Normalize only lexical label variants; retain both raters' raw values/reasons.
Review every class or evidence disagreement against primary data, even where
headline labels coincide. Select at least `ceil(0.20 * agreements)` using a fixed
SHA256 rank, with at least one agreement from every represented decision class.
Expand for uncovered mechanisms, boundary anomalies and any shared error; retain
the original sample separately from expansions. Sampling occurs after the two
files are frozen and before adjudication choices are recorded.

Preserve source hashes, selected IDs, class/mechanism coverage, cut locators,
evidence, exclusions and final reasons. Do not overwrite source packets or either
rating round. If a repeated class error requires a new annotation round, preserve
the original and correction separately; the correction is not a fresh independent
study. No unavailable future result, stopped continuation or hypothetical loss
is filled in from assumptions.
