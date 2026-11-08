# Spec Compliance

- ❌ Issues found at `models.py:80` / `experiment.py:309` and `features.py:255-260`: the full-fit CAL interface fails on precomputed features, and the P2 mandatory-proof gate does not reject an explicitly mismatched delegation call. Base `c24ff91`, head `8e805e0`.
- ⚠️ Not established by this task-scoped diff: corpus-wide prepare/fitting results, collision counts, 72 completed model artifacts, or native adapter correctness. Full fitting is intentionally deferred; `features-training-report.md:183-203` is explicit about this limit.

# Strengths

- `experiment.py:82-88,289-310` implements mean-one, equal-source/equal-base-group weights and a common contract-specific CAL outside the four arm loops. The fixed loops produce 72 requested model configurations without CAL refitting.
- `models.py:30-34,60-74,83-85` separates precomputed and observation inputs, fits preprocessing on TRAIN, supplies explicit no-class unavailability and constant one-class behavior, and maps absent classes to exactly zero. The separation is sound in design; the probability wrapper defect below breaks its CAL use.
- `features.py:80-128,140-148,153-185` keeps proof-source permissions, newest-evidence selection before value/version matching, normalized Decimal equality, scope and binding relations, and finite typed structural features separate from labels and the gate result.
- `features.py:255-282` respects the major cut boundaries: no P4 readiness at P2; optional human approval only above 10000; human clearance only after a known HOLD; gate failure yields UNKNOWN at `experiment.py:363-370`, never a new business BLOCK.
- `experiment.py:237-244,350-356` verifies frozen artifacts before unpickling and requires frozen threshold membership. `experiment.py:309-319` calibrates and records raw/gated variants separately, preserving gate attribution.

# Issues

## Critical (Must Fix)

- None found within this review scope.

## Important (Should Fix)

- **[P1] Preserve FeatureBatch during probability inference — `models.py:80`, called by `experiment.py:298,309`.** `rows=list(rows)` discards the marker that `feature_rows()` uses to recognize precomputed dictionaries. Every available model in the full fit therefore receives its CAL feature dictionaries as if they were raw observations; `project_v3()` attempts to access `checkpoint` and fails. A minimal one-class LR trained on `FeatureBatch([{'x':1.}], 'old')` succeeds, but `probabilities(model, FeatureBatch([{'x':1.}], 'old'))` raises `KeyError('checkpoint')`. Preserve the wrapper as `fit_model()` already does, and add a focused regression that compares raw-observation and precomputed CAL probabilities for the same model. Full72 fitting cannot proceed reliably until fixed.

- **[P2] Reject mismatched P2 delegation-call linkage — `features.py:255-260` and `features.py:101`.** The P2 branch requires successful completion and nonempty parent/delegation IDs, while proof validation binds the attestation only to `context.call_id`. It never requires `context.delegation_call_id == context.call_id`. A schema-valid own fixture with successful registered child, valid prior scoped server-context proofs, `call_id='current-call'` and `delegation_call_id='other-call'` returns `{'allow': True, 'reasons': []}`. Its feature at `features.py:167` correctly records the mismatch, but a classifier ALLOW passes the mandatory linkage gate. Require the applicable current/completed call linkage to agree before allowing P2; add a mismatched-linkage regression. This concerns the required technical linkage, not a business verdict or proof-source authentication claim.

## Minor (Nice to Have)

- None requiring implementation changes beyond the regressions above.

# Focused Checks and Qualifications

- **New reproduction, not a suite rerun:** used the installed ML interpreter with `PYTHONDONTWRITEBYTECODE=1` for the exact FeatureBatch probability path, no-safe-CAL helper case, and the P2 mismatched-call fixture. No corpus fit, prior test artifact, LLM API, git command, or implementation mutation was used. Existing 15-test results were read from `features-training-report.md:190-202` and were not rerun.
- **No-safe CAL adjudication — `experiment.py:213,227` and `features-training-report.md:137-140`:** a BLOCK-only one-episode CAL returns `feasible=True`, `no_safe_cal_episodes=True`, `safe_stop_fpr=None`. The zero-count inequality is vacuously satisfied. This matches the report's explicit unmeasured-denominator convention, so it is not an undisclosed calculation defect; it does not establish a measured safe-stop FPR of at most 5%. Downstream reporting must retain the flag/None and qualify feasibility accordingly.
- **Frozen CAL gold adjudication — `experiment.py:317,324,237-244,337-345`:** freeze verification reads bytes of all frozen CAL artifacts, including their stored `gold`, for integrity hashes. It does not load new-test gold or use CAL gold to score new observations. Thus the closed-test boundary is preserved; “never opens labels” and receipt `labels_opened=False` should be interpreted as no prediction-dataset supervision, not literally no historical supervision bytes read.
- **Named unchanged-source risk checked: gate applicability/provenance interpretation.** Inspected only the copied `v4-POLICY.md`, `v4-policy.json` and `v4-schema.json` to compare P2 linkage, proof freshness, material-version applicability, optional permissions and B binding/claim shapes. `v4-POLICY.md:71-85,101-105` supports the source/time/scope and current-snapshot interpretation. The stricter material-version map is explicitly proposed and disclosed at `features-training-report.md:101-124` and frozen at `experiment.py:328-329`; no separate defect is assigned merely for that disclosed ambiguity. Revoked B approval is represented as null by the trusted producer (`v4-POLICY.md:101`), so no fabricated revocation field is required.
- **Diff handling:** the first tool result truncated the middle of the supplied package; only omitted hunks were subsequently retrieved to complete the single review pass. No changed source was separately reread for review.

# Assessment

**Task quality: Needs fixes.** The data/model/calibration separation and explicit limitations are well aligned with the brief, but the exact full-fit inference interface currently crashes and the P2 gate omits a required technical linkage check. Fix these before full fitting or creating the closed test.
