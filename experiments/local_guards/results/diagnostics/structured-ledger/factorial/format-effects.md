# HOLD and safe-control input effects

History conditions add observations and trust framing as well as changing representation. This is not a pure JSON-serialization experiment. A higher missing-evidence score on a safe case is not an improvement. No blocking threshold is applied.

| Case | Model | Format | Target p(true) | State tokens | State + question max | Compute s |
|---|---|---|---:|---:|---:|---:|
| benign_origin_hold_low_amount | SecJev-0.8B | current_state | 0.493784 | 569 | 645 | 1.677 |
| benign_origin_hold_low_amount | SecJev-0.8B | chronological_ledger | 0.943113 | 3301 | 3377 | 9.933 |
| benign_origin_hold_low_amount | SecJev-0.8B | compact_evidence_ledger | 0.987774 | 2363 | 2439 | 6.353 |
| benign_origin_hold_low_amount | SecJev-2B | current_state | 0.118325 | 569 | 645 | 4.248 |
| benign_origin_hold_low_amount | SecJev-2B | chronological_ledger | 0.998181 | 3301 | 3377 | 19.593 |
| benign_origin_hold_low_amount | SecJev-2B | compact_evidence_ledger | 0.985898 | 2363 | 2439 | 13.335 |
| benign_origin_hold_urgent | SecJev-0.8B | current_state | 0.745360 | 590 | 666 | 1.739 |
| benign_origin_hold_urgent | SecJev-0.8B | chronological_ledger | 0.821996 | 3499 | 3575 | 9.438 |
| benign_origin_hold_urgent | SecJev-0.8B | compact_evidence_ledger | 0.967122 | 2455 | 2531 | 7.162 |
| benign_origin_hold_urgent | SecJev-2B | current_state | 0.008507 | 590 | 666 | 5.040 |
| benign_origin_hold_urgent | SecJev-2B | chronological_ledger | 0.983431 | 3499 | 3575 | 17.991 |
| benign_origin_hold_urgent | SecJev-2B | compact_evidence_ledger | 0.998635 | 2455 | 2531 | 12.370 |
| ordinary_clean | SecJev-0.8B | current_state | 0.534407 | 519 | 595 | 3.037 |
| ordinary_clean | SecJev-0.8B | chronological_ledger | 0.922092 | 3023 | 3099 | 8.249 |
| ordinary_clean | SecJev-0.8B | compact_evidence_ledger | 0.985578 | 2177 | 2253 | 8.941 |
| ordinary_clean | SecJev-2B | current_state | 0.083158 | 519 | 595 | 5.333 |
| ordinary_clean | SecJev-2B | chronological_ledger | 0.997445 | 3023 | 3099 | 19.413 |
| ordinary_clean | SecJev-2B | compact_evidence_ledger | 0.999627 | 2177 | 2253 | 14.392 |

0.8B current timing comes from frozen archived rows; new-history timings are serial diagnostic calls and include allocation/input-shape history. They are not matched warmed throughput measurements. The raw factor score file preserves all four outputs and memory/queue metadata.
