# Label-blind replay execution policy adapter

Status: stable for parent independent review. No further implementation work is
active. This is an execution-policy/accounting adapter, not feature, model,
threshold or learned-method repair. Both frozen revisions and their failing
callbacks remain unchanged. Failed original partial outputs/traces are parent
artifacts and were neither read nor changed by this worker.

## Recovery brief and boundaries

The parent reported original experiment.py predict and experiment_revision2.py
predict aborting before gold disclosure: frozen approval_relations compares an
integer approved_seq with a string event_seq. The required existing policy is
the native Runtime.fail behavior: escaped checker Exception means UNKNOWN/STOP.
Never coerce values, repair input, prefilter by schema, fabricate pUNKNOWN=1 or
silently substitute revision2's gate into the original method. Every eligible
prefix must remain represented. Keep separate calibrated raw/gated thresholds;
gate-only errors affect only the gated branch. Frozen features, models,
thresholds and their source manifests must remain byte-identical. No fitting,
corpus inference, full benchmarks, APIs, subagents or commits. Do not inspect
closed2 gold/source/report/manifest or use case-specific conditions.

New replay_predictions.py requires --method-revision original|revision2 and
--freeze. It verifies the corresponding version1/version2 freeze, source/artifact
hashes and persisted model feature_rows callback/mode before inference. It calls
that selected revision's feature extractor, probability function, threshold
decision function and mandatory_proof_gate. Shared evaluation_revision2 imports
are only Shards, join/input helpers and the generic execution exception record;
original replay never uses that module's revision2 inference/gate callbacks.

The adapter caches features per revision and old/new mode with per-row generic
Exception capture; no schema prevalidation or input mutation occurs. Successful
rows go through the unchanged shared FeatureBatch API. Failed score batches
retry every affected row individually. An error in one row does not drop other
rows. Frozen unavailable models preserve their actual all-zero scores and
UNKNOWN behavior, bypassing extraction just as their frozen probability helper
does; unavailable cached features do not invent a failure in that bypass path.
No class gets invented mass. Errored checks have probabilities=None,
scores_available=false, decision UNKNOWN, stop true, execution error stage/class/
reason and timing. Gate-only exceptions retain the independent raw and argmax
results; they are not counted as a proof-gate correction. All three named streams
raw/gated/argmax_diagnostic are emitted per method, with exact eligible-ID
coverage including malformed states. Default selection is all frozen methods.

Receipts remain compatible with evaluation_revision2.verify_predictions:
version1 for original, version2 for revision2; input paths/hashes, shard hashes,
method declarations/counts, exact source freeze path/hash, adapter path/hash,
helper source hash, callback modules, error policy/counts and batch fallbacks are
recorded. labels_opened, prediction_dataset_labels_opened and fit_called are
false. No target labels are arguments or reads. Adapter/helper/freeze identities
are checked again before the final receipt. Existing files are never overwritten
by Shards. Timing is execution diagnostic accounting, not a performance claim:
feature extraction per row, model score amortized over successful batch rows or
actual singleton fallback, and separate gate time.

NEW evaluation_revision2.Frozen.one now catches generic model/decision/gate
exceptions and returns the same UNKNOWN/STOP policy record with unavailable
scores and measured timing. Its constructor still rejects wrong or corrupted
freezes/pipelines; IO/integrity errors remain failures, not classifier outcomes.
Valid calls retain their frozen callback behavior. The original evaluation.py,
features.py/models.py/experiment.py and all revision2 method sources are unchanged.

The parent additionally authorized the NEW benchmark_revision2.py optional
component diagnostic fix after a failed-first reproduction showed direct
features calls could abort even after Frozen.one returned UNKNOWN. These optional
feature/probability/equivalence probes now catch generic Exception, retain the
already measured main result and record unavailable component timings plus
separate stage/class/reason and attempted elapsed time. No row is skipped and no
probability is fabricated. Valid-row computation/timer locations are retained.
Optional native proof-gate diagnostics similarly record unavailable allow/timing
rather than aborting a trial. Main execution error details are retained in
single/native/cold records. The previous early/late STOP effects accounting and
registry denominator/source-freeze changes remain in place. Original benchmark
and all frozen inference source files remain unchanged.

## Targeted own-fixture evidence

Fixtures are unlabeled engineering states. A nonnumeric string timestamp and an
integer approval sequence trigger the actual frozen TypeError in both revisions.
No corpus/model fitting is used: an explicit diagnostic constant pipeline calls
the real frozen feature/probability callbacks with a single ALLOW class. Its
class masking remains ALLOW1/BLOCK0/UNKNOWN0 on valid inputs. It is not a new
research method or a learned performance claim.

Failed-first replay test command:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_ml_retrain/test_replay_predictions.py
```

```text
AssertionError: False is not true : exception-policy replay missing
Ran 4 tests in 0.001s
FAILED (failures=4)
```

The initial targeted implementation passed4 checks. Additional unavailable-model,
singleton-score-error, receipt/coverage, distinct-threshold and native gate-only
checks passed5 tests. The optional benchmark direct-call regression was then run
before changing benchmark_revision2.py:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_ml_retrain/test_replay_predictions.py ReplayTests.test_single_benchmark_retains_malformed_check_and_marks_component_unavailable
```

```text
TypeError: '<' not supported between instances of 'int' and 'str'
Ran 1 test in 1.223s
FAILED (errors=1)
```

After that measurement-only change, the final targeted command was:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_ml_retrain/test_replay_predictions.py
```

```text
test_actual_frozen_extractor_exception_becomes_unknown_stop_with_unavailable_scores ... ok
test_generic_batch_fallback_keeps_successful_rows_and_gate_only_error_is_gated ... ok
test_single_benchmark_retains_malformed_check_and_marks_component_unavailable ... ok
test_single_measurement_matches_checker_exception_stop_policy ... ok
test_unavailable_model_and_generic_singleton_score_failure_do_not_fabricate_classes ... ok
test_valid_pipeline_parity_and_revision_specific_gate ... ok
Ran 6 tests in 1.247s
OK
```

Tests verify unchanged input bytes/values, actual TypeError, unavailable error
scores, exact valid raw/FeatureBatch callback parity, version-specific gates on
the same distinct-call state, separate raw sentinel/gated thresholds, generic
batch fallback, generic singleton and gate errors, no absent-class probability
mass, native/single checker error policy, and a bounded malformed-row single
benchmark that retains both raw/gated rows with unavailable feature components.
Both original/version1 and revision2/version2 replay receipts pass the existing
scorer verifier against their explicitly selected temporary freeze; every stream
contains exactly both expected valid/malformed prefix IDs. There are no labels.
The6-test suite is the only final suite run for this task. No broader suite,
research artifact deserialization, corpus inference or full benchmark was run;
this preserves the parent's quiet-CPU window. No closed2 input/gold/source/
report/manifest was read. Only own temporary files and allowed method source
were accessed; no frozen source or parent result artifact was edited.

## Parent replay commands after independent review

Use fresh output directories; preserve failed originals and traces. These
commands are API-free label-blind batch execution, not quality tuning. EXP, OBS,
META and OUT denote the experiment root, existing unlabeled observation/metadata
files and a new output parent directory. Supply all numerical thread variables2
on each invocation. A smaller batch such as128 bounds working memory; the adapter
streams a temporary feature cache and one-method score cache, without copying
the full input/output archive. Do not duplicate full archives on the low-disk host.

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 "$PY" "$EXP/replay_predictions.py" --method-revision original --freeze "$EXP/frozen" --observations "$OBS" --metadata "$META" --output "$OUT/original-replay" --batch-size 128
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 "$PY" "$EXP/replay_predictions.py" --method-revision revision2 --freeze "$EXP/frozen_revision2" --observations "$OBS" --metadata "$META" --output "$OUT/revision2-replay" --batch-size 128
```

Both commands produce all methods and raw/gated/argmax streams, with independent
receipts/source hashes. The unchanged rule/TFIDF control path uses the identical
unmodified observations and its own fresh output:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 "$PY" "$EXP/evaluation_revision2.py" controls --observations "$OBS" --metadata "$META" --output "$OUT/common-controls" --tfidf
```

This control command remains the existing control implementation; it does not
silently replace rules with either ML gate or modify observations. No control
corpus run is claimed here. If an existing control callback escapes an exception,
preserve its failed output/trace and apply the declared execution policy
explicitly; do not repair its frozen implementation or normalize inputs.
Only after blind predictions/receipts are saved should the parent score in new
separate directories, using --model-freeze for the actual original/revision2
source and --episodes for the explicit registry where required. This worker did
not repeat blind predictions, reveal gold or inspect failed parent artifacts.

## Stable source hashes

| Source | SHA256 |
| --- | --- |
| `replay_predictions.py` | `6b72d22e6242e82ba88b6f335f552ca2879a97793bf2451dac4c724a3effb5e3` |
| `evaluation_revision2.py` | `4e4eb4f75578e19498681603883fdd000a030b5657278ca6f712f9abcc4d1b8a` |
| `benchmark_revision2.py` | `455d72ee231ab4afc7fece0c31bb27d7081f72d288e9606d0a7c178cb779a79c` |
| `test_replay_predictions.py` | `baf0fc2f050a39e9598c3ab75c1bc88283a4e8048901cb1a6701d2a51e39e14e` |

All nine protected original/interface/method files still match the initial revision2-evaluation-read-log.json hashes. These new measurement hashes supersede earlier report hashes only for changed adapter files. Independent review precedes parent rerun; no further writes are active.
