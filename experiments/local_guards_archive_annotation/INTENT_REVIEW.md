# Axis A source-only review

Model-assisted adjudication, not human gold. The two sealed records were compared without opening method predictions, results, reports, action labels or methods. Axis A and author fixture categories are separate; neither establishes action correctness or real-world harm.

## Intent adjudication

Both raters have 542 unique IDs. Cross-tab (r1 × r2): unknown/unknown 363, benign/unknown 96, attack/attack 45, benign/benign 38. Raw agreement is 446/542, not an accuracy estimate. All 96 disagreements concern `base` invoice construction: four exact invoice/amount groups of 63, 11, 10 and 12 cases. For every case the bounded source files were reopened and hashed in `labels/intent-adjudication-readlog.jsonl`. The original fixture records `variant=base`; the available current generator calls base ordinary text and its description matches, but its bytes are not bound to the historical run. This supports the benign interpretation but does not establish that the historic construction was a benign control. The adjudicated label is unknown for all 96; this is a conservative evidence judgment, not proof of attack. The amount-based `policy` source category is not used as intent truth.

Agreement audit: Python `random.Random(17).sample(sorted(agreement_ids), 30)` selected 25 unknown, 3 attack and 2 benign. Case IDs and source hashes are in the readlog. The sample supports retaining the ratings: ordinary or approval/urgency language can have different objectives; the explicit instruction to avoid additional checks supports workflow redirection, with scope of 'additional' not fully specified; neutral delivery text plus matched placebo construction supports benign, subject to generator-binding caveat. This is a small random audit, not an exhaustive independent review of agreements. The remaining 416 agreements are explicitly marked inherited, with the two complete original ratings and evidence preserved. Final distribution: unknown 459, attack 45, benign 38. Status distinguishes the 96 adjudications, 30 audited agreements and 416 inherited agreements.

## Original author categories

Each of 494 archived fixture declarations was independently checked against the stated archive SHA-256, member SHA-256 and JSON pointer to `truth`; all matched. The other 48 references were checked to exist at their source-hashed gzip line (including seven git-blob sources); no author declaration was recovered in the curated records. This does not establish that no such declaration exists elsewhere. Counts over 542: legit 160, injection 216, policy 110, fraud 8, unknown 48. `labels/author-category-reviewed.jsonl` retains per-case provenance and verification. Unknown refers to absence of a recovered category, not a fifth author category.

All seven supplied definition excerpts were checked against current file SHA-256 and exact source lines. The pairs/custom constructors assign `policy` to base/placebo when amount exceeds 10,000, and `legit` below that threshold; sweep uses `policy` for base scenarios. This is a constructed policy category, not a declaration of adversarial intent. The v5 source assigns injection to generator-provided attack examples, noting that some are borderline. `fraud` is a separate recorded fixture category; its exact semantics are not established by the supplied definition excerpts. Generator files are current saved sources and are not cryptographically bound to historical execution. Matching text and amounts support provenance but do not close that gap. None of the four values is automatically mapped to independent benign/attack or to an action label.

## Integrity

SHA-256:
- `labels/intent-r1.jsonl`: `8bbcc6b15873d79bbfa3c66d9b51dc896ec3c8d3cb0ae20b1c280493e1d61f55`
- `labels/intent-r2.jsonl`: `df950c0700d4d3c30d76adc7242740ff83d0c01dc376c191cd946263031edac7`
- `labels/intent-r1-readlog.md`: `9c33072b6eab79250c32cb1e2d2f08362fcceb897320dc66887f2da58f570efe`
- `labels/intent-r2-readlog.jsonl`: `2baf83373460d6eeb5d4b88d731216f7acc5be1f6f0b10d96ab0a74b24cbbd31`
- `labels/intent-adjudicated.jsonl`: `f56a6a36a58d8a814faa0b0c96cbe7b539244e1f20242d1969f6aaa7818aac05`
- `labels/intent-adjudication-readlog.jsonl`: `558525c303498ef0a7bd23ec9703c3343294a87f6784abf23312c0b8bddec7c6`
- `labels/author-category-reviewed.jsonl`: `b7cb242e32a972600a17bed4781be7792a0aea0a2a10d2dcb6ec217514ee8a2d`
- `scenario_sources/author_intent_declarations/custodian_definition_evidence.json`: `24615cbda325356236fa1428bf072607fc24786c2740b87483934c3e4d47e7b5`
