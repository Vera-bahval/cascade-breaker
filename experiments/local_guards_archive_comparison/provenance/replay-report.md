# API-free replay and latency verification

Executed only local scripted FinBot paths and a preselected TRAIN timing probe. No executor/model API, remote Git operation, archive-outcome parse, CAL row, selected evaluation row or label was used. The current checked-out `finbot/` import is the execution subject; this is not a rerun of historical PR477 agents.

`results/replay-native.json` is the new native-profile integration result. `results/replay.json` is the unchanged v4 policy-extension control. They use different declared tasks, so their chain times are not a head-to-head method comparison.

## New native P4 hook

Frozen `methods.py` SHA256: `8e7aa49c198a23f8313fdc9ee2873ad099c1112aae2d4a7d85990888be73a81b`. Frozen `ml.py` SHA256 verified before each native worker/trial: `f8c09e6230fb648aea10d7cd3af9de8e7564a9fa18358bc5f472cb0c3200d218`. ML was hashed, never imported, fit or executed. The native result additionally binds 79 actually loaded local source files.

The actual runner is `run_payments_agent` on an explicitly approved isolated invoice, with a scripted client and real native/in-process MCP calls: `get_invoice_for_payment → finstripe__create_transfer → process_payment → complete_task`. The new `methods.guard(row, "native")` runs at the actual P4 interception, before the MCP transfer effect. All other bridge checkpoints are explicitly unchecked. There is no orchestrator recipe in this direct Payments task; this does not verify native N08 for new-invoice orchestration.

At P4 the adapter freshly reads native Invoice/Vendor and records current amount/status/number/vendor relation, bank-field presence and opaque account equality tokens. Proposal values are the actual intercepted arguments, including the source-defined `bank_transfer` default. The retained prefix contains actual native invocation/return events. Common-row provenance is explicitly local declared instrumentation with observed snapshot values, not historical attestation. No currency, approval registry, human decision, session gate, no-HOLD fact or semantic clearance is invented.

30 rounds, seed 17, shuffled scenario/diagnosis order. Each successful trial has exactly one actual local PaymentTransaction and invoice status paid; each STOP has zero transfers and the invoice remains approved.

| Scenario | Diagnosis | Completed / STOP | Successful full chain, p50 / p95 ms | Time to STOP, p50 / p95 ms | P4 decision-ready, p50 / p95 ms |
| --- | --- | ---: | ---: | ---: | ---: |
| safe | diagnosis_off | 30 / 0 | 24.363 / 47.187 | — | 1.069 / 1.562 |
| safe | diagnosis_on | 30 / 0 | 25.323 / 47.184 | — | 1.041 / 1.717 |
| amount_mismatch | diagnosis_off | 0 / 30 | — | 15.901 / 35.391 | 1.668 / 3.922 |
| amount_mismatch | diagnosis_on | 0 / 30 | — | 15.277 / 26.150 | 1.669 / 3.140 |

All 60 diagnosis on/off pairs have identical P4 verdicts, STOP reasons, effects and scripted-call sequence. After every mismatch STOP the runner actually attempts a later contextual-model call and a direct decorated native mutation: both are blocked, no scripted-model call is added, and the DB state stays unchanged. The STOP is read back from the actual durable sidecar.

| Native safe, diagnosis off: component | p50 / p95 ms |
| --- | ---: |
| Fresh common-row DB read and provenance construction | 0.338 / 0.793 |
| Pure new native guard | 0.063 / 0.087 |
| Reused bridge snapshot, all its checkpoints | 0.713 / 1.769 |
| SQLite BEGIN IMMEDIATE, actual event write | 0.008 / 0.016 |
| Optional JSON diagnosis, all bridge checks, diagnosis on | 0.007 / 0.012 |

Decision-ready includes required current-state reads, method evaluation and STOP persistence where applicable; optional JSON serialization runs afterward. The reused bridge performs extra snapshots and journal reads even at unchecked points. Working-store calls (`stopped`, `events`, `record_event`, etc.) have actual per-trial p50/p95/counts in `working_store_inclusive`. Timings are inclusive and nested; do not add them. Diagnosis off still constructs the guard’s mandatory reasons/evidence; only optional serialization is toggled.

## TRAIN timing and fresh processes

Before executing the frozen new guard, selected the first 10 normalized TRAIN rows by SHA256 of the original JSONL payload from the 1512-row package (source SHA256 `c6104f65e3a4cca86960384abbc58e5ab0553ae7262eff92f1abd3261b460831`). The frozen selection is `results/replay-train-selection.json`. It contains 7 P2_afterFraud and 3 P4 inputs. Thirty shuffled passes give 300 single-row calls, p50 / p95 0.041 / 0.104 ms. These are 10 repeated inputs for timing, not 300 independent cases or an accuracy estimate. No labels were read.

30 native fresh-process probes: whole Python process including startup/imports/trial/exit p50 / p95 1371.763 / 1725.840 ms; inside-worker native imports plus first trial 946.690 / 1256.291 ms. Peak RSS p50 / p95 154271744 / 154550272 bytes. OS file caches were not cleared; RSS includes native dependencies. All 30 worker source-DB removal readbacks and all main-series sidecar/source-DB removal readbacks are true.

## Separate v4 extension control

The original default-off v4 Runtime/guard/store are reused unchanged. This explicitly stronger fixture supplies USD and initial no-HOLD, then records native approval binding and typed Fraud completion. It is not the archive-native business policy. The actual path is chat `start_workflow → captured background runtime → Invoice → Fraud → Payments → Communication`, with real native calls and in-process FinStripe MCP. Communication completes locally; no email is sent.

| Extension/control, diagnosis off | Completed / STOP | Successful full chain, p50 / p95 ms | Time to STOP, p50 / p95 ms | Full check, p50 / p95 ms |
| --- | ---: | ---: | ---: | ---: |
| off/safe/diagnosis_off | 30 / 0 | 46.860 / 77.114 | — | — |
| extension/safe/diagnosis_off | 30 / 0 | 116.535 / 199.801 | — | 1.729 / 2.799 |
| extension/amount_mismatch/diagnosis_off | 0 / 30 | — | 83.988 / 181.401 | 1.655 / 2.554 |
| extension/material_change/diagnosis_off | 0 / 30 | — | 89.714 / 232.006 | 1.728 / 3.130 |

The extension has 90 matching diagnosis on/off pairs. Material-change is a separate X04-style approval-freshness extension: an actual approval record is read before a DB amount edit, then read as absent afterward; transfer is stopped with B01 UNKNOWN. It does not relabel a native approved invoice as an established native violation. Native mismatch and material-change STOPs have zero transfers, durable STOP and no later model/native effect.

Actual registry readback on every completed extension chain: four `technical_delegation` events (Invoice, Fraud, Payments, Communication), four parent call IDs, one completed-transfer event, and a released claim. No parent workflow ID is present in those delegation contexts; no producing source-call ID is present in the snapshot proofs. These missing bindings remain unverified. No parent/child/source-call attestation is fabricated.

Extension safe full-check state collection p50 / p95 1.512 / 2.464 ms; pure v4 guard 0.112 / 0.154 ms. Total inclusive working-store calls per successful chain: 44.074 / 59.737 ms. Full chain results and store totals overlap and are not additive. Extension fresh-process p50 / p95 1460.063 / 1931.522 ms; peak RSS 155566080 / 155926528 bytes. All recorded temporary cleanup checks are true.

## Concurrent claim/SQLite test

`results/replay-contention-cleanup.json` reruns only the affected readback/cleanup path after fixing a local SQLite connection-close omission. Thirty shuffled rounds, four workers and real EvidenceStore transactions per scope. A barrier prevents release until all acquisition attempts finish, so accepted distinct claims coexist. This is controlled claim contention, not parallel archived episodes, whole-agent load, real payments or production throughput.

| Scope | Admitted | Business duplicate denied | SQLite lock errors |
| --- | ---: | ---: | ---: |
| same_invoice | 30 | 90 | 0 |
| different_invoices | 120 | 0 | 0 |
| different_vendor_keys | 120 | 0 | 0 |
| vendor_overlap | 0 | 120 | 0 |

`different_vendor_keys` uses distinct vendor-wide keys (`invoice_id=None`); `different_invoices` uses distinct invoice keys for one vendor. SQL BEGIN IMMEDIATE wait is recorded per acquisition separately from semantic ClaimConflict denial. All 120 batches have zero remaining active/uncertain claims, zero SQLite lock errors and zero ResourceWarnings. Serialization/waiting at the global SQLite writer lock does not by itself mean a duplicate was denied.

## Verification and source receipts

Fresh final command: `python -m unittest experiments.local_guards_archive_comparison.tests.test_replay experiments.local_guards_v4.tests.test_runtime -q` in the existing native environment: 37 tests passed (5 new replay checks plus 32 existing native tests), no ResourceWarning. Existing Authlib deprecation/default development-key notices remain. The benchmark additionally records a 12-case native regression subset covering direct MCP interception, corrupt journal/verifier exceptions, restart uncertainty, chat duplicate admission, captured background scope, later-call STOP, suspended hook/native/MCP STOP races and material reapproval.

Measurement entrypoint SHA256: `05fa9f3cf62a0a7868cfb229ba343174849b43de96b3bc9771eb3a0ff1735197`. Final entrypoint SHA256: `11e8b50d4a62540a4776e4a128e21d570e014f71db00e3d6815e5d3dbe9d702a`. After measurement, only the contention readback connection was changed to explicit closing. `results/replay-source-receipt.json` records the exact reversible two-line replacements; reversing them reconstructs the measured entrypoint byte-for-byte. New native hook/guard/timing boundaries did not change, so unaffected native timing runs were not repeated. The affected 120 contention batches and full 37-test check were rerun.

Implemented only `replay.py`, `tests/test_replay.py`, `results/replay*.json` and these provenance files. No method/data/main report edit, dependency installation, remote Git action or model request occurred.

Unverified: adaptive executor/LLM behavior, archive accuracy/prevention, whole-orchestrator use of the new native profile, semantic native N10/N11/N14 reasoning/tax coverage, source-DB/sidecar/bank atomicity, external-write races, unobserved ABA, production exactly-once payments and throughput. The current runtime remains a research bridge. Small 30-observation tail quantiles are descriptive measurements, not an SLA.
