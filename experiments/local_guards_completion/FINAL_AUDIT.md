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

## Phase 2: frozen result and accounting audit

**Verdict: frozen experiment integrity and the checked arithmetic pass.** The
final rendered prose and figure are reviewed separately below. This phase used
saved answers, probabilities and timings only; it ran no model inference,
training, benchmark, executor or studied-model/API request.

The frozen source admission is retained separately in `SOURCE_ADMISSION.md`.
Its hash, the 10 frozen local algorithm files, 11 reused project dependencies,
label freeze and records manifest match `code-freeze.json`. The prediction and
benchmark receipts match their outputs. All **18 historical artifacts** hashed
independently before execution remain byte-identical afterward, including prior
P4/early/176 labels, predictions, inputs, saved LLM answers and timing artifacts.

Independently checked output identities and coverage:

| Output | Verified records | Identity and arithmetic checks |
|---|---:|---|
| Payment rule answers | 3,780 | Unique dataset/mode/method/prefix, exact receipt cohort counts |
| Early rule answers | 37,352 | 18,676 per mode, unique mode/prefix |
| Rule timings | 43,080 | Unique repetition keys, 30 per case/method, nonnegative finite components, exact working-component sums |
| OOF answers | 1,084 | Two methods across all 542 prefixes, unique method/prefix, finite normalized binary probabilities |
| ML timings | 1,800 | Two methods across the saved 30-state sample, 30 repetitions, calibrated/argmax/process working-component sums |
| Fitted models | 10 | Model-file hashes, declared fixed parameters, exact resolved-FIT membership and binary classes |

FIT, CAL and outer-test prefix/group sets partition the same population and are
pairwise disjoint in every fold. Each prefix appears in one outer test fold per
method. The six admissible full-target rows belong to six groups; each CAL set
has only one or two admissible rows. This supports the stated feasibility check,
but is a very weak basis for estimating safety outside this archive.

Recounted all **586 main decision vectors on three axes** (1,758 score blocks)
and all **588 original-source-expectation vectors** directly from the saved
answers, independently of the evaluator's scoring functions. Counts match,
including UNKNOWN, model unavailability, resolved denominators, errors and
correct local coverage. Recomputed all 200 fixed-grid curve count rows from
stored probabilities; complete abstention is present. This is arithmetic on
saved scores, not a new inference run.

The current and baseline rule vectors each contain 534 BLOCK, four UNKNOWN and
four ALLOW on common P4 inputs. Against the substantive target this means two
correct ALLOW, 317 correct BLOCK, two wrong ALLOW and **185 wrong BLOCK**. Against
the full target it means two correct ALLOW, 534 correct BLOCK, two wrong ALLOW
and four deferrals. These different readings must remain visible; full-target
accuracy cannot stand in for useful substantive payment decisions.

For all 36 primary cascade systems, independently reconstructed the routing
sets, unique saved-query counts, Decimal charge sums, local decision coverage,
final error counts and quantiles. Paired local latencies were checked against
means of the raw timing components; the shared process gate uses the common
source/projection once and omits model work when its BLOCK settles the route.
The process gate supplies 534 BLOCKs, so a gated model's apparent coverage is
not evidence of an equivalent classifier contribution.

Recomputed the original source-target audit with filesystem writes intercepted:
the generated 542-row source projection and explanatory report are identical to
the saved files. The source-bound fixture, scenario, dispatch and oracle checks
confirm **147 ALLOW / 85 BLOCK / 310 not_defined**. Undefined cases retain their
176 injection, 110 policy and 24 legit author categories without converting
those categories into a new absolute target. A neutral invoice in profile D
retains its bank-change/holder-mismatch BEC context.

### Tax availability and the older series

Checked the captured pre-cut Payments tool schemas in all 176 source-prefix
records. Every latest Payments request includes `taxcalc__calculate_tax` (plus
the other captured TaxCalc tools); none proves absence. These source-prefixes
retain hash `87b2177f0cbd38fe5ba6804f206048592c5ce8d3005aaf423e486bac5b1856dd`.
The same raw source has hash
`0d16d93500789d716f0b07a2beab64e78af6deea03c072d66133b3480389c504`.

Forty-one of those raw runs overlap the selected 542. Joining by raw run ID and
the exact P4 cut shows that **all 41 already have observed availability** in the
frozen P4 records; none is incorrectly removed in the unknown-availability
sensitivity. For example, canonical prefix `10f2944043c2bd8fc604e065d800`
joins raw run `cle-clean_01-7fa3e1`, legacy prefix
`38e969b864be9bced07218f9`, P4 event 157, Payments LLM step 77 and captured
tool-set key `887990eeae7df02c`.

The legacy converter's `assumed` origin therefore reflects lost actor/session
links, not evidence that the tool was absent. The new default rule's 176/176
BLOCK is consistent with a missing available tax procedure, but it permits no
standalone continuation among the 93 actions accepted by the older contract.
It is not an improvement in attack prevention. All 352 current/baseline
full-time rows were checked against the archived stop/continuation clock and
the matched old evidence-builder plus new guard timing components. Early STOP
times are not successful-task speedups.

### Concrete defect found and corrected

The first integrated evaluator reopened ignored, unpublished
`supplementary_evidence*/availability.json` and `blind_inputs` merely to count
captured availability. That would make the documented saved-result evaluation
fail on a clean checkout despite published frozen records. The evaluator owner
removed this dependency: `frozen_tax_availability` verifies the code-freeze-bound
records manifest, record hash, observed origins and captured provenance strings
without opening those private paths. The counts remain 92 observed, 450 assumed,
87 captured lists and five actual-call-only observations. The fix changes no
frozen algorithm, label, prediction, model or timing.

### Cost reconciliation

Verified the cost audit's referenced source hashes and independently summed the
3,100 unique charged response IDs using serialized Decimal values:

`12.1979602559999997645 = 2.3217584399999999539 + 9.8762018159999998106`.

The partition is the selected 542 answers versus the other 2,558 requests in
the same stored run. Nine-decimal displayed totals are respectively
**$12.197960256**, **$2.321758440** and **$9.876201816**. Saved-answer reuse does
not create another charge. This does not establish complete provider billing,
internal retry history or the original executor's total cost.

Not checked in this phase: a new live execution or new generalization. The
rendered report, links, figure and final summary binding follow in phase 3.

## Phase 3: final summary, report and publication review

**Verdict: ship as bounded retrospective research. No unresolved must-fix
finding remains in this audit.** This verdict does not qualify a live payment
guard, establish new generalization, or certify the model-assisted labels as
human gold.

The reviewed final `results-summary.json` has SHA-256
`0701794b8de73f6193ecc982567c5b1d2ba07d48dcd0b6f30d8e0caf09c0cfbd`.
All 28 sources in that summary match their recorded hashes. Without writing
files, independently rebuilt the main report, its directory-local copy and the
complete tables from the final summary, cost audit, captured policy count,
curves and feature audit. All three saved texts match exactly. The main report
has 208 lines; the complete tables have 15,545 lines. Verified local Markdown
links and image targets in both reports, tables and completion README.

Visually inspected `OOF_CURVES.png`. Its labels are readable, the axes show
correct local decisions over all 542 states, unsafe ALLOW counts, and admissible
actions without ALLOW. It identifies the full action target and all prespecified
threshold pairs; it does not present an outer-test-selected operating point.
The underlying 200 curve counts were independently checked in phase 2.

The report keeps original author expectations separate from the three action
targets and explicitly reports the 310 undefined original expectations. It
places substantive interruptions near the beginning: 185/191 substantively
admissible actions receive BLOCK from the current rule, with another four
deferred. It also states the 176/176 legacy BLOCK result and the interruption
of all 93 actions admitted by the older contract. The legacy N14-exclusion row
is labeled counterfactual rather than implying that TaxCalc was absent.

New ML is described as trained on the full action target; its substantive score
is diagnostic. The report distinguishes old saved systems, new fits, argmax
diagnostics and the shared process gate, and identifies the baseline/current
rule pair as variants of one checker. The 586 scored main vectors are not
represented as 586 new fits. Cost and latency retain their historical and
paired-sample scopes; UNKNOWN routed to the saved LLM is useful deferral rather
than a correct local decision or an automatic whole-task failure.

The README distinguishes table verification from a fresh computation run,
documents the existing-path receipt restriction, requires original archives
for source extraction, and preserves exclusive new-output handling. The old
`archive_profile.update_report` entry point now delegates to the current
renderer; its historical generator remains recoverable at the documented Git
revision. The fixed hidden-supplement dependency no longer contradicts the
saved-result verification claim.

Publication boundary: the pre-existing untracked root
`HANDOFF_NO_LLM_RESEARCH.md`, ignored `WORKING.md`, raw policy plaintext and
private supplementary directories are not needed for publishing this result.
The branch owner should retain their explicit publication selection. This
review performed no external message, commit, push or merge.

Remaining risks are the disclosed archive, model-assisted labels without
technical rater isolation, bounded source spot-checks rather than a new full
annotation pass, and the tiny admissible full-target/CAL cohorts. Group
intervals do not absorb annotation or policy-assumption uncertainty. No new
inference, fit, benchmark, studied-model/API request or live payment execution
was run by this final audit.
