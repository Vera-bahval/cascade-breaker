# Independent completion audit

## Phase 1: source admission before experimental execution

What this change does: The completion rebuilds source-bound pre-action facts,
keeps process compliance separate from substantive payment admissibility, and
adds fixed group-disjoint LR/CatBoost evaluation on a disclosed archive. It
preserves prior research artifacts and routes unresolved local decisions to
stored LLM answers for explicitly retrospective cascade accounting.

**Verdict: source logic admitted within this scope.** No concrete blocking
defect was found in the reviewed implementation. This is not approval of
research conclusions or an assertion that all annotations are correct. Final
receipt and report verification remains a separate phase after the owner runs
the frozen experiment. The owner is adding explicit reused-dependency hash
checks before the code freeze; those checks must cover `source_links.py` and
the executable source converters, projection, pairing, and ML dependencies.

### Independent checks performed

- Read `PROTOCOL.md`, `REVIEW_CLARIFICATIONS.md`, annotation assembly,
  preparation, rules, P4 source-link restoration, records assembly, OOF ML,
  singleton ML timing, rule runner, evaluator and relevant reused helpers.
- Verified the frozen label file, protocol, clarifications, and all 27 declared
  label/review source hashes. Joined all 542 final annotation IDs and prefix IDs
  to their review packets and to the hash-checked source input files.
- Independently confirmed full labels **536 BLOCK / 6 ALLOW**, process labels
  **534 BLOCK / 8 ALLOW**, and substantive labels **319 BLOCK / 191 ALLOW /
  32 INSUFFICIENT**. Final provenance comprises 232 third reviews, 36 expanded
  agreement reviews and 274 remaining independent agreements. The two initial
  passes have 200 disagreements and 32 sampled agreements in the third pass.
- Inspected source evidence for two corrected expanded-agreement cases:
  `a-7dc4d7d17fc849f166f3b17a` has a $2,890 seven-day multi-item rental with
  relevant paid rental comparators; `a-c39ae6bc8a76ff64ce19b91e` has $2,500
  talent fees against equipment-rental history. The former supports removing a
  mean-only violation; the latter retains legitimate unresolved service-scope
  uncertainty. Thirty of the 36 expanded cases change their initial N11 state.
- Also inspected an unchanged agreement with a successful unresolved Fraud
  escalation (`a-1f6dc89ce9872210de712d95`) and an admissible action with an
  actual same-prefix successful TaxCalc call
  (`a-0619c364472c91b679e78e65`). The retained ratings follow the stated hold and
  tax conventions. This bounded source check is not another complete rating
  pass or human gold.
- Audited all 542 regenerated records without invoking their guard. The
  original native payloads are preserved; every raw event and proposed-action
  field other than `session_id`/`agent_name` matches the canonical input. All
  prefix events remain strictly before the action cut. No gold, label,
  prediction, `db_final` or `final_db` key occurs in the predictor inputs.
- Verified the record gzip, source P4 input and captured-policy gzip against
  `records-manifest.json`. The P4 source hash is
  `7cc1fec196651f7fbd8f6b0e37589b002fc1f8096a68bac160dc993335f97f38`.
  Prepared facts contain 13 qualifying tax verifications. They identify 92
  observed availability cases and 450 assumed cases: 87 captured tool-set
  records plus five source-bound actual matching Payments TaxCalc calls. The
  sensitivity must retain the latter five as observed availability.
- Ran 23 synthetic unit tests for source links, evaluation/accounting,
  annotation aggregation and ML logic in the existing Python 3.13 environment:
  **PASS**. These tests do not fit the archive or infer its guard decisions.

### Boundaries found in source

`source_links.restore` binds episode, action cut, tool and available subject IDs;
it restores only missing link fields at existing event coordinates. The raw
archive loader checks archive/member hashes. It copies no future result or
financial argument and keeps source session strings opaque. The action header
at the cut supplies only a link, not a result from after the action.

The OOF code separates FIT, CAL and outer-test groups, fits preprocessing only
on resolved FIT rows, and fits only ALLOW/BLOCK. INSUFFICIENT remains a split
stratum. Features use explicit structural allowlists and equalities rather
than IDs, annotation explanations, target labels or final state. The fixed grid
includes a threshold above one, ties abstain, and infeasible CAL retains valid
probabilities. Six admissible full-target actions are too few for precise false
positive or generalization claims, even with group intervals.

The evaluator distinguishes UNKNOWN from a wrong BLOCK, excludes UNKNOWN from
local decision coverage, and routes deferrals to the saved LLM in the declared
cascade modes. It keeps classifier and shared-process-gate vectors separate.
Costs sum stored Decimal charges; latency sums paired per-case components
before computing quantiles. Timing excludes acquisition of the original
evidence and is not a live adaptive executor result. Early checkpoints do not
reuse a saved P4 LLM answer.

N14 largely measures a conditional process obligation. A missing tax check is
not proof of injection success, financial loss, incorrect tax law, or completed
task failure. Arithmetic consistency does not establish the applicability of
the category, jurisdiction, or configured tax rates. Business exceptions and
uncertain substantive context are not replaced with an invented external
approval registry.

Reviewed stable implementation hashes: `prepare.py`
`62724d9fb4983f05905a2c75b7f81d8a226886feb90aa1998fdae6b40ee4c894`,
`rules.py` `5b70053ecc180d67f7d2cd76f986cc902223a8378dbec170b40448d823b1638a`,
`source_links.py`
`92554b16cb8a4f65afdd3f02a179d2b300e5623eed2e3e8cfa862ed9f0fbc611`,
and `ml.py` `9f16bca9c4b431de694d4eb606936269aa074eebdb0b5eacc41fc619b0d44285`.
Integration/receipt files were still being finalized during this phase.

Not checked in this phase: experimental predictions, archive model fitting,
latency runs, final rendered report or publication. The audit ran no archive
guard predictions, model fits, benchmark or new studied-model/API call.
