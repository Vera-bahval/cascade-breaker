# Spec Compliance

- ❌ One native measurement defect remains: a transfer followed by a later STOP aborts the trial instead of being recorded (`benchmark_revision2.py:279`).
- ✅ The explicit versioned adapters use revision2 extraction, model inference and gate imports (`evaluation_revision2.py:23`, `evaluation_revision2.py:25`, `evaluation_revision2.py:26`). The benchmark resolves that same evaluation module, including single, cold and native paths (`benchmark_revision2.py:34`).
- ✅ Original sources and methods are outside the supplied executable changes. Fitted-model smoke, full benchmarks, full-assessment sealing and the new closed-test author step remain later acceptance work, not claimed results (`revision2-evaluation-report.md:3`, `revision2-evaluation-report.md:154`).

# Strengths

- The adapter rejects version1 freezes and available pipelines whose stateless transformer is not `models_revision2.feature_rows`; the own fixtures cover both newly fitted and explicitly rebound tiny pipelines, including raw/precomputed/single inference and legacy-pipeline rejection (`test_evaluation_revision2.py:96`, `test_evaluation_revision2.py:137`). The named engine-interface inspection confirmed the shared FeatureBatch alias and explicit revision2 extractor in `models_revision2.py:16`, `models_revision2.py:25`.
- Checking-call identity is preserved. The common enrichment changes only an existing trusted native completion proof when its current checking-call binding, successful delegation context and actual `_INVOKING` source agree; absent/foreign/false evidence remains unavailable. Own fixtures exercise these cases and the old rule A/B disagreement on the identical corrected snapshot (`test_evaluation_revision2.py:35`, `test_evaluation_revision2.py:48`).
- Receipt verification still precedes target-label/outcome reads, and the accepted split-filtered registry, first-STOP reachability, bootstrap and quantile semantics are retained (`evaluation_revision2.py:418`, `evaluation_revision2.py:421`, `evaluation_revision2.py:449`).

# Issues

## Critical (Must Fix)

- None found.

## Important (Should Fix)

- **[P2] Record STOP after an already completed transfer — `benchmark_revision2.py:279`.** The blanket assertion that every stopped trial has zero PaymentTransaction rows is invalid for the actual native chain: `finstripe__create_transfer` precedes the later `process_payment` invocation, so a candidate can ALLOW the transfer and first STOP at that later check. The driver then raises `AssertionError('stopped fixture had a payment')` and produces no trial record, potentially aborting the planned all-model native benchmark. This is inherited from the original driver, but is also present in the new adapter being accepted. Keep the original frozen source unchanged; update the new adapter to retain the stopped status, existing payment count, invoice status and exact stop checkpoint instead of assuming STOP rolls back prior effects. Add an own diagnostic regression for this path and retain the no-post-STOP invocation check.

## Minor (Nice to Have)

- None required for this gate.

# Checks and evidence

- Read the new brief, REVISION_2_PLAN.md, P2_CALL_BINDING_CLARIFICATION.md and supplied `2fc8668..433fb8d` task diff once, including the implementation report. No changed source file was reread; no git operation was run.
- Named external interface risks checked: deserialized/reused transformer identity and shared FeatureBatch (`models_revision2.py`); versioned file-prediction receipt and freeze APIs (`experiment_revision2.py:240`, `experiment_revision2.py:416`); corrected completion versus checking proof binding (`features_revision2.py:103`, `features_revision2.py:259`); actual native success/source/checking provenance (`local_guards_v4/runtime.py:255`, `local_guards_v4/runtime.py:378`). No additional issue was found in those interfaces.
- The report supplies8 new own-fixture tests and15 legacy fixture checks passing. Those suites were not rerun. The constant-classifier and72-descriptor fixtures are explicitly diagnostic engineering evidence, not fitted-model quality/performance evidence. Existing Authlib/default-development-key/invoice-note warnings are disclosed; no timing conclusion under concurrent fitting is claimed.
- Ran one focused new reproduction with uniform numerical thread limits and the offline native fixture: an own diagnostic candidate ALLOWs through the transfer and returns UNKNOWN at `process_payment`. `native_trial` raises **`stopped fixture had a payment`**. This uses only scripted native calls and disposable SQLite data; it does not rerun a model benchmark or an existing suite.
- No original1200 source/gold/results, research TRAIN/CAL corpus, revision2 closed-test state, fitted research model, external API or subagent was used. Only this review report was written.

# Assessment

**Task quality: Needs fixes.**

The revision2 inference and native source-binding boundaries are coherent, and the copied reporting semantics retain the accepted fixes. The native driver must also preserve valid stopped-after-transfer outcomes before it can reliably measure every frozen candidate.
