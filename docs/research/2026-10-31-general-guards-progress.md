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

- Task4 complete: independent policy-only author generated320 P4cases after model/threshold freeze; independent review PASS, 160pairs,233uniqueviews, noTRAIN/CAL overlap. Predicted25600armrows and hashed receipt before gold release. No method or threshold changes after release.
- Primary result: rules160ALLOW/95BLOCK/65UNKNOWN, exact320/320 tri-state; wrong safe stops0/160. LR/CatBoost fail distribution shift; results retained unchanged.
- Archive descriptive result: rules would prevent57/112 source-oracle harms, strict-contract168/168; formal safe-stop0/593 but source-legit interruption90/846. Staged checks same57 harms with325/846 interruptions.
- Task5 diagnostics: nativeFinBot+SQLite+FinStripeMCP fivefreshworkers verifiedzeroexternalconnections, no callsafterSTOP and duplicateblocked. Single-prefix rulep95 .01646ms. Text/identity invariance320rows PASS. SavedLLMcontext227P2 matches; all227finalviews rejectedforfutureprocess_paymentnotes;214reachablefallbackrequests,73matched/141unavailable.
- Final integrity PASS: source/policy/data/modelhashes unchanged; independent recount57/112 and320/320. Full157 v3 +42 source tests passed beforefreeze; newhelpers selfchecked without refits. Mainreport and staticplot written. Await consolidated final audit.

- Final consolidated independent audit PASS: all80arms, bothpredictionreceipts and exactcoverage, ninefittedhashes, CAL-onlyselection and independent57/112 /168/168 /320tri-state recount verified. Only README CLI wording corrected; no frozenmethod or threshold changes.
- Task5 complete: report, figure, reproducible code, immutable artifacts and independent audits committed. New inference API requests0. Research branch retained for user review.
