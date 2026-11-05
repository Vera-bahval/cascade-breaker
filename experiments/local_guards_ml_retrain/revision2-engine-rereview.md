# Revision2 engine scoped re-review

Reviewed `3970e0c..2fc8668` using `.superpowers/sdd/PLAN/review-3970e0c..2fc8668.diff` (SHA-256 `9b0a3bbb204f5ae2522097f6c498018fa007ab66cac0723a8db281d8c6cea7ca`). Scope was the original P2/P3 findings and regressions introduced by their fixes, not a second broad engine or study review.

**Specification verdict: PASS. Quality verdict: PASS. Both original findings addressed; no new actionable issue in this scoped diff.** The parent may proceed with the actual TRAIN/CAL fitting and equivalence audit. No corpus equivalence, performance, complete freeze or closed-test acceptance is implied.

## Findings disposition

- **P2, frozen policy clarification: addressed.** `experiment_revision2.py:236` now includes `P2_CALL_BINDING_CLARIFICATION.md` in `sources()`. The existing pre/post-fit source check and generic freeze verification therefore cover its exact text. The own assertion at `test_revision2.py:113-117` checks both file digest and registry membership. Independently checked current SHA-256 `85d32c17bf36f89b92383894f3710cc0057e6fc0b529d1babc1afdde23088978` and AST membership. The new independent author/reviewer briefs explicitly list this same clarification as a permitted policy input and preserve current versus completed-source call semantics.
- **P3, final brief provenance: addressed.** `revision2-read-log.json` retains the initial `ea3cfe6...` digest with an explicit historical-revision label and appends the final `f4e8c429fb14b86d44c0ec5eb4d6018620229be01aeb4f515314d7f7f09424d4` read. `revision2-engine-report.md` explains the chronology and final scope hash. Independently checked the current brief digest and matching final read-log entry.

## Regression check and evidence

The executable change is the single source-registry addition plus its own assertion. Feature/model files retain their previously reviewed hashes; no inference, model parameter, threshold, calibration, reuse or original-method change appears in this diff. Current hashes match the updated read log:

| File | SHA-256 |
| --- | --- |
| `features_revision2.py` | `74d007f275120dce9dfca1b6ce86097a95f85ea348e032693eeaa908a60a37cc` |
| `models_revision2.py` | `550c99c3f75b52964a548af1cb04c6d7a4b73ee1342fd5fe075b8a06767fed75` |
| `experiment_revision2.py` | `b2850eeb68772197fe58215aeb0e909d5502b0b4807ab8c9cb92e0a45ac39c0c` |
| `test_revision2.py` | `f7788ffe81e5de6094b7b19a4eeb820e260218dec0d2d3dde2bb1f3f8e1f426e` |

Reviewed the supplied failed-first assertion and subsequent 13-test success evidence (0.345 s); no tests were rerun. The new author/reviewer briefs contain protocol instructions rather than test data: authorship starts only after the verified freeze, policy-only labeling is separated from methods, gold stays embargoed until predictions are saved, and the reviewer independently checks labels and overlap. No change in those instructions invalidates the accepted source-call correction.

Only the supplied diff and named current source/hash metadata were inspected. No corpus, CAL gold, original1200, new test states, results, model artifact, API or subagent was used. Only this re-review file was written. The initial review remains historical evidence; this document resolves its two findings for the reviewed revision.
