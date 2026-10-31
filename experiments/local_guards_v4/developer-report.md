# Fresh isolated v4 rules developer report

Status: ready for independent review/integration; 37 scoped unit tests pass.
No network/inference calls, subagents, commits, Git history/diffs, archive/corpus,
TRAIN/CAL, old reports/tests/results or other-agent source reads were used.

## Complete project-source read allowlist and hashes

Only these pre-existing project source files were read. Own files below were
created and subsequently read/tested. The local TDD skill was also read; no
additional project instruction/source discovery was performed under isolation.

| Input | SHA-256 |
| --- | --- |
| `experiments/local_guards_v4/POLICY.md` | `ee3996481669acee11caf633ff3284892767a6642f5c740657fa889106449353` |
| `experiments/local_guards_v4/policy.json` | `5b239e4d1802d6c70c4dbe34dad4ce75620a482af9271bad81474f9d98a3da02` |
| `experiments/local_guards_v4/schema.json` | `9e75dd6e2ae4cfac702b706d1a2b5408f71d6525b40c4a4dee3fc8fbbc04a07b` |
| `experiments/local_guards_v4/contract-freeze.json` | `c6f12f666e136aa05a3714c102a70543638f21ec2d019c0989d16f4d3dc1f0ab` |
| `experiments/local_guards_v3/rules_v3.py` | `279a3b8bfc37f4244e67696eba0150c84ed71d67a0f6b527dc32279c002bf38b` |

All three policy/schema hashes match `contract-freeze.json` after implementation.
The frozen files were never modified. v3 is loaded with `ast`: only unchanged
function definitions and its three literal fact constants execute, with Decimal,
perf_counter and frozen v4 `payment_policy` injected. v3 module imports and its
old `policy.json` are never executed/read. v3 `_facts` and `_evaluate` remain
unchanged and operate only on the validated projection.

## Interfaces

`guard(observation, policy=None)` returns exactly decision, reasons, evidence,
timing_ms, stop and requirements. Default profile A; `"A"`, `"B"`, or a dict with
`profile` selects the immutable registry profile. The immutable registry itself
may be passed, with optional profile. `enabled_requirements` may contain only
predeclared IDs belonging to the selected profile; invalid controls return
UNKNOWN. Each registry requirement has a state, including not_applicable for
out-of-cut/disabled/non-triggered requirements. BLOCK dominates UNKNOWN. P5
retains legacy detection-only UNKNOWN and always sets stop=false.

Newest eligible attested same-scope prior proof is selected before checking its
value and covered versions. Same-sequence conflicts, latest mismatches and
latest stale versions yield unknown instead of selecting an older safe record.
Boolean IDs cannot match integer IDs. Human evidence accepts only independent
registry. Saved fact evidence carries original source, record ID, checkpoint
and applicable registry requirement IDs; rejected evidence carries bounded
structured diagnostics without free text.

Known entity native calls require their typed subject. Null attachments mean
unknown arguments; `[]` is the explicit no-attachment observation. P3 approval
checks source terminal status, positive policy-bound amount, active vendor and
hold; no P3 human threshold/fraud/zero-transfer prerequisite was introduced.
`process_payment` A07 checks matching completed transfer reference independently
of A08 zero-prior-transfer prevention, and forbids invented target_status.

`EvidenceStore(path)` is a durable file-backed SQLite store. Exact integration
interfaces:

- `material_state(namespace, invoice_id, vendor_id, amount, currency, account_ref, seq)` returns `{invoice_version, vendor_version}`. invoice_id/vendor_id are positive ints; amount a finite decimal string; seq nonnegative int. Namespace scopes both revisions. Covered material changes increment revisions; notes are absent; Decimal-equivalent representations and currency case do not change material identity. Stale/equal-seq changed observations raise ValueError.
- `bind_approval(context, amount, currency, seq)` returns the schema approval record. Context needs namespace, invoice_id, vendor_id, account_ref, invoice_version, vendor_version and must match current stored material. This is ordinary approval, never independent human approval.
- `approval(context)` returns the current matching unrevoked record or None. Covered material changes delete affected bindings, and later restorations do not revive them.
- `acquire_claim(namespace, vendor_id, invoice_id, owner_workflow_id, seq)` returns the schema claim record or raises ClaimConflict. invoice_id=None is vendor-wide. BEGIN IMMEDIATE checks namespace plus same invoice ID (even across vendor arguments), or same vendor with either claim vendor-wide. Distinct invoices coexist. Repeated exact active owner/key returns the original record for internal inheritance; other/uncertain owner scopes conflict. Adapter must assign a fresh owner to every chat start_workflow.
- `claim(owner)` returns the schema record or None. Guard accepts an inherited vendor-wide record for a narrower same-vendor invoice child with the same admitted owner. Missing owner at workflow-only actors/P4 is B02 UNKNOWN. Guard can validate only the current store snapshot supplied by its trusted producer.
- `release_claim(owner, known_outcome=True)` returns None; False retains uncertain; True releases only after known outcome. A later independently reconciled True releases an uncertain claim. No TTL/auto-release exists. New acquisitions advance durable generations and create new record IDs.
- `mark_stop(owner, decision, reasons)` persists the first BLOCK/UNKNOWN STOP; `stopped(owner)` returns it or None. Runtime must consult this before tools/models/completion/retries and propagate STOP outside recoverable tool handlers.
- `record_event(owner, kind, payload, seq)` persists a dict payload; `events(owner)` returns insertion-ordered `{kind,payload,seq}` records. SQL parameters are bound and each operation uses its own connection.

## TDD and validation evidence

Command (repo root):

```sh
python3 -m unittest discover -s experiments/local_guards_v4/tests -p 'test_*.py' -v
```

RED: before production files existed, 27 tests failed explicitly for missing
implementation (the first placeholder run also exposed a missing test-result
`reasons` key; that test placeholder was corrected before the 27-failure run).
GREEN: initial implementation passed 27/27. Additional regressions were first
observed failing for missing payment subjects, boolean IDs, malformed containers,
invented bookkeeping status, cross-vendor same-invoice conflict, inherited
vendor-wide child scope, null attachments/missing native typed subject, and
missing workflow B02 applicability; each was fixed and rerun. Latest command:
37 tests, 0 failures/errors, OK (28 guard + 9 store).

Coverage includes P0 early ALLOW/UNKNOWN/STOP; violation precedence; exact
technical actor/registered tool matrix; enum mutations; P2 technical completion;
P3 approval and bookkeeping; P4 unchanged v3 payment rules, independent human
proof and freshness; P5 stop=false; malformed/null/cross-scope/future/conflicting/
stale proofs; strict A/B/ablation controls; store restart/concurrency,
vendor-wide/same-invoice conflicts, uncertain retention, generation and ABA.

Only own test modules were discovered. Broader repository tests are deliberately
outside this developer's read allowlist; no broader acceptance claim is made.

## Output hashes

| File | Lines | SHA-256 |
| --- | ---: | --- |
| `guard.py` | 314 | `e500f64479dca783e625a998baab1002da20df50e19eb5e6156383336ffb989f` |
| `store.py` | 213 | `57505966787b1a7ae40ed618ec2f0d5db9b8a7e4e1b1f9b76994c5e324f11f77` |
| `tests/test_guard.py` | 204 | `8d88537755214b9a5eda781b848acd4159b4e1acb340e382c2ad4ed281bf3435` |
| `tests/test_store.py` | 99 | `194b33d2de4d6dea56a1050230c35d10a5195fef7d466267bc8a9ce9334f283b` |
| `tests/fixtures.py` | 47 | `fdc1aa3ee12685172458a359d66295bed5a360e259b72bd2d61317e4b285c89f` |

## Limits and integration obligations

These are trusted adapter snapshots, not self-authenticating JSON. Runtime must
supply actual class/callable/scope facts and independent currency evidence;
USD policy alone is not observed invoice currency. All relevant protected writes
must call material_state, including observed restoration. Sidecar SQLite cannot
make native source-DB changes, HTTP writes, or check/effect pairs atomic. External
writers/races, incomplete writer coverage and distributed exactly-once are not
solved. Guard/store do not claim whole-runtime enforcement until adapter STOP,
claim admission and effect integration are independently verified.


## Revision 4.1 amendment (pre-global freeze)

The original 4.0 read/hash log above is retained as historical evidence. Root
authorized rereading only the original four v4 contract inputs; neither the
preserved 4.0 freeze nor contract-report/native source was opened. Updated
contract hashes for this amendment:

| Input | SHA-256 |
| --- | --- |
| `POLICY.md` | `8e0ba70727761edff5485bd4d0fb20af0bc48922cb9d1e12b23c3e8757c9306a` |
| `policy.json` | `5456778530e32b508cbf5d4f9eab78d383d83a91c927fefdf5e8f2e6b04492ca` |
| `schema.json` | `9e75dd6e2ae4cfac702b706d1a2b5408f71d6525b40c4a4dee3fc8fbbc04a07b` |
| `contract-freeze.json` | `c91b74316ebae3a86a2d57fc71d2d90af92346a8550d392985e49d3357445f4e` |

A05 now requires a known canonical current invoice status, with existing typed
actor/target and approval obligations. Approved/rejected/paid current status
alone no longer forbids re-review. Tests cover approved to approved, rejected
to processing, paid to processing, invalid current status UNKNOWN and missing
hold proof UNKNOWN during reapproval.

MATERIALVERSION excludes only binding_hold and human_cleared. Both remain bound
to exact invoice/vendor subject, namespace/session/workflow, accepted attester,
prior sequence and newest-event rules. Material edits do not clear known holds
or invalidate known no-HOLD history from the declared complete synthetic
producer. Independent clearance must follow the newest hold, while fraud review
and independent human approval remain material-version-bound. No new hold,
clearance or human approval facts are fabricated. Store was not changed.

TDD: focused guard suite first failed seven assertions/subtests against 4.0
behavior (three terminal cases, historical hold/no-hold/clearance and old terminal
expectation), then passed all 34 guard tests after the two precise code changes.
Receipt:

```sh
python3 -m unittest discover -s experiments/local_guards_v4/tests -p test_guard.py -v
# Ran 34 tests; OK
```

Procedural isolation incident: after the focused green receipt, the developer
incorrectly reused the historical wildcard test command. The shared directory
now contained other participants' test modules. unittest auto-imported
test_data/test_evaluate/test_runtime and their dependencies outside this
developer's source allowlist. The output showed test names and dependency
stack traces; no aggregate result/outcome data appeared. The run executed 66
tests with four errors: three missing-numpy dependency errors in evaluator
tests and missing-fastmcp during runtime-test import. This run is NOT an
isolated rules validation receipt. The controller was immediately notified;
no further broad discovery or source reads were made. This procedural breach
must be considered in any final experimental independence claim. Subsequent
verification must name only owned test_guard.py and test_store.py explicitly.

Amendment output hashes before any further controller request:

- `guard.py`: `366a4afdd76481e81205191dbce293d1312600da2ce3bf6baf90c231246b5d78`
- `tests/test_guard.py`: `32a1e3156a2f69e917c442cb91b6f335c4dad0bdfc341c24a1224eec48d2c0df`
- `store.py`: `57505966787b1a7ae40ed618ec2f0d5db9b8a7e4e1b1f9b76994c5e324f11f77`


## Final authorized 4.1 currency-attester clarification

The controller explicitly authorized the contract's third clarification. For
invoice_currency only, server_context is eligible only when operation is exactly
`currency_contract_attest`. Generic server_context currency observations and
near-match operation names remain rejected. Scope, value, subject, prior sequence
and current material-version requirements remain unchanged. Only a trusted
declared isolated fixture producer may emit this contract attestation; this is
not evidence that a native Invoice has a currency column, nor authentication of
caller-supplied JSON. Accepted evidence now retains operation alongside original
source and record_id, preserving the declared synthetic contract evidence identity
through the unchanged v3 projection. No other attester permission was broadened.

TDD receipt: the added positive contract test first failed UNKNOWN rather than
ALLOW; negative and stale/mismatched scope/value/time/version regressions passed.
After implementation, the only verification commands were the two exact owned
file patterns below; no wildcard/full-suite command was repeated:

```sh
python3 -m unittest discover -s experiments/local_guards_v4/tests -p test_guard.py -v
# Ran 37 tests; OK
python3 -m unittest discover -s experiments/local_guards_v4/tests -p test_store.py -v
# Ran 9 tests; OK
```

Latest owned validation: 46 tests pass in two explicitly scoped receipts.
Store remains unchanged. Final output hashes:

| File | SHA-256 |
| --- | --- |
| `guard.py` | `3b4de65b0520e79c5268eff538e80aa14def236f3a05d67eb753c18744ad8a72` |
| `store.py` | `57505966787b1a7ae40ed618ec2f0d5db9b8a7e4e1b1f9b76994c5e324f11f77` |
| `tests/test_guard.py` | `8e5cbd4a79f265f1231843e761a15c6a28e8cd0ebc80f7708394d6391f843410` |
| `tests/test_store.py` | `194b33d2de4d6dea56a1050230c35d10a5195fef7d466267bc8a9ce9334f283b` |

### Procedural incident expansion and disposition

The disallowed wildcard run auto-imported at least these non-owned test paths:

- experiments/local_guards_v4/tests/test_data.py
- experiments/local_guards_v4/tests/test_evaluate.py
- experiments/local_guards_v4/tests/test_runtime.py

Visible exception traces also establish execution/import of at least:

- experiments/local_guards_v4/evaluate.py (calibrate/score/intervals)
- experiments/local_guards_v3/ml_v3.py (top-level import)
- finbot/finbot/agents/base.py (top-level import)

The visible output listed four CustodianTests, eighteen EvaluationTests, the
then-34 owned GuardTests, nine owned StoreTests and a failed runtime-module
import, for 66 test entries total. Four entries errored: evaluator calibration,
frozen ML loading and score roundtrip because numpy was unavailable; runtime
import because fastmcp was unavailable. The output printed names, pass/error
statuses, dependency tracebacks and a temporary-directory ResourceWarning. It
did not print aggregate metrics, archived rows or gold labels. The complete
transitive import/file-read set was not captured; this developer cannot
independently verify every dependency side effect or every file opened by that
run. No additional outside-allowlist file was opened to reconstruct it.

The controller ruled to retain implementation with this disclosure, reporting
that no closed 400-case set existed and the imported data code exposed no
archived rows/gold. That controller assessment is distinct from this developer's
directly observed console evidence. Procedural independence was breached; no
technical isolation or fully unexposed author context is claimed. A fresh sealed
author remains a separate post-freeze role. The original read log is preserved
for the earlier pre-incident phase and is not a complete read log for the
disallowed wildcard run. No reimplementation was requested.
