# Research execution ledger — plan: docs/research/2026-10-31-general-guards-plan.md

## Preflight

| Producer / consumer | Shared contract | Resolution |
|---|---|---|
| Custodian / rules and ML | policy + observation schema, TRAIN package | Freeze before developer dispatch; no labels in observations. |
| Rules / evaluator | tri-state decisions and proof gate | UNKNOWN counts toward standalone safe stops; never fabricate authorization. |
| ML / evaluator | frozen scores + CAL thresholds | No post-CAL fit; model/executor/group fields excluded. |
| Generator / evaluator | closed policy-only cases and separate gold | Generate after method freeze; predictions hash before reveal. |
| Evaluator / report | metrics, coverage, denominators | Action validity, source intent, continuation harm remain separate. |
| Every task | no inference API, immutable test protocol | Approved plan is the spec; no further user decisions needed. |

## Sources

- origin/main fetched 2026-10-31: dd3983c478bbda51c05ada9b3a79b8057206dd23.
- cheap-guards source: ec93a1b (existing publication branch).
- four-model source: 924e64b (existing comparison worktree).

## Progress

- Created isolated Git worktree and research/general-guards-v3-2026-10-31 branch from updated origin/main.
- Task1 dispatched to independent custodian /root/data_feasibility; developers not yet given data.
- Baseline native FinBot probe tests started with mock LLM and isolated /private/tmp SQLite.

- Task1 complete: 1352 episodes, 20153 prefixes, 277 groups; 207 TRAIN/70 CAL groups; all Luna TEST_EXECUTOR. Source manifest 01c4201c1cfcd8a5f4f22b4ee26e768373f01fdad5a6872e9226436e3ed9dd67.
- Tasks2/3 code complete: fresh TRAIN-only rule/ML developers, evaluator; independent prefreeze audit PASS; 157 v3 tests and 42 native probe baseline tests passed.
- Ruling: absence of flags/transfers is known only with authenticated fresh invoice plus complete ordered journal; missing history stays UNKNOWN. Source-oracle harm is separate from typed-contract harm.
- Ruling: experimental P4 is immediate finstripe__create_transfer; later process_payment bookkeeping excluded. Source/schema clarifications and all audit corrections occurred before first research fit or new test generation.
- Source/policy freeze saved in results/source-freeze.json; proceeding to one TRAIN fit per model/seed and CAL-only thresholds.
