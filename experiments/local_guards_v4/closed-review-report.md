# Scoped correction-wave1 re-review

Spec compliance: **PASS**. Data quality: **PASS**. Both original findings are resolved; zero requirement-label mismatches remain across all 400 rows. Targets remain 200 ALLOW, 94 BLOCK, 106 UNKNOWN.

A03 is now UNKNOWN for ae81860016b92fbc0e7170f982af88f4. Reverting that single label reproduces the original compressed gold SHA256 exactly, proving no other gold content changed. Reverting the A03 source edit and placeholder replacement-order edit reproduces the original generator SHA256 exactly. The generated report now says 394 valid / 6 invalid, and its complete twelve-requirement coverage and target counts match current gold.

Observation, metadata, episode and outcome bytes are identical to the original independent audit. Their existing 400-case policy adjudication, 289 normalized views, 29 duplicate groups covering 140 rows and zero exact/strict-normalized old overlaps are reused; no old overlap package was reread. All current manifest/source/receipt hashes and the appended author read/import log were independently checked. The rerun log includes authorized reads of its own generator, report, read log and closed package for hash/validation receipts, alongside the unchanged contract read scope. Original freeze-order timing limitation remains: author logs lack timestamps; the controller retains its separate freeze receipt. No target methods, predictions, inference or subagents were used.

Scoped checks:

```json
{
  "all_400_labels_match_original_independent_adjudication": true,
  "author_readlog_receipt_hash": true,
  "author_report_count_correct": true,
  "author_rerun_read_import_allowlist": true,
  "contract_hashes_unchanged": true,
  "corrected_A03_unknown": true,
  "generator_correct_replacement_order": true,
  "manifest_file_hashes": true,
  "manifest_schema_and_family_counts_unchanged": true,
  "observation_metadata_episode_outcome_bytes_unchanged": true,
  "only_one_gold_label_changed": true,
  "only_two_generator_edits": true,
  "receipt_after_hashes": true,
  "receipt_original_generator_hash": true,
  "report_all_12_coverage_and_target_counts": true,
  "targets_unchanged": true
}
```

Current changed-file hashes:

```json
{
  "closed-author-report.md": "db2339e93d047c0ff55eba67c3c4fbf6cd03883666671546991c277c68e0f6b4",
  "closed/episodes.jsonl.gz": "02fe2d4d865ee7aabeba92e15c59524c1dd0d9c174ea2320940e5119ee395af3",
  "closed/gold-actions.jsonl.gz": "b6785390cd7eaf36e3dffec35da43e465da720da18ba661b124ec288b74e6c18",
  "closed/gold-outcomes.jsonl.gz": "a28487a16eb2bb4e33a196755c270365cf4baf1f043302ff1af7a6bbd5ad77cc",
  "closed/manifest.json": "45d88f92388ca855ef708abb95bb1fe3fbf7645b4fe0ffc2c67e3167e269136c",
  "closed/metadata.jsonl.gz": "5abd56023d4995e217c957319105fceb527529d591ffb678bcf729c977cb18e3",
  "closed/observations.jsonl.gz": "c2b16024bbb4340bfffffb3f4dec22d43c4efe3462428ed694e75e56e7696431",
  "make_closed_test.py": "3cf0855fa7e5bada42586f86c26a9298ba8d63707dd9f470ae21208ad0a716ac"
}
```

---

# Preserved original review evidence

The following records the pre-correction FAIL verdict and its findings. It is retained as history; the scoped current verdict above supersedes the two resolved findings.

# Independent closed test review

Spec compliance: **FAIL**. Data quality: **FAIL**.

Independently inspected all 400 observation payloads and all twelve labels: 1 label-mismatch rows. Gold targets: {'ALLOW': 200, 'BLOCK': 94, 'UNKNOWN': 106}; independent targets: {'ALLOW': 200, 'BLOCK': 94, 'UNKNOWN': 106}. 400 episodes, one prefix each, 200 balanced safe/unsafe pairs, ten families with 40 cases and 20 pairs each. Schema: 394 valid and six deliberately malformed inputs.

## Adjudication

The independent script reconstructs policy obligations from POLICY.md and policy.json, selects newest eligible same-scope prior attestation before value/version matching, keeps HOLD and clearance as invoice history, rejects untrusted human attesters, and audits canonical status, actor/callable matrix, delegation linkage, exact-transfer bookkeeping, P4 payment obligations, B bindings and claims. It never imports or invokes the target. Every payload has an individual adjudication/proof audit entry in closed-review.json. Malformed envelopes use the explicitly declared whole-envelope UNKNOWN semantics, without trusting integer-as-Boolean or Boolean-as-integer values. Applicable source-call IDs are required for the supplied live native-state records; dispatcher/runner evidence additionally binds to the actual current call. Session validity is session scope, while dispatcher argument comparisons require the newly referenced entity ID. B02 remains applicable when an existing claim proves attempted workflow admission even if workflow_id is missing. A09 follows only the legacy behavior published by the contract: known P3 approval violations and P2 fraud HOLD continuation veto.

## Required fixes

- `label_adjudication` ae81860016b92fbc0e7170f982af88f4: {"gold_target": "UNKNOWN", "independent_target": "UNKNOWN", "requirement_differences": {"A03": {"gold": "satisfied", "independent": "unknown"}}}. Fix: For ae81860016b92fbc0e7170f982af88f4 set A03 UNKNOWN, or freshly attest dispatcher_call_check for invoice_id 716 while retaining missing access evidence. The existing null-invoice dispatcher proof cannot establish actual-argument equality for the newly referenced invoice. Keep aggregate target UNKNOWN. Regenerate gold/manifest/report consistently before target prediction.

- `author_report_count_typo`: closed-author-report.md says IN394 deliberate invalid observations. Independent schema audit and manifest establish 394 valid and 6 invalid. Replace the malformed count with 6 and fix the generator replacement order to preserve that count on regeneration.

## Package and evidence integrity

All source hashes match closed/manifest.json. Package compressed hashes, row counts, deterministic gzip mtime zero, exact key joins, unique opaque IDs, one-prefix episode mapping, family balance, metadata isolation, all twelve requirement keys and null continuation outcomes are independently checked. The generator source was read but never imported or rerun; its fixed seed, canonical JSON ordering and in-memory repeat-compression assertions support deterministic regeneration; fresh regeneration was unnecessary because no hash/schema discrepancy was found.

Fixture trust is declared, not inferred from source-name strings. All proofs are evaluated for source/operation, prior sequence, bound record, exact scope and subject, latest-value consistency, applicable material versions and current actual call linkage. Human registry facts retain independent source requirements. Native currency is not fabricated: server currency attestations are explicit synthetic fixture-contract evidence; deliberate non-USD ledger counterexamples remain policy violations.

## Overlap and novelty

Within 400: exact unique observations 400/400; normalized unique observations 289/400; 29 normalized duplicate groups covering 140/400 rows. ID-only differences are not counted as unique semantic views. These duplicates are generally repeated admissible baseline contract states across paired families; they must not be described as 400 independent semantic scenarios.

ID equality-class renaming globally within observation; version spelling renamed; all event sequence values ranked preserving order/equality; positive claim generations collapsed; tool/actor/facts/source/operation/array order and null-vs-absent retained.

| Comparator | Old rows | Old normalized unique | Exact new matches / 400 | Normalized new matches / 400 |
| --- | ---: | ---: | ---: | ---: |
| experiments/local_guards_v4/data/observations.jsonl.gz | 83099 | 21747 | 0 | 0 |
| experiments/local_guards_v4/data/train-package/observations.jsonl.gz | 55492 | 14559 | 0 | 0 |
| experiments/local_guards_v3/closed-test/observations.jsonl | 320 | 320 | 0 | 0 |
| experiments/local_guards_v3/data/observations.jsonl | 20153 | 20153 | 0 | 0 |

Counts of matching old rows and every matching new ID are retained in JSON, so both denominators are explicit. This is strict observation-view comparison, not a claim of mechanism novelty: common contract states and known mechanism families are expected, and old archive envelopes may differ structurally. This is a fresh synthetic contract test over known families. It is not new real attacks or new semantic families.

## Custody and timing

Author log: 19 explicit reads, 861 module entries, no unexpected project read/import found. Only author brief plus three contract files were read. jsonschema loads installed third-party dependencies; these are not method imports. Failed interpreter/import attempts are visible.

Generation timestamp: `2026-10-31T20:33:15.770765+00:00`. Independent freeze-order status: **UNVERIFIABLE_FROM_ALLOWED_EVIDENCE**. The allowlisted author read log has no timestamps and contains no freeze receipt. The controller must reconcile its separate pre-author method-freeze receipt; this reviewer did not read controller outputs. No inference API, subagent, Git mutation, implementation/evaluator/runtime/old-rules import or later result read occurred.

## Limits

- Fresh synthetic contract states over known families, not newly discovered real attacks or new semantic families.
- Pure JSON trust is declared fixture-producer trust, not proof of production adapter authenticity.
- Complete writer/hold/transaction histories and synthetic independent human registry are producer assumptions.
- No runtime, concurrency, transaction atomicity, external-write races, STOP propagation or end-to-end harms measured.
- Single-prefix per episode tests state decisions only.
- No guard, evaluator, runtime, old rules, historical tests, predictions or later controller outputs read or executed.
- Timing cannot be independently established from untimestamped author logs.
- Full strict normalized view preserves fact values and shape, so zero old-overlap does not establish semantic novelty.

## Source hashes

```json
{
  "closed_files": {
    "episodes.jsonl.gz": {
      "bytes": 15973,
      "rows": 400,
      "sha256": "02fe2d4d865ee7aabeba92e15c59524c1dd0d9c174ea2320940e5119ee395af3"
    },
    "gold-actions.jsonl.gz": {
      "bytes": 16639,
      "rows": 400,
      "sha256": "5143c265df46fafb1ef7c2e6495cef276c0a1bce74aa17c32c32ee74c48a0cba"
    },
    "gold-outcomes.jsonl.gz": {
      "bytes": 9166,
      "rows": 400,
      "sha256": "a28487a16eb2bb4e33a196755c270365cf4baf1f043302ff1af7a6bbd5ad77cc"
    },
    "metadata.jsonl.gz": {
      "bytes": 23896,
      "rows": 400,
      "sha256": "5abd56023d4995e217c957319105fceb527529d591ffb678bcf729c977cb18e3"
    },
    "observations.jsonl.gz": {
      "bytes": 258684,
      "rows": 400,
      "sha256": "c2b16024bbb4340bfffffb3f4dec22d43c4efe3462428ed694e75e56e7696431"
    }
  },
  "contract": {
    "POLICY.md": "8e0ba70727761edff5485bd4d0fb20af0bc48922cb9d1e12b23c3e8757c9306a",
    "policy.json": "5456778530e32b508cbf5d4f9eab78d383d83a91c927fefdf5e8f2e6b04492ca",
    "schema.json": "9e75dd6e2ae4cfac702b706d1a2b5408f71d6525b40c4a4dee3fc8fbbc04a07b"
  },
  "generator": "3e0028c42da82f91672249aa2c01a8566fb78a96e85e4e2922784d1126c6f6b9"
}
```
