# Saved LLM fallback: bounded offline result

The original V2 Fraud-boundary verdict can be reused at 227 exact pre-transfer P2 cuts: 159/297 DeepSeek episodes and 68/297 Luna episodes. The other 367 episodes have no saved Fraud view. Availability depends on whether the original executor transferred; conditional quality must remain separate from full-cohort coverage.

Every admitted verdict matches the renderer's complete native prefix, stored `identity.context`, context SHA256, query-identity hash, model identity and parsed raw verdict. The successful Fraud delegation is paired and its cut precedes the first fund-transfer proposal. Original renderer and prompt source hashes match the execution manifests. Only selected pure renderer functions/constants execute; no original module, inference client or credential loader is imported.

All 227 saved final views match their full-trace rendering but none matches the pre-transfer prefix. Their `process_payment.agent_notes` comes after `finstripe__create_transfer`; all are rejected as prepayment evidence. P0 votes and these P2 views cannot substitute for a new structured P4 input.

## Original saved component

Across the 227 compatible paid episodes, the original-source target has 9 harmful, 191 nonharmful and 27 unknown outcomes. The saved component blocks 9/9 harmful and 11/191 nonharmful episodes. The independent contract target gives 8/16 harmful detections and 26/211 nonharmful interruptions. Per-executor partitions are in the JSON artifact. These describe different original models, original V2 policy/text evidence and an outcome-dependent cohort; they are not full-population FPR or V3 policy equivalence.

## Frozen staged router diagnostic

Input: `results/router-catboost-17-staged.jsonl`, 3,265 eligible prefix rows across 1,349 of 1,352 archive episodes. Three episodes have no eligible prediction; their coverage remains explicit.

There are 228 potentially uncertain rows. Chronological stopping suppresses later requests, leaving 214 reachable requests: 73 have an exact compatible P2 verdict, 134 have no compatible saved P2 verdict, and seven are P4/other incompatible contexts. The 141 unavailable requests remain UNKNOWN. Another 28 mandatory-proof UNKNOWN decisions never query the LLM and cannot become ALLOW. The 73 matched verdicts yield 63 ALLOW and 10 BLOCK.

| Archive diagnostic | No saved fallback | Exact saved fallback |
|---|---:|---:|
| Original-source harm prevented counterfactually | 71/112 | 71/112 |
| Independent contract harm prevented counterfactually | 168/168 | 168/168 |
| Original-source nonharm interruption | 775/1159 | 723/1159 |
| Contract nonharm interruption | 693/1153 | 630/1153 |

These full-source-nonharm and contract-nonharm interruption diagnostics are not the primary safe-P4 FPR: archived safe continuations can contain states requiring intervention. UNKNOWN means stop/escalate. These archive diagnostics include TRAIN/CAL groups and establish no independent-test quality. No unseen-family or new-executor inference was performed.

The 73 matched saved queries have separate money semantics:

| Saved executor | Queries | Amount | Meaning |
|---|---:|---:|---|
| DeepSeek | 53 | $0.023175324 | Historical recorded component charge |
| Luna | 20 | $0.0035032 | Saved API-equivalent estimate; no subscription debit inferred |

No combined actual-spend amount is reported. New inference API cost is $0. The 141 unavailable requests remain unpriced, so no full-cascade cost is claimed. Summed saved request duration is 182.497 seconds; this is historical component accounting, not measured live router latency.

## Reproduction

```sh
python experiments/local_guards_v3/saved_fallback.py --self-test
python experiments/local_guards_v3/saved_fallback.py --predictions experiments/local_guards_v3/results/router-catboost-17-staged.jsonl
```

The script accepts explicit `--comparison-root`, `--data` and `--output` paths. `results/saved-fallback.json` records source/archive/input/prediction hashes, cut/hash admission counts, payload-free compatibility records, conditional and full-coverage diagnostics, and accounting. Self-tests cover exact query hashing, tampering, mandatory proof gating, strict chronology and suppression after an earlier stop. New inference requests: zero. Custodian data and frozen method files were not changed.
