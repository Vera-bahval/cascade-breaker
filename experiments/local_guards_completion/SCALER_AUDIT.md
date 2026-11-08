# Frozen OOF scaler audit

**PASS: no numerical failure of the fitted classifiers.** The four LR-fold
warnings arise from a square root of tiny negative weighted variance estimates
for exactly constant FIT columns. No refitting, warning suppression, threshold
change or mutation of the frozen model/source files was needed.

## What was checked

Loaded all ten hash-verified model bundles and reconstructed their actual FIT
and outer-test matrices from the frozen `records.jsonl.gz`. FIT membership was
taken from each model's `resolved_fit_prefixes`; outer-test membership came from
the frozen `folds.json`. No action labels were loaded for this diagnosis.

All saved LR `mean_`, `var_` and `scale_` entries are finite, and every scale is
positive. All raw FIT/test matrices and all scaled LR FIT/test matrices are
finite. For each negative variance column the independently reconstructed FIT
values are exactly equal, sklearn marks the column constant, and the saved scale
is exactly 1. CatBoost has no StandardScaler.

| Fold | FIT rows | Test rows | Feature columns | Negative LR variances |
|---|---:|---:|---:|---:|
| 0 | 319 | 116 | 143 | 0 |
| 1 | 319 | 107 | 147 | 37 |
| 2 | 320 | 106 | 147 | 1 |
| 3 | 320 | 106 | 143 | 39 |
| 4 | 319 | 107 | 140 | 44 |

There are 121 negative entries across folds, involving 47 distinct feature
names. The largest absolute negative variance is `4.1325973271096046e-41`.
The largest `abs(var) / max(mean**2, 1)` is `1.6530389308438325e-44`.
Full per-column values, reconstructed ranges, constant masks and sklearn's
constant-feature error bounds are retained in `scaler-audit.json`.

The installed scikit-learn 1.9.1 implementation computes its constant mask on
the raw variances before taking the square root. Its subsequent
`_handle_zeros_in_scale(..., constant_mask=...)` replaces these constant-column
scales with 1. The warning therefore describes an intermediate arithmetic
operation; no NaN remains in the stored scales or transformed observations.

Finally, recomputed all 1084 outer-test probability rows from the frozen LR and
CatBoost models. Every probability is finite, in [0, 1], and each row sums to 1.
All probabilities match the saved OOF results exactly (`max_difference=0.0`
for each of the ten model/fold combinations; acceptance tolerance `1e-10`).
Current records, prediction and all ten model-file hashes match their frozen
identities.

## Scope

This audit resolves the scaler warning for these frozen models. It does not
validate annotation correctness, the chosen task target, representativeness,
generalization, or reliable safety estimates from a small admissible class.
No study API calls or extra fits were performed. The diagnostic probability
reconstruction was not a latency measurement.
