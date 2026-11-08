# Revision2 measurement adapter

Status: ready for parent independent code review. No full-assessment freeze or
new-test author step is authorized by this implementation report alone.

New files are `evaluation_revision2.py`, `benchmark_revision2.py`,
`test_evaluation_revision2.py`, this report and
`revision2-evaluation-read-log.json`. No existing file was edited. The nine
original/interface/method files checked against current HEAD match byte for byte:
`evaluation.py`, `benchmark.py`, `features.py`, `models.py`, `experiment.py`,
`features_revision2.py`, `models_revision2.py`, `experiment_revision2.py` and
`evaluation-report.md`. Original results, weights, policies and the main report
remain unchanged. Concurrent fitting artifacts belong to the parent.

## Auditable delta

The evaluation adapter is an explicit copy with imports from
`experiment_revision2`, `features_revision2` and `models_revision2`. It retains the
shared original `models.FeatureBatch` class alias. Available fitted pipelines must
persist `models_revision2.feature_rows`, including reused weights; a legacy
transformer or version1 freeze is rejected by `Frozen`. Prediction receipts are
version2, and CLI/default calibration/file-receipt references target
`frozen_revision2`. The sharded command emits raw, gated and deterministic argmax
diagnostics for every selected method; the unchanged selection loop covers all72
methods by default. File predictions from `experiment_revision2.predict` retain
raw/gated compatibility and obtain deterministic argmax diagnostics while scoring.

The original Rule and optional historical TFIDF implementations are unchanged.
No observation repair is applied by either control or prediction command. AST
comparison confirms21 evaluation functions/classes are unchanged after only
normalizing canonical freeze paths: Rule, Shards, stats, all metric/replay/
denominator/bootstrap/outcome functions, controls, predict, score and related
IO/join functions. Nine benchmark functions are identical, including single,
load, cold_worker, native_imports, native_summary, stratified_sample, offline,
environment and method selection. Single inference still includes feature
construction; separately repeated component calls are diagnostic rather than an
additive timing decomposition. Cold first-response and process teardown remain
separate. Full Runtime.check timing still includes snapshot/enrichment/sidecar IO.
No timing measurement is interpreted here as model performance.

## Common native producer

The adapter first calls original Runtime.snapshot without overriding call_id and
retains a deep copy in base_observations. The common enrichment function then:

1. Reads the real parent workflow and completed source call from the current
   `_INVOKING` delegation tuple.
2. Attests parent_workflow_id from that actual parent.
3. Only when existing delegation_call_id matches the actual source and existing
   delegation_succeeded is True, changes an existing server_context/native_snapshot
   True delegation attestation's call_id from its original checking call to the
   completed source call. The attestation itself, fact, success, permissions and
   human approval are never created or promoted.

Each change records an exact field path, before/after value and actual source;
base snapshots, enriched snapshots and changes are returned and written in full
native shards by the benchmark command. Fresh checking call_id is retained in all
contexts and checking-call proof bindings. Missing/foreign actual source,
absent proof, foreign proof, failed completion and False attestation are left
unavailable. The same function runs before any candidate sees the snapshot.

Frozen rule A/B legitimately disagree on these corrected snapshots: their legacy
proof reader binds completion proof to the current checking ID. Their UNKNOWN is
retained, and old positive-completion assertions were removed for these full
contracts. Original-producer diagnostics remain available with enriched=False;
base/enriched equality is then preserved. Completed and stopped chain timing
remains separate. The mismatch fixture can stop earlier at a legacy rule P2, so
its observed stop/checkpoint must be reported rather than described as a payment
amount BLOCK if execution never reached transfer.

## Own-fixture verification

All commands ran from the repository root, with:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2
PY=/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python
```

The environment assignments were supplied on each invocation, not as standalone
non-exported shell variables. Exact invoked command suffixes and outputs:

```text
$PY experiments/local_guards_ml_retrain/test_evaluation_revision2.py
Ran 8 tests in 3.331s
OK

$PY -m unittest discover -s experiments/local_guards_ml_retrain/tests -p 'test_evaluation.py' -v
Ran 12 tests in 1.039s
OK

$PY -m unittest discover -s experiments/local_guards_ml_retrain/tests -p 'test_benchmark.py' -v
Ran 3 tests in 0.788s
OK
```

The new tests cover distinct checking/source completion, absent/foreign linkage
and proof, unsuccessful completion, missing proof and unchanged false evidence;
raw/precomputed/single-state parity for explicit revision2 and explicitly rebound
reused tiny pipelines; rejection of legacy pipeline/freeze; cold-worker versioned
inference; all72 descriptor streams times raw/gated/argmax (216 streams) on one
own state; versioned original-file receipt/scoring compatibility (144 streams
plus72 argmax diagnostics); all3 rule controls and144 CAL export descriptors;
receipt-before-gold tamper rejection; unchanged metric/bootstrap and quantile
semantics; and native no-post-STOP calls and correct FinBot import paths.
The72-descriptor fixture deliberately reuses tiny one-class engineering pipelines
under protocol descriptors. It is not72 fitted research models, nor a quality
comparison. No research TRAIN/CAL corpus was opened for these fixtures.

Bounded native fixture results: the explicit constant-classifier/proof-gate
diagnostic completes the native chat/background/orchestrator/fraud/invoice/
payment chain with one disposable SQLite payment and three P2 snapshots. Each
P2 checking ID differs from its actual source ID; completion proof equals source
ID and the revision2 gate allows. Both frozen rule A and B return UNKNOWN on
those exact same P2 snapshots. A separate rule-B native trial stops with zero
payments. A forced diagnostic P2 stop performs no later invocation or transfer.
The original-producer rule-B diagnostic completes and records no enrichment.
These are execution/proof fixtures, not a new method or evidence of model quality.
External IPv4/IPv6 socket connects are blocked. Recorded FinBot imports resolve
under this checkout's finbot/finbot.

Failed-first evidence: before implementation all6 initial checks failed on the
missing evaluation adapter. An intermediate import-order experiment caused one
native test error because loading FinBot before the existing fixture configured
its mock provider attempted to instantiate an unconfigured OpenAI client. No API
call was made; the socket guard was active. Restoring the accepted fixture-first
import ordering fixed it. Final warnings are the existing Authlib deprecation,
default local SECRET_KEY notice and missing invoice-ID notes warnings. No secret
value was printed.

AST/immutability verification printed:

```text
evaluation.py: unchanged AST (versioned freeze paths only) for 21 functions/classes
benchmark.py: unchanged AST (versioned freeze paths only) for 9 functions/classes
9 original/interface/method files match HEAD exactly
```

## Hashes and acceptance boundary

| New source | SHA256 |
| --- | --- |
| `evaluation_revision2.py` | `b233f816cfd29f68a7c38bdbac5877c79a99b9e19f94e2b11378015ec8f16fa1` |
| `benchmark_revision2.py` | `2516a7560715c75ca23f5c38bafd6dc0ec0275842363d2c8f5bb9b1d52384401` |
| `test_evaluation_revision2.py` | `a620dd387eaeaa323a576fa2948ee35ee0f71fc4543c530e023a9518d10f24c3` |

The read log contains hashes for the brief, plan, clarification, accepted
interfaces and relevant source/import inputs. A broad repository test discovery
was intentionally not run because it can open excluded research/closed data;
only the allowed engineering tests above were executed. There was no API,
subagent, commit, research archive/new-test inference, performance benchmark,
fitted72 native smoke or reading of original1200 gold/source/results or
otherthread v4.2. No performance conclusion is valid while the parent's final fit
is concurrent. Parent independent review must precede full-assessment freeze and
new closed-test author access. Actual fitted-model smoke and all-model benchmarks
remain later parent steps on quiet CPU. Revision1/revision2 predictions must use
separate output directories before new gold release because method names match.


## Independent review fix round1 (base433fb8d)

Read `revision2-evaluation-review.md` and reproduced its Important finding. The
new native driver previously asserted every STOP had zero PaymentTransaction
rows. That discarded a valid path where P4 allowed the transfer and the first
STOP occurred at the subsequent process_payment check. Original benchmark.py and
all model/feature/policy sources remain unchanged. Only benchmark_revision2.py,
test_evaluation_revision2.py and this appended report were changed this round.

The new benchmark removes that blanket assertion. Final transaction status and
source-journal completed_transfer events are read after the timed chain has
ended, not from inside Runtime.check or candidate scoring. Existing payments,
invoice_status, status, stop and timing fields retain their meaning. Added
accounting fields record payment_statuses, confirmed_transfers, stop_checkpoint,
stop_tool, stop_event_seq, first_confirmed_transfer_event_seq,
confirmed_transfer_before_stop and stop_effect_phase. Stopped trials are
classified as stopped_before_transfer, stopped_after_confirmed_transfer, or
stopped_transfer_timing_unknown when evidence cannot establish the ordering.
A confirmed earlier transfer is retained as an effect. Late STOP is never
reported as preventing that transfer. No native_summary, evaluation metric,
denominator, model or timing definition was changed.

The new benchmark comments explicitly distinguish effects already permitted by
a model/control from forbidden later activity. Invocations after the first STOP
and confirmed transfer journal events at/after STOP remain assertion failures.
The regression asserts process_payment is the last attempted native invocation,
its write did not execute (invoice remains approved), and a completed transfer
was recorded strictly before the STOP. The existing early P2 STOP test now also
asserts stopped_before_transfer, zero confirmed transfers and absent transfer
sequence. The existing bounded diagnostic candidates remain engineering
fixtures, not model quality methods.

Failed-first command, with no implementation change yet:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_ml_retrain/test_evaluation_revision2.py EvaluationRevision2Tests.test_native_late_stop_retains_earlier_confirmed_transfer_without_prevention_credit
```

Exact decisive red output:

```text
FAIL: test_native_late_stop_retains_earlier_confirmed_transfer_without_prevention_credit (__main__.EvaluationRevision2Tests.test_native_late_stop_retains_earlier_confirmed_transfer_without_prevention_credit)
AssertionError: stopped fixture had a payment
Ran 1 test in 2.273s
FAILED (failures=1)
```

After the implementation fix, the covering test_evaluation_revision2.py run
passed9 tests in2.455s. An additional assertion for the early phase classification
and a readability-only diagnostic predicate change led to this final command:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_ml_retrain/test_evaluation_revision2.py
```

Exact final summary:

```text
Ran 9 tests in 2.276s
OK
```

The late-STOP own diagnostic ALLOWs through the transfer and returns UNKNOWN on
process_payment: status stopped; stop_checkpoint P1; stop_tool process_payment;
payments1; payment_statuses ['completed']; confirmed_transfers1; invoice_status
approved; stop_effect_phase stopped_after_confirmed_transfer;
confirmed_transfer_before_stop True; first transfer sequence strictly before
stop sequence. All values/order are asserted by the new regression. Existing
Authlib, local development-key and invoice-note warnings remain disclosed; no
credential value or external API call is involved. Test-run durations are not
model or native-performance claims. No other suite, full benchmark, fitted model
or prohibited research/closed data was opened this round.

Round1 source SHA256 values supersede only the corresponding generated-source
hashes in the initial read log/table; that initial implementation audit is retained:

| Source | SHA256 |
| --- | --- |
| `evaluation_revision2.py` | `b233f816cfd29f68a7c38bdbac5877c79a99b9e19f94e2b11378015ec8f16fa1` |
| `benchmark_revision2.py` | `299583748dbcfb083a3b8b7a18ba8d1c2e02c6183805d109bb0a79546f055e55` |
| `test_evaluation_revision2.py` | `c7854da6e741210fed945960d1055b2451e88372039fa270e648bf4724ec2c58` |

Review input SHA256: `d02bbd964c4aacc649da6731269335ba75b1b9ee7fdbe8fd8a9451660b7564ac`. The nine protected original/interface/method files still match their initial read-log hashes; evaluation_revision2.py is unchanged. Ready for parent review recheck; no full-assessment freeze or new-test work was performed.


## Episode-registry denominator correction

Both known measurement defects are implemented; the late-STOP benchmark file
remains byte-identical to round1 SHA299583748dbcfb083a3b8b7a18ba8d1c2e02c6183805d109bb0a79546f055e55.
This round changed only evaluation_revision2.py, its own fixture tests and this
appended report. No feature/model/threshold/policy, original source or original
output was changed. Full archive scoring is a later parent step.

Parent readback identified five archive episodes with no observation prefixes,
which a metadata-only registry omitted. The allowed structure inspection read
existing local_guards_v4/data/episodes.jsonl.gz and metadata.jsonl.gz only to
summarize row counts, field names/types and split/intent counts. It found3378
episode registry rows and83099 metadata rows; no source narrative, gold or
closed-test content was used. Episode records have exact episode_id and split
fields, plus source_intent and existing archive provenance. The scorer never
rewrites these IDs. Parent will supply a source-prefixed combined CAL registry
when scoring prepared mixed-source data.

`score --episodes PATH` now validates nonempty unique episode IDs and splits,
selected metadata coverage, split agreement, source intent when available, and
requested split existence before opening gold or outcomes. Registry members
without prefixes are retained verbatim. Split filtering keeps selected
no-prefix/no-check members and excludes other partitions. Omitting --episodes
retains a metadata-derived observed-member fallback, explicitly identified as
lacking an external registry; it cannot establish the entire archive universe.

The existing all-eligible, reached-action and eligible-episode denominators
remain distinct and unchanged. No observation, label, ALLOW/UNKNOWN decision or
fake action is generated for a registry-only member. A method declared in a
sharded receipt with zero applicable checks now emits an all-slice accounting
row with zero action/eligible-episode counts and the supplied registry totals.
Actual observed guard UNKNOWN decisions remain real observed STOPs. Unavailable
stop evidence is stored internally as stopped=None, not an observed UNKNOWN and
not proof of safety or no STOP.

`outcomes_all_registry` retains actual outcome availability/payment counts and
adds episodes_with_observation_prefixes, episodes_without_observation_prefixes,
episodes_with_guard_decisions, unassessed_episodes, unassessed_episode_ids,
no_observation_episode_ids and observed_guard_unknown_actions. These make
outcome availability independent from guard-decision availability. Honest
interruption bounds use the full supplied legitimate registry denominator:
confirmed observed interruptions form the lower count; the upper additionally
includes unassessed legitimate members. The point legitimate_interruption_all
rate is null whenever such unassessed legitimate members exist. Reached-only
rates retain their observed denominator. Added text qualifies stop-dependent
outcome/prevention rates as evidence-based lower bounds where stop evidence is
missing; known outcomes alone never establish prevention. No safety or no-stop
claim is derived from absent logs.

`score --model-freeze PATH` defaults to frozen_revision2 and governs both
prediction receipt expectations and frozen-calibration.json export from the
actual selected source manifest. Version1 file and sharded receipts are accepted
against an explicit version1 source freeze; a mismatched source freeze fails
before gold IO. Inference/Frozen remains revision2-only. Standalone sharded
receipt verification without an override preserves its receipt-bound freeze;
score always passes the explicitly resolved source freeze. Inputs record exact
registry and source-freeze paths/hashes. Original-v1 corrected accounting must
be written to a new output directory with --model-freeze frozen, preserving all
published original bytes.

Failed-first command:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_ml_retrain/test_evaluation_revision2.py EvaluationRevision2Tests.test_explicit_registry_retains_no_prefix_legit_payment_without_fake_guard_decision
```

Exact red summary:

```text
TypeError: score() got an unexpected keyword argument 'episodes'
Ran 1 test in 1.320s
FAILED (errors=1)
```

A second failed-first regression exposed silent omission of a method with zero
applicable checks:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_ml_retrain/test_evaluation_revision2.py EvaluationRevision2Tests.test_registry_survives_zero_applicable_checks_without_creating_actions
```

```text
AssertionError: 0 != 1
Ran 1 test in 1.355s
FAILED (failures=1)
```

An intermediate13-test run also found two tiny receipt-fixture failures because
an implicit directory verifier default was bound to the canonical source rather
than its own receipt source. That intermediate validation hashed current frozen
artifacts for integrity only; no fitted research pickle was deserialized or
inferred. Preserving the existing receipt-bound standalone behavior fixed the
tiny API parity while score still enforces its selected source freeze. All13
then passed. After zero-check and extra split rejection coverage, all14 passed.

Final covering command:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_ml_retrain/test_evaluation_revision2.py
```

Exact final summary:

```text
Ran 14 tests in 3.502s
OK
```

New assertions cover one observed episode plus one legitimate no-prefix member
with a confirmed completed payment and no observed attempt: actions1, observed
UNKNOWN1, reached actions1, eligible episodes1, full registry2, completed
transfers1, attempts0, unassessed1, no-prefix1, point honest interruption null,
bounds[0.5,1]. No decision is invented for the no-prefix member. The CAL fixture
retains selected no-check and no-prefix members while excluding TRAIN members;
its action denominator1 and registry denominator3 remain separate. A zero-check
fixture reports zero actions/UNKNOWN/eligible episodes, two unassessed members
and honest bounds[0,1]. Missing/duplicate/wrong-split/wrong-intent registries,
absent selected split and mismatched model freeze all reject before missing-gold
IO. Version1 immutable file prediction plus version1 sharded receipt are tested
with tiny original pipelines, and CAL export hash matches that exact source
freeze. All these are disposable engineering fixtures, not assessment-quality
results. The previous native binding/late-STOP tests still pass in the same run.
Existing local warnings remain as disclosed above. Test durations are not model
performance claims; no full run, other suite, API, subagent, commit, new closed
revision2 data or original1200 input/gold/results was accessed.

Final source SHA256 values (superseding generated-source values above):

| Source | SHA256 |
| --- | --- |
| `evaluation_revision2.py` | `1576821dea0c8447344ed7e0c1106e50a27f495b6cb520244da30c8ee0d3eff2` |
| `benchmark_revision2.py` | `299583748dbcfb083a3b8b7a18ba8d1c2e02c6183805d109bb0a79546f055e55` |
| `test_evaluation_revision2.py` | `37c7742215eaa865feea6fd5d47fbabb3887e1c56c29efe0f3571d07351fa434` |

The nine protected original/interface/method sources still match the initial read-log hashes. Both accounting fixes are stable and ready for parent independent re-review; no further source work is active.
