# Final reporting/provenance correction

Base HEAD: `3a34e3d36a37e1b7bf84a37fb8a7735fbeefb499`.
Scope: the single reporting-only wave requested by the [final independent
audit](final-audit-report.md) ([JSON](final-audit.json)), F1.
No method, runtime/native source, policy, schema, data, gold, prediction, score,
model, test or prior receipt was edited. No inference API, dependency install,
subagent, Git mutation, or repeated test wave was used. The controller commits
and requests a scoped independent re-review; this report is not that re-review.

## Corrections

- `REPORT.md` places the native F1 qualification immediately after the 32/32
  scripted-test success claim; `APPENDIX.md` adds it to the A04 counterexample.
  All 12 saved P2 snapshots have null `parent_workflow_id`: 11 ALLOW and one
  HOLD-related BLOCK, not a parent-link rejection. `snapshot` initializes None
  and `child_complete` does not override it. The `_INVOKING` context and delegation
  event retain an implicit parent/call relation. This is a representation and
  contract-conformance gap, not a demonstrated cross-parent exploit. The 32 tests
  establish the implemented runner-attestation convention, not independent gold's
  explicit-parent interpretation. A next version must specify admissible parent
  linkage, bind/validate the actual relation and assess it on a new test.
- `REPORT.md`, `APPENDIX.md` and `README.md` link the final audit and distinguish
  valid research with qualification from research-only implementation that is
  not accepted for full contract conformance or as a ready standalone authorizer.
  Original aggregate counts, both ALLOW-vs-UNKNOWN errors and the disputed safe
  getter remain unchanged, including the original 1/200 gold-labeled safe STOP.
- `provenance/` retains exact copies of `closed-author-brief.md`,
  `closed-review-brief.md`, and `final-audit-brief.md` from
  `.superpowers/sdd/2026-10-31-no-llm-v4-plan/`. Its [README](provenance/README.md)
  records their original paths and SHA256. These preserve procedural read
  allowlists; they establish neither a technical sandbox nor independent
  trusted-clock evidence. Coordinator rulings remain in `APPENDIX.md`; no large
  diff package or progress ledger was copied.
- `research-manifest.json` preserves all original experiment/baseline/freeze
  metadata and adds only a separate `reporting_updated_at`, seven reporting/
  provenance file entries, and new hashes for the three changed documents.
  It does not hash itself. This report does not embed the resulting manifest hash.

## Verification and evidence

Before editing or refreshing any manifest, a `python3` SHA256 walk checked the
original delivery manifest (`files`), `results/frozen-methods.json` (`sources`
and `files`), the closed-package freeze (`files`), closed-gold-release
(`gold_hashes`), and its explicit receipt/prediction/freeze links. Result:
**174 references / 125 unique paths, zero mismatches**: delivery 104, frozen
methods/data 49, closed-package 14, gold-release data 3, chain links 4. The latter
three sets are **21 closed-chain references**. Counts overlap and are not unique
file totals. This is a narrower hash check than the independent auditor's 199
references, not a rerun of its full provenance traversal.

A separate pre-edit SHA256 snapshot of existing files under `experiments/` and
`finbot/` was compared after the edits, excluding only the four owned existing
reporting paths. **1,012 existing protected files were unchanged**, including
both initially untracked auditor outputs. All original non-reporting manifest
hash entries and method/closed-freeze references were retained unchanged.

A direct read of `results/native-untraced.json` selected `checkpoint == "P2"` and
counted parent nullness and `result.decision`: 148 total, 12 P2, 12 null parents,
11 ALLOW and one BLOCK with `unresolved_binding_hold`/`A09:violated`. This is a
recount of saved evidence, not a test rerun. Source inspection was limited to
the relevant `snapshot`, `child_complete` and A04 logic for this qualification.

The required existing CLI, run from this research checkout using the known ML
environment, is:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv/bin/python -m experiments.local_guards_v4.verify_artifacts
```

The CLI completed once with exit 0: **160 checked hashes, no failures,
`v3_unchanged_from_baseline=true`, `new_inference_api_calls=0`**. This checks
artifact integrity and baseline preservation, not runtime/test correctness.
The invocation occurred before this receipt paragraph was added. Its only
subsequent artifact changes were this report and its manifest entry. A final
read-only direct SHA256 pass checked the finalized manifest's 111 files and all
49 frozen-method/data references (160 references), plus the 21 closed-chain
references: **181 references / 132 unique paths, zero mismatches**. The 1,012
protected existing-file hashes still match the pre-edit snapshot. No test suite
was rerun.

Read-only Git checks used `git rev-parse HEAD`, `git status --short`,
`git diff --check`, `git diff --name-only` and inspection of the reporting diff.
Final scope is the four owned existing documents, this new fix report,
`provenance/`, and the two previously untracked auditor outputs.
`git diff --check` passed; the tracked diff names only `REPORT.md`, `APPENDIX.md`,
`README.md`, and `research-manifest.json`. There are no
commits, index updates, resets or other Git mutations in this correction.

## Remaining concerns

The method and gold disagreements are intentionally unresolved in frozen v4.
Procedural isolation limitations, local unsigned receipts, partial coordinator
visibility and the limits on native/real-world efficacy remain. Copying briefs
and refreshing reporting hashes cannot retrospectively strengthen those claims.
