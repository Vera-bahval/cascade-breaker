# Feature/training implementation handoff

Status: implementation and own-fixture verification complete; full72 corpus fits
have NOT been run. Parent controls prepare/full-fit after independent code review.
Only the new experiment's files were edited. No commit, API call, package install,
old test/result access, oracle/guard source import, or outcomes read occurred.

## Interfaces and execution

- `features.py`: `project_v3(row)`, `features(row,mode='new')`,
  `mandatory_proof_gate(row,contract)`; accepts observation wrappers or observations.
- `models.py`: `fit_model(family,rows,labels,weights,feature_mode,seed)`,
  `probabilities(model,rows)`; a sklearn Pipeline for available classes, explicit
  `UnavailableModel` for no training classes. A single observed class uses a
  fitted constant classifier, so every absent class remains exactly0.
- `experiment.py`: `prepare --output NEW_DIR`, `fit --data DATA --output NEW_FREEZE`,
  `predict --freeze FREEZE --observations PATH --metadata PATH --output NEW.jsonl.gz`.
  Optional prepare `--archive`/`--synthetic` paths support isolated verification.
- Shared pure helpers: eligibility, stored-requirement reduction, source/group
  weighting, threshold decisions, episode grouping, reference/fast replay,
  calibration and action metrics. Prediction imports only inference helpers and
  opens the freeze, observations and metadata; it never opens labels/outcomes.

Use installed ML interpreter:
`/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv/bin/python`.
No `jsonschema` dependency is required: gate validation implements only the
keywords actually used in the copied v4 schema. v3 has a descriptive schema,
so payment gate uses the v3 envelope and required fact/provenance validation.

## Feature boundary and training

Old mode is exactly unchanged `ml_v3.features(project_v3(row))`. Explicit
`payment_baseline` is preferred; the fallback uses the declared representation
projection from v4 evaluate source. That module is not imported or executed.
New mode adds finite typed actor/portal/tool/target categories, nullable relation
facts, proof availability/source permission/prior/scope/subject/value/version/
call linkage relations, latest conflict, approval bindings and claim ownership.
Only session_validate and currency_contract_attest are recognized operations;
other operation strings become nonempty booleans. No writer text is inspected.
Raw IDs/accounts/versions/generation/sequences, arbitrary reason text,
metadata/split/executor/group, requirement aggregates, labels, predictions and
untrusted text are excluded. IDs/versions contribute presence or equality only.
New numeric zero entries are omitted with identical DictVectorizer semantics;
shared keys are interned to reduce precomputation memory. Old dictionary output
is retained exactly. Internal `FeatureBatch` precomputes dictionaries once while
keeping raw-observation sklearn Pipeline inference intact.

Prepare first selects archive metadata TRAIN/CAL and excludes Luna, diagnostics
and executor-test splits. It retains only those observation/gold IDs from the
combined stream and never opens outcomes. Source prefixes protect prefix/base/
episode/component IDs from collisions. Base group IDs determine equal-group
fit weights; component IDs determine split overlap checks. Existing archive split
is preserved. A/B archive labels reduce stored independent requirement states;
payment_v3 uses stored A08, representing its compatible baseline scope rather
than full A or B. Synthetic labels remain the independent supplied labels.
All arms use the same archive+synthetic CAL per contract.

Fixed72 artifacts cover3 contracts x2 feature modes x2 sources x2 families x3
seeds. DictVectorizer/scaler fit inside TRAIN only. Mixed source total mass is
50/50 when both sources are present; each base group receives equal mass within
source; weights sum to row count. LR and CatBoost parameters match the brief;
no hyperparameter search or CAL refit. Model manifests retain class counts,
available classes, per-class/total weights, library versions, preprocessing
feature names/scaler statistics plus their fingerprint, data/prefix/weight/source
hashes and fit time. Feature collision diagnostics report TRAIN/CAL identical
vectors and within-TRAIN different-label vectors for each contract/arm without
changing splits or feature definitions.

## Mandatory-proof gate, independently attributed

The gate never invokes a guard or oracle. It can only replace classifier ALLOW
with UNKNOWN. It does not create a business BLOCK or independently enforce
amount/status/duplicate business verdicts. The same gate applies to all4 arms.
Raw and gated threshold calibration/output are separate. During CAL, gate masks
are precomputed independently of gold and reused across threshold candidates;
prediction invokes the gate only when the gated classifier would ALLOW.

Protected conditions are:

- Valid input shape; authenticated session/context availability and explicit
  required session/entity/tool/delegation technical permission, not mere proof
  presence. Typed callable and mutation enum permissions come from copied policy.
- Per-cut applicability: entity/access checks only for references; technical tool
  scope at P1/P3/P4; explicit successful linked child/parent at P2; P3 approval
  amount/status/vendor/hold availability; bookkeeping reference proof at P3;
  full payment evidence only at P4. P2 does not demand future payment readiness.
- Human approval is required only at P4 above10000; clearance only with a known
  HOLD and must be independently attested after the newest hold. An explicit
  required human/technical denial cannot be auto-approved.
- A/B evidence is typed, permitted-source, scoped, prior, subject matched,
  record/call linked where applicable. Select newest eligible proof BEFORE value
  or version matching; tied newest conflicts and stale/mismatching newest records
  stay unavailable. Missing transfer history cannot establish zero transfers.
- B at P4 additionally requires current prior approval binding with matching
  amount/currency/IDs/account/versions. B workflow admission/continuation requires
  active scoped prior claim with actual owner and positive generation. Ordinary
  chat reads with no admitted workflow have no claim prerequisite; P1
  start_workflow does require admission ownership. B vendor-origin SystemUtils
  permission remains protected.

Exact proposed material-version map (frozen in source and freeze manifest):

| Facts | Required versions |
| --- | --- |
| vendor_status | vendor_version |
| invoice_amount, invoice_currency, invoice_status, fraud_review_completed, amount_matches_invoice, recipient_matches_authorized, human_approved, payment_reference_matches_transfer | invoice_version and vendor_version |
| binding_hold, human_cleared, prior_completed_transfers | No material-version match; scoped newest prior history still required |
| session/access/tool/delegation facts | No material-version match; typed scope/subject/call permission checks still required |

The copied policy says applicable material versions without specifying a full
per-fact map. Requiring both material versions for the listed invoice/payment
facts is a conservative proposed gate interpretation, NOT a claim of identical
behavior to the existing v4 guard. HOLD/clearance and transfer count are history:
material edits cannot clear them. Tests cover persistence of hold history through
material-version changes. This mapping and any native missing-version slice must
be disclosed separately; it was not selected using test performance.

Chat/P0 may precede workflow admission: namespace/session must be present, while
explicit workflow_id=null may match explicit null in trusted session/entity
proof. Missing workflow proof keys are unavailable. Admitted actor/continuation
requirements remain separate. V3 payment projection instead retains its frozen
minimal source/prior/subject proof semantics, including initial_fixture sequence
-1; it does not acquire v4 material/session prerequisites. V4 still requires
nonnegative prior proof events. These are different contract scopes.

Schema/source tags validate trusted producer outputs; they cannot authenticate
arbitrary JSON. No TOCTOU, external-writer coverage, native parent linkage or
full atomicity guarantee is added by this experiment.

## Calibration, freeze and prediction

CAL confidence grids use41 observed quantiles per decisive class plus.5 and
finite sentinel1.000001. ALLOW/BLOCK requires strict unique winning class; ties
and all other cases are UNKNOWN. Select correct decisive episode coverage under
zero reached false ALLOW on gold!=ALLOW and <=5% stops (including UNKNOWN) on
all-gold-ALLOW episodes. Tie order is coverage, fewer safe stops, then larger
ALLOW and BLOCK thresholds lexicographically. As of review round2, zero safe episodes makes calibration infeasible with
reason `unassessable_safe_denominator` and null FPR. A positive safe denominator
is required; no larger minimum denominator is invented. Infeasible
CAL returns sentinel thresholds and explicit infeasible plus unconstrained
argmax diagnostics. Zero observed CAL error is not a test guarantee.

Episode replay stops at the first non-ALLOW. UNKNOWN is unresolved. Earlier
incorrect ALLOW cannot be rescued by a later correct BLOCK; future unreached
states receive no solved-episode or reached-action credit. Per-action confusion
and all-eligible action correctness are separately named. No-check baselines are
outside these model methods and must retain decision=None/non-autonomous in
parent evaluation.

CAL precomputes feature dictionaries, probability arrays, gate masks, grouping,
confidence masks, and uses numeric vectorized reduceat replay per grid pair.
5000 purely random own-fixture CAL rows/1000 episodes completed in0.098s; this is
an algorithm smoke timing, not a native runtime performance claim.

Outputs refuse overwrite; deterministic canonical JSON/gzip contains no NaN or
Infinity. Full-fit manifest is written only after all72 artifacts and unchanged
source verification. It hashes inference/feature/gate/model/helper sources,
copied policies/schemas/config, every pickle/threshold/CAL artifact, collision
audit and input manifest. Prediction verifies all frozen file/source hashes
before any pickle deserialization and requires threshold membership in the
frozen files. A sidecar receipt hashes freeze, observations, metadata and final
predictions. Timing fields distinguish amortized batch model score time from
separately measured gate time; later benchmark must measure real single calls.
Freeze source paths are local absolute paths; portable relocation is not claimed.

## Verification and read audit

Command:
`.../experiments/local_guards/.venv/bin/python experiments/local_guards_ml_retrain/tests/test_training.py`
from research/finbot-general-guards.

15 own-fixture tests passed in the final run0.951s after preprocessing
fingerprints and the normalized Decimal newest-proof equality repair.
Covered old/new differentiation, trusted proof mutation, raw-ID/text/metadata/
operation renaming invariance, source/group weights, split overlap and Luna
rejection, LR/CatBoost two-class tiny fits, absent classes0, one/no-class cases,
TRAIN-only categories, optional/denied human permission, optional chat workflow,
actual workflow admission, newest conflict/history/version handling, v3 fixture
-1, vectorized/reference replay and calibrated grid equivalence, UNKNOWN first
STOP, CAL infeasibility, prepare filtering with isolated fixture streams,
immutable writes, label-blind real tiny-model prediction and verified-before-
unpickle failure. Broader project discovery is intentionally excluded by brief.

`features-read-log.json` records allowed source/data reads and SHA256. Archive
observations/gold/outcomes were not opened by this implementer; loader behavior
was verified with own fixtures. No corpus model results exist from this task;
feature-collision counts appear only when parent runs full fit.

## Final verification (source state delivered to parent)

Exact final own-test output:

```text
...............
----------------------------------------------------------------------
Ran 15 tests in 0.951s

OK
```

`python -m py_compile` of features/models/experiment and `git diff --check`
completed with exit0. The added Decimal equality regression first failed with
`AssertionError: True is not false`, then passed with the full own-test file.
No full72 fits were run.

| Final source | SHA256 |
| --- | --- |
| features.py | 7121544384a4e54127295c502bbf17bc1bd45f1842c3d277e2a8a008d99976df |
| models.py | 6d80646b02a8cb1f13449e47728fb8ad7e09249d4e311a21f446cc001d00c365 |
| experiment.py | fb32014ff273f737bc4547fa17c780ceb2fa1bf77d397784d748fe498218b160 |
| tests/test_training.py | 722d50c3db341782ce9a1fcd6549b9489b8e84daa475a0d668282c342de2f00c |

## Review fix round1/5, baseline8e805e0

Only the two Important findings from `engine-review.md` were changed.
`probabilities()` now preserves explicit `FeatureBatch`, as the fitter already
does. The new regression trains on tiny own precomputed TRAIN fixtures and
checks exact equality of raw-observation versus precomputed CAL probabilities
for old/new features and LR/CatBoost. P2 now requires present, equal explicit
`call_id` and `delegation_call_id`; a mismatch or unavailable ID makes the
mandatory gate refuse ALLOW. Its regression covers positive linkage, mismatch
and absent IDs for A and B, with an independently valid own claim fixture for B.

Commands were run from
`/Users/proskurin-dmi/Documents/hw-itmo/cascades/research/finbot-general-guards`.

Before either implementation fix, the regression command was:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv/bin/python experiments/local_guards_ml_retrain/tests/test_training.py TrainingTests.test_precomputed_cal_probabilities_match_raw_rows TrainingTests.test_p2_requires_matching_explicit_delegation_call
```

Observed output began `EEEEFF`; each old/new x LR/CatBoost subtest raised
`KeyError: 'event_seq'` in `project_v3`, and both A/B mismatched-P2 subtests raised
`AssertionError: True is not false`. Exact final summary, exit1:

```text
Ran 2 tests in 1.568s

FAILED (failures=2, errors=4)
```

After the two fixes, the covering own-test command was:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv/bin/python experiments/local_guards_ml_retrain/tests/test_training.py
```

Exact output, exit0:

```text
.................
----------------------------------------------------------------------
Ran 17 tests in 1.112s

OK
```

`git diff --check` also returned exit0. No broad discovery, full corpus fits,
old test access, model API calls, subagents or commits were performed.
No-safe-CAL behavior is unchanged: `no_safe_cal_episodes=True` and
`safe_stop_fpr=None` remain explicit and do not establish a measured <=5% FPR.

| Round1 final source | SHA256 |
| --- | --- |
| features.py | 06bff0aa070c89fda38d2ff61ba03940f72521c02ae9a5fe837be05650719c7b |
| models.py | c270e53aa2d5636e5dae672f2ef77783f1b8837716befc124600ef1d0d8f3144 |
| experiment.py (unchanged) | fb32014ff273f737bc4547fa17c780ceb2fa1bf77d397784d748fe498218b160 |
| tests/test_training.py | 49dbd603f099d25d58dd20d63d4def2b422bf2081773494c4220da7c9731be5e |


## Review fix round2/5, pre-freeze safe denominator

The previously disclosed vacuous feasibility convention is superseded before
freeze: feasibility now requires `safe_episodes>0`, in addition to zero false
ALLOW and the observed <=5% safe-stop constraint. A zero denominator cannot
establish evidence for that FPR bound. Such CAL returns `feasible=False`,
`infeasibility_reason="unassessable_safe_denominator"`,
`no_safe_cal_episodes=True`, `safe_stop_fpr=null`, and both abstention thresholds
at1.000001. Existing unconstrained argmax diagnostics remain intact. Other
infeasible cases have reason `no_threshold_satisfies_cal_constraints`; feasible
cases have a null reason. No model, feature, train/source weighting, confidence
grid, or positive-denominator tie/constraint behavior changed.

The focused own-fixture regression covers BLOCK-only CAL with both raw and gated
entry points. It also checks that an informative ALLOW+BLOCK CAL remains feasible
with zero safe stops and complete correct episode coverage. This enforces the
stated evidence requirement; it was not chosen from model/test performance.
Aborted fitting artifacts were not opened. No full fits, old test access, test
author work, old-file edits, model API calls, subagents or commits were performed.

Commands were run from
`/Users/proskurin-dmi/Documents/hw-itmo/cascades/research/finbot-general-guards`.

Red command before the implementation change:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv/bin/python experiments/local_guards_ml_retrain/tests/test_training.py TrainingTests.test_calibration_without_safe_episodes_is_unassessable
```

Observed output began `FFE`: the two zero-safe subtests raised
`AssertionError: True is not false`, and the new informative-case reason field
was absent (`KeyError: 'infeasibility_reason'`). Exact final summary, exit1:

```text
Ran 1 test in 1.404s

FAILED (failures=2, errors=1)
```

Green covering command:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv/bin/python experiments/local_guards_ml_retrain/tests/test_training.py
```

Exact output, exit0:

```text
..................
----------------------------------------------------------------------
Ran 18 tests in 2.133s

OK
```

`git diff --check` returned exit0.

| Round2 final source | SHA256 |
| --- | --- |
| features.py (unchanged) | 06bff0aa070c89fda38d2ff61ba03940f72521c02ae9a5fe837be05650719c7b |
| models.py (unchanged) | c270e53aa2d5636e5dae672f2ef77783f1b8837716befc124600ef1d0d8f3144 |
| experiment.py | ddea700e5293bb2f3200427a64bf650f82e6c910c79eee0a49c293cd1c2b2892 |
| tests/test_training.py | 31ff93fae5117ebaa0d3a5be6a2c4be1829245be11104d0321cd136990c74492 |
