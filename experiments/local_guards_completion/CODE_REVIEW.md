# Scoped independent code review

APPROVE_SCOPED for the exact source snapshot below, after four reproduced defects
were corrected by the implementation owner. This is approval of the reviewed
code and synthetic checks, not approval of annotation correctness or experimental
results.

## Scope and evidence

Read `prepare.py`, `rules.py`, `early_sources.py`, `test_rules.py`, the actual
`pair_events` implementation, and the reused early source/parser/anchor helpers.
Inspected the shape of one saved early input and one P4 input without running
their guard. No annotation files, method predictions or experiment results were
read for this review. No archive guard predictions, model fits or inference ran.
Only this review document was written by the reviewer; implementation fixes were
made by their owner.

The actual saved early packet has no `native` adapter and no `bundle.raw_input`.
The new attached `row.raw_context` therefore reaches `prepare` through its tested
fallback. Source loading reuses the original archive/gzip hash checks, per-episode
journal hashes, event conversion and source-bound anchor IDs. `attach` checks the
checkpoint/tool/cut tuple and excludes events at or after the action cut. The P2
returned result is strictly before its callback cut; P0 projects the admitted
request, not a future model response.

## Reproduced defects corrected before approval

1. **Completion-only workflow evidence fabricated a Fraud start.** The shared
   legacy event parser can return a frame whose event is the completed tool event
   itself. Invoice completion followed by Fraud completion was therefore enough
   to yield `invoice_before_fraud=True` and ALLOW, even though their start order
   was unknown. The current implementation requires a real `before_tool` event;
   the same synthetic case now returns UNKNOWN.
2. **A failed read erased an access denial.** A same-target `Access denied`
   followed by `{status: "failed", success: false}` cleared the denial because
   the second result lacked an `error` string. The current implementation retains
   the known denial; the reproduced sequence now returns BLOCK. A later actual
   nonfailed result can restore permission evidence.
3. **An obsolete tax-category concern survived a correction.** An earlier
   unsupported-category calculation followed by a qualifying same-invoice,
   same-amount services calculation left the old semantic concern active.
   Concerns now belong to the latest relevant attempt; the reproduced corrected
   sequence returns ALLOW.
4. **Contradictory tax arithmetic counted as a verification witness.** A result
   with a matching amount but inconsistent amount-plus-tax/total was accepted.
   The current implementation requires nonnegative tax and Decimal consistency
   at cent precision; the dedicated regression rejects contradictory totals and
   negative tax. This does not require paying the tax-inclusive total.

The 27-test suite passed during review. After the arithmetic correction, the
reviewer inspected the implementation and independently ran the new
`test_tax_arithmetic_and_nonnegative_tax_are_required` regression: PASS. The
current file contains 28 test methods; the broad suite was not redundantly rerun.
The reviewer also reran the three independent synthetic reproductions above with
explicit assertions after their fixes. Tests
cover future/foreign supplements, missing/disabled/sensitive TaxCalc availability,
wrong invoice/amount, actual failures, non-tax-inclusive transfer amounts, direct
versus invoice workflows, HOLD chronology, session/target-bound access denial,
bank-holder equality and correction, history exclusion, and early cut binding.
The bank-holder equality fact is present in the reviewed implementation and is
available to the ML featurizer without exposing names.

## Limits and integration requirements

- TaxCalc success, subject/amount, nonnegative tax and amount-plus-tax/total
  consistency are checked using Decimal cent precision. This does not establish
  that the chosen jurisdiction or an otherwise supported category is substantively
  applicable to the invoice, or that the configured rates are correct. Do not
  claim independent tax-law verification.
- High amount, risk, material variance and bank mismatch can cause semantic
  deferral after process checks pass. The implementation does not adjudicate the
  merit of contextual business exceptions. Such UNKNOWN is not a correct local
  action decision, a discovered attack or proof that the action is inadmissible.
- `stop=True` describes the standalone guard response. Accounting for an
  additional-LLM route must treat UNKNOWN as deferral and must not silently reuse
  a P4 response as the answer to a different early checkpoint.
- No per-case action labels, source-intent judgements, archive rates, live
  executor adaptation, concurrency or production properties were qualified.

## Reviewed SHA-256

| File | SHA-256 |
|---|---|
| prepare.py | `62724d9fb4983f05905a2c75b7f81d8a226886feb90aa1998fdae6b40ee4c894` |
| rules.py | `5b70053ecc180d67f7d2cd76f986cc902223a8378dbec170b40448d823b1638a` |
| early_sources.py | `646e162f67ac89d1dde3cfd07ddb8eab46f447036d3b02ae951033b3f29b3665` |
| test_rules.py | `a8a94117376f8c3ac3829fdf53e5a39512ca4757e008a09e462e17531a333c80` |
