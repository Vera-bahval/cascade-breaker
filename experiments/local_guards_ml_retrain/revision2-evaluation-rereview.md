# Spec Compliance

- ✅ **Original P2, late STOP: resolved.** The new driver retains transaction status and completed-transfer journal evidence after the timed chain (`benchmark_revision2.py:280`), records the ordering relative to the first STOP, and rejects later invocations or confirmed transfers at/after STOP (`benchmark_revision2.py:288`, `benchmark_revision2.py:297`). A permitted earlier transfer is no longer discarded by the old zero-payment assertion.
- ✅ **Added accounting gap, registry-only episodes: resolved in the scoped interface.** The optional independent episode registry retains exact episode IDs and selected-split no-prefix/no-check members; it validates selected metadata membership, split and available intent agreement before target-label/outcome IO (`evaluation_revision2.py:329`). Registry-only membership creates no action or UNKNOWN decision. Unassessed legitimate members make the full-registry interruption point rate unavailable and contribute explicitly to interruption bounds (`evaluation_revision2.py:360`).
- ✅ **Added source-freeze interface: coherent.** `verify_predictions(..., model_freeze=...)` checks the selected source against model prediction receipts before target labels are opened (`evaluation_revision2.py:199`). The same resolved source manifest supplies CAL export. Version1 compatibility is scoring/accounting only; the versioned inference path remains revision2-only.
- ✅ The original frozen methods, original sources and published outputs are outside this path-scoped diff. These accounting changes do not alter feature extraction, learned weights, thresholds or policy.

# Strengths

- The late-STOP regression checks the actual intended path: transfer allowed at P4, first STOP on `process_payment`, one completed transfer strictly before STOP, invoice still approved and no later invocation (`test_evaluation_revision2.py:215`). Existing early-STOP checks now distinguish the before-transfer phase.
- Registry tests cover real observed UNKNOWN separately from missing guard evidence, selected no-check/no-prefix members, a zero-action method, registry identity errors before missing-gold IO, explicit v1 receipts and CAL export from the actual selected source. The report supplies14 passing own-fixture tests plus failed-first evidence for late STOP, missing registry support and omitted zero-check methods.
- Outcome accounting remains outside chain/check timing. Full-registry bounds and qualifications preserve the distinction between known outcome data and available STOP evidence.

# Issues

- Critical: none.
- Important: none found in this scoped re-review.
- Minor: none required for this gate.

# Checks and limits

- Reviewed only `.superpowers/sdd/PLAN/rev2-measurement-fix1.diff`, including its appended implementation report, for the original late-STOP finding, the added registry/freeze interfaces and direct fix breakage. The initial tool output was truncated in the middle; only the omitted middle hunks/report were retrieved afterward. No changed source file was read separately.
- No tests, corpus runs, full benchmarks, APIs, subagents, model inference or gold/data reads were performed. The recorded14-test result and focused regressions are sufficient for this accounting patch; existing suites were not repeated.
- The five archive members cited by the implementation report are parent-supplied evidence. This review verifies the registry interface and its fixture behavior, not the real archive membership/count or a completed full-archive result.
- This verdict does not claim final measurement acceptance, fitted-model quality, quiet-CPU timing evidence or completion of the independent new-test protocol. Only this re-review file was written.

# Assessment

**Specification: Approved for the reviewed fixes. Code quality: Approved.**

The late-STOP fix preserves prior effects without crediting their prevention. The additional registry and explicit-freeze interfaces keep missing decision evidence visible, preserve the intended denominators and validate provenance before target-label IO; no new blocking regression is apparent in the scoped diff.
