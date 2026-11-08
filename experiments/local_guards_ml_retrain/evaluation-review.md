# Spec Compliance

- ❌ Issues found: the phase1 scoring driver does not preserve the requested split when computing all-registry outcome denominators (`evaluation.py:426`, `evaluation.py:442`).
- ✅ Phase1 boundaries are respected in the supplied diff: full archive/new-test scoring, all72-model measurements and the final Russian results appendix remain explicitly not yet executed, rather than being presented as completed evidence (`evaluation-report.md:3`). They are later acceptance work, not missing phase1 code.
- ⚠️ The provided package is task-scoped, base `ad77387` to head `ccc1e4f`. Protected-artifact identity and the recorded14 own-fixture checks/13 native trials are supplied evidence; this review did not regenerate them or audit interleaved out-of-task commits. The final whole-experiment audit still follows full measurements.

# Strengths

- All supplied prediction receipts are verified before target labels or outcomes are opened (`evaluation.py:412`, `evaluation.py:413`, `evaluation.py:415`). Verification checks exact eligible prefix sets rather than relying only on row counts.
- Reachability is marked on the full method stream before checkpoint/family/source slices are built (`evaluation.py:437`, `evaluation.py:439`). The supplied regression test exercises a later P4 decision after an earlier P0 STOP.
- Frozen full-observation inference and cached-feature inference use the same unchanged `models.FeatureBatch`/`probabilities` contract; the focused inspection of unchanged `models.py:24` and `models.py:79` found no alternate feature or inference implementation.
- The native adapter's linkage enrichment is consistent with the unchanged runtime's actual delegation provenance: `_INVOKING` contains the source agent and original call observation, and `child_complete` already supplies the same delegation call ID (`local_guards_v4/runtime.py:308`, `local_guards_v4/runtime.py:378`). Existing `check`/`invoke` stop guards remain on the real execution path (`local_guards_v4/runtime.py:274`, `local_guards_v4/runtime.py:292`). No policy/proof relaxation was found in that enrichment.

# Issues

## Critical (Must Fix)

- None found.

## Important (Should Fix)

- **[P2] Restrict the all-registry outcome universe to the selected split — `evaluation.py:442`.** `score(..., split='CAL')` filters prediction rows at line426, but then calls `registry_outcomes(variant_rows, meta, truth)` with metadata for every split. Consequently its `outcomes_all_registry` includes TRAIN/TEST episodes that cannot have a CAL prediction, treats them as unreached and dilutes legitimate-interruption and harm-prevention rates. This affects the explicitly documented same-corrected-CAL command as well as any other split-specific report. Pass metadata filtered to the same split while preserving episodes within that split that have no applicable check. Add a regression checking both the all-registry episode count and its outcome denominators.

## Minor (Nice to Have)

- None required for this gate.

# Checks and scope

- Read the supplied brief, implementation report and complete task diff once. No changed source file was reread, no git operation was run and no gold/closed-label file was read.
- Named unchanged-code checks: inference parity (`models.py`); eligibility/original prediction receipt compatibility (`experiment.py`); native delegation provenance and stop propagation (`local_guards_v4/runtime.py`); historical TFIDF missing-text abstention (`local_guards_v4/latency_followup.py:82`). These checks found no additional issue.
- Ran one focused reproduction for the new split-denominator doubt, using temporary, self-authored observations/metadata/labels only: one CAL and one TRAIN episode, both legitimate, `controls --contracts A`, then `score(..., split='CAL', bootstrap=0)`. Result: eligible episodes1, ordinary outcome episodes1 and legitimate interruption1.0; **all-registry episodes2 and legitimate interruption0.5**. The expected CAL all-registry values are1 and1.0. No existing smoke or suite was rerun.
- The supplied own-fixture evidence reports11 evaluation tests and3 benchmark tests passing. Native smoke warnings are explicitly disclosed in the implementation report; they do not establish clean full-benchmark output or constitute real-LLM evidence.

# Assessment

**Task quality: Needs fixes.**

The inference, receipt and benchmark boundaries are coherent for phase1, but split-specific all-registry metrics currently use the wrong population. Fix that denominator before accepting the drivers for the planned full measurements.
