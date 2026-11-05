# Progress: repaired archive evaluation

Base: c42ca383. Scope: approved user request; no new model API calls, fits or live FinBot.

- Preflight:64 adapter controls PASS; input audit38978/759113 PASS.
- Protocol saved before inference. All registry variants retained, no test-based selection.
- Ruling: use frozen batch inference with singleton parity, never batch averages as single-call latency.
- Ruling: early A08-only is not run; no applicable payment requirement there.
- New scoring controls:4 PASS.
- Next: freeze config, infer five groups, seal predictions, score, benchmark ready-input decisions, edit report, independent audit, publish.

- Runner defect fixed before scoring: output hashing moved after the read fence. Incomplete attempt retained in /tmp/finbot-repeat-attempt1; no labels read or quality computed. Regression test PASS.

- Inference complete:all five groups,569 P4 configurations,18 early configurations,587 files,1597530 rows.
- Score sealed before labels; two further scoring passes reproduced five data files exactly.
- Benchmark:38090 singleton/batch matches, no execution errors.
- Posthoc routing added without changing methods:BLOCK-only and determinate fallback.
- Main report rewritten around real-state coverage, errors, ordinary-task burden and early false stops.
- 69 controls PASS; full integrity audit PASS before final review.

- HOLD RELEASE:independent source-format audit found legacy proposal/callback mismatch and completed-LLM representation errors. First-pass outputs above are superseded, moved to /tmp/finbot-repeat-superseded-legacy-pairing; no results published.
- Source-format repairs general, not rules/threshold changes.72 adapter controls pass.
- Next:prepare revision2 inputs, independent approval on exact source/manifest, then rerun all local inference and scoring.

- Independent legacy source diagnosis:raw shadow-main#L90 cle-clean_09-beda74, source gzip SHA0d16d93500789d716f0b07a2beab64e78af6deea03c072d66133b3480389c504. No old source commit equivalence assumed.

- Parser fix code review:no blockers after captured-parent, namespace and alias controls. Independent9 structural controls PASS. Full77 adapter tests PASS.
- Reviewed evidence.py SHA32d09adb1d59b33dc2130254c02db79c71aa1d36c9092250c5c82bae9666f299.
- Stable preparation started:/tmp/finbot-adapter-final-legacy-v2 and same name -reproduction. Do not change adapter *.py while running. Final exact-SHA/manifest gate still required before any new predictions.

- Revision2 exact gate APPROVE: b20c6587 + manifest5915413a.77 adapter/82 combined controls PASS; independent928182 value/provenance and272718 boundary checks.39 shards+manifest reproducible. Approval recorded; all inference restarts from scratch.

- Valid revision2 run complete:569 P4 /18 early configurations,587 files,1597530 records. All inputs pinned to5915413a. Source methods/models unchanged.
- Audit PASS;38120 singleton/batch comparisons. Second score reproduces all five data outputs exactly. No model API or fit calls. Report now reflects revision2 outputs only.
