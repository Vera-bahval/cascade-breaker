# Independent pre-freeze audit

Status: **PASS for method freeze**. No unresolved material correctness blocker remains in the reviewed pre-freeze sources. This permits the planned frozen research run and independent closed-test creation; it does not assert empirical quality, achievement of the 5% target, or live prevention. No closed-test case creation or reveal was used in this review.

The implementation follows the approved design in its main boundaries: typed structured guards; text-only diagnostic separated from structured features; TRAIN-fitted preprocessing; fixed hyperparameters; grouped TRAIN/CAL; Luna outside both; seed 17 primary selection; UNKNOWN counted as a stop; episode-union calibration; strictly earlier stops for counterfactual prevention; P5 and post-transfer bookkeeping excluded from prevention; controlled serial API-free native replay. These are code/protocol conclusions, not classification-quality or live-prevention claims.

## Material findings and verification

- **Resolved clearance chronology.** `rules_v3.py` accepts a human-clearance proof before a later binding flag because it checks only the fact boolean. A synthetic independent-registry clearance at event 1, native binding hold at event 2 and P4 cut 3 returned ALLOW with no missing proof. The policy requires clearance of this exact binding hold. A stale clearance must not authorize the later hold; the guard, missing-evidence gate and any oracle accepting such evidence must agree. No archival example was involved. The correction now rejects clearance before or at the latest hold, accepts a later independent clearance, and includes unavailable clearance in the standalone ML proof gate. Independent synthetic assertions verified all three chronologies.

- **Resolved currency oracle consistency.** The intermediate `prepare_data.py:426-431` checked only invoice/proposal currency equality. A fully evidenced EUR/EUR P4 synthetic observation yielded action-gold ALLOW and rules BLOCK. The frozen policy explicitly requires USD. Whitespace/case normalization must also agree. This was reported and corrected before method freeze. Independent assertions now confirm EUR/EUR BLOCK, whitespace/case-normalized USD ALLOW, and missing/blank currency UNKNOWN in both rules and action gold.
- **Structured currency feature correction verified.** The initial ML features equated USD/USD and EUR/EUR. The current code adds normalized proposal/invoice policy-currency relations. A synthetic comparison confirmed the feature dictionaries now differ. This was found from the policy, not archival examples or closed-test results.
- Previously identified fixes were reconciled: missing independent manual approval must be UNKNOWN; scoped Fraud review must show current invoice inventory; primary observed harm must use original source scenario oracle plus native completion separately from typed contract harm; missing hold-clearance proof must gate standalone ML; prediction evaluation must verify metadata identity/hash; compressed predictions remain deterministic and hash-verified. Code inspection plus independent synthetic assertions verified the authorization and source/contract separation; scoped Fraud extraction was inspected with the corresponding synthetic regression source.

## Final corruption and subject-scope checks

The evaluator now checks exact observation/metadata membership and per-method eligible prediction count/hash before opening gold. An independent minimal synthetic freeze/predict/evaluate exercise rejected missing, duplicated and extra observations, and missing, duplicated and unknown-method predictions. Gold paths deliberately did not exist: every corrupt-input case failed with the intended ValueError before gold access. Deterministic gzip round-tripped in this exercise. No research fit or prediction was involved.

A direct native-getter-context synthetic check established current invoice 1/vendor 2/account A. The matching transfer proposal was ALLOW. A foreign invoice, absent invoice ID, foreign vendor, or both foreign identifiers left the amount/account relation proof unavailable and yielded UNKNOWN in both rules and action gold. The raw identifiers remain inside the extractor, outside model features; no new feature was required.

## Scope and limitations of metrics

Episode action gold is intentionally based on P4 proposal labels. An episode containing only an eligible P2 BLOCK-gold row is episode-UNKNOWN. Thus `intervention_recall` is recall on episodes with a policy-violating proposed transfer; it is not recall across all early intervention-positive actions. The evaluator report states the denominator. Source-benign interruptions and source-oracle continuation harm are necessary separate views. No retrospective STOP is live causal prevention.

The router optimizes a declared bounded CAL quantile grid, not all real-valued threshold pairs. This is disclosed. Batch-amortized score timings are not online latency; controlled serial replay does not establish concurrency safety. Old/raw64/hidden240 data are development evidence; Luna is same-scenario executor shift, not unseen-family validation. The independent 320-case test can establish synthetic contract behavior only.

## Integrity checks performed

A metadata-only integrity check found zero duplicate prefix IDs, zero TRAIN/CAL group overlap, zero inconsistent episode group/split/executor identity, zero Luna rows outside TEST_EXECUTOR, and zero non-Luna rows in TEST_EXECUTOR. No research predictions, fit, calibration or inference API was run by this auditor. Synthetic predictions used only an always-ALLOW control and a tiny local fixture; they created no learned model. The settled source-manifest SHA-256 is `01c4201c1cfcd8a5f4f22b4ee26e768373f01fdad5a6872e9226436e3ed9dd67`; its extractor, schema and policy hashes match the actual current sources. Independent synthetic assertions covered currency normalization/policy matching, absent authorization, stale/equal/later clearance, standalone proof gating and source-versus-contract outcome separation.

## Read audit

Read: approved plan and progress ledger; canonical workspace AGENTS; all nine assigned v3 source/policy/schema/interface files; developer/custodian/evaluator reports; synthetic unit-test sources; initial verification evidence; data source manifest, split/summary metadata and metadata rows. Inspected native FinStripe create-transfer, native flagging, reference payment policy and historical run-record wrapper source for boundary/default/provenance support. Read the installed using-superpowers skill, whose subagent stop clause applies.

Not read: raw research observations, full action/outcome gold, TRAIN package rows (allowed but unnecessary), raw TEST episodes/observations/gold, future independent closed-test cases/gold, archived LLM calls, model artifacts or TEST predictions. Reading aggregate data summaries exposed aggregate counts only; no method or threshold was chosen from them. No edits outside this audit report; no shared Git operations; no subagents; no network or inference API calls; no full-suite rerun.

## Audited source SHA-256

- `prepare_data.py`: `89490353defde60ab46136de29cf0f1ed12c23f85f56c5d1ede99b0c5bd584f9`
- `rules_v3.py`: `279a3b8bfc37f4244e67696eba0150c84ed71d67a0f6b527dc32279c002bf38b`
- `ml_v3.py`: `62651a89b6745e8e966b05f6b66962638b39cde8424563a1694cee410c6db485`
- `evaluate_v3.py`: `94d6ac87d18920ec79328eeb4271419efae948c62592d3792d66772707f2b761`
- `legacy_adapter.py`: `5fe68237e835fdd01aaaa9a46d080a15a730aa4d3b94fcdf9f6d56d846dbfe54`
- `integration_replay.py`: `466dcededae04065f37bd56aa36725a8673099aed5fad05ded9149b853109573`
- `policy.json`: `bdaaffe0715d7b7233cc40e1ce7f6ada7989bac927269998aa5827d385f65c85`
- `schema.json`: `62efd6d8ec3b1dced204d3705c9c2691b7e9af1d503c4327ce388e1e6be84711`
- `POLICY.md`: `17416fe66bcefa6e16fe729dae93c19abb2e046421b603451446e8f73be07240`
