# Frozen derived tables

Primary action coverage is correct decisive actions / **all full-target actions**. UNKNOWN and no-check remain unresolved. Method-specific ablation gold is excluded. Intervals and executor/cohort strata are in `results/summary.json`.

## Common payment and full-contract comparisons

| Method | Old320 original payment | Old400 original fullB41 | Old400 clarified fullB42 | New800 fullA42 | New800 fullB42 |
| --- | --- | --- | --- | --- | --- |
| v3_p4 | 255/320 (79.69%) | 109/400 (27.25%) | 115/400 (28.75%) | 158/800 (19.75%) | 129/800 (16.12%) |
| v41_payment_common | 250/320 (78.12%) | 109/400 (27.25%) | 116/400 (29.00%) | 158/800 (19.75%) | 129/800 (16.12%) |
| v41_fullA | 250/320 (78.12%) | 256/400 (64.00%) | 262/400 (65.50%) | 512/800 (64.00%) | 466/800 (58.25%) |
| v41_fullB | 90/320 (28.12%) | 291/400 (72.75%) | 302/400 (75.50%) | 466/800 (58.25%) | 534/800 (66.75%) |
| v42_payment_common | 250/320 (78.12%) | 109/400 (27.25%) | 116/400 (29.00%) | 219/800 (27.38%) | 175/800 (21.88%) |
| v42_p4 | 250/320 (78.12%) | 110/400 (27.50%) | 117/400 (29.25%) | 219/800 (27.38%) | 175/800 (21.88%) |
| v42_early | 0/320 (0.00%) | 145/400 (36.25%) | 145/400 (36.25%) | 375/800 (46.88%) | 357/800 (44.62%) |
| v42_fullA | 250/320 (78.12%) | 255/400 (63.75%) | 262/400 (65.50%) | 594/800 (74.25%) | 532/800 (66.50%) |
| v42_plusB01 | 90/320 (28.12%) | 274/400 (68.50%) | 283/400 (70.75%) | 554/800 (69.25%) | 572/800 (71.50%) |
| v42_plusB02 | 90/320 (28.12%) | 268/400 (67.00%) | 278/400 (69.50%) | 576/800 (72.00%) | 552/800 (69.00%) |
| v42_plusB03 | 250/320 (78.12%) | 258/400 (64.50%) | 265/400 (66.25%) | 590/800 (73.75%) | 540/800 (67.50%) |
| v42_fullB | 90/320 (28.12%) | 290/400 (72.50%) | 302/400 (75.50%) | 532/800 (66.50%) | 600/800 (75.00%) |

Old400 uses `old400-original.score.json` and the exact restored original 4.1 requirements (36 corrected label rows); the earlier `old400.score.json` is not an input. New800 has 800 actions per full target, 80 per family, 400 paired groups. Primary hand gold is independent of oracle42.

## New800 fullB42 families

| Family (80 each) | v41_fullB | v42_fullA | v42_fullB |
| --- | --- | --- | --- |
| account_edit_after_approval | 47/80 (58.75%) | 40/80 (50.00%) | 60/80 (75.00%) |
| delegation_provenance | 60/80 (75.00%) | 60/80 (75.00%) | 60/80 (75.00%) |
| hold_completion | 50/80 (62.50%) | 60/80 (75.00%) | 60/80 (75.00%) |
| invoice_edit_after_approval | 47/80 (58.75%) | 40/80 (50.00%) | 60/80 (75.00%) |
| missing_corrupt_events | 55/80 (68.75%) | 60/80 (75.00%) | 60/80 (75.00%) |
| payment_obligations | 47/80 (58.75%) | 60/80 (75.00%) | 60/80 (75.00%) |
| session_object_scope | 60/80 (75.00%) | 60/80 (75.00%) | 60/80 (75.00%) |
| state_transitions | 53/80 (66.25%) | 60/80 (75.00%) | 60/80 (75.00%) |
| tool_authority | 60/80 (75.00%) | 52/80 (65.00%) | 60/80 (75.00%) |
| workflow_duplicates | 55/80 (68.75%) | 40/80 (50.00%) | 60/80 (75.00%) |

Exact structural dedup retains all 800 structures and all outcomes. This does not establish semantic novelty. Four A05 HOLD component states disagree with the hand labels while aggregate BLOCK remains correct; aggregate agreement must not be reported as 100% component correctness.

## Conditional archive fullB42

| Method | Strict | Session vendor | Session admin | Technical vendor | Technical admin |
| --- | --- | --- | --- | --- | --- |
| v3_p4 | 0/82855 (0.00%) | 0/82855 (0.00%) | 0/82855 (0.00%) | 92/82855 (0.11%) | 92/82855 (0.11%) |
| v41_payment_common | 0/82855 (0.00%) | 0/82855 (0.00%) | 0/82855 (0.00%) | 92/82855 (0.11%) | 92/82855 (0.11%) |
| v41_fullA | 353/82855 (0.43%) | 353/82855 (0.43%) | 353/82855 (0.43%) | 26811/82855 (32.36%) | 26811/82855 (32.36%) |
| v41_fullB | 364/82855 (0.44%) | 387/82855 (0.47%) | 364/82855 (0.44%) | 26879/82855 (32.44%) | 26856/82855 (32.41%) |
| v42_payment_common | 0/82855 (0.00%) | 0/82855 (0.00%) | 0/82855 (0.00%) | 92/82855 (0.11%) | 92/82855 (0.11%) |
| v42_p4 | 0/82855 (0.00%) | 0/82855 (0.00%) | 0/82855 (0.00%) | 92/82855 (0.11%) | 92/82855 (0.11%) |
| v42_early | 353/82855 (0.43%) | 353/82855 (0.43%) | 353/82855 (0.43%) | 26719/82855 (32.25%) | 26719/82855 (32.25%) |
| v42_fullA | 353/82855 (0.43%) | 353/82855 (0.43%) | 353/82855 (0.43%) | 26811/82855 (32.36%) | 26811/82855 (32.36%) |
| v42_plusB01 | 353/82855 (0.43%) | 353/82855 (0.43%) | 353/82855 (0.43%) | 26811/82855 (32.36%) | 26811/82855 (32.36%) |
| v42_plusB02 | 353/82855 (0.43%) | 353/82855 (0.43%) | 353/82855 (0.43%) | 26845/82855 (32.40%) | 26845/82855 (32.40%) |
| v42_plusB03 | 364/82855 (0.44%) | 387/82855 (0.47%) | 364/82855 (0.44%) | 26845/82855 (32.40%) | 26822/82855 (32.37%) |
| v42_fullB | 364/82855 (0.44%) | 387/82855 (0.47%) | 364/82855 (0.44%) | 26879/82855 (32.44%) | 26856/82855 (32.41%) |

Each archive variant uses all 3,378 episodes, including five empty source-legitimate episodes; `original_main` has 1,352 episodes and is a separate stratum. Whole/executor/original-main action and episode counts are retained in JSON. Prefix ALLOW after replay STOP is not a practically solved workflow.

## Archive v42_fullB episode/source outcomes

| Variant | Correct full-scope episodes | Original-main correct full-scope | Source harm prevented / harmful | Source legit stopped / whole | Source legit stopped / reached | Offline ALLOW after STOP |
| --- | --- | --- | --- | --- | --- | --- |
| strict | 0/3378 | 0/1352 | 114/114 | 1263/1268 | 1263/1263 | 0 |
| session_vendor | 0/3378 | 0/1352 | 114/114 | 1263/1268 | 1263/1263 | 0 |
| session_admin | 0/3378 | 0/1352 | 114/114 | 1263/1268 | 1263/1263 | 0 |
| technical_vendor | 13/3378 | 13/1352 | 114/114 | 1263/1268 | 1263/1263 | 18605 |
| technical_admin | 13/3378 | 13/1352 | 114/114 | 1263/1268 | 1263/1263 | 18605 |

## Native latency, diagnostics off

All timing pairs below are p50 / p95 milliseconds. Selected collection+guard is a component, not complete working overhead. Unselected gathering is common adapter overhead. Whole request includes necessary sidecar work outside checks. STOP vs OFF differences include avoided workflow work.


### Safe complete fixture

| Method | Pure ready observation (new800) | Selected collection + guard / request | Extra unselected collection | Whole actual request | Paired OFF difference | Diagnostic copying (on) | Safe cold parent ms; RSS MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| off | — / — | 0.000 / 0.000 | 0.000 / 0.000 | 49.962 / 73.568 | 0.000 / 0.000 | 0.000 / 0.000 | 2138.3; 151.5 |
| v3_p4 | 0.069 / 0.142 | 1.616 / 2.611 | 37.141 / 53.061 | 106.805 / 163.579 | 54.194 / 106.505 | 1.946 / 2.370 | 1862.6; 152.3 |
| v41_payment_common | 0.199 / 0.235 | 1.875 / 5.040 | 38.859 / 58.478 | 115.016 / 160.308 | 67.256 / 104.948 | 1.976 / 2.399 | 1526.8; 152.0 |
| v41_fullA | 0.204 / 0.806 | 46.459 / 71.488 | 0.000 / 0.000 | 121.525 / 262.803 | 72.411 / 206.479 | 2.859 / 3.625 | 1461.4; 151.9 |
| v41_fullB | 0.218 / 0.923 | 47.789 / 113.306 | 0.000 / 0.000 | 118.310 / 266.335 | 66.003 / 208.307 | 2.924 / 3.308 | 1404.6; 152.1 |
| v42_payment_common | 0.351 / 0.694 | 2.123 / 4.538 | 38.441 / 69.089 | 115.145 / 216.130 | 63.454 / 168.450 | 1.980 / 2.443 | 1603.0; 152.1 |
| v42_p4 | 0.371 / 0.538 | 2.022 / 3.491 | 36.540 / 68.163 | 101.601 / 200.106 | 56.526 / 157.718 | 1.997 / 2.277 | 1505.3; 150.9 |
| v42_early | 0.346 / 0.754 | 45.555 / 58.777 | 1.628 / 3.371 | 115.945 / 162.632 | 64.101 / 111.225 | 2.947 / 3.271 | 1588.3; 152.2 |
| v42_fullA | 0.346 / 0.528 | 48.895 / 118.305 | 0.000 / 0.000 | 121.967 / 221.361 | 66.201 / 170.898 | 3.063 / 3.484 | 1508.2; 149.3 |
| v42_plusB01 | 0.347 / 0.423 | 48.308 / 70.628 | 0.000 / 0.000 | 121.577 / 177.801 | 63.692 / 120.669 | 3.037 / 4.508 | 1521.2; 151.8 |
| v42_plusB02 | 0.354 / 0.709 | 49.732 / 76.327 | 0.000 / 0.000 | 122.495 / 196.123 | 68.011 / 149.538 | 3.065 / 3.681 | 1574.3; 151.7 |
| v42_plusB03 | 0.346 / 0.407 | 47.121 / 76.434 | 0.000 / 0.000 | 114.998 / 200.968 | 64.904 / 153.288 | 3.018 / 3.339 | 1408.1; 151.9 |
| v42_fullB | 0.349 / 0.406 | 52.481 / 86.303 | 0.000 / 0.000 | 126.732 / 205.040 | 68.459 / 157.360 | 3.058 / 3.626 | 1407.3; 152.0 |

### HOLD / STOP fixture

| Method | Pure ready observation (new800) | Selected collection + guard / request | Extra unselected collection | Whole actual request | Paired OFF difference | Diagnostic copying (on) | Safe cold parent ms; RSS MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| off | — / — | 0.000 / 0.000 | 0.000 / 0.000 | 50.631 / 84.939 | 0.000 / 0.000 | 0.000 / 0.000 | 2138.3; 151.5 |
| v3_p4 | 0.069 / 0.142 | 1.731 / 3.952 | 28.291 / 47.241 | 92.245 / 244.892 | 40.123 / 199.265 | 1.472 / 1.631 | 1862.6; 152.3 |
| v41_payment_common | 0.199 / 0.235 | 1.811 / 3.771 | 27.228 / 66.356 | 89.126 / 315.823 | 38.602 / 247.569 | 1.505 / 1.986 | 1526.8; 152.0 |
| v41_fullA | 0.204 / 0.806 | 12.772 / 28.583 | 0.000 / 0.000 | 41.093 / 77.355 | -9.132 / 27.390 | 0.856 / 1.269 | 1461.4; 151.9 |
| v41_fullB | 0.218 / 0.923 | 15.124 / 23.822 | 0.000 / 0.000 | 44.536 / 82.991 | -5.300 / 25.640 | 0.874 / 1.071 | 1404.6; 152.1 |
| v42_payment_common | 0.351 / 0.694 | 2.055 / 2.462 | 26.817 / 49.436 | 82.583 / 130.171 | 33.319 / 87.222 | 1.512 / 1.772 | 1603.0; 152.1 |
| v42_p4 | 0.371 / 0.538 | 2.092 / 3.182 | 27.841 / 37.046 | 88.087 / 159.083 | 35.777 / 86.958 | 1.543 / 1.809 | 1505.3; 150.9 |
| v42_early | 0.346 / 0.754 | 14.521 / 29.124 | 0.000 / 0.000 | 42.996 / 89.071 | -4.940 / 16.946 | 0.874 / 1.161 | 1588.3; 152.2 |
| v42_fullA | 0.346 / 0.528 | 14.407 / 24.531 | 0.000 / 0.000 | 43.540 / 254.096 | -10.825 / 207.042 | 0.882 / 0.991 | 1508.2; 149.3 |
| v42_plusB01 | 0.347 / 0.423 | 14.612 / 21.706 | 0.000 / 0.000 | 42.379 / 67.569 | -7.301 / 13.167 | 0.908 / 1.194 | 1521.2; 151.8 |
| v42_plusB02 | 0.354 / 0.709 | 16.524 / 23.206 | 0.000 / 0.000 | 48.252 / 70.338 | -2.994 / 14.340 | 0.903 / 1.176 | 1574.3; 151.7 |
| v42_plusB03 | 0.346 / 0.407 | 15.787 / 23.066 | 0.000 / 0.000 | 44.749 / 74.258 | -6.675 / 13.919 | 0.889 / 1.260 | 1408.1; 151.9 |
| v42_fullB | 0.349 / 0.406 | 15.266 / 22.705 | 0.000 / 0.000 | 46.926 / 139.450 | -3.129 / 86.357 | 0.908 / 1.126 | 1407.3; 152.0 |

There are 1,560 native trials, 30 repeats per method/case/diagnostics mode, 26 diagnostics parity pairs and 26 cold workers. Full benchmark peak RSS: 344.9 MiB. Pure timings use each fixed mask's eligible new800 rows; populations differ and sample counts are in JSON. Cold values are safe first responses, repeated in the HOLD table for reference. Model-stub/tool counts, statuses, payments, inclusive store timings, and explicitly conditional per-request trimmed estimates are in JSON. No real-LLM API latency or savings claim follows from these measurements.

## Mutant sensitivity

| Mutant | Defined wrong actions | Defined predictions | Crashes |
| --- | --- | --- | --- |
| no_currency | 5 | 800 | 0 |
| human_every_amount | 90 | 800 | 0 |
| no_hold | 38 | 800 | 0 |
| unknown_first | 94 | 800 | 0 |
| no_origin_parent_binding | 37 | 799 | 1 |

Crashes are reported separately and never count as a successful sensitivity detection. Independent oracle42 is diagnostic, not primary new800 gold; its comparison-call interpretation is disputed. Frozen methods and labels remain unchanged.

Reproduce: `python3 experiments/local_guards_v4_followup/summarize.py`. The script hashes every input and refuses to overwrite existing summary/table outputs. It accepts score JSON files compressed to `.json.gz`.
