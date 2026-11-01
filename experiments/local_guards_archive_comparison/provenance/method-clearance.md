# Scoped method clearance review

**Not cleared: two important blockers.** The initial review is preserved. Reviewed `methods.py` SHA256 `12bd9937145be015f11e56fcbf100e3385846aec63e589162282fb935a01fec5` and `ml.py` SHA256 `d31d05ad1203255084eb7935cc4a3ea5550c52a720fd1e1dceb0c63e7302529a`. Full reviewed-file hashes are in the JSON companion.

## Remaining blockers

1. **Malformed operands become BLOCK or crash rather than UNKNOWN.** At `methods.py:208–224`, the authored positive fixture with supported `invoice_status=123`, `vendor_bank_details_present="true"`, or `proposal.invoice_id=True` returns BLOCK. These are wrong schema types, not established native violations. A supported list-valued Fraud recommendation raises TypeError in `ml.py:147`; a raw delegate return with list-valued `task_status` raises TypeError in `methods.py:125`. This directly conflicts with evaluation ruling 5. Validate types before comparisons/set membership, represent malformed operands as unknown/invalid, and retain BLOCK only when an independent valid operand proves a real violation. Raw tool results need this handling even when the normalized observation passed schema validation.

2. **An unexecuted Fraud proposal downgrades an established current HOLD.** `methods.py:142–166,228–234` changes native BLOCK to UNKNOWN after a lone later same-vendor `recorded_model_proposal`, without dispatch or return. This is explicitly reproduced and enshrined by `test_methods.py:53–58`. The interface states that such a proposal is not an observed invocation. It cannot establish a later reassessment or displace an existing current flag. Require evidence that a later same-subject reassessment actually occurred before marking old flag applicability unresolved. A merely proposed or explicitly failed follow-up should retain the current HOLD; same-call completion and arbitrary notes must not clear it either.

## Closed findings and accepted changes

M1 is closed: derived delta overflow becomes INVALID and the nonfinite value is not emitted. M2 is closed: target-scored/unscored/mixed populations and identities are explicit. Only fully target-scored episodes enter correct decisive coverage or legitimate stop denominators, while known unsafe ALLOW remains counted in mixed episodes. Native UNKNOWN remains a scored class.

The original P2 proof-order logic remains coherent: native task_status completion, later paired proposals, overlapping unknown order and actual known misorder are distinguished. P2 does not demand future payment arguments. The new current-flag logic preserves same-call completion and ignores free-text clearance; blocker 2 is limited to its separate later-call path.

The new generic native change features use a fixed tool-category vocabulary and counts of same-subject observed amount/account changes. Object IDs/accounts are equality inputs, not feature values; arbitrary notes, company names, source paths and script text are not vectorized. Counts are declared observed lower bounds.

The sparse LR StandardScaler is fit only inside `fit_one` on selected TRAIN rows, with the same group weights. CAL/inference only transform. Scaler object/parameters are saved and its settings are included in configuration; constant/unavailable fallbacks do not fabricate one. Target/role/placement attribution is retained, including empty-CAL infeasibility.

## Verification boundary

A single targeted synthetic command reproduced the two blockers from the authored fixture. It also ran one two-row LR numerical probe with a finite extreme amount; the fit returned with RuntimeWarning/ConvergenceWarning, so no additional numerical blocker is asserted without a demonstrated incorrect output. No model/file was saved by that command, and bytecode writes were disabled.

No real data, labels, selected predictions, archives, other experiment code, API or git operations were accessed. The full reported suite was not rerun. No source was edited. Executing the copied frozen code and checking weight/source hashes remains a separate root-owned acceptance condition.
