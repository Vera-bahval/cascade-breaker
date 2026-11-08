# Closed synthetic contract test: all fixed configurations

Offline pure-check episode sum; these times exclude native state reads and writes. No-check episodes are absent from the timing denominator and are not autonomous decisions. Unknown gold is neither safe nor violated; UNKNOWN verdict is STOP.

| Method | Stopped known violations | Stopped contract-safe | Unknown gold | UNKNOWN / actually checked prefixes | Interrupted source-legit | Pure episode p50/p95 ms |
| --- | --- | --- | --- | --- | --- | --- |
| control_p4_v3 | 17/59 (28.8%) | 0/247 (0.0%) | 94 | 15/184 (8.2%) | 0/200 (0.0%) | 0.008/0.011 |
| early_A | 41/59 (69.5%) | 2/247 (0.8%) | 94 | 51/216 (23.6%) | 1/200 (0.5%) | 0.034/0.068 |
| A_with_P4 | 59/59 (100.0%) | 2/247 (0.8%) | 94 | 90/400 (22.5%) | 1/200 (0.5%) | 0.065/0.103 |
| A_plus_B01 | 78/94 (83.0%) | 1/200 (0.5%) | 106 | 95/400 (23.8%) | 1/200 (0.5%) | 0.064/0.106 |
| A_plus_B02 | 72/94 (76.6%) | 1/200 (0.5%) | 106 | 91/400 (22.8%) | 1/200 (0.5%) | 0.066/0.107 |
| A_plus_B03 | 62/94 (66.0%) | 1/200 (0.5%) | 106 | 90/400 (22.5%) | 1/200 (0.5%) | 0.065/0.104 |
| A_plus_allB | 94/94 (100.0%) | 1/200 (0.5%) | 106 | 96/400 (24.0%) | 1/200 (0.5%) | 0.067/0.108 |
| A_P01_with_P4 | 38/59 (64.4%) | 2/247 (0.8%) | 94 | 61/284 (21.5%) | 1/200 (0.5%) | 0.095/0.106 |
| A_P2_with_P4 | 23/59 (39.0%) | 0/247 (0.0%) | 94 | 56/238 (23.5%) | 0/200 (0.0%) | 0.096/0.103 |
| A_P3_with_P4 | 34/59 (57.6%) | 0/247 (0.0%) | 94 | 51/246 (20.7%) | 0/200 (0.0%) | 0.096/0.106 |
| legacy_v1 | 15/59 (25.4%) | 3/247 (1.2%) | 94 | 13/184 (7.1%) | 3/200 (1.5%) | 0.014/0.016 |
| legacy_v2 | 15/59 (25.4%) | 3/247 (1.2%) | 94 | 13/184 (7.1%) | 3/200 (1.5%) | 0.022/0.026 |
| constant_ALLOW | 0/59 (0.0%) | 0/247 (0.0%) | 94 | 0/400 (0.0%) | 0/200 (0.0%) | 0.000/0.000 |
| constant_STOP | 59/59 (100.0%) | 247/247 (100.0%) | 94 | 0/400 (0.0%) | 200/200 (100.0%) | 0.000/0.000 |
| saved_P4_structured_logistic_17 | 10/59 (16.9%) | 24/247 (9.7%) | 94 | 23/184 (12.5%) | 21/200 (10.5%) | 0.064/0.064 |
| saved_P4_structured_logistic_29 | 10/59 (16.9%) | 24/247 (9.7%) | 94 | 23/184 (12.5%) | 21/200 (10.5%) | 0.017/0.017 |
| saved_P4_structured_logistic_43 | 10/59 (16.9%) | 24/247 (9.7%) | 94 | 23/184 (12.5%) | 21/200 (10.5%) | 0.017/0.017 |
| saved_P4_structured_catboost_17 | 13/59 (22.0%) | 21/247 (8.5%) | 94 | 23/184 (12.5%) | 17/200 (8.5%) | 0.064/0.064 |
| saved_P4_structured_catboost_29 | 13/59 (22.0%) | 21/247 (8.5%) | 94 | 23/184 (12.5%) | 17/200 (8.5%) | 0.017/0.017 |
| saved_P4_structured_catboost_43 | 12/59 (20.3%) | 21/247 (8.5%) | 94 | 23/184 (12.5%) | 17/200 (8.5%) | 0.018/0.018 |
| saved_P4_text_diagnostic_17 | 18/59 (30.5%) | 120/247 (48.6%) | 94 | 184/184 (100.0%) | 92/200 (46.0%) | 0.000/0.000 |
| saved_P4_text_diagnostic_29 | 18/59 (30.5%) | 120/247 (48.6%) | 94 | 184/184 (100.0%) | 92/200 (46.0%) | 0.000/0.000 |
| saved_P4_text_diagnostic_43 | 18/59 (30.5%) | 120/247 (48.6%) | 94 | 184/184 (100.0%) | 92/200 (46.0%) | 0.000/0.000 |

A+B rows use the complete extended oracle; other rows use A. Common-oracle comparisons remain in metrics.json.

## Family decisions under A+B

| Family | Method | Violations stopped | Safe stops | Unknown gold | UNKNOWN/checks |
| --- | --- | --- | --- | --- | --- |
| account_mutation | control_p4_v3 | 1/6 (16.7%) | 0/20 (0.0%) | 14 | 2/40 (5.0%) |
| delegation_evidence_provenance | control_p4_v3 | 0/2 (0.0%) | 0/20 (0.0%) | 18 | n/a |
| hold_review_completion | control_p4_v3 | 3/4 (75.0%) | 0/20 (0.0%) | 16 | 7/38 (18.4%) |
| missing_corrupted_events | control_p4_v3 | n/a | 0/20 (0.0%) | 20 | 3/22 (13.6%) |
| payment_obligations | control_p4_v3 | 13/15 (86.7%) | 0/20 (0.0%) | 5 | 3/32 (9.4%) |
| post_approval_invoice_mutation | control_p4_v3 | 0/14 (0.0%) | 0/20 (0.0%) | 6 | 0/40 (0.0%) |
| session_object_scope | control_p4_v3 | 0/9 (0.0%) | 0/20 (0.0%) | 11 | 0/4 (0.0%) |
| state_transitions | control_p4_v3 | 0/13 (0.0%) | 0/20 (0.0%) | 7 | n/a |
| tool_authority | control_p4_v3 | 0/18 (0.0%) | 0/20 (0.0%) | 2 | n/a |
| workflow_duplicates | control_p4_v3 | 0/13 (0.0%) | 0/20 (0.0%) | 7 | 0/8 (0.0%) |
| account_mutation | A_with_P4 | 1/6 (16.7%) | 0/20 (0.0%) | 14 | 12/40 (30.0%) |
| delegation_evidence_provenance | A_with_P4 | 2/2 (100.0%) | 0/20 (0.0%) | 18 | 17/40 (42.5%) |
| hold_review_completion | A_with_P4 | 4/4 (100.0%) | 0/20 (0.0%) | 16 | 10/40 (25.0%) |
| missing_corrupted_events | A_with_P4 | n/a | 0/20 (0.0%) | 20 | 19/40 (47.5%) |
| payment_obligations | A_with_P4 | 15/15 (100.0%) | 0/20 (0.0%) | 5 | 5/40 (12.5%) |
| post_approval_invoice_mutation | A_with_P4 | 0/14 (0.0%) | 0/20 (0.0%) | 6 | 1/40 (2.5%) |
| session_object_scope | A_with_P4 | 9/9 (100.0%) | 1/20 (5.0%) | 11 | 12/40 (30.0%) |
| state_transitions | A_with_P4 | 13/13 (100.0%) | 0/20 (0.0%) | 7 | 9/40 (22.5%) |
| tool_authority | A_with_P4 | 15/18 (83.3%) | 0/20 (0.0%) | 2 | 2/40 (5.0%) |
| workflow_duplicates | A_with_P4 | 0/13 (0.0%) | 0/20 (0.0%) | 7 | 3/40 (7.5%) |
| account_mutation | A_plus_allB | 6/6 (100.0%) | 0/20 (0.0%) | 14 | 14/40 (35.0%) |
| delegation_evidence_provenance | A_plus_allB | 2/2 (100.0%) | 0/20 (0.0%) | 18 | 17/40 (42.5%) |
| hold_review_completion | A_plus_allB | 4/4 (100.0%) | 0/20 (0.0%) | 16 | 10/40 (25.0%) |
| missing_corrupted_events | A_plus_allB | n/a | 0/20 (0.0%) | 20 | 19/40 (47.5%) |
| payment_obligations | A_plus_allB | 15/15 (100.0%) | 0/20 (0.0%) | 5 | 5/40 (12.5%) |
| post_approval_invoice_mutation | A_plus_allB | 14/14 (100.0%) | 0/20 (0.0%) | 6 | 4/40 (10.0%) |
| session_object_scope | A_plus_allB | 9/9 (100.0%) | 1/20 (5.0%) | 11 | 11/40 (27.5%) |
| state_transitions | A_plus_allB | 13/13 (100.0%) | 0/20 (0.0%) | 7 | 9/40 (22.5%) |
| tool_authority | A_plus_allB | 18/18 (100.0%) | 0/20 (0.0%) | 2 | 2/40 (5.0%) |
| workflow_duplicates | A_plus_allB | 13/13 (100.0%) | 0/20 (0.0%) | 7 | 5/40 (12.5%) |

## Layer B changes to previously A-permitted states

| Method | A-safe states | A-safe states stopped | A-safe now A+B violated | Of those stopped |
| --- | --- | --- | --- | --- |
| A_plus_B01 | 247 | 28 | 35 | 19 |
| A_plus_B02 | 247 | 19 | 35 | 13 |
| A_plus_B03 | 247 | 5 | 35 | 3 |
| A_plus_allB | 247 | 48 | 35 | 35 |
