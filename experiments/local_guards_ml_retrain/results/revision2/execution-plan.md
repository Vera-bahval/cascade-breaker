# Revision2 remaining execution plan — PREPARED, NOT STARTED

Execution only: no source edits, fits, new tests or subagents. No CPU window is
open. No inference is authorized until the controller supplies accepted hashes
and the reviewed CLI contract for `replay_predictions.py`. The revision2 engine
freeze stays `1de30a75`, receipt prefix `c3289efd`. Do not change models, features,
proof gate, thresholds, calibration or labels.

New independent1200 labels remain embargoed. Do not open
`closed_revision2/gold*`, author/source files, manifests or review reports before
explicit release. Observation/metadata paths below are planned inputs only; this
preparation did not read them. The controller handles ORIGINAL and revision2
predictions on that new1200, and their receipts, before gold release. Do not
create a duplicate prediction run.

## Prerequisites and ownership

1. Receive accepted wrapper source hashes and exact CLI schema. Confirm which
   accepted measurement adapter hashes apply; never execute a partially written
   wrapper or bypass it with the older direct predict path.
2. Reconcile any existing/partial revision2 inference outputs and the external
   archive agent's ownership/receipt. Do not overwrite, delete or duplicate work.
   The proposed `*-ml-wrapper` paths below are fresh destinations if no accepted
   equivalent result exists; the controller may supply an existing receipt.
3. Receive acceptance of the new observation/metadata identities and a coordinated
   quiet-window START. Hold all other heavy CPU work for the entire native →
   single → load sequence. No scoring or archive work overlaps that window.
4. Gold release is a separate prerequisite for new1200 scoring. It is not needed
   for accepted label-blind observations used by single/load. No gold, author
   source or review content is needed for the timing commands.

## Common command environment

Run from `research/finbot-general-guards`:

```sh
FINBOT_ML_PY=/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python
E=experiments/local_guards_ml_retrain
R=$E/results/revision2
F=$E/frozen_revision2
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2
```

These are future commands, not executed by preparation. Every output is
append-once; existing paths require reconciliation rather than overwrite.

## Coordinated quiet timing window

Only after controller START and accepted source/input hashes, run sequentially:

```sh
"$FINBOT_ML_PY" "$E/benchmark_revision2.py" native \
  --freeze "$F" --output "$R/native-quiet" --repeats 5 \
  > "$R/native-quiet.log" 2>&1

"$FINBOT_ML_PY" "$E/benchmark_revision2.py" single \
  --freeze "$F" \
  --observations "$E/closed_revision2/observations.jsonl.gz" \
  --metadata "$E/closed_revision2/metadata.jsonl.gz" \
  --output "$R/single" --repeats 5 --limit 128 \
  > "$R/single.log" 2>&1

"$FINBOT_ML_PY" "$E/benchmark_revision2.py" load \
  --freeze "$F" \
  --observations "$E/closed_revision2/observations.jsonl.gz" \
  --metadata "$E/closed_revision2/metadata.jsonl.gz" \
  --output "$R/load" > "$R/load.log" 2>&1
```

If the controller supplies different accepted observation paths, substitute only
those exact paths/identities. Keep the quiet hold through all three commands;
report intermediate completion without declaring CPU-clear. Send CPU-clear
immediately after load completes or after a blocking failure. If a command
actually fails, preserve output/log, report the exact fixture/error and wait for
serialized repair; do not patch source or tune a method.

Preserve `results/revision2/native` as preliminary and excluded from primary
latency because of the known independent-audit CPU overlap. Its effects/status
remain evidence. `native-quiet` is the coordinated replacement, not an overwrite
or selection of the faster result. Native control timing and single-call rule
timing are part of this accepted measurement workload; offline controls below
are reused without rerunning prediction.

Expected complete workload:72 models×raw/gated×5 plus off/rule native controls
and declared diagnostics; single≤128 applicable states per contract×5, individual
features+inference included;72 fresh load workers. Preserve native stop-effect
phase, completed versus stopped chains, first-response availability versus exit,
raw timings, source hashes, thread environment and whole-process RSS caveats.

## Label-blind inference jobs after wrapper acceptance

The wrapper's CLI is still under independent implementation/review. Do not guess
its flags or execute it now. Once its accepted schema/hash arrives, bind these
exact argument sets to that CLI and record the actual argv in each receipt:

| Job | Model freeze | Observations / metadata | Contracts | Fresh proposed output |
| --- | --- | --- | --- | --- |
| Common CAL |`$F`|`$E/results/original-v1/cal-inputs/{observations,metadata}.jsonl.gz`|payment_v3 A B|`$R/cal-ml-wrapper`|
| Full compatible archive — external ownership first |`$F`|`experiments/local_guards_v4/data/{observations,metadata}.jsonl.gz`|payment_v3 A B|`$R/archive-ml-wrapper` or existing accepted external receipt|
| Open old320 |`$F`|`experiments/local_guards_v3/closed-test/{observations,metadata}.jsonl`|payment_v3 only|`$R/old320-ml-wrapper`|
| Open old400 |`$F`|`experiments/local_guards_v4/closed/{observations,metadata}.jsonl.gz`|payment_v3 A B|`$R/old400-ml-wrapper`|
| First, already exposed1200 |`$F`|`$E/closed/{observations,metadata}.jsonl.gz`|payment_v3 A B|`$R/first1200-ml-wrapper`|
| New independent1200 |original `frozen` and corrected `$F`|controller's accepted new observation/metadata identities|as controller declares|CONTROLLER OWNED; reuse its committed receipts|

The reviewed wrapper must retain every eligible prefix, raw/gated operating
points and separately named argmax diagnostic, plus explicit per-check
exception→UNKNOWN receipts/counts. Exceptions must not silently drop states or
replace a threshold. Keep deterministic streamed/sharded predictions and hashes.
Do not batch-amortize the separate single-call latency measurements.

Reuse existing rule/TFIDF prediction receipts only on identical observation and
metadata hashes:

- CAL: `$E/results/original-v1/cal-controls` (three rules + unchanged TFIDF).
- Archive: `$E/results/original-v1/archive-controls`.
- Old320: `$E/results/original-v1/old320-controls`.
- Old400: `$E/results/original-v1/old400-controls`.
- First1200: `$E/results/closed-controls` (three existing rule controls).
- New1200: controller's identical-input control receipt; never borrow controls
  from the first1200 or regenerate accepted identical controls unnecessarily.

## Explicit episode registries

Archive: `experiments/local_guards_v4/data/episodes.jsonl.gz`,3378 members including
five no-prefix episodes. CAL:
`$E/results/original-v1-corrected-accounting/cal-registry/episodes.jsonl.gz`,2727
members including two CAL no-prefix archive members. Reuse its receipt and exact
prepare() `archive:` / synthetic episode IDs; never strip or recreate IDs.

Old400: `experiments/local_guards_v4/closed/episodes.jsonl.gz` (400 members).
Old320 and first1200 lack an already used explicit registry. After execution
release, construct minimal `{episode_id, split, source_intent}` registries from
their original non-label metadata, preserving IDs and declaring no inferred
source intent. Save independent input/selection/hash receipts at
`$R/registries/old320/` and `$R/registries/first1200/`; expected320/1200 members.
For new1200, use the controller's accepted non-label episode registry/identity;
no author/source/manifest/review read is necessary to obtain it.

## Scoring after timing; new1200 only after explicit gold release

Use `evaluation_revision2.py score`, bootstrap1000 and explicit
`--model-freeze "$F"` in every revision2 score. Below `ACCEPTED_*_ML` denotes the
verified wrapper output above, or an identical accepted external/controller
receipt. Resolve these variables only after receipt/ownership reconciliation.

```sh
"$FINBOT_ML_PY" "$E/evaluation_revision2.py" score --model-freeze "$F" \
  --predictions "$ACCEPTED_CAL_ML" "$E/results/original-v1/cal-controls" \
  --observations "$E/results/original-v1/cal-inputs/observations.jsonl.gz" \
  --metadata "$E/results/original-v1/cal-inputs/metadata.jsonl.gz" \
  --labels "$E/results/original-v1/cal-inputs/labels.jsonl.gz" \
  --episodes "$E/results/original-v1-corrected-accounting/cal-registry/episodes.jsonl.gz" \
  --split CAL --bootstrap 1000 --output "$R/cal-scores"

"$FINBOT_ML_PY" "$E/evaluation_revision2.py" score --model-freeze "$F" \
  --predictions "$ACCEPTED_ARCHIVE_ML" "$E/results/original-v1/archive-controls" \
  --observations experiments/local_guards_v4/data/observations.jsonl.gz \
  --metadata experiments/local_guards_v4/data/metadata.jsonl.gz \
  --labels experiments/local_guards_v4/data/gold-actions.jsonl.gz \
  --outcomes experiments/local_guards_v4/data/gold-outcomes.jsonl.gz \
  --episodes experiments/local_guards_v4/data/episodes.jsonl.gz \
  --bootstrap 1000 --output "$R/archive-scores"

"$FINBOT_ML_PY" "$E/evaluation_revision2.py" score --model-freeze "$F" \
  --predictions "$ACCEPTED_OLD320_ML" "$E/results/original-v1/old320-controls" \
  --observations experiments/local_guards_v3/closed-test/observations.jsonl \
  --metadata experiments/local_guards_v3/closed-test/metadata.jsonl \
  --labels experiments/local_guards_v3/closed-test/gold-actions.jsonl \
  --outcomes experiments/local_guards_v3/closed-test/gold-outcomes.jsonl \
  --episodes "$R/registries/old320/episodes.jsonl.gz" \
  --bootstrap 1000 --output "$R/old320-scores"

"$FINBOT_ML_PY" "$E/evaluation_revision2.py" score --model-freeze "$F" \
  --predictions "$ACCEPTED_OLD400_ML" "$E/results/original-v1/old400-controls" \
  --observations experiments/local_guards_v4/closed/observations.jsonl.gz \
  --metadata experiments/local_guards_v4/closed/metadata.jsonl.gz \
  --labels experiments/local_guards_v4/closed/gold-actions.jsonl.gz \
  --outcomes experiments/local_guards_v4/closed/gold-outcomes.jsonl.gz \
  --episodes experiments/local_guards_v4/closed/episodes.jsonl.gz \
  --bootstrap 1000 --output "$R/old400-scores"

"$FINBOT_ML_PY" "$E/evaluation_revision2.py" score --model-freeze "$F" \
  --predictions "$ACCEPTED_FIRST1200_ML" "$E/results/closed-controls" \
  --observations "$E/closed/observations.jsonl.gz" \
  --metadata "$E/closed/metadata.jsonl.gz" \
  --labels "$E/closed/gold-actions.jsonl.gz" \
  --episodes "$R/registries/first1200/episodes.jsonl.gz" \
  --bootstrap 1000 --output "$R/first1200-scores"
```

After explicit new-gold release, the controller supplies its accepted original /
corrected prediction receipts, matching controls, non-label episode registry and
gold path. Score them separately with `--model-freeze "$E/frozen"` versus
`--model-freeze "$F"`, into fresh versioned `new1200-original-scores` and
`new1200-scores`. Do not substitute one freeze's calibration summary for the
other. No new1200 gold command is activated in this prepared plan.

## Readback and stop conditions

- Verify accepted source hashes, model-freeze/input identities and every receipt
  before gold IO; full prefix coverage and exception accounting, no silent sample.
- Archive registry3378, CAL2727; no-prefix5/2 remain unassessed without observed
  guard evidence. Keep interruption bounds/null rates and no later-action credit.
- Same corrected CAL eligible/safe denominators remain payment1342/616,
  full A2725/787 and full B2725/501. Missing outcomes stay unknown.
- Preserve original-v1, corrected-accounting outputs, preliminary native and any
  failed partial directory. Do not rerun unchanged accepted controls or inference.
- Main seed17,29/43 sensitivity; no best-test-seed or raw-coverage winner selection.
  Same frozen41-quantile CAL search is not proof of global infeasibility.
- First1200/old320/old400/archive remain exposed diagnostics. Payment-view duplicate
  clustering/sensitivity remains separately qualified; no claim of independent
  payment policy states from raw row counts. Primary new1200 claims require its
  independent review, prediction-before-gold receipt and explicit release.
- Save logs, gzip data, hashes, manifests and exact argv. No main Russian report,
  learned-method fix, source patch or extra testing is part of this execution.

Prepared status only: no inference, timing, scoring, fit or test command was run
while writing this plan. Wrapper schema/hash acceptance, accepted observations,
coordinated START and new-gold release remain controller-owned gates.
