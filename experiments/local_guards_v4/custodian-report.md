# V4 data custody and independent oracle

The controller wrote the extractor/oracle from the contract before reading target guard implementation; it imports the independently frozen v3 payment oracle, never v4 guard/store or defender verdicts. A separate read-only custodian inspected source archives, source-version evidence, grouping, labels and final artifact joins. Its final spec/data-quality verdict was PASS on extractor `8a547a818d594a205697178245addae36d3a6e343255196e2ca855e77d13f14a`.

## Population and grouping

Available records: **3,378 episodes, 83,099 prefixes, 308 connected base-task groups**. The cohorts are original main 1,352; additional historical 1,864; valid pilots 32; invalid partial attempts 7; extra legacy records 15; previously enforced/censored records 108. These cohorts are not interchangeable quality denominators. Byte-equivalent/canonical journal aliases are counted once, with packaged source/phase metadata taking precedence over raw copies. Source archives and recovery/offline diagnostic hooks are inventoried without pretending they are independent executions.

Exact normalized input and explicit source pair aliases form connected components across variants, profiles, repetitions and executors. Seed17 splits eligible non-Luna groups 75/25. All317 Luna episodes remain TEST_EXECUTOR, including diagnostic phases; report original-main297 separately. TRAIN/CAL overlap is zero; the two TRAIN-package files exactly match TRAIN prefix IDs and contain zero Luna records. Existing archives and API-MAST are developer-exposed, not new blind tests.

## Evidence and labels

Only prefix-visible native results and input/source records establish features. Final DB snapshots are outcome-only. New context uses actual recorded session/workflow IDs where available; legacy random session IDs remain null and their workflow ID is derived from the pinned harness. Verified demo user IDs and source fixture context are named as such. Unverified supplemental native revisions remain null rather than inferred from a filename. No source scenario title, intent, split, executor or gold enters the guard observation; baseline invoice text is retained only in the separate legacy/ML payment view.

All archived `session_valid` facts remain UNKNOWN: timestamp validity alone does not establish server authentication. Source-verified DeepSeek/Luna workers capture `utc_started` before constructing their two-hour session; this permits a conservative expiry lower bound at the current prefix, saved as audit metadata only. Legacy `started_at` is post-run and is not used. No final duration or future hook timestamp creates a feature.

Lineage requires exact prior call/return matches including arguments, session and workflow. A broken lineage never recovers guessed technical authority. P2 completion distinguishes successful, explicit failed and missing/invalid status. Transfer results pair with pending calls rather than the latest preceding P4. A07 bookkeeping receipts additionally match the current session/workflow, invoice/vendor, reference, amount, currency and previously established recipient comparison. Missing scope stays unknown. All attempt/completion coordinates use the same observation phases.

Action gold is requirement-wise A/B contract adjudication, independent of target predictions. A05 follows contract4.1: canonical current status is not itself a ban on re-review. Scenario intent, action correctness and archived harm stay separate. Original-main source outcomes reproduce **112 harmful, 1,162 nonharmful, 78 unknown**. Supplemental intent tags are not silently converted using the original-main funnel oracle; source harm remains unknown without an explicit applicable original expected outcome. Inherited `contract_continuation_harm` is explicitly **v3 payment-only**, not evidence of every v4 technical effect. SystemUtils outputs are mock calls, not physical damage.

## Verification and limits

Four focused custodian tests cover pre-cut session bounds, exact transfer pairing, scoped receipt binding and broken-lineage authority. The independent audit checked final hashes, all ID joins, zero future evidence, zero TRAIN/CAL group overlap, Luna exclusion and cohort counts without importing target guard/store. No model calls or fitting occurred.

Complete server authority, shared admission registry and material-bound approval records cannot be reconstructed from most historical logs. Consequently a full-A retrospective safe denominator can be unavailable. This is a data limit, not evidence that full-A deployment would stop every real task when live trusted context is present. Native scripted integration measures that separate execution path.

Reproduction: preserve `data/source-inventory.json` as the immutable Git-object input index. `inventory_sources.py --refs-json data/source-inventory.json --output NEW.json` reuses pinned source revisions; `prepare_data.py` rebuilds payloads from the existing index and Git blobs. `data/manifest.json` records every payload, source inventory, policy and reused v3 oracle hash. Never regenerate published payloads in place after method freeze; use a copy for reproduction.
