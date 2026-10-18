# External diagnostics v2 source review

SOURCE_REVIEW_PASS. Reviewed source and public synthetic fixtures only; no hidden observations, predictions, scores or labels accessed. Frozen MF05 files unchanged.

The v1 control identity bug is fixed: v2 requires control rows to match the exact main frozen row SHA and joins each episode/cutoff against sealed input provenance. Source, tests, method, prediction and row pins are required. Both evaluator UNBLINDED and the root release marker gate access.

Six independent public tests pass, including tied AP goldens and order invariance, absent-positive support, UNKNOWN/backend null preservation, and episode/cutoff swap rejection. Owner public integration test rejects swapped rows before any control file opens.

AP is stepwise precision-recall area with tied groups admitted together. Component/composite scores remain descriptive ranking signals. Cross-wrapper AP requires matched known cohorts or coverage caveats. The backend diagnostic is modeled policy violation, not measured financial loss or live prevention. This helper does not replace the pre-unblind full main label/pair validator.

Exact hashes are recorded in EXTERNAL_DIAGNOSTICS_REVIEW_V2.json.
