# ML retraining on guard observations

Approved user plan: compare all stages and a separate v3 payment slice. Correct
decisive coverage is correct ALLOW/BLOCK / all eligible cases; UNKNOWN not solved.
No model API calls, no UX/public API changes, no old rule/policy/model/result or
main report changes. Default-off research. Preserve baseline.json protected paths.

## Fixed design
- Contracts: payment_v3 (P4 transfer only), A (v4 P0-P4), B (A+B01/02/03).
- LR C=1,max_iter=2000,L2; CatBoost200,depth3,lr.03,L2=5,threads2.
- 3-class classification ALLOW/BLOCK/UNKNOWN; probability for absent classes=0.
- Seeds17/29/43; main17. Four arms old/archive,new/archive,old/mixed,new/mixed.
- Fit preprocessing TRAIN only; same CAL across four arms. Synthetic8000 states,
  group split75/25 seed17, archive split unchanged, Luna excluded TRAIN/CAL.
- Mixed TRAIN source mass50/50, equal mass per base group inside source; normalize
  sample weights to mean1 so LR regularization is not collapsed by total weight1.
- No raw IDs, scenario/executor/outcome/split labels, rule outputs or requirement
  verdict aggregates in features. Equality relations and proof quality allowed.
- Three separately calibrated models per arm/family/seed =72 fitted artifacts.
- Pure classifier and classifier+mandatory-proof gate reported separately. The
  safety gate cannot call guard or use target labels. Cost/contribution separate.
- Select allow/block confidence thresholds only CAL; UNKNOWN otherwise. Maximize
  correct decisive episode coverage subject zero observed false allows (gold!=A)
  and <=5% stops on gold ALLOW including UNKNOWN. Explicit infeasibility. No refit.
- Frozen TFIDF historical diagnostic only; not counted as a structured retrain.

## Tasks and handoff
1. Independent policy-only dev author: oracle.py,generate_dev.py,8000 states,
   grouped metadata and labels, audits/tests. No target guard imports/reads.
2. Feature/training implementer: structural proof/context/approval/claim features,
   old features reused without modifying old module; independent ALLOW proof gate,
   archive loader, 72 fits, CAL, immutable freeze and prediction pipeline.
3. After freeze independent policy-only author creates1200 test states over10
   families; independent reviewer audits labels and normalized overlaps. Predict
   without labels; receipt then disclose. No method repair after disclosure.
4. Evaluate contracts/sources/points and old320/400 open diagnostics. Benchmark
   single calls, full native-adapter check/chain, load/RSS for new variants.
   Archive outcomes separately; unsupported versions stay unknown.
5. Independent audit; concise standalone Russian appendix in existing PR7.
   Main report unchanged. Source/data/model/prediction hashes and commands saved.

## Rulings fixed before development
- New synthetic dev states are required because full v4 archive has no fully
  proven ALLOW and manual approval/clearance never positive in original TRAIN.
  Keep archive-only arms even if missing classes makes CAL constraint infeasible.
- Frozen v3/v4 policies remain authoritative. Mark inherently ambiguous contract
  interpretations in audit and separate slices; do not silently relabel old tests.
- New test is new sampled contract states, not unseen attack mechanisms or LLM runs.
- Same source data access for rule and ML; shared parsing/evidence validation may
  encode provenance semantics but not business rule verdicts. Report any gate-only
  savings honestly instead of attributing them to a classifier.
