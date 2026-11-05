# Scoped transport clearance before method freeze

Reviewed 2026-11-01: only the uncommitted `eliza.py` / `tests/test_eliza.py` delta adding `cumulative_cap`, bounded concurrent batches and batch draining, against checkout HEAD `8645543ed2f1e11092ea23b5af138a4abd11c67c`. The earlier `eliza-review.md` is preserved. No API/auth/metadata/paid calls, source edits, commits or test rerun. The supplied eight-test PASS is not an independent execution claim; the new test assertions were inspected.

Reviewed SHA-256:

- `eliza.py`: `8b364d5ccaf30b7f7c98133bf4b24818f6cf97e0c1e022bae2be46539e0fa8ea`
- `tests/test_eliza.py`: `3b46299ee446d62f4c42da3a15a192f1110218582176c7cdfcc3e191193f376b`

**Verdict: no critical, important or minor defect found in this bounded delta.** The change does not introduce an observed quota, duplicate-request or ledger regression.

- **Resume quota arithmetic:** `cumulative_cap()` (`eliza.py:107–111`) converts live remaining quota into a cumulative ledger ceiling by adding the job's completed spend once, then limits it by the requested total. Since reservation subtracts both completed costs and unresolved reservations, the effective new exposure remains bounded by live daily/monthly availability minus the existing safety margin. The two new scalar assertions cover an ordinary resume and constrained remaining quota. Existing finite-input, finite-quota and finite-charge boundaries remain in place.
- **Concurrent ledger safety:** concurrency is an integer from 1 to 8 (`:216–217`). Each task commits its reservation synchronously before POST (`:222–229`); `BEGIN IMMEDIATE` and the existing reserve calculation include every other in-flight reservation. Same-process pending requests are permitted for this batch, while previous-process pending requests and durable overruns still block dispatch. Completed charges are persisted independently per response.
- **Error draining:** `run_batch()` uses `gather(return_exceptions=True)` and raises only after all batch jobs finish (`:114–119`). A peer failure therefore does not cancel other normal in-flight requests or discard their accounting. The outer loop does not schedule another batch after this error. External process cancellation/crash still relies on the existing pending-ledger restart stop; this review does not claim crash-proof response collection.
- **No duplicate paid dispatch:** cached identities and the new `scheduled` set are both checked (`:248–258`), so identical bodies in the same batch cannot race into duplicate POSTs. Every selected case retains its mapping before the skip. The cumulative request limit includes queued jobs, including a final partial batch (`:257–263`). There is no automatic retry loop, and no new cases or alternate route are introduced.

This clearance covers the reviewed transport delta only. Final method fixes/freeze, complete manifest, selected receipt, packed input schema and prompt/config still require their planned pre-inference validation. The announced `lossless-path-references-v1` packet and equivalence of expanded local-method facts were not inspected in this scope. This report grants no separate paid-readiness acceptance and does not validate results.
