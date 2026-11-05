# Scoped final correction re-review

Reviewed source range: `3a34e3d36a37e1b7bf84a37fb8a7735fbeefb499` →
`393a9900d929a240ec670f5bcff3e19a6a2c9471`.
The checkout HEAD matched the latter commit and was clean before this report.
Scope is the single reporting/provenance correction supplied in
`.superpowers/sdd/2026-10-31-no-llm-v4-plan/final-correction-review-package.md`,
under `final-rereview-brief.md` and `final-fix-brief.md`. This is not another
whole-branch audit or an implementation acceptance review.

## Verdicts

**Scoped specification: PASS.** Required reporting finding **F1: ADDRESSED**.
The native disclosure, research-only interpretation, preserved disagreements,
provenance retention and manifest update meet this correction's requirements.

**Scoped reporting/provenance quality: PASS.** No remaining blocking finding
was identified in the correction. Research remains valid with the disclosed
qualifications. The implementation remains **RESEARCH-ONLY**, not accepted as
full contract conformance or a ready standalone authorizer. F1's underlying
contract/representation disagreement has not been repaired or waived.

## Finding dispositions

- **F1 — ADDRESSED for reporting.** `REPORT.md:110` places the qualification
  immediately after the saved 32/32 native success claim; `APPENDIX.md:128`
  adds it beside the A04 counterexample. `README.md:7` also summarizes it.
  They state all 12 saved native P2 snapshots have null parent ID, with 11
  ALLOW and one HOLD-related BLOCK. They distinguish the implemented
  runner-attestation convention from independent gold's explicit-parent-ID
  interpretation, retain the implicit `_INVOKING`/delegation-event relation,
  and make no claim that a cross-parent exploit was demonstrated. The next
  version must define admissible parent linkage, bind/validate the actual
  relation and assess it on a new test.
- **F2 — RETAINED, no additional reporting blocker.** The original P4 missing
  source-call-ID UNKNOWN→ALLOW mismatch remains in `APPENDIX.md:139`, together
  with the applicability ambiguity. `REPORT.md:83` still discloses both
  original UNKNOWN→ALLOW decisions. Neither was removed from the counts.
- **F3 — RETAINED, no additional reporting blocker.** `APPENDIX.md:145` retains
  the missing-invoice-ID getter and explains that the frozen gold-labeled
  safe STOP does not demonstrate loss of a valid native business operation.
  The original 1/200 and other aggregate counts are unchanged by the diff.

The report, appendix and README link the original final audit and preserve its
separate research and implementation verdicts. The audit's original required-
qualification status is historical evidence, not a claim that the correction
itself was already independently reviewed.

## Evidence and integrity

- A direct read-only selection of `checkpoint == "P2"` from saved
  `results/native-untraced.json` independently confirmed **148 total traces,
  12 P2, 12 null parents, 11 ALLOW and one BLOCK**. The BLOCK has reasons
  `unresolved_binding_hold` and `A09:violated`; it is not a parent-link
  rejection. The saved receipt records 32 successful tests. This inspection
  did not execute tests or the target method.
- The exact Git range contains only 11 reporting/provenance paths: the three
  edited documents, manifest, original auditor outputs, fix report and four
  provenance files. `git diff --check` passed. No method, native source,
  policy, schema, data, prediction, gold, score, model, test or old receipt
  changed in this correction. A read-only baseline comparison also confirmed
  v3 remains unchanged from `750e2de8c1b5f40a146e37bf39fd93e9ba56ac45`.
- Manifest comparison against the base found **104 → 111 entries**, seven
  additions, three changed document hashes, no removals and **101 unchanged
  existing hash entries**. All original experiment/baseline/freeze metadata
  is preserved; only the separate `reporting_updated_at` field was added.
  The manifest excludes itself. Direct SHA256 checks matched all ten added
  or changed document entries, including both original audit outputs.
- Frozen-method receipt bytes are unchanged from the base, preserving its
  **38 source + 11 data references**. Closed-package freeze and gold-release
  receipt bytes/maps are likewise unchanged, including the 14-file closed
  freeze map and original prediction/gold links. Together with the restricted
  Git diff and unchanged protected manifest entries, this gives no indication
  of silently refreshed hashes for changed protected inputs.
- Each of the three retained briefs is byte-for-byte equal to its original
  scratch-path file. Their SHA256 values match both `provenance/README.md`
  and the manifest. The README correctly records original paths and limits
  these copies to procedural read allowlists, not technical isolation,
  trusted-clock evidence or retrospective repair of the read-allowlist breach.
- The covering verifier evidence in `final-fix-report.md:71` records one
  successful existing CLI invocation (160 hashes, no failures, v3 unchanged,
  zero new inference calls). Its final direct integrity pass records 181
  overlapping references / 132 unique paths and 1,012 protected existing
  files unchanged. These are the fixer's reported checks, not reruns or new
  independent totals from this re-review. Their scope/timing qualification is
  clear and sufficient for this correction.

## Limits

No broad re-audit, archive rescoring, 400-case relabeling, test/verifier rerun,
inference API, dependency install, subagent, source/gold edit or Git mutation
was performed. Only this report was written. Local unsigned receipts,
procedural isolation failure, partial coordinator visibility, contract
ambiguities and native/real-world efficacy limits remain as disclosed in the
original audit. No new out-of-scope issue was identified during this scoped
review. This report was produced after the reviewed commit and is not an entry
in that commit's manifest.
