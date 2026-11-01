# Revision2 engine implementation evidence

Status: stable for independent code review. No research-corpus reads, full fits,
new closed-set creation, API calls, commits or subagents performed by this worker.
The parent owns review, complete fitting, final freeze and subsequent independent
policy-only corpus authoring. Version1 files/models/policies remain immutable.

## Change and inference identity

`features_revision2.py` is a versioned copy of the original. Its only changed
function bodies are `proof_relations` and `_mandatory_proof_gate`:
completion proof `call_id` binds `context.delegation_call_id`; tool proof binds
`context.call_id`. P2 requires the two context IDs present, without requiring
that they equal each other. Original `context.delegation_call_matches` remains
an observable relation. No raw ID or dataset predicate was added. The corrected
proof relation applies at every stage; no payment/stage shortcut suppresses
unrelated source evidence. Newest eligible evidence/conflict/value/version logic
is otherwise unchanged.

`models_revision2.py` imports shared original `FeatureBatch` and
`UnavailableModel` types. Fixed parameters, fit_model, feature_rows and
probabilities function bodies are AST-identical to original. Module imports bind
new fitted Pipeline transformers explicitly to `models_revision2.feature_rows`,
which uses the revision2 extractor. `bind_reused_model` replaces only an existing
Pipeline's stateless feature function on a separately deserialized model. The
new revision2 pickle therefore supports ordinary raw/native single-row inference
without a special wrapper. Original pickle bytes and fitting manifests are never
rewritten. Learned vectorizer/scaler/classifier state hashes must match before
and after the explicit transformer replacement.

`experiment_revision2.py` preserves calibration, preprocessing/weight recipes,
class handling, seed loops, threshold tie-breaking, prediction/receipts and
artifact verification. AST comparison shows only original `fit`, `sources` and
`main` function bodies changed; `matrix_equivalence` and
`learned_state_fingerprint` are added. Shared original `FeatureBatch` keeps both
precomputed and raw inference compatible with versioned/reused models.

Before reuse, exact ordered TRAIN and CAL feature-dictionary fingerprints are
compared under original and corrected extraction. The proof also records row IDs,
labels, TRAIN weights and explicitly unweighted CAL. The prepared manifest must
match the original freeze; original model TRAIN-prefix, weight, input-manifest,
source and method provenance is checked. A/B new-feature arms always refit. Any
other arm with a dictionary mismatch refits using the unchanged parameters.
No expected reuse count is hardcoded. Matrix-equivalence and per-model versioned
provenance record original pickle SHA, new artifact SHA via freeze method entry,
unchanged fitted-provenance SHA, learned-state, class and preprocessing hashes,
source hashes and the reuse/refit reason. Reused `.model.json` is copied byte-for-byte;
its original fit provenance remains attributable to the original artifact.

CAL probabilities and raw/gated thresholds are recomputed using corrected
features and gate. No post-CAL refit was introduced. `sources()` includes original
inference sources needed by reused pickles, revision2 modules and own tests,
revision2 plan, original plan, unchanged six contracts and original v3 extractor.
The generic verifier body is unchanged and supports both manifest versions.
New CLI: `experiment_revision2.py fit --data PREPARED --output NEWDIR`, optional
`--original-freeze ORIGINAL`, with default output `frozen_revision2` and default
original `frozen`. Prediction remains labelblind and verifies source/artifact
hashes before unpickling. It supports all 72 methods and raw/gated variants.

## Own verification

Resource sequence: source work only until parent CPU-clear; all model tests below
ran after that explicit notice. Thread environment fixed to 2 as provided.

Command (from finbot-general-guards root):

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv/bin/python experiments/local_guards_ml_retrain/test_revision2.py
```

Output:

```text
test_conflicting_newest_value_is_unavailable ... ok
test_distinct_source_completion_is_available_and_relation_retained ... ok
test_foreign_proof_is_unavailable_and_features_distinguish_it ... ok
test_missing_source_or_checking_call_is_unavailable ... ok
test_newest_foreign_ignored_newest_bound_value_not_skipped ... ok
test_original_sources_unchanged ... ok
test_renaming_opaque_ids_does_not_change_features_or_gate ... ok
test_same_call_remains_available ... ok
test_tool_proof_binds_checking_call ... ok
test_labelblind_72_methods_both_variants_and_integrity_receipt ... ok
test_matrix_proof_includes_cal_and_dictionary_values ... ok
test_new_and_reused_pickle_raw_precomputed_parity ... ok
Ran 12 tests in 0.349s
OK
```

Own policy fixtures cover separate current/source IDs, correct completion binding,
foreign source, missing source/checking call, same-call case, current tool binding,
proof ordering, newer foreign versus newer bound mismatched record, newest
conflict, ID-renaming invariance and original source immutability. The gate's
unavailable ALLOW path becomes UNKNOWN in the retained decision code.

Tiny six-row fixtures exercise Logistic Regression and CatBoost, old and new
modes, new and versioned reused Pipelines, raw/precomputed/pickle probability
parity, unseen separate current/source IDs, shared batch identity, retained learned
state and zero/one-class handling. Reuse parity training fixtures have equal
original/revision2 dictionaries; unseen distinct-call counterfactuals exercise
the explicitly persisted corrected transformer. No research labels are used.

The 72-method prediction protocol fixture aliases one tiny model under 72 method
entries and asserts 144 raw/gated records, distinct method/variant identities,
no gold fields, labels_opened=false, and prediction receipt digest. It is a
protocol test, not 72 research fits or a performance assessment. Corrupt pickle
bytes are rejected by artifact hash validation before unpickling; generic manifest
version1 verification is also exercised.

Before the successful command, a test attempt with cascades/.venv-cheap exited
immediately with ModuleNotFoundError: catboost. No fitting occurred; the existing
parent-provided ML runtime fixed the interpreter selection without installs.

A stdlib AST parse of all four new Python files passed. AST delta auditing
confirms copied fit_model and calibration functions remain unchanged. Original
features.py/models.py/experiment.py SHA checks passed. Exact commands producing
these checks were inline Python using ast.parse, ast.dump(include_attributes=False)
and hashlib.sha256 against the read log; no external corpus scanning was used.

## Read and output hashes

`revision2-read-log.json` records authorized source hashes, operational instruction
reads and developed output hashes. No CAL gold/data, oracle, rule implementation,
closed set, old test/result/report, old 320/400 or otherthread material was read.
Initial failed `cat REVISION_2_PLAN.md` only checked the wrong root path, then the
explicit experiment path was read. Scope and development input hashes:

- `revision2-engine-brief.md`: `ea3cfe6e61daa002035bdc8c6b76672fe22a10399fb47b1616259fe89cbb502d`
- `REVISION_2_PLAN.md`: `3be079356d8fd1f46672d215e3eb0087d8a559558132bb5c05ec3019a2f95ce4`
- `features.py`: `06bff0aa070c89fda38d2ff61ba03940f72521c02ae9a5fe837be05650719c7b`
- `models.py`: `c270e53aa2d5636e5dae672f2ef77783f1b8837716befc124600ef1d0d8f3144`
- `experiment.py`: `ddea700e5293bb2f3200427a64bf650f82e6c910c79eee0a49c293cd1c2b2892`
- `v4-policy.json`: `5456778530e32b508cbf5d4f9eab78d383d83a91c927fefdf5e8f2e6b04492ca`
- `v4-schema.json`: `9e75dd6e2ae4cfac702b706d1a2b5408f71d6525b40c4a4dee3fc8fbbc04a07b`
- `v4-POLICY.md`: `8e0ba70727761edff5485bd4d0fb20af0bc48922cb9d1e12b23c3e8757c9306a`
- `v3-policy.json`: `bdaaffe0715d7b7233cc40e1ce7f6ada7989bac927269998aa5827d385f65c85`
- `v3-schema.json`: `62efd6d8ec3b1dced204d3705c9c2691b7e9af1d503c4327ce388e1e6be84711`
- `v3-POLICY.md`: `17416fe66bcefa6e16fe729dae93c19abb2e046421b603451446e8f73be07240`
- `ml_v3.py`: `62651a89b6745e8e966b05f6b66962638b39cde8424563a1694cee410c6db485`

Versioned implementation hashes after passing checks:

- `features_revision2.py`: `74d007f275120dce9dfca1b6ce86097a95f85ea348e032693eeaa908a60a37cc`
- `models_revision2.py`: `550c99c3f75b52964a548af1cb04c6d7a4b73ee1342fd5fe075b8a06767fed75`
- `experiment_revision2.py`: `9091efe468f2786cb63ee6dcd6a401383262ed3bce089a09707cbc1dc311f7a3`
- `test_revision2.py`: `1275248c90a2d8c78ccc2022391d6a3dcea4c17611015ff31a85ea1c2d9552b5`

## Pending parent-owned acceptance

Independent code review and the actual TRAIN/CAL equivalence audit/full fits are
still required. No reuse count, corpus performance or final frozen acceptance is
claimed here. Parent must retain a complete new freeze before dispatching the
fresh policy-only closed1200 author/reviewer, and preserve the original freeze.
