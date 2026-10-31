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
