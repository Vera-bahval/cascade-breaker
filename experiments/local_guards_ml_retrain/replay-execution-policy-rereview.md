# Spec Compliance

- ✅ **Original P2, missing/unusable event timing: addressed.** The replay writer preserves missing time as null and existing null/string values without input mutation or a metadata fallback (`replay_predictions.py:166`). The downstream join uses the same unavailable-value representation (`evaluation_revision2.py:316`), removing the second missing-key failure.
- ✅ Temporal replay checks source timestamp availability before sorting. An episode with a missing, null, string, boolean, negative or other invalid time retains its eligible action rows but receives unavailable ordering, reachability, first-STOP/correctness and stopped status. Globally unordered episodes remain unordered in slices; the existing numeric sort/tie convention is retained for valid numeric episodes (`evaluation_revision2.py:414`).
- ✅ Stop-dependent accounting and calibration do not turn zero assessed reached rows into a safety/pass claim. Unavailable ordering is exposed through explicit assessed/unassessed action/episode denominators, null unsupported full-episode rates/constraints, assessed-subset rates and qualified registry interruption bounds. Action confusion/coverage remains based on all eligible rows.
- ✅ Related rule/TFIDF control wrappers apply generic callback-exception UNKNOWN/STOP policy and preserve unavailable event time; they do not repair the unchanged frozen controls (`evaluation_revision2.py:141`). No feature/model/threshold or observation change appears in this scoped fix.

# Strengths

- The new mixed-time own fixture exercises both method revisions and old/new modes through replay, exact receipt coverage, control prediction and scoring. A deliberately supplied metadata time999 does not replace missing source time. It checks all4 action rows, no reached-action credit, null episode/prevention rates and explicit CSV availability counts (`test_replay_predictions.py:208`).
- The valid-numeric regression retains first-STOP and strict prevention behavior, including the cross-checkpoint no-later-credit slice. The separately run numeric metric fixture recursively checks that every pre-existing metric value is unchanged while allowing the new availability fields (`test_evaluation_revision2.py:67`).
- Registry stop-evidence availability now includes unordered eligible episodes separately from no-check/no-prefix members. Unknown stop evidence contributes to bounds rather than being counted as observed UNKNOWN or no STOP.

# Issues

- Critical: none.
- Important: none found in the scoped fix.
- Minor: none required for this gate.

# Checks and evidence

- Reviewed only `.superpowers/sdd/PLAN/review-7e9f7334..9ca02e97.diff`, the requirements and appended implementation report, for the original P2 and direct breakage from its fix. No changed source file was read separately and no broader audit was performed.
- Supplied evidence: failed-first missing/mixed-time and missing-time payment-control regressions, then9 targeted tests passing in1.375s and1 numeric metric compatibility test passing in0.802s. No successful test, corpus/fitting/timing run or integrity check was repeated by this reviewer.
- The report records unchanged revision2 manifest bytes plus all model, threshold, freeze-member and frozen-source hashes, and the nine protected sources matching the initial read log. These are supplied drift-verification evidence, not an additional independent model/corpus acceptance claim.
- No new closed2 observation, gold, source, manifest, author/review content, API or subagent was accessed. Only this re-review file was written.

# Assessment

**Specification: Approved for the original finding and its fix. Code quality: Approved.**

The fix preserves malformed-time membership through output and scoring, keeps valid numeric semantics, and makes unsupported temporal conclusions unavailable instead of inventing timestamps or dropping actions. No new blocking regression is apparent in the scoped delta.
