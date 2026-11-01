# Spec Compliance

- ❌ One generic malformed-row retention gap remains: an eligible row without event_seq aborts the replay writer; serializing only a null value would also leave downstream scoring failures (`replay_predictions.py:165`, `evaluation_revision2.py:309`, `evaluation_revision2.py:407`).
- ✅ The replay selects original versus revision2 modules explicitly, validates the corresponding freeze version and persisted feature callback/mode, and uses that revision's feature extractor, probability helper, threshold decision and gate (`replay_predictions.py:34`, `replay_predictions.py:44`). No frozen feature/model/threshold/input repair appears in this delta.
- ✅ Separate raw/gated thresholds and argmax streams are retained. Feature/model failures remain per-row UNKNOWN/STOP with unavailable scores; batch scoring retries affected rows individually, and gate-only failures affect only the gated result (`replay_predictions.py:69`, `replay_predictions.py:102`). No artificial UNKNOWN class probability is introduced.

# Strengths

- Available frozen probabilities pass unchanged through the shared FeatureBatch interface. Unavailable models bypass extraction as in their frozen helper, retaining their actual all-zero scores rather than receiving invented class mass. The targeted fixtures check both revision-specific gates, separate thresholds, singleton fallback and absent-class behavior (`test_replay_predictions.py:97`, `test_replay_predictions.py:169`).
- Frozen.one catches escaped checker failures while leaving constructor/integrity failures fatal, and optional benchmark probes retain the already measured main result. Failed feature/probability/equivalence components have separate error details and unavailable component timing, without replacing the main latency or decision (`evaluation_revision2.py:101`, `benchmark_revision2.py:112`).
- Receipts retain exact eligible prefix coverage, selected source freeze and adapter/helper hashes, error policy/counts and label-blind flags; both temporary revision receipts were verified by the existing scorer interface in the supplied six-test evidence (`replay_predictions.py:172`, `test_replay_predictions.py:90`).

# Issues

## Critical (Must Fix)

- None found.

## Important (Should Fix)

- **[P2] Preserve unavailable timestamps through replay and downstream accounting — `replay_predictions.py:165`.** The per-check catches do not protect the output expression `revision.features.obj(row)['event_seq']`. `eligible` requires a valid checkpoint, not the presence of this field (`experiment.py:60`), and metadata validation only checks checkpoint agreement. Therefore a row with a valid prefix_id/P0 checkpoint but no event_seq reaches this expression and raises KeyError, aborting the entire replay instead of retaining that eligible prefix. This violates the generic policy/coverage requirement even though the known string-timestamp fixture passes.

  Minimal own fixture: take the existing unlabeled `fixture()`, remove only event_seq, wrap it as `{'prefix_id':'missing-time','observation':row}`, and give it matching metadata with episode_id and checkpoint. Exercise both method revisions and old/new modes. The adapter must preserve the input and row membership, record timestamp/order evidence as unavailable, and retain the applicable frozen decision or exception UNKNOWN/STOP; it must not manufacture an integer timestamp, normalize the observation or drop the row. Also cover explicit null and the existing nonnumeric string.

  Fix compatibility through scoring, rather than moving the abort: the receipt verifier already accepts prediction rows without validating event_seq (`evaluation_revision2.py:236`), but `join_record` rereads the missing observation key at line309. With a null timestamp serialized instead, `replay` compares raw timestamp values at line407, so a multi-prefix episode containing null/string and integer times raises TypeError. Stop-dependent outcome comparisons likewise require comparable timing (`evaluation_revision2.py:433`, `evaluation_revision2.py:435`, `evaluation_revision2.py:438`). Preserve valid numeric ordering exactly; retain all eligible action rows and explicitly withhold temporal/reachability/prevention credit where the source evidence cannot establish ordering. Add focused own fixtures covering receipt verification and this downstream path, without changing either frozen method or prefiltering the malformed state.

## Minor (Nice to Have)

- None required for this gate.

# Checks and scope

- Read `provenance/replay-policy-brief.md` first, then the supplied `1792bbd3..65301bb9` delta and implementation report once. Reviewed only this execution-policy adapter and the two new measurement-hook changes.
- Named source-only compatibility check for the concrete missing/null timestamp finding: unchanged eligibility and frozen approval relations; current scorer receipt validation, join_record, replay ordering and stop-dependent outcome comparisons. The parent explicitly requested this downstream check. Only those named sections outside the diff were inspected; no broader audit was performed.
- The six targeted own-fixture tests are recorded passing in1.247s. No test was rerun and no new execution fixture was run: the missing-key and mixed-type comparison failures follow directly from the shown expressions. The minimal regression fixture above is a repair requirement, not claimed executed evidence.
- No corpus/fits/timing run, new closed2 observations/gold/manifest/author/review content, API, subagent or original failed parent artifact was used. Only this review report was written.

# Assessment

**Specification: Needs fixes. Code quality: Needs fixes.**

The adapter correctly separates execution policy from the frozen methods for the covered feature/model/gate failures. Its row writer and downstream temporal accounting still assume a usable timestamp, so the generic malformed-row guarantee is not yet complete.
