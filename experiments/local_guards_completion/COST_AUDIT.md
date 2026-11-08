# Stored request cost audit

The captured Eliza guard run cost **$12.197960256 across 3100 unique charged requests**. The previous **$2.321758440** figure covers only 542 selected saved answers from that same run. The remaining 2558 charged requests total **$9.876201816**. These scopes reconcile exactly; saved answers and normalized views are not additional API charges.

| Scope | Unique requests | Recorded charge, rounded to 9 decimals |
|---|---:|---:|
| Stored charged guard run | 3100 | $12.197960256 |
| Selected 542, reused historical answers | 542 | $2.321758440 |
| Charged requests outside selected 542 | 2558 | $9.876201816 |
| New calls in this completion | 0 | $0 |

The user's approximate $12 total is consistent with the captured run. This does not establish every charge for the whole original FinBot study: original executor inference and any other provider sessions have no complete billing evidence in these audited sources. Local compute is not assigned a USD price. This completion uses stored responses and makes no new model/API calls.

## Primary-source reconciliation

- `responses.jsonl.gz`, `requests.jsonl.gz` and read-only `ledger.sqlite` contain 3100 matching unique query IDs. Every response cost equals its ledger cost when SQLite REAL values use their round-trip decimal representation. All ledger rows are `complete`; no cost is missing and no unresolved reserve is substituted for a charge.
- The exact Decimal sum of the serialized response numeric fields is `12.1979602559999997645`; the selected 542 sum is `2.3217584399999999539`; the outside-selected sum is `9.8762018159999998106`. Their exact partition equality is checked. Nine-place display removes stored floating-point serialization noise; tokens are never repriced.
- The prior repaired-evaluation cost report's `2.321758440` matches the selected sum rounded to nine decimals. The final run summary reports 3100 requests and `12.197960256`.
- The existing normalized historical view has 3096 responses totalling `$12.181478868`. The four other charged run responses have `instrumented/` case IDs and total `$0.016481388`. This directly observed origin split is recorded without inferring why normalization excluded them. All 542 selected rows have `historical/` case IDs. The normalized receipt's response, mapping, ledger and producer-code hashes match current sources; the difference is not attributed to stale input hashes.
- Strata files select the same charged responses, with overlap between views; they are not separate bills. The progress snapshot reports 3096 requests and `$12.17879058`, so its request count must not be used to assume it contains the same 3096 queries as the normalized view.

## Failures, retries, caching and gaps

- No duplicate logical request ID or provider response ID is observed. The producer checks HTTP 200 and `attempt_count == 1` before persisting a response, but direct HTTP status and attempt count are not retained in response rows. Provider-internal retry history therefore cannot be independently reconstructed from this snapshot.
- There is no stored errors file and no explicitly evidenced charged-failure row. This is an evidence limit, not a claim that every historical attempt in every session succeeded.
- Case mapping has 3101 unique query IDs. One has no request, response or ledger record. Its outcome and charge are unknown; it is excluded from explicit-charge totals, not priced at zero. Its private identifiers are retained in `cost-audit.json`.
- 3095 responses report positive prompt-cache-hit tokens and 5 report zero. Token totals: 5,499,776 cache-hit prompt tokens and 39,024,956 cache-miss prompt tokens. Cache-hit requests still have explicit charges; prompt caching and local reuse of saved answers are different accounting concepts.
- Full provider statements, raw HTTP receipts, direct retry fields and original executor billing are unavailable to this bounded audit. No explanation for unsupported billing differences is invented.

## Reproduce and verify

Run `python3 -B experiments/local_guards_completion/cost_audit.py` from the repository root. The script uses only the standard library, reads charge/identity/usage metadata, opens SQLite read-only, checks source hashes before and after, and writes only this report and `cost-audit.json`. Its embedded self-check covers exact sums, invalid charges, duplicate-ID conflicts and scope reconciliation. The JSON records SHA-256 for every input and the audit script; source files remain unchanged.
