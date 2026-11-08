# Spec compliance: FAIL

**EMBARGOED: contains closed gold and case identifiers. Parent must save frozen predictions before opening this report or its JSON.** Author may use it for a documented pre-prediction correction.

The required independent audit found **8 incorrect contract labels across 4 states**, arising from one checkpoint-applicability error. Task quality: **Needs fixes**. No target predictions, target guard, training oracle, features, models, thresholds, or target performance were read or executed.

## Strengths

The package contains 1200 distinct prefix IDs, ten families of 120 states, 1200 independent episode IDs, and 120 groups of related variants. Each state has its own episode; the variants are not represented as one chronological replay. The three data files and author source match their sealed manifest hashes, and the freeze reference matches the supplied freeze receipt. All 48 full-envelope schema violations have UNKNOWN gold for both general profiles. The independently written shape checker agrees exactly with the existing environment's `jsonschema.Draft202012Validator`.

The author explicitly separates ordinary approval binding from independent human authorization, preserves material-edit HOLD history, exposes newest stale proof and known-violation-plus-unknown combinations, and does not require payment readiness at unrelated early cuts. Optional human authorization at/below the automatic limit is correctly optional, including explicit denial. The report accurately limits synthetic examples and shared-filesystem isolation claims.

## Issues

### Critical

None.

### Important: early HOLD evidence is treated as a full readiness prerequisite

`closed_author.py:243-245` sets UNKNOWN for the newest-proof conflict in every HOLD-family checkpoint. This is correct at the transfer and invoice-approval cuts, but incorrect at the post-fraud continuation cut. `v3-policy.json:35` says that after completed Fraud delegation only a positively established active hold vetoes continuation; otherwise the result is provisional ALLOW. `v4-policy.json:351-361` preserves this legacy check as A09, and `v4-POLICY.md:111` requires validated projection into that unchanged applicability rule. The fact-validation rule at `v4-POLICY.md:73` makes this HOLD fact unavailable; it does not create a new mandatory P2 no-HOLD prerequisite.

| State | Contract labels to correct | Current gold | Independently adjudicated | Reason |
|---|---|---|---|---|
| closed-state-0506 | A, B | UNKNOWN, UNKNOWN | ALLOW, ALLOW | P2 linked successful fraud completion; conflicting newest HOLD proof establishes no positive hold veto; all independently applicable general/claim controls pass. |
| closed-state-0536 | A, B | UNKNOWN, UNKNOWN | ALLOW, ALLOW | Same applicability issue in a distinct independent state. |
| closed-state-0566 | A, B | UNKNOWN, UNKNOWN | ALLOW, ALLOW | Same applicability issue in a distinct independent state. |
| closed-state-0596 | A, B | UNKNOWN, UNKNOWN | ALLOW, ALLOW | Same applicability issue in a distinct independent state. |

Repair the author's checkpoint-specific counterfactual declaration/rationale, regenerate only the sealed closed package and associated counts/manifests/read log, preserve the original hashes, and re-review before prediction. No observation, model, feature, threshold, or policy change is needed. The detailed JSON includes all 1200 independent adjudications and the eight differing label slots. Independently checked applicable labels: 2860 (2400 A/B plus 460 payment-v3); 740 remaining payment-v3 slots correctly have null applicability.

### Minor: ambiguity metadata is overbroad for risk-only variants

`closed_author.py:402-405` marks both variants 6 and 7 of both vendor mutation functions as missing-enum ambiguity. For `update_vendor_risk`, variant 7 actually removes the concrete actor (`closed_author.py:215`), rather than a required enum. Two metadata rows therefore describe the wrong uncertainty mechanism. Narrow this annotation to the missing-argument variants; the associated gold already has the appropriate missing-authority result. The broader ten annotated state-transition rows include these two misleading descriptions.

## Policy ambiguity and accepted interpretations

These are separate from the eight definite applicability disagreements above:

- Missing mandatory native vendor-mutation arguments: the author chooses UNKNOWN because the observation does not establish a supplied invalid enum. A supplied noncanonical enum is a known violation. The copied prose's demand for all callable arguments could instead be read as a known call-shape failure; the corpus flags this and the interpretation must be frozen before disclosure. I accept the evidence-availability reading used here and did not consult an implementation to choose it.
- Failed versus unavailable delegation success: a known failed completion cannot authorize P2 continuation, while missing completion/parent/call evidence is UNKNOWN. The complete parent/call relation is represented by the trusted dispatcher comparison plus current context; no unrepresented source-parent equality was invented. Every tested P2 proof binds the completed delegation call. The corpus's current call and delegation call are normally equal, so it does not establish behavior for all possible distinct-current-call schemas.
- B02 generation: a positive supplied generation is structurally valid; the pure snapshot cannot independently prove atomic store ownership or compare it with an unrepresented authoritative current generation. Nonpositive generation is a full-envelope shape failure. Vendor-wide claims cover same-vendor invoice descendants; wrong namespace/vendor/invoice/owner and released state are known mismatches. Equal/future acquisition is unavailable prior claim evidence. These are explicit snapshot-level assumptions, not store-concurrency evidence.
- B01: missing current account/version or absent ordinary approval is unavailable evidence; complete conflicting bound fields are known mismatches. Equal/future approval sequence is not prior authorization. Case-normalized USD and Decimal amount equality are retained. Material-version changes do not erase HOLD/clearance invoice history, and clearance must follow the newest hold. Newest stale recipient evidence is not skipped to revive an older current proof.
- The supplied payment baseline is an independent v3 envelope. It lacks v4 proof-value, session, material-version and B-store semantics. A v4-only corruption need not invalidate this separately well-formed baseline. Shared malformed event sequence does invalidate both. This capability difference is explicit, rather than a target-performance adjustment.

The independent checks exercise all rows rather than accepting the author's declared class totals. Corrected fully-ALLOW independent one-state episode counts would be payment-v3 309, A 426, B 195. These are corpus gold counts, **not model results**. Full detailed counts remain in the embargoed JSON.

## Observation-only novelty and overlap audit

Only the observation files of development8000, historical320 (v3 closed test), and historical400 (v4 closed test) were read. No reference labels, outcomes, results, old guard, normalization implementation, or training oracle were read. Raw comparison always unwraps `observation` and removes top-level prefix ID and metadata/text. Canonical normalization preserves ID equality classes, anchors current context before proof renaming, parses claim keys, canonicalizes invoice/vendor version equality independently, normalizes Decimal/currency values, sorts proof/list structures and replaces event/approval/acquisition numbers with their joint within-observation ordering. Null/absent optional fields are equivalent in normalized comparisons. Unsorted provenance does not generate artificial uniqueness.

| View | Closed unique / 1200 | Development8000 unique | Historical320 unique | Historical400 unique | Closed rows overlapping dev / hist320 / hist400 |
|---|---:|---:|---:|---:|---|
| Raw observation | 1200 | 8000 | 320 | 400 | 0 / 0 / 0 |
| Full v4-compatible normalized envelope | 1200 | 2959 | 173 | 340 | 0 / 0 / 0 |
| Shared v3 envelope projection, normalized | 395 | 575 | 162 | 105 | 337 / 0 / 408 |
| Shared v3 projection, state-attester/operation spelling canonicalized | 395 | 575 | 162 | 104 | 347 / 0 / 420 |
| V3 obligation evidence view | 371 | 486 | 162 | 88 | 462 / 11 / 495 |

The projection retains shared payment facts and prior provenance, removes v4-only controls, and uses the supplied separate baseline where available. It is intentionally weaker than full v4 identity: many early general-guard states share the same provisional v3 view. The v3 obligation evidence view additionally removes irrelevant writer/operation spelling and retains independently accepted fact availability, exact amounts/currency, proposed action and clearance-after-hold ordering; it is a policy-information collision diagnostic, not proof of byte-level duplication or label copying.

For the **460 applicable P4 transfer states**, full/raw/shared-v3 syntactic views have zero cross-package overlap. The v3 obligation evidence view has 229 unique P4 structures and overlaps 39 development rows of this test (36 structures), 11 historical320 rows of this test (10 structures), and 6 historical400 rows of this test (5 structures). These test-row counts must not be added because the same test state can overlap multiple references. The detailed JSON records the exact within-closed and cross-package collision components.

Consequently 1200 full-envelope unique states is accurate; 1200 policy-novel mechanisms or completely independent v3 information patterns would be inaccurate. Envelope-shape differences are not evidence of novelty. General v4 controls can distinguish states that intentionally have identical payment-v3 information. No overlap rows were deleted or relabeled by the reviewer. Any downstream split/CI must retain the existing variant groups and account for duplicate projection components where that policy view is the estimand.

## Procedure, scope, and evidence

The source-read log enumerates only the author brief, six copied contracts, freeze receipt hashes and preserved own artifacts; its claims of zero APIs, subagents and target imports are consistent with inspected author source. This establishes documented procedural fresh-context discipline, not operating-system isolation or an independent record of every possible filesystem read. Parent separately verified the pre-author source/model freeze. This review verifies the freeze receipt's hash, without interpreting its model contents.

The supplied diff was read once. The tool output truncated the large diff (which includes preserved original drafts); focused reads of the current author's functions were necessary to inspect the truncated active sections. No separate old-version source was read. Named external checks were only (1) the six copied policy/schema files for adjudication and shape risk, (2) the three allowed observation-only packages for normalization/overlap risk, and (3) the existing standards-based schema library for a focused full-shape cross-check. The author's generation/check suite was not rerun. No API, subagent, commit, target guard, model, feature, threshold, prediction or TRAIN oracle was accessed.

Independent audit command: `/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_ml_retrain/closed_review.py`. It validates all rows/label slots, full shape, experimental units, manifest/freezing hashes, and the observation-only comparisons. The first stdlib execution established the policy discrepancies; the second execution added the requested independent JSON-schema cross-check and P4-specific overlap partition. Successful author checks were not repeated.

Sealed input observation SHA256: `4f0f9ccee27c630b356199a8d295644c64a9564e215377081317481bb561cc59`.

Sealed input gold SHA256: `a5177b36f354aa9f8a56bcffe92db5817bbdf4daf9a912d0f331949e19e37d3e`.

Sealed input metadata SHA256: `176c760138c0579dc112e995689863fe4a9af2e1a3f62335c3fcc7e963504108`.

Freeze receipt SHA256: `929793c35c692e6f2bd88a892784a6af374d447f69b62604d9fba32c46e06bfd`.

## Assessment

**Spec compliance: FAIL. Task quality: Needs fixes.** The corpus is structurally sound and procedurally documented, but the four early-continuation gold states must be corrected before evaluation. Preserve the current artifact hashes, route this embargoed report to the author, then review the documented correction with unchanged frozen source/models.
