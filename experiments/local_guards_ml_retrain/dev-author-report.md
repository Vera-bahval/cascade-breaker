# Independent development-data author report

Completed Task 1 in the isolated policy-only author context. No target guard, learned model, archived examples, historical tests/results, prior reports, repository history, network service or external API was read or invoked. No commits or subagents were created. This is development TRAIN/CAL data only; no 1200-state held-out test was authored.

## Deliverables and counts

`oracle.py` independently implements `adjudicate(observation, contract, payment_baseline=None)` and an internal requirement trace. It imports no target guard. `generate_dev.py` uses only Python stdlib and the copied frozen policy/schema files. `tests/test_data.py` is the only invoked test module.

The three gzip streams join only through outer `prefix_id`. Observations contain no label, rationale, family, group, split or executor field. Metadata preserves original `group_id` and episode provenance, plus `split_group_id` for duplicate-connected split/bootstrap units. Gold contains contract labels and internal requirement states. All rows have synthetic metadata.

Exactly 8000 states comprise 2000 original base groups with four variants each; each of the ten required families has 200 base groups. TRAIN has 1500 base groups / 6000 states; CAL has 500 / 2000. Generation and component ordering use seed 17.

| Contract | ALLOW | BLOCK | UNKNOWN | Ineligible/null |
| --- | ---: | ---: | ---: | ---: |
| payment_v3 | 2267 | 867 | 694 | 4172 |
| A | 3242 | 2676 | 2082 | 0 |
| B | 1992 | 3811 | 2197 | 0 |

There are 200 deliberately malformed envelopes. These return UNKNOWN before known violations are considered. Their representational v3 projections can have a different shape outcome where v4-only malformed fields do not exist in v3; this is not relabeling or evidence repair.

## Duplicate-aware split

The original raw-group-only seed17 split had 435 normalized state signatures appearing in both TRAIN and CAL. Following the parent's explicit pretraining ruling, groups sharing any normalized observation were joined transitively. The final split uses 908 connected components, of which 660 are TRAIN and 248 CAL; the largest spans 26 original base groups. A size-only subset-sum after seed17 component shuffling achieved the original exact 1500/500 base-group target without splitting components or consulting labels/performance.

Normalized observations have 6370 unique state signatures and 1630 duplicate occurrences; largest exact normalized equivalence class is 13 states. Final TRAIN/CAL signature overlap is zero. Normalization erases opaque record/context IDs, canonicalizes subject equality and claim keys, and retains actual monetary/state values, proof sources, scope relationships, material-version equality and relative chronology. A dedicated test confirms that changing only opaque IDs preserves signatures and changing claim owner relationships changes them. The signature is a conservative structural normalization, not a proof of every possible policy-equivalent state.

The parent should use original `group_id` for equal-base fitting weights and `split_group_id` for indivisible split/bootstrap clusters. No fitted model or measured performance influenced data, oracle or split.

## Policy implementation

The oracle validates typed shapes with a stdlib implementation of the keywords present in the copied v4 JSON schema. Boolean-as-integer, unknown properties, malformed decimals, invalid nested structures and duplicate attachment IDs are rejected. Decimal arithmetic and uppercase currency normalization preserve boundaries. payment_v3 is eligible only immediately before `finstripe__create_transfer` at P4; A/B cover P0-P4. Other cuts are null.

Facts are nullable evidence, not state truth inferred from missing values. The oracle checks attester families, exact prior sequence, same subject and execution scope, typed comparison call linkage and applicable material versions. It selects newest eligible attestation before comparing supplied value/current version, so a stale or mismatched newest attestation cannot revive an older safe one. Same-sequence conflicting values stay unknown. Future, other-scope and wrong-source records cannot establish facts. Rejected evidence is reflected in unknown requirement annotations without using free text.

Known violations outrank unavailable evidence. A known binding HOLD remains violated until independently attested later clearance; absent clearance is not clearance. Clearances preceding the newest hold do not clear it. HOLD/clearance are invoice history and ignore material-version changes; ordinary review/payment/approval facts remain version bound. Independent human approval and independent clearance never substitute for one another. Human approval is required only above 10000; low amounts/no HOLD have valid positives with absent optional approval/clearance. P3 approval does not require later payment readiness or a universal human threshold. No trust/risk business thresholds were added.

A includes early session/entity checks, exact native actor/callable registration, explicit delegation completion/linkage, native mutation enum/shape checks, transfer-before-bookkeeping reference evidence and frozen payment obligations. Positive delegation fixtures include explicit parent relation and call proof; negatives cover explicit relation mismatch and missing proof. B additionally checks structured approval binding, supplied active claim ownership/key/sequence and inherited vendor-origin SystemUtils restrictions.

Fixture variation includes all requested families, monetary thresholds 5000/10000/50000 and adjacent amounts, negative/zero/positive values, USD and EUR/RUB/JPY, denial and absent authorization, separate clearance chronology, actor/origin combinations, multiple violations, known-plus-unknown cases, scope/version/time/source errors, postapproval invoice/account mutation and uncertain/released/other-owner claims. Variation is not limited to random identifiers.

The v3 projection only changes representation: deterministic server comparisons become native_tool, and explicit synthetic currency-contract attestation becomes initial_fixture/source_currency_contract. It keeps actual values, missingness, source/time/subject flags representable in v3. It never fills a missing fact or filters a bad value to make payment safe. New v4 scope/version/value bindings cannot be represented by the v3 envelope and are not fabricated there. Exact serialized projection rows are included with each observation.

## Explicit interpretation limits

- Trust is the declared producer boundary. JSON source names do not authenticate a producer. The schema has no independent proof of complete external writer coverage, current claim generation, atomic acquisition, revoked-approval history or check/effect atomicity. The oracle validates the producer-supplied current structured snapshot and leaves missing/unbound supported fields unknown; it makes no cryptographic, distributed exactly-once or external-write race claim.
- Claim positive generation is shape-valid, not independent verification of a store's current generation. The producer must have validated currentness. Future acquisition/approval sequences are unknown. Inactive/released/uncertain or wrong-owner claim snapshots are violations. Fixture claims use the canonical typed subject key; invoice-context fixtures do not assert a same-vendor vendor-wide claim as an invoice-key positive.
- A proof's operation string is not a completeness classifier. The oracle has no arbitrary substring checks or invented lookup-name allowlists. Native transfer/reference and currency facts are accepted only under the trusted producer's actual authoritative observations; an operation name cannot create completeness, account proof or currency data. Exact session_validate and server currency_contract_attest names are checked where expressly specified in the copied contract.
- Native Invoice normally lacks a currency field. Native-tool currency evidence is permitted when actually independently available from an authoritative observation; ordinary Invoice getters must leave it unknown. Generated positive currency evidence explicitly uses the declared synthetic immutable ledger attestation, never the probe USD constraint as observed currency.
- Applicable version binding follows fact families. HOLD and human clearance deliberately exclude material versions; session/access/dispatcher relationships are independently scoped. The producer remains responsible for actual native access gates and authoritative state meaning.
- Missing explicit parent relation is UNKNOWN. The schema cannot reconstruct an unstated native root-parent convention from a summary; no inferred parent identity was invented.
- No blanket own-vendor read restriction, high-trust eligibility threshold, time TTL, FX conversion, business merit rule or archive-derived outcome rule was introduced.

## Verification and publication behavior

Commands executed from the isolated worktree:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 experiments/local_guards_ml_retrain/generate_dev.py
PYTHONDONTWRITEBYTECODE=1 python3 experiments/local_guards_ml_retrain/tests/test_data.py -v
```

Final result: **25 tests passed in 6.661 seconds**. Tests pin optional authorization, exact monetary boundaries, non-USD, mixed BLOCK/UNKNOWN priority, malformed-envelope precedence, source/scope/time/version/newest evidence, HOLD chronology, human-action separation, early applicability, explicit delegation parent, native mutation shapes, bookkeeping, B freshness/claim/SystemUtils, normalized-ID invariance, disjoint base groups, zero normalized TRAIN/CAL leakage, wrapper joins/no labels in observation, file hashes, class coverage and publication refusal.

The final generator regenerated identical existing observation/gold gzip bytes after pretraining code/source clarifications and split correction; final metadata changed only for the approved component split and added split_group_id. Draft manifest/split metadata were explicitly removed before correction, before delivery. The generator itself always refuses to overwrite different existing published bytes. The own publication test confirms identical bytes are accepted and different bytes raise without changing the original file. All gzip headers have mtime 0. No target or broad test discovery was run.

An initial import created author-owned Python bytecode. Those files were removed; subsequent commands set PYTHONDONTWRITEBYTECODE=1, and final inspection found no author bytecode left. All lasting writes are in the task allowlist.

`data/manifest.json` contains exact hashes, contract/class/family/split counts, raw positive/negative/missing proof-presence coverage, semantic duplicate statistics and both base/component split counts. Coverage counts describe authored proof presence/sign; they do not silently claim every intentionally corrupt proof was accepted. `dev-read-log.json` records the explicit input read set and hashes.

## Explicit read log

The first read was the exact author brief. Only the six copied policy/schema files were subsequently read as task inputs. Directory entry names were inspected solely to locate their copied names. All remaining reads were of this author's own outputs/tests. No memory, repository instruction/history file, target code, baseline implementation, previous test/result/report or another agent's report was read.

| Input | SHA256 |
| --- | --- |
| provenance/dev-author-brief.md | `8c48a55b85bf9ab1e238a09cbe052f71563424148b516303c11e03a0ede7bd2c` |
| v3-POLICY.md | `17416fe66bcefa6e16fe729dae93c19abb2e046421b603451446e8f73be07240` |
| v3-policy.json | `bdaaffe0715d7b7233cc40e1ce7f6ada7989bac927269998aa5827d385f65c85` |
| v3-schema.json | `62efd6d8ec3b1dced204d3705c9c2691b7e9af1d503c4327ce388e1e6be84711` |
| v4-POLICY.md | `8e0ba70727761edff5485bd4d0fb20af0bc48922cb9d1e12b23c3e8757c9306a` |
| v4-policy.json | `5456778530e32b508cbf5d4f9eab78d383d83a91c927fefdf5e8f2e6b04492ca` |
| v4-schema.json | `9e75dd6e2ae4cfac702b706d1a2b5408f71d6525b40c4a4dee3fc8fbbc04a07b` |

## Final artifact hashes

| Artifact | SHA256 |
| --- | --- |
| data/gold-actions.jsonl.gz | `997cf15e4302fbec65eeacaef81bea7f86499dc1c138e0515dd95669d52eca75` |
| data/metadata.jsonl.gz | `43e7b02d06f593294d64c76ac48acaccc47987699c9fe5bda8a44651ea85175a` |
| data/observations.jsonl.gz | `1562a6c8a75721e663418749b154318bd4ca098a2dba3d9e346209a7ac4148ea` |
| oracle.py | `5eedd7c4ad266d1e47a8c00a131c7756e0f78703cda39db1995098425312b914` |
| generate_dev.py | `63f1fce31c2c2f2101f1c78398518aad4effb050275569251eb7471f652b1cb6` |
| tests/test_data.py | `a1accbf40b04213b6bfbfa0e1b062b0d402ef68a6336dcddb27d5b7cf470f189` |


## Task 1 review fix round 1/5

Applied only the two confirmed v3 shape findings in `dev-review.md`. The only implementation changes are inside `valid_v3`: a declared `subject_matches` may be boolean or null; optional `untrusted_text`, when present, must be an object and its supplied invoice/agent channels must be strings; optional proof writer, when present and nonnull, must be a string. Missing optional fields and unspecified proof extensions retain the previous treatment. No new required text channels, extra-property policy, text parsing, writer authority, decimal grammar, v4 rule, generator design or corpus scenario was introduced.

Evidence eligibility already required `subject_matches is True`, so null now makes that proof locally unavailable. A known inactive vendor plus unavailable review remains BLOCK; an otherwise safe no-HOLD payment with irrelevant optional clearance linkage null remains ALLOW. Required missing review remains UNKNOWN. The v4 boolean-only subject schema remains unchanged. Malformed auxiliary types return UNKNOWN before applicable violation aggregation.

Three regression methods were added to the author's own test module before changing `oracle.py`. The explicit red command was:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 experiments/local_guards_ml_retrain/tests/test_data.py IndependentPolicyTests.test_v3_nullable_subject_evidence_is_local_unknown IndependentPolicyTests.test_v3_optional_nullable_subject_does_not_stop_payment IndependentPolicyTests.test_v3_auxiliary_field_types_are_envelope_checks -v
```

Observed before fix: exit 1, `Ran 3 tests in 0.003s`, `FAILED (failures=14)`. The first regressions showed actual UNKNOWN versus expected BLOCK/ALLOW; malformed text/writer subcases showed actual ALLOW (or BLOCK with an inactive vendor) versus expected UNKNOWN.

The explicit amended own-suite command was:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 experiments/local_guards_ml_retrain/tests/test_data.py -v
```

Observed after fix: exit 0, `Ran 28 tests in 6.865s`, `OK`. No broad discovery, target guard, model, network call or commit was used.

A bounded in-memory readback then recomputed all 8000 complete gold records (all three contract labels, requirement traces and rationale), compared each record to published gold, serialized the records using the unchanged author's deterministic JSON/gzip procedure, and obtained byte-for-byte identical `gold-actions.jsonl.gz`. All three published stream hashes still match their existing manifest entries. Observations, metadata, gold, split, class counts and generator source were preserved byte-for-byte; no generator publication write or data rewrite occurred.

The manifest's only field change is `author_code_hashes.oracle.py`, explicitly authorized in this fix request. Its former value was `5eedd7c4ad266d1e47a8c00a131c7756e0f78703cda39db1995098425312b914`; its new value is listed below. The initial read-log file remains the original authoring attestation. This appendix supplements the exact task-read log with `dev-review.md` SHA256 `d77f45882b89d2e0d04b94e625395608b3789a2f40bc5b08b8b4544c59c087ef`; the copied v3 schema was reread at its unchanged original recorded hash. All other reads in this pass were own oracle/tests/report/manifest and own data streams.

| Reviewed artifact | SHA256 after fix |
| --- | --- |
| oracle.py | `f250e24300ac9bc778ec1ba938eedff70db4dcc9d84df4b30df0ab98b8aab0e4` |
| tests/test_data.py | `7daf05ccdb8fa22d6380c5380256aa55eefc8c08e13c041cc041e2fbf3f1335d` |
| generate_dev.py | `63f1fce31c2c2f2101f1c78398518aad4effb050275569251eb7471f652b1cb6` |
| data/manifest.json | `b9aa95ddeccba2c31bcd252f77de458cd0e7d194c2ce6c38869a73cbadd4e8ed` |

Manifest before this authorized metadata update: `01692204a17a6214b2cc65b865dd3f5c447e6439bfdda7ea0c9e896e700d9af3`.

Published data hashes remain:

- `gold-actions.jsonl.gz`: `997cf15e4302fbec65eeacaef81bea7f86499dc1c138e0515dd95669d52eca75`
- `metadata.jsonl.gz`: `43e7b02d06f593294d64c76ac48acaccc47987699c9fe5bda8a44651ea85175a`
- `observations.jsonl.gz`: `1562a6c8a75721e663418749b154318bd4ca098a2dba3d9e346209a7ac4148ea`
