# Consolidated independent final audit

**Verdict: PASS for the approved research deliverable, specification compliance and reporting quality.** No unresolved material correctness, leakage, denominator, chronology or reproducibility blocker was found. This is acceptance of the experiment and its bounded conclusions, not acceptance of every evaluated method as a useful guard. The learned classifiers' large closed-test error rates are valid negative results and are preserved.

Audited worktree: `research/general-guards-v3-2026-10-31`; implementation commit `a0209ef`, results commit `4245933`. The final documentation/artifact-manifest commit may follow this report. Earlier implementation issues and their independent synthetic verification remain in `prefreeze-audit.md`.

## Independent result recount

The auditor streamed the frozen prediction files directly and joined raw action/outcome gold and metadata without invoking the evaluator's aggregation functions, fitting a model or changing a threshold.

| View | Independently confirmed result |
| --- | --- |
| Archive rules P4 | 57/112 original-source harms stopped before the first harmful transfer |
| Archive strict contract | 168/168 contract harms stopped before the first contract-harmful transfer |
| Archive formal safe P4 | 0/593 stopped |
| Archive source-legit tasks | 90/846 interrupted at P4; 325/846 with staged placement |
| Closed rules | 160 ALLOW→ALLOW, 95 BLOCK→BLOCK, 65 UNKNOWN→UNKNOWN |
| Closed rules autonomous decisions | 255/320; all 65 UNKNOWN remain stops/escalations |
| Closed LR / CatBoost, seed 17 | 128/160 and 124/160 safe stops; 16/95 and 9/95 proven violations incorrectly allowed |
| Closed legacy v1 / v2 | 76/160 safe stops for each; 95/95 proven violations stopped |

The other reported closed-table and archive-table counts also matched the independent recount. UNKNOWN is counted as a stop, not as approval. The archived source oracle has 112 harmful, 1,162 nonharmful and 78 unknown episodes; the separate contract oracle has 168 harmful, 1,156 nonharmful and 28 unknown episodes. Contract outcome export was verified to copy the contract fields exactly without replacing the primary source target.

The source-safe, formal-safe and source-legit denominators are different and the report clearly says so. The archive is explicitly descriptive and includes TRAIN/CAL. P4-based episode intervention recall is not presented as recall across every early action. The recommendation to use P4 on these traces follows the unchanged 57/112 prevention count and the larger interruption burden of early placement.

## Freeze, identity and blinding evidence

- The actual method/threshold manifest SHA-256 remains `eb9d78e7cad94fa63970ef5890a4409d7f12f83224777987998468c6d0d3939c`, matching the pre-test record, both prediction receipts and the closed-test manifest.
- Every source hash in both the source freeze and fitted-method manifest matches the current file. All nine fitted model byte hashes match the manifest. No post-test decision-source/model/threshold mutation was found.
- Independently verified all prediction prefix/episode identities and every declared per-method eligible-prefix count/hash: 159,684 archive rows and 25,600 closed rows across 80 method/seed/strategy arms in each cohort. No duplicated arm/prefix identity was found.
- The closed prediction receipt time is `2026-10-30T22:41:37.215778+00:00`; the recorded gold release is later, `2026-10-30T22:42:11.605944+00:00`. Prediction bytes match the release receipt. The pre-test manifest records that the test did not yet exist, and the independent generator pins that method freeze.
- The sealed closed payload hashes still match their manifest. Independent review is PASS, with 320 cases, 160 pairs, eight policy mechanisms, 233 unique model views, zero contradictory duplicate-label sets and no reported TRAIN/CAL input overlap. The generator and independent review code implement the declared contract-only construction and independent adjudication.
- Rechecked CAL selection from the frozen manifest: rules win under the declared recall/simplicity criterion for P4 and staged, with 38/38 intervention episodes stopped and 0/126 formal-safe stops. The selection uses seed 17; sensitivity seeds are not selected retrospectively.

Fresh developer contexts, allowlists, review logs and freeze receipts support procedural blinding. A shared filesystem is not an OS isolation boundary; the documentation makes that limitation explicit. The final audit reads released test gold only after prediction/release evidence is established and makes no method changes.

## Diagnostics, fallback and reproducibility

The report's claims agree with the diagnostic implementation/artifacts. The measured latency includes JSON decoding and a full single-prefix call; batch evaluator timings are not substituted for online latency. Imports, verified model loading and aggregate process memory are separated. The figure was visually inspected and is legible. The pre-freeze test XML records 157 tests, zero failures and zero errors; saved evidence separately records 42 native probe tests. No full suite was rerun for this final audit.

Native replay is accurately described as five controlled serial workers with separate fresh SQLite databases and no external connections. It establishes wiring, contemporaneous snapshot checking, duplicate prevention and the STOP latch, not concurrency safety or live LLM causal prevention. Structured text/identity invariance is a post-freeze diagnostic, not training or selection evidence.

Saved fallback remains a bounded archival diagnostic. The 227 admitted records have unique episode/cut identities and cuts strictly before their first transfer proposal; all 227 future-dependent final views are rejected. The 214 reachable requests contain 73 matches and 141 unavailable views; unavailable proof cannot be converted into authorization. Code checks full rendered context, query identity/context hashes, model identity and parsed raw verdict. DeepSeek's 53 matched historical charges and Luna's 20 matched API-equivalent estimates remain separate; no full-cascade actual-spend total is invented. Conditional paid-cohort quality is not presented as population FPR or policy equivalence.

README provides metric reproduction from published derived data and frozen predictions, and separately describes source extraction, fresh prediction and environment-dependent native integration. The only final documentation issue found was an unsupported `--help` instruction for the generator/reviewer; it was corrected to explicit commands and their write behavior, and the correction was inspected. No frozen method/data/prediction changed for that correction.

## Scientific limits retained in acceptance

The 320 cases are synthetic contract tests with paired and repeated inputs; eight mechanisms do not establish broad unseen-attack transfer or a guaranteed population FPR. Rules verify trusted payment obligations and still miss 55/112 original-source harmful continuations. Positive independent human authorization is stipulated in the synthetic corpus, absent from the archival training evidence. ML failure under that shift is reported without repair or seed selection. Missing source families, missing saved contexts, unknown outcomes, development cost and online latency remain explicitly unavailable where appropriate.

## Final read/write scope

Read: approved plan and prior pre-freeze audit; final review patch/stat; REPORT/README and developer/generator/review reports; freeze, prediction/release, integrity, latency, invariance, native summary and contract-export artifacts; released action/outcome gold and metadata; frozen archive/closed predictions; generator, independent reviewer, report builder, diagnostics, benchmark and saved-fallback source; source/model files for byte hashes; saved-fallback aggregate and compatibility records; pre-freeze test XML; the result image; read-only Git status/log.

The final audit did not read original raw LLM calls or credentials, rerun full suites, call an inference API, spawn agents, refit/recalibrate models, rewrite data/predictions or mutate shared Git state. Only this new `final-audit.md` was authored during the final audit. Artifact-manifest refresh and the concluding commit remain with the executor so that this report and final packaging metadata are included.
