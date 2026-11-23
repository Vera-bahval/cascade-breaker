# Jev settlement choice changes with JSON order and assigned letters

On the 24 new CT supplier families, changing the order of the meanings in the JSON criteria object moved more probability mass than reassigning their A/B/C keys. Both comparisons changed the selected meaning in 24 of 864 pairs. Identical requests also sometimes changed outcomes, including two of 24 repeated calls, so the observed pair differences include response variability. The evidence-focused prompt gave the supported settlement label on all 432 primary calls, including all 216 where the receipt view was withheld.

| Matched comparison | Mean semantic total variation (95% interval) | Pairs that changed the selected meaning | Mean absolute log-loss change (95% interval) |
|---|---:|---:|---:|
| Reassign letters, hold semantic order fixed | 0.03539 [0.03212, 0.03878] | 24/864 | 0.08406 [0.07246, 0.09660] |
| Change JSON semantic order, hold letter assignment fixed | 0.04709 [0.04336, 0.05149] | 24/864 | 0.10506 [0.09073, 0.12211] |
| Repeat the exact same request body | 0.03458 [0.01625, 0.05625] | 2/24 | 0.07763 [0.03164, 0.13005] |

Total variation is half the sum of absolute probability differences after mapping each answer back from its letter to SAME, OTHER or DEFER. The within-family order-minus-letter difference was 0.01170 [0.00895, 0.01447] in total variation and 0.02100 [0.01329, 0.02936] in absolute log-loss change. Both factors' flip rates were 2.78% [1.39%, 4.40%] and involved seven supplier families each. The paired order-minus-letter flip-rate interval was [−0.46, +0.46] percentage points. Every flip changed correctness. In the original full-view arm, flips were between SAME and DEFER. In the original no-receipt arm, flips were between OTHER and DEFER. Each original arm accounted for 12 positive flip pairs per factor. Neither focused arm had a flip, although its probability distributions still varied.

The repeat comparison measures variability on one prespecified cell per family, with six repeats per prompt × receipt arm. Fifteen of 24 same-body pairs changed the semantic distribution. The repeat block has a wider interval and followed the primary block. Its average does not identify how much of each factor comparison was caused by the manipulation. Signed level comparisons show that the ordering can matter even within an arm with zero flips. For the focused no-receipt arm, moving from SAME, OTHER, DEFER to DEFER, SAME, OTHER raised gold log loss by 0.01517 [0.0092, 0.0220], averaged over all three letter assignments. Under the original no-receipt wording, moving from SAME, OTHER, DEFER to OTHER, DEFER, SAME lowered gold log loss by 0.1284 [0.0741, 0.1887]. These are individual level comparisons with unadjusted intervals. The API observes distinct serialized requests. TypeSafe's internal representation and inference path are unobserved. [Paired effects, transitions and arm-level results](choice_results.json)

## Prompt and receipt ablation

| Receipt evidence | Wording | Correct | Mean log loss | Letter assignment TV | JSON semantic order TV |
|---|---|---:|---:|---:|---:|
| Full | Original | 169/216 | 0.36907 | 0.04847 | 0.07269 |
| Full | Focused | 216/216 | 0.01537 | 0.00542 | 0.00657 |
| Absent | Original | 61/216 | 1.08270 | 0.06954 | 0.08921 |
| Absent | Focused | 216/216 | 0.08275 | 0.01815 | 0.01991 |

All 47 errors on full original views were unsupported abstentions on SAME states. All 155 original errors on no-receipt views reported OTHER without the settlement link needed to support it. Switching to the focused wording lowered paired log loss by 0.354 [0.312, 0.394] with full receipts and by 1.000 [0.905, 1.102] without receipts. When receipt access was removed, all 108 focused SAME and all 108 focused OTHER responses switched to DEFER. That ablation changes the supported answer: the target is the settlement link established by the evidence visible at the pre-Fraud checkpoint. It neither measures authorization nor predicts necessarily identical outcomes elsewhere in the workflow.

## Source, analysis and evidence

The selection uses retained CT simulations built from municipal payment records. It balances paid and stale status fixtures against SAME and OTHER settlement linkage. The selection excludes 67 case IDs and supplier groups across the earlier paid register panels and the original 12-family contrast. Forty-two of those occur in the CT source frame, leaving 49–52 eligible cases in each stratum before drawing six. The separately paid native receipt bridge shared zero suppliers with the selected 24. Full views matched the previously blinded state and both prior Terra labels, and the original read-only SQLite transaction projection. Two new blind Terra reads independently returned DEFER on all 24 receipt-removed views.

The primary schedule contains 864 unique UTF-8 bodies, nine letter/order combinations under each receipt × wording condition for each family. The order manipulation changes the JSON insertion order of the criteria; a sorted-key hash collapses three valid order variants to one. Dispatch sent the exact frozen bytes via the official TypeSafe endpoint. Intervals resample the 24 families within the four strata, preserving all repeated conditions together. The experiment covers these three cyclic rotations and this balanced frame. [Frozen protocol](choice_protocol.md) · [Source selection and exact-wire design](choice_design.py)

All 888 paid calls resolved as Jev `jev-1.14.0`. The isolated ledger reconciled to 711,288 input tokens and **$0.029874096** at the frozen tariff, including repeats, with zero unresolved reservations. Median response latency was 0.241 seconds. The private `.runtime/payment-controls-chp3/scale-choice-v1/` directory contains 864 bodies, 888 raw and typed receipts with occurrence and response hashes, the freeze and release manifests, the two new ratings, and the paid ledger. The scorer independently read every request, raw reply, typed receipt and ledger entry before writing the aggregate. [Runner](choice_run.py) · [Reconciler](choice_score.py)
