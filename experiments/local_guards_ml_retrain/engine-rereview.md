# Spec Compliance

- ✅ Spec compliant within the scoped fix review, base `8e805e0`, head `2126729`. Both original Important findings are addressed; no new breakage found in the fixes.

# Original Findings

- **[P1] FeatureBatch inference: ADDRESSED — `models.py:80`.** `probabilities()` now preserves explicit `FeatureBatch`, so the pipeline recognizes precomputed CAL dictionaries rather than projecting them as observations. Ordinary iterable inputs still become lists; unavailable-model and empty-input behavior remain intact. `tests/test_training.py:80-93` compares precomputed and raw CAL probabilities for both feature modes and both model families after precomputed TRAIN fitting.
- **[P2] P2 delegation-call linkage: ADDRESSED — `features.py:258-259`.** The gate now rejects missing or mismatched current/delegation call IDs before ALLOW. The condition safely short-circuits absent keys and remains inside the P2 branch, preserving other cut applicability. `tests/test_training.py:95-111` covers valid linkage, mismatch and null IDs for A/B, with a valid claim for B.

# Evidence and Scope

- `features-training-report.md:226-240` records the targeted regressions failing before the fixes: four old/new × LR/CatBoost projection errors and two A/B mismatch failures; exit1.
- `features-training-report.md:242-258` records the covering 17-test run passing after both fixes, exit0, and clean diff checking. The shown output has no warnings. Tests were not rerun during this re-review.
- The supplied fix diff was reviewed once. No additional source inspection, corpus fitting, test creation, git commands or implementation changes were performed. Prepared corpus binaries and the prior review report are outside this two-finding re-review; their presence does not establish corpus acceptance.
- Previous qualifications about an unmeasured no-safe-CAL denominator and historical CAL bytes hashed for freeze integrity remain unchanged; this fix does not claim to resolve or broaden them.

# Assessment

**Spec compliance: Approved within scope. Code quality: Approved within scope.** Both fixes are small, directly repair the demonstrated defects and have relevant red/green regression evidence. No remaining blocker from these two findings prevents proceeding to the separately authorized full-fit stage.
