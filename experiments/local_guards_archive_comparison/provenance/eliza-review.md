# Independent Eliza transport review

Reviewed 2026-11-01 before inference. Scope: `PLAN.md` global constraints, the supplied review diff, `eliza.py`, `tests/test_eliza.py`, and the existing DeepSeek transport as reference. No inference, metadata/auth calls, test-suite rerun, source edits, or commits. Only this report was written. The already reported three passing tests were not independently rerun.

Reviewed source SHA-256: `eliza.py` = `09d8fea8ac7f3065c6c352e54f26b7a9d47514a0d46175de66dc02b548080369`; `tests/test_eliza.py` = `d283a2b2ec19f3708b33e794d901dc7660d63f91ff2e55e2cc20d30ba4063f7d`. Checkout HEAD at inspection: `ae3c44441eb122fd72ea7ee54118246811e35275`.

## Critical

1. **Reject non-finite caps before any paid call** (`eliza.py:42,56,131–133,182`). `--cap nan` is accepted by argparse; `min(nan, daily, monthly)` remains NaN. Both `cap <= 0` and `spent + worst > cap` are false, disabling the research cap. Verified using scalar arithmetic only: finite=false, cap_rejected=false, spend_check_blocks=false. Require a finite positive CLI cap and finite quota balances before constructing the ledger. Also validate the frozen price/token bounds: `worst` currently uses arbitrary config prices (`:145`), and `complete()` never stops when actual charge exceeds the reservation (`:61–67`). Record the authoritative charge, then stop on a violated upper bound; the reference transport already does this. These are small boundary checks, not a new accounting framework.

## Important

2. **Freeze and selected-input integrity are not enforced yet** (`eliza.py:118–128,138–140`). `{"sources":{}}` passes; there is no required binding to this transport, methods, config, prompt, selected manifest, or the actual `--inputs` bytes. An arbitrary record with a REPRESENTATIVE/CHALLENGE string is accepted, including a changed input for an otherwise selected case. Everything nested under `row['input']` is sent, so gold/outcomes inserted there would reach the model. Top-level case/split labels are correctly omitted, but that alone does not establish the raw-prefix/initial-fixture boundary. Before prediction freeze, require the final manifest's mandatory artifacts and hashes, verify selected IDs/groups and raw input digest, and validate the permitted input schema before metadata/auth calls. This is unfinished runner enforcement, not evidence that the draft has already leaked labels. Prompt content and upstream collector correctness were outside this review.

3. **Sanitize metadata before persistence** (`eliza.py:105–112,129–130,173`). The three metadata routes correctly use GET, but their entire JSON envelopes are written to quota files. Unlike inference envelopes, they have no field allowlist or recursive credential masking. Unknown fields or account/key identifiers can therefore enter provenance. No actual disclosure was observed because this review made no metadata calls. Persist only needed quota, usage and model/pricing fields; keep credentials and identity fields out. Apply masking to retained free text/provider fields as needed. The native OAuth token is otherwise confined to the client header, and inference envelope `key` is not explicitly persisted.

4. **Bind pilot/main to one ledger and preserve case-to-query mappings** (`eliza.py:117,133–143,147,169`). Deduplication works only inside the chosen output directory; separate pilot/main directories pay again for the same body. The current runner has no frozen run/output identity or shared ledger requirement. Also, two selected case IDs with identical bodies produce one response associated only with the first case: the cache skip happens before recording the second case-to-query mapping. Before pilot/main, make the common ledger/cache location part of the frozen invocation and retain a mapping for every selected case, including cache hits. Keep exact-context reuse; do not add retries or a second cache system.

## Minor / acceptance limits

- Existing tests cover basic duplicate/pending accounting, invalid charges, parse fallback, two identity changes and quota arithmetic. They do not exercise `run()` or the blockers above. After fixes, add only focused offline checks for those boundaries; rerunning the same three tests is insufficient evidence.
- The body identity includes prompt/messages and all dispatched model parameters (`:20–21,138–141`), so ordinary reuse is exact-context within a shared cache. Historical-cache provenance/import and cache-to-request/ledger reconciliation are not implemented or verified here. Require an auditable matching request before accepting imported historical responses.
- Normal pending-charge behavior is appropriately fail closed: reservation is committed before POST; missing/invalid charges, exceptions and malformed JSON leave it pending; a subsequent process cannot reserve another request. A known charge recorded before a later response-validation failure still prevents replay of that query via the ledger primary key. No automatic paid retry loop exists; `attempt_count == 1` is checked.
- Fixed Eliza base, DeepSeek model and chat route are explicitly enforced (`:16–17,123–124,149`); no executor import or call is present. The selected prompt/config, after-Fraud/P4 placement, shared method inputs, finalized pilot cap/stop procedure and method freeze still need their planned pre-inference artifacts and runner checks. This review does not authorize starting predictions.

**Disposition:** draft is suitable for continued preparation, but resolve the critical/important boundary checks and freeze the final invocation before pilot or main inference. No extra framework requested.

## Scoped re-review: fixround1

Reviewed `provenance/eliza-fix-diff.txt` against current `eliza.py` and tests at HEAD `5d2b5ff20b9a2bd8dccb13adaea5938da3a27776`. Source SHA-256: `eliza.py` = `398f53440809fa8b173c5af10f469c995e10cc6912a2bba7b0bbbdd7d269426e`; tests = `277132b890d15d56bd15b8b0800da8ec13227068fa28d734f135bdc04520ed7f`. No API/auth/metadata calls, test-suite rerun, source edits or commits. The reported six passing tests are supplied evidence, not independently rerun here. One pure offline synthetic sanitizer/price check was run with bytecode writing disabled.

Original finding disposition:

| Finding | Status in this draft |
| --- | --- |
| 1. Non-finite cap / price bounds / overrun | Original cap bypass addressed (`:43–44,146`); frozen bounds are finite and positive (`:176–178`); actual overruns commit an `overrun` status before raising, and subsequent reservations stop (`:56,65–75`). Live-price validation still has the issue below. |
| 2. Freeze / selected input integrity | Mechanism addressed (`:149–173`): mandatory transport/config/prompt/input/method/schema hashes, nonempty method manifest with verified member hashes, exact unique selected case IDs, selected split check and schema validation all precede auth. Whether the final schema excludes gold/outcomes, includes only raw prefix/initial fixtures, and the manifest covers every method remains final-artifact review; those artifacts are explicitly not ready yet. |
| 3. Metadata sanitation | Partially addressed (`:113–140`): envelope identities and unknown top-level fields are removed, quota counters restricted, and remaining balances checked finite. Nested `prices` remains unsanitized, as below. |
| 4. Pilot/main deduplication / case mapping | Addressed for normal use of the frozen receipt: output directory is bound (`:162–163`); each case maps to its exact query before the cache-hit branch (`:198,205–209`). This preserves duplicate-context cases while avoiding duplicate POSTs in the shared ledger/cache. Historical imported-cache provenance remains the prior acceptance limit. |

Remaining important issues introduced/exposed in the fix:

1. **Restrict the nested price payload too** (`eliza.py:129,193`). `sanitize_metadata()` copies `prices` without checking its members. A synthetic model record with `prices={'input_tokens':'nan','output_tokens':'0.1','key':'private-demo'}` retains `private-demo` in the supposedly safe result. No real secret exposure was observed. Keep only required input/output price fields as validated numbers instead of persisting an arbitrary object; similarly avoid accepting arbitrary structured values in retained model metadata fields. The new metadata test checks unknown envelope/model siblings, but not this retained nested object.

2. **Reject non-finite live prices before comparing** (`eliza.py:191–192`). `float('nan') > frozen_bound` is false, so a NaN live price passes the new price check and generation can proceed without a valid live upper bound. The same synthetic check confirmed this without network calls. Parse each required live price once, require finite/nonnegative, and use the validated value both in safe metadata and in the comparison. Frozen caps and the durable overrun stop remain effective; this does not reopen the original NaN cap bypass.

**Scoped verdict:** the draft fixes the original critical cap failure and most original important mechanisms. Two small metadata-boundary fixes remain. Final input schema, prompt/config, complete method manifest, selected receipt and frozen invocation still require their planned post-method-freeze review before paid readiness. No new framework, extra experiment, or inference is requested by this review.

## Scoped re-review: fixround2

Reviewed only `provenance/eliza-fix2-diff.txt`, the changed sanitizer and its focused test against the two remaining concrete findings. HEAD: `17670b461f7e660b50d4d19d00e2a4846b4dbb86`. Source SHA-256: `eliza.py` = `8968fbc5bf3abee2730689373c1441d754f619b975fdcfb5889918cee3c7ae10`; tests = `987c13f0648827ea1490915b100c90451d8d6c10144467f81e5c92065a5ab350`. No API/auth/metadata calls, test rerun, source edits or commits. Supplied evidence reports the focused failure before repair and six passing tests afterward; this re-review inspected the corresponding assertions rather than duplicating them.

- **Nested price payload finding: addressed.** `sanitize_metadata()` now constructs a fresh dictionary containing only `input_tokens` and `output_tokens`, converting their values to floats (`eliza.py:130–132`). Unknown nested price fields cannot reach saved metadata. The focused test includes `prices.secret_key` and checks its removal (`tests/test_eliza.py:56–64`).
- **NaN live price finding: addressed.** Both parsed live prices must be finite and nonnegative before metadata returns (`eliza.py:131`); the existing live/frozen comparison therefore receives validated finite values. Missing, malformed, infinite or negative values stop before generation. The test explicitly rejects the previous string-NaN case.
- Original findings 1–4 are now addressed at the draft mechanism level described in fixround1, including the two metadata corrections above. No new concrete defect was found in this narrowly scoped fix.

**Current verdict:** no remaining critical/important code finding from this review blocks continued draft preparation. This is not paid-readiness acceptance. Final schema/selected inputs, prompt/config, full method manifest and freeze receipt/invocation still need their planned post-method-freeze audit; historical cache reuse still requires exact request provenance and reconciliation. No inference has been reviewed or authorized by this report.
