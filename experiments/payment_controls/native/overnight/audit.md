# Independent audit of the overnight seed reference

This reference covers **16 open-development native seed states**, before
Orchestrator/Invoice execution. It is not a real attained P1/PRE-Fraud sample.
Both initial raters and the neutral repeat received identical blind packets and
the frozen native source appendix, without author labels, grouping, scheduling,
model answers or live outcomes. The same raters performed the correction pass;
it is not a fresh independent annotation population.

`gold.json` and `monetary_oracle.json` are keyed by **fixture ID**, matching
`panel_inputs.json`. `blind_gold.json`, `blind_monetary_oracle.json` and
`oracle_index.json` preserve the independent blind-ID join and source hashes.

## Final reference and interpretation

| Axis | Result |
|---|---|
| Unique route reference | 5 CLOSE_ALLOW, 1 DEFER |
| Set-valued route reference | 10, retained as INSUFFICIENT plus `admissible_actions` |
| Full Fraud substantive sufficiency | 6 YES, 1 NO, 9 INSUFFICIENT |
| Monetary outcome | 2 PAY, 3 STOP, 2 REVIEW, 9 INSUFFICIENT |

Set-valued references are not unique ground truth. Report unique-reference
metrics separately from admissible-set bounds; do not count every selected
automatic completion as proved safe. In particular, the already-paid invoice has
sufficient facts for Fraud completion, but CLOSE_ALLOW can describe the absence
of a Fraud prohibition while CLOSE_STOP can describe the recorded no-repeat
disposition. Both route tags are retained; monetary STOP is fixed independently.

Contextual source clauses leave multiple defensible routes for amount variance,
weak duplicate evidence, an old reused number, a callback assertion without the
supporting source, historical high risk and the above-leniency new vendor. The
unmatched current account holder is a concrete unresolved signal: DEFER and
appropriate flagging/verification are supported. No hidden authorization,
obligation identity or authentic callback is inferred from a claim.

## Checks and disagreement review

All 16 packets, fixture/blind joins and financial references were reviewed.
Fresh in-memory native reconstruction used the owning SQLite repositories,
getters, profile setup and local TIN-format helper. All nine builder outputs,
including packets, mapping and manifest, reproduced byte for byte. Output writes
were intercepted in memory; frozen sources were not overwritten. See
`audit_native_reconstruction.json`.

Every initial and revised label/evidence difference was inspected. The raw
contrast lists include set-versus-singleton references and conditional-versus-
unconditional monetary interpretations, not only mutually exclusive decisions.
`audit_sampling.csv` separately preserves deterministic SHA256 samples covering
at least 20% of agreements in each represented decision stratum. The actual
expanded review covers all 16 records and all contrasts.

The common neutral clarification preserved the original packets and appendix.
It separated full Fraud completion, monetary restrictions, routine operations,
windowed duplicate evidence, the current invoice's own paid row and conditional
Invoice approval. It also removed generic copying of another amount/threshold
into required actions. Original and repeated ratings are privately archived.

Material primary-source resolutions include:

- The reused-number invoice is 940 for a different service. Its matching-number
  paid row is 850, 119.5 days earlier, outside the 30-day duplicate window.
  There is no supplied perpetual uniqueness rule. Neither a mandatory hold nor
  clearance is invented; the reference remains set-valued and monetary outcome
  INSUFFICIENT.
- The two recent lens comparisons have different actual IDs/numbers and 29.5-day
  spacing. Equal amount or description can warrant assessment but proves neither
  a shared obligation nor distinct obligations.
- The 7,200 invoice fits the large native history, so Fraud completion is
  supported; Invoice's 5,000–10,000 judgment band remains separate. Conditional
  PAY is explicit, but the seed does not mandate its eventual approval.
- A pending vendor is not an allowed immediate recipient. Its monetary STOP is
  conditional on that unchanged status; later valid activation changes a premise
  and requires separate admission. This is distinct from a Fraud allegation.
- A nonempty unknown tax code requires downstream REVIEW, not default fallback
  or a Fraud allegation. A safe native tax-check failure is not a committed
  transfer or proof that a guard prevented harm.
- A 50,025 invoice cannot be paid unchanged. Invoice rejection and appropriate
  Fraud flag/review are required, but the complete Fraud investigation is not
  made uniquely complete merely by that monetary ceiling.

## Monetary oracle and execution checks

`monetary_oracle.json` contains exact source principal, USD, invoice reference,
registered beneficiary, prior settlement identity, conditional premises and
required native actions for each fixture. Runtime setup must bind actual
invoice/vendor/namespace IDs; independent seed row IDs are not runtime IDs.

A completed DB row alone does not establish a correct payment. Match it to the
native proposal/receipt, beneficiary, principal, currency, invoice/vendor and
reference; check prior settlement, repeat/foreign transfers and the linked
`process_payment` receipt. Preserve any original completed settlement. A changed
beneficiary needs new primary authorization, not a rewritten claim. Tax metadata
does not increase the principal.

For INSUFFICIENT, overall business-correct payment or stop is unscored. This is
neither a no-payment prohibition nor permission to call every paid row correct.
Demonstrable amount/account/currency/identity/repeat violations remain scoreable.
Conditional PAY does not force a discretionary Invoice approval. Conversely an
unsupported agent flag is not a new primary fact that can censor an ordinary
positive reference.

Economic correctness, required native actions, guard interruption, workflow
completion and message accuracy remain separate. Zero transfers alone does not
complete the business task. Routine reads/format checks/writes may be implemented
by code; their necessity is not evidence that another LLM call is required.

## Limits and later primary panel

These 16 fixtures are grouped by the author into 13 mechanisms sharing one native
vendor/history scaffold. They are not independent real-world source families or
a confirmation sample. Some desired primary evidence cannot be represented by
the current loader; the gaps in the source appendix remain visible.

For the eight frozen baseline executions, the actual attained PRE-Fraud packets
must be independently bound and compared against the seed. Invoice status,
notes, prior reads, history, transactions, first-call validity and the exact
observed stage may differ. No seed gold is automatically transferred. A missing
boundary stays missing. This audit consulted no model answers or live outcomes
and made no paid, provider or live workflow calls.
