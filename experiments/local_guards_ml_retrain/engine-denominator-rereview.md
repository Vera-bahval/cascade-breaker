# Spec Compliance

- **ADDRESSED. Spec compliance: PASS. Code quality: PASS within scope.** Reviewed base `26774d2` to head `5c62bf9` solely for the safe-CAL-denominator predicate, its regression coverage and new breakage in that fix. No new defect found within this scope.

# Findings Readback

- `experiment.py:213` now requires `safe_episodes>0` alongside the existing positive episode count, zero reached false ALLOW and <=5% safe-stop count constraint. With no safe episode, no threshold candidate can become the selected feasible result.
- `experiment.py:222-230` consequently returns both finite abstention thresholds at `1.000001`, `feasible=False`, `infeasibility_reason='unassessable_safe_denominator'`, and the existing `no_safe_cal_episodes=True`. Metrics retain a null safe-stop FPR; unconstrained argmax diagnostics remain separately available. The new reason also distinguishes ordinary positive-denominator constraint infeasibility from an unassessable denominator.
- `experiment.py:203-230` preserves informative-CAL behavior: when the safe denominator is positive, the added predicate is true and the previous confidence grid, reached-action constraints, episode objective, threshold tie ordering, raw/gated scoring and selection remain unchanged. A feasible result has a null reason.

# Regression Evidence

- `tests/test_training.py:138-158` checks a BLOCK-only CAL for raw and gated helper entry points: infeasible status, exact reason, zero safe count, null FPR, both sentinel thresholds, and retained correct unconstrained argmax diagnosis. Its informative ALLOW+BLOCK case checks feasible status, null reason, zero safe-stop FPR and complete correct episode coverage.
- `features-training-report.md:295-309` records this regression failing before the fix with two failures and one missing-field error. `features-training-report.md:311-327` records the covering 18-test run passing with exit0 and clean diff checking; the displayed output has no warnings. These are reviewed author-run results, not reviewer reruns.

# Scope and Assessment

- The prior acceptance of a disclosed vacuous-feasibility convention is superseded by this explicit pre-freeze requirement. A zero denominator now correctly prevents claiming feasibility of the safe-stop bound.
- Reviewed the supplied diff once and the appended report. No tests, corpus fits, git commands, historical artifacts or additional source inspections were run. Rebuilt prepared binaries, the independent episode-unit fix/audit and the latency-quantile brief amendment were not re-audited in this deliberately narrow review.
- **Approved for this predicate fix.** No blocker from this scoped denominator re-review remains before the separately authorized full-fit/freeze stage. This verdict does not establish corpus-wide model feasibility or measured test safety.
