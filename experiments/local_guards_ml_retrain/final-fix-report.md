# Final reporting fix wave

Status: DONE; one authorized reporting-only wave after the final whole-study audit.
The parent owns release-manifest refresh, commit and one scoped re-review.

## Findings addressed

R1: REPORT and APPENDIX now distinguish the8000-state development pool from
6000TRAIN fitting states and2000CAL states used for threshold selection.
The302 new-test payment overlaps mean296TRAIN and6CAL-only. APPENDIX preserves
the audit's269both/27TRAIN-only/6CAL-only/158neither partition and example
r2c-0649. All212 safe payment rows overlapTRAIN. These facts were read from the
audit, not recomputed from a corpus; scores, sensitivity weights and tables
remain unchanged.

R2: README names the original absolute checkout and saved absolute receipt,
prediction and freeze/source paths; records the macOS/native dependency
environment and required matching FinBot runtime/fixtures. A relocated fresh
clone or another platform has not been demonstrated. It directs reproduction
to the complete pure-ML release commit pinned by the PR, before later
integration changes the protected root main report. Baseline rejection after
that change is expected; no guard, source, frozen receipt or manifest was
edited to suggest portability. No future commit SHA is invented.

Small prose clarifications define P4 as before transfer, explain duplicate-task
restriction and replace missing-prefix jargon in the summary with unavailable
usable observations. No standalone antifraud objective was introduced.

## Exact bounded checks

Executed one /usr/bin/python3 heredoc from the recorded repository root.
It read only the audit JSON, changed documents, verification metadata, the two
analysis source files for hash identity, and the recorded native environment
summary. It did not open corpus rows or execute an analysis/model/benchmark.

Checks compared the exact audit overlap partition and safeTRAIN count to the
corrected prose; matched documented dependency versions to the recorded
environment; checked path/commit-context/portability disclosures; SHA256-compared
all Markdown table lines with the pre-edit snapshot; verified analysis.py and
archive_intervals.py hashes unchanged; verified the original analysis-report
byte prefix unchanged; and scanned the Russian documents for the loaded
humanizer-ru hard prohibitions. The verification JSON was compared field-by-field
to its pre-edit snapshot: only report_words, appended verification_sequence and
the four changed-document deliverable_sha256 entries may differ. All numeric
counts, source/analysis-output digest fields and other deliverable hashes match.

The previous full-study checks remain historical evidence. No inference, fit,
timing, bootstrap, corpus calculation, broad test or full analysis was repeated.

## Check result

{
  "audit_findings_addressed": [
    "R1",
    "R2"
  ],
  "prose_facts_match_audit": true,
  "recorded_environment_disclosed": true,
  "existing_markdown_tables_unchanged": {
    "REPORT.md": {
      "sha256": "f394374399c3c2191749289c56597bb6a6fcf80a5b39d90b944f0a6c4184b9e8",
      "rows": 11
    },
    "APPENDIX.md": {
      "sha256": "f6908a6cbcab6ba59bceced4b4dc950c1614a6bd20218c6203e83da1a147ee57",
      "rows": 268
    },
    "README.md": {
      "sha256": "b9432b5cd7d62b7bf058cfa6675e8fe5d1e5b890d278f41818db60516090f92d",
      "rows": 20
    }
  },
  "analysis_sources_unchanged": [
    "analysis.py",
    "archive_intervals.py"
  ],
  "analysis_report_append_only": true,
  "verification_changes_limited_to_authorized_fields": true,
  "all_numeric_counts_and_analysis_output_digests_preserved": true,
  "report_words": 1024,
  "inferences": 0,
  "fits": 0,
  "timings": 0,
  "analysis_reruns": 0,
  "broad_tests": 0
}

## Input audit hashes

{
  "final-audit.md": "980521cb88afced3780c71998425272aa41e0089741435f382b8f8d1e4db2e57",
  "final-audit.json": "eec0343654352966aff6a8f3a776d5111a80e3ba91b16ca9d562940e5f61bfdc"
}

## Before and after file hashes

{
  "REPORT.md": {
    "before": "8b211fd49260c528facf1803edb568ffec6ad04964da8fff37cec68c5480d992",
    "after": "f3b48bbf9c5048c9bd3a88a13a2271c29ffbb900882ce4a310a9837b7be12940"
  },
  "APPENDIX.md": {
    "before": "e3c0616dd0d7f2c427ffddee4a1517ddde2929ecc155affcf31bde8b52e41564",
    "after": "878a8c38bb8cceeabb047a5337c7b37a6b3bf697b0ce29e4560e48e70f608384"
  },
  "README.md": {
    "before": "5cf0f1aecc583ad5a976e1b687c6c5cf08691642d0c179b6f37afbd72c7e373e",
    "after": "1bef4d14592f74d8b585545bb7500b96cc92dfc04a6ef5b5b54cf3f1bc9fed82"
  },
  "analysis-report.md": {
    "before": "8f2210d9099038aa50f9e53224994604480135f38b54fad43959da1b0655623c",
    "after": "9d69ddfad23416a0f64a8fa42446c22d941678f115ecd4830a74e53651b38e73"
  },
  "analysis/verification.json": {
    "before": "78be57ee6e84dce47c8d8aad9fed2a870bcef78738bc54499a872f2c573c1a50",
    "after": "3b6e0f53636f29dcc699ae93dede4ef9edd4e5ecee88c5aa4438ac3daf139c1d"
  },
  "analysis.py": {
    "before": "6db72654689603a821ef1e0bee2b4ef5671be997b82ed0ed5daaed77a293f73e",
    "after": "6db72654689603a821ef1e0bee2b4ef5671be997b82ed0ed5daaed77a293f73e"
  },
  "archive_intervals.py": {
    "before": "ea2a995f00b69b1a56f8028a2e41da268b804b3be1f6cb69ef964b542ccc766a",
    "after": "ea2a995f00b69b1a56f8028a2e41da268b804b3be1f6cb69ef964b542ccc766a"
  }
}

No commits were made. Writes stop at this handoff; the parent refreshes the release manifest with this report and the audit chain.

## Final scoped-review editorial clarification

Applied the reviewer-proposed phrase “на 158 строках вне обеих частей набора разработки” across its existing line wrap. Initial exact-match assertion found no single-line phrase and changed nothing; the verified line-wrapped replacement occurred exactly once. Markdown-table digest is unchanged. No number, calculation, model or source changed. Current Appendix SHA256: `abbf8adf53be795bdb7e80c889270bb7f6c6ed8675be32c49268aff1bc9b2c13`. Verification metadata is refreshed. Earlier hash maps remain historical fix-wave records.
