# Task 1 independent spec and quality review

Reviewed commit `2f92cd8321f14a13b6f5e5d9a701b536061dda0a`, against the supplied `81fb026..2f92cd8` review diff, exact author brief, author report, and copied frozen v3/v4 policy/schema files. This review covers the new independent oracle, generator, own tests, and published development streams. Existing guards are not an oracle for this review and were not read or invoked.

**Spec compliance: changes required. Code/data quality: changes required.** Two confirmed v3 envelope-validation defects remain. The published 8000-state corpus does not exercise either defect, so these findings do not establish incorrect existing published labels. They do prevent accepting this oracle as a faithful independent adjudicator for subsequent valid and malformed v3 inputs. Resolve these before training/freeze, with a bounded author-owned regression check.

## Confirmed findings

### 1. P2: v3 nullable subject evidence is incorrectly treated as a malformed envelope

Location: `oracle.py:263` (within `valid_v3`, lines 257–266).

The copied `v3-schema.json:35` explicitly permits `subject_matches:boolean|null`; only `true` establishes a current-subject fact. The validator instead requires an exact boolean. Consequently a schema-valid proof with unavailable subject linkage makes the *entire* observation UNKNOWN before other requirements run. This violates the contract's separation of unavailable evidence from malformed shape and its verified-violation precedence.

Minimal in-memory reproduction, starting from this author's valid fixtures:

```python
o = setup('review-null', 1)
set_fact(o, 'vendor_status', 'inactive')
b = project_v3(o)
b['provenance']['fraud_review_completed'][0]['subject_matches'] = None
adjudicate(o, 'payment_v3', b)  # actual UNKNOWN; expected BLOCK
```

The independently proven inactive vendor remains a known payment violation; the review proof merely fails to establish fraud review. A second diagnostic with an otherwise safe low-amount/no-HOLD payment and `subject_matches=None` on optional `human_cleared` returns UNKNOWN, although this optional clearance is not required and the expected result is ALLOW. Accept nullable subject linkage at the v3 shape boundary, then let evidence eligibility reject it. Keep v4's different boolean-only proof schema intact. Add regressions for both mixed BLOCK/unknown and optional irrelevant evidence.

### 2. P2: malformed v3 auxiliary fields bypass envelope validation and receive ALLOW

Location: `oracle.py:230–267`, especially the outer allowed-field check at line 237 and proof validation at lines 260–266.

The function allows `untrusted_text` without checking its shape, and accepts a proof's `writer` without checking its declared type. The copied `v3-schema.json:35–39` describes `writer` as string/null and `untrusted_text` as an object with string invoice/agent channels. The frozen policy says invalid observations remain UNKNOWN (`v3-POLICY.md:11`; also v3 policy applicability.malformed).

Starting from `b = project_v3(setup('review', 1))`, each of these independent mutations still returns ALLOW from the payment oracle:

```python
b['untrusted_text'] = 17
# or, on a separate clean baseline:
b['provenance']['invoice_amount'][0]['writer'] = 17
```

These are invalid typed envelopes, not harmless missing proof. Validate the optional v3 text channel and declared proof fields before deciding payment obligations; add negative tests that require UNKNOWN even when all payment facts would otherwise pass. This request concerns shape only: do not parse text or writer labels into authority or business decisions. The permissive treatment of unspecified proof extensions is not separately charged here because the descriptive v3 schema does not state an additional-properties rule.

## What meets the brief

- The oracle is independently expressed against the copied contracts and uses only stdlib. It imports no target guard or learned model, and contains no case-ID, family, archive-outcome, arbitrary operation-substring, or lookup-name classification. Exact actor/callable lists and expressly specified session/currency operation names are contract checks.
- The three contracts and eligibility are distinct: payment_v3 applies only to P4 create-transfer; A/B cover P0–P4. Known violations outrank unknown requirements after envelope validation. The v4 validator handles schema shape, unknown properties, boolean/integer distinctions, duplicate attachment IDs, and Decimal strings.
- Payment checks preserve positive/exact amounts, USD, maximum 50000, independent human approval only above 10000, approved invoice, active vendor, review, authorized recipient, and no duplicate transfer. Low-amount/no-HOLD fixtures include absent optional human authorization and clearance. Non-USD currencies, zero/negative/maximum-exceeding amounts, denial, multiple violations, and known-plus-unknown states are present.
- Evidence logic checks producer-bound scope, subject, prior sequence, value equality, applicable material versions and dispatcher call linkage. It selects newest eligible proof before checking supplied value/current version, does not revive older safe evidence, and leaves newest conflicts unknown. HOLD/clearance are correctly excluded from material-version matching and maintain independent chronological clearance. Approval and clearance do not substitute for one another.
- Early A controls do not demand future payment readiness. The callable matrix, mutation shapes/enums, separate technical delegation completion, explicit parent presence, false relation evidence, missing linkage, bookkeeping reference evidence, and B approval/claim/SystemUtils checks are represented. No business trust threshold or blanket same-vendor read ban was added.
- Observation, metadata and gold streams remain separate. Opaque IDs are outside labels/family/split annotations. A separate representational v3 baseline retains actual values and available v3 source/time/subject semantics rather than filling missing facts. V4-only scope/version/value bindings cannot be represented in v3 and are not claimed as independently revalidated by that baseline.

## Data and split verification

Minimal read-only diagnostics independently read the three published gzip streams and manifest. They confirmed:

- All streams have 8000 joined rows with the same prefix order; 2000 base groups have exactly four variants and one split each.
- Each of the ten families has 200 base groups. TRAIN has 1500 groups/6000 states; CAL has 500 groups/2000 states.
- All published stream hashes, author-code hashes and copied-input hashes match the manifest. All gzip mtimes are zero.
- Class counts are payment_v3 ALLOW 2267, BLOCK 867, UNKNOWN 694, ineligible 4172; A ALLOW 3242, BLOCK 2676, UNKNOWN 2082; B ALLOW 1992, BLOCK 3811, UNKNOWN 2197.
- The duplicate-component split contains 908 components (660 TRAIN, 248 CAL), with largest component 26 original base groups. It selects components using only seeded order and size; it does not inspect labels or fitted performance.
- Recomputing the author's structural normalized signatures finds zero TRAIN/CAL crossings. An additional independent check uppercased proposal/fact/proof currency strings before computing those signatures and also found zero crossings.

The split is conservative structural deduplication, not proof that all policy-equivalent situations are unique. It deliberately preserves substantive monetary/state values, proof details and chronology; the report already scopes that limitation. Family proportions are not individually 75/25 after component grouping, which the brief does not require. No split repair is requested.

Metadata provides both `group_id` and `split_group_id`. Original group IDs support equal-base fitting weights; duplicate-connected split group IDs support indivisible split/bootstrap units. There is no sample-weight array in Task 1, nor is one required by this author brief. This review does **not** claim that downstream training actually uses the required source masses, normalized weights, or component bootstrap interface; the training implementation must verify those separately. A larger collision component must not silently replace an original base group as the fitting-weight unit.

## Interpretation boundaries and remaining limits

- Source labels authenticate nothing outside the trusted producer boundary. This is explicitly stated in the frozen contract and report; accepting an authoritative supplied fact is not a new oracle heuristic. Completeness of transaction history, native currency availability and actual account comparisons remain producer responsibilities. Ordinary Invoice getters do not gain a currency field merely from an operation name.
- B approval and claim input records are validated current snapshots supplied by the adapter/store. This schema cannot independently prove writer coverage, revoked-record history, atomic acquisition, claim-generation currentness, conflict-store completeness, or check/effect atomicity. These limitations are disclosed rather than silently converted into new business requirements or global production claims.
- A04's explicit parent field and trusted dispatcher comparison cannot reconstruct an omitted native root-parent relation; missing relation stays UNKNOWN. Positive fixtures supply the field; mismatch negatives use explicit false subject/linkage evidence. No invented identity convention is needed for accepting this corpus.
- The descriptive v3 schema is less formal than the v4 JSON schema. Extra proof-property permissiveness and exact lexical decimal grammar deserve an explicit interpretation if expanded later. The two findings above use declared types/nullability and do not depend on guessing those ambiguous details.
- The read log and source hashes are consistent with the declared independent policy-only input set. A read log is author attestation, not filesystem isolation or cryptographic proof of every file access. The review did not read historical memory, archives, target implementations or other agents' reports to establish labels.
- Existing tests contain useful hand-authored policy examples, but the corpus-label consistency test checks the oracle against its own output and is not independent proof of gold fidelity. This review's contract comparison is therefore necessary; 25 green tests alone do not close the two uncovered v3 cases.

## Validation performed and disposition

No model/API/network call, broad discovery, generator rerun, or full test rerun was performed. The reported 25 passing author tests are read from the author report, not a new reviewer test claim. Reviewer diagnostics were bounded Python snippets with `PYTHONDONTWRITEBYTECODE=1`: stream/hash/group/split inspection, extra currency-case normalization, and the in-memory malformed/null-proof examples above. No published data or existing rule was changed. Only this reviewer report was written.

Route one bounded pretraining fix pass to the original author for the two v3 shape issues and targeted regressions. If this changes oracle source hashes, refresh the author report/readback and manifest code hashes through the agreed publication process; do not silently overwrite different published bytes. Recheck whether generated label bytes actually change before claiming the existing corpus is unaffected. No new data design, guard modification, model call or full test rerun is required by this review.
