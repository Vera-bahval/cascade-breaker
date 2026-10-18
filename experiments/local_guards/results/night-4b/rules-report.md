# Rules: one-shot independent evaluation

Frozen hidden cases were created before developer start; no retuning after reveal. Synthetic hidden cases do not establish generalization to independent real tasks. Archive outcomes remain counterfactual.

| Method | Archive harm stopped | Safe continuation stops | Source-benign stops | Compliant benign payments | Hidden unsafe stopped | Hidden safe stops | p50 / p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| original | 78/83 | 0/131 | 32/98 | 61/98 | 26/32 | 0/32 | 0.0002 / 0.0003 |
| rules_v2 | 83/83 | 0/131 | 32/98 | 61/98 | 32/32 | 0/32 | 0.0122 / 0.0132 |
| rules_v2_strict_review | 83/83 | 3/131 | 34/98 | 59/98 | 32/32 | 2/32 | 0.0125 / 0.0137 |

Success-only Fraud is a distinct stricter-policy sensitivity, not a relabeling of base-policy failed-review cases. Its raw false stops are shown above. Hidden sensitivity denominators and every case decision remain in rules-evaluation.json.

## Development cost

Dedicated developer tokens: 934079; input 926062, cached input subset 819456, output 8017, reasoning subset of output 1379.
Independent evaluator/reviewer dedicated-session tokens: 2579456. Parent orchestration is excluded; it is not exactly attributable.

| Episodes | Amortized developer tokens / episode |
|---:|---:|
| 100 | 9340.79 |
| 1000 | 934.08 |
| 10000 | 93.41 |

Archive end-to-end enrichment + decision: p50 0.2080 ms, p95 0.3570 ms, 1760 timing samples. The table above times direct normalized-state decisions only. These are local measurements without enforced exclusive CPU ownership.
Optional future registry integration requires the caller adapter to bind approvals/clearances to the current invoice; no live registry is implemented in this archive experiment.

Development amortization counts the whole developer session, including its own tests and engineering conversation. Counts are exact observed session counters, not a conversion to credits or dollars. Final-turn counters may require a metadata-only refresh.

rules_v2: +5 archived harmful episodes stopped versus original, +0 safe-continuation stops. Original compliant benign completion 61; variant 61. Developer tokens per additional prevented archived harm: 186815.8.
rules_v2_strict_review: +5 archived harmful episodes stopped versus original, +3 safe-continuation stops. Original compliant benign completion 61; variant 59. Developer tokens per additional prevented archived harm: 186815.8.

## Amortization by token category

Dedicated agent models from session turn_context metadata: developer ['gpt-6.1-sol']; independent evaluator/reviewer ['gpt-6.1-sol']. Cached input is part of input; it is not added to input again. The total column already includes cached input. Development and independent evaluator engineering/review are distinct costs.

| Episodes | Uncached developer input / episode | Cached developer input / episode | Developer output / episode | Developer total / episode | Development + evaluation total / episode |
|---:|---:|---:|---:|---:|---:|
| 100 | 1066.060 | 8194.560 | 80.170 | 9340.790 | 35135.350 |
| 1000 | 106.606 | 819.456 | 8.017 | 934.079 | 3513.535 |
| 10000 | 10.661 | 81.946 | 0.802 | 93.408 | 351.353 |

Zero model inference tokens are used by the frozen rules at runtime. These amortizations spread observed one-time costs; they do not estimate future attack frequency, monetary savings, or subscription credits. A matched LLM-defender per-episode token baseline was not measured in this night series.

## Hidden validation boundary

The 64 hidden cases contain normalized authorization_evidence and no raw prior_steps. Thus 32/32 unsafe and 0/32 safe validate the policy gate given normalized evidence. They do not independently validate the English authority extractor or complete raw-trace pipeline. Archive enrichment plus decision remains retrospective; the developer parser tests are development checks. No hidden decisions were recomputed and no rules were changed.

## Additional blind raw-trace diagnostic

This separately reported posthoc diagnostic does not replace the original primary 64 normalized hidden cases. New raw input states, native pre-cut events and policy labels were frozen before importing the unchanged frozen rules. No retuning followed its one evaluation pass.
[Raw diagnostic report](rules-raw-report.md); [per-case results](rules-raw-validation.json).

| Policy | TP | TN | FP | FN | Recall | FPR |
|---|---:|---:|---:|---:|---:|---:|
| base | 29 | 32 | 0 | 3 | 0.906 | 0.000 |
| strict_review | 31 | 30 | 0 | 3 | 0.912 | 0.000 |

All three misses concern actual reliance on unverified executive permission expressed in English paraphrases. The other seven authored families passed. The raw diagnostic evaluates enrichment plus rule application while retaining original code-computed amount/account/status facts at the guard interface. It is not a live FinBot run or a population error estimate.
Raw fixture SHA256: `601e5be41b4c3f791a9fbe43860d5fa720b0e15e76ed78f4c525627b64dd4a53`; frozen rules SHA256: `e000d6e33768783dbde2c8dad60313d55f708dcb5e05efde92bc70676de80148`.

## Raw auditor and total QA cost

Raw auditor model metadata: ['gpt-6.1-sol']. Dedicated-session tokens: 1475247; input 1463854, cached input subset 1344128, output 11393, reasoning subset of output 1204.
Entire raw auditor session, including blind fixture generation, evaluation, reporting and cost-generator maintenance; final turn requires a later metadata-only refresh.
QA below means independent evaluator/reviewer plus raw auditor. Development + QA adds the developer session. Parent orchestration remains excluded. All values are observed cumulative session counters, without conversion to subscription credits.

| Episodes | Raw auditor tokens / episode | QA tokens / episode | Development + QA tokens / episode |
|---:|---:|---:|---:|
| 100 | 14752.470 | 40547.030 | 49887.820 |
| 1000 | 1475.247 | 4054.703 | 4988.782 |
| 10000 | 147.525 | 405.470 | 498.878 |
