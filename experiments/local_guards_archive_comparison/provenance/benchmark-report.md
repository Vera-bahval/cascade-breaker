# Frozen-method shared-input latency

Completed a bounded local timing benchmark of 13 methods, using the exact same 30 released normalized TRAIN P4 inputs. An additional working-hook phase measured 600 scripted native chains. There was no refit, API/model request, archived-LLM executor rerun or quality scoring. Old replay code/results/reports were not edited.

## Selection, source and timing boundary

The coordinator predeclared the selection rule before inspection: first 30 P4 JSONL payloads by SHA256 from `packages/release/TRAIN-rows.jsonl.gz`. Selection identities and hashes are in `results/method-latency.json`. The source file SHA256 is `c6104f65e3a4cca86960384abbc58e5ab0553ae7262eff92f1abd3261b460831`. Every method receives the same 30 inputs for 30 shuffled rounds (seed 17): 900 measured calls per method, 11,700 call records total. All methods/inputs are warmed once before measurement; probability-only and combined ML call order alternates to reduce precedence effects. These are repeated timing inputs, not independent accuracy cases or a representative latency/SLA sample.

Frozen native source: `8e7aa49c198a23f8313fdc9ee2873ad099c1112aae2d4a7d85990888be73a81b`. Executed ML source: `4be593465378240c8885d317abca80455d2695e1c66184a18606120f3bcf00ca`. Shared frozen evaluation/control adapter: `86409c43c830b41ab538191472f45315da37dbe3e2305d7717d2b2e12361215d`. Before joblib deserialization, the methods-freeze binding of the release manifest, all 12 weight hashes, copied/current source hashes and historical control freezes are verified. Only the six primary source-target (`scenario_decision`) ML weights are loaded and timed; the six native_core diagnostic-target weights are hashed but not loaded. The manifest hash and actual historical Git constructor receipt are retained in JSON.

Warm values start with an already decoded common row. They include native predicate evaluation or frozen control adaptation; ML includes structural features, vectorizer/scaler, required dense conversion and single-row probability prediction. They exclude gzip/JSON input loading, collector reconstruction, optional diagnosis, native DB reads and durable working-store operations. The separately measured real native P4 decision-ready cost of 1.069 / 1.562 ms p50/p95 belongs to `replay-native.json`; it is not added to archive gzip/collector timing or relabeled as an ML deployment result. The ready-observation table alone does not measure ML-in-FinBot workflow latency; actual direct-Payments callbacks are measured separately below. Adaptive executor latency remains unmeasured.

## Warm single-row results

All numbers are milliseconds, nearest-rank p50 / p95. Full means actual common-row method call including its adapter; guard-only uses only actually executed old guards. Nested component quantiles are not additive.

| Method | Full common-row call | Guard only | Adapter | Applied adapter calls / 900 |
| --- | ---: | ---: | ---: | ---: |
| native | 0.0613 / 0.0759 | 0.0613 / 0.0759 | — | 900 |
| native_core | 0.0594 / 0.0730 | 0.0594 / 0.0730 | — | 900 |
| v1 | 0.0673 / 0.1935 | 0.0010 / 0.0018 | 0.0665 / 0.1914 | 90 |
| v2 | 0.0663 / 0.2148 | 0.0308 / 0.0378 | 0.0658 / 0.1832 | 90 |
| v3 | 0.0579 / 0.0730 | 0.0089 / 0.0115 | 0.0483 / 0.0605 | 900 |
| v42_payment_common | 0.1580 / 0.1848 | 0.0987 / 0.1123 | 0.0577 / 0.0712 | 900 |
| v42_fullA | 0.1653 / 0.2022 | 0.1048 / 0.1287 | 0.0585 / 0.0752 | 900 |

v1/v2 can reconstruct their original binary input on only 3 of the 30 selected inputs: 90 applicable calls each. The other 810 calls lack `initial_transactions`; they return adapter-unavailable UNKNOWN. Their guard timing is null, not fabricated zero. Full/adapter timing still records the actual unavailable-input processing. Guard-only quantiles for v1/v2 therefore use 90 calls; other guard rows use 900. `adapter_applicable=True` on v3/v4.2 means the frozen wrapper ran, not that missing business/technical evidence was certified. Original raw decisions, unavailable fields and adapted decisions remain in raw records.

| Primary source-target ML | Probability only, including features | Probability + frozen CAL point + native_core gate |
| --- | ---: | ---: |
| scenario_decision-lr-17 | 0.2764 / 0.3482 | 0.3452 / 0.4141 |
| scenario_decision-lr-29 | 0.2780 / 0.3584 | 0.3478 / 0.4182 |
| scenario_decision-lr-43 | 0.2763 / 0.3340 | 0.3452 / 0.4049 |
| scenario_decision-catboost-17 | 0.2509 / 0.3298 | 0.3178 / 0.3723 |
| scenario_decision-catboost-29 | 0.2519 / 0.3409 | 0.3193 / 0.3792 |
| scenario_decision-catboost-43 | 0.2514 / 0.3376 | 0.3191 / 0.3884 |

The combined column is the actual frozen `Predictor.predict(row, native_gate=True, placement="p4")` call, not a sum/subtraction of quantiles or a shortcut around prediction. All 5,400 probability-only outputs match the probabilities produced by their combined call within 1e-12. Every primary P4 operating point in this release is INFEASIBLE: calibration returns UNKNOWN, while the native_core gate can force BLOCK. The benchmark still computes real probabilities before that fallback; these latency numbers do not establish a feasible operational security policy.

## Fresh-process measurements

30 fresh processes per listed method, 270 total; the cold phase took 76.62 seconds, so the 10-round budget fallback was not used. All methods receive the same first selected P4 row through stdin, with one identical canonical input hash verified across all 270 workers. LR/CatBoost seeds 29/43 were timed warm but not measured in fresh processes.

| Method | Import/load/first response after verification, ms | Whole Python process, ms | Peak RSS p50 / p95, MiB | First adapter available |
| --- | ---: | ---: | ---: | --- |
| native | 1.2150 / 1.3315 | 87.1697 / 96.6936 | 34.69 / 34.80 | True |
| native_core | 1.2441 / 1.3779 | 85.5353 / 103.8044 | 34.69 / 34.86 | True |
| v1 | 1.2722 / 1.5622 | 85.9361 / 94.1694 | 34.70 / 34.84 | False |
| v2 | 1.2526 / 1.4471 | 86.4821 / 98.1162 | 34.72 / 34.78 | False |
| v3 | 1.6153 / 1.8411 | 86.5901 / 98.5143 | 34.72 / 34.84 | True |
| v42_payment_common | 4.7498 / 5.3822 | 89.3941 / 102.0781 | 35.00 / 35.12 | True |
| v42_fullA | 4.7259 / 5.1089 | 90.3375 / 104.6179 | 35.05 / 35.17 | True |
| scenario_decision-lr-17 | 783.3157 / 942.8662 | 960.1353 / 1120.1813 | 154.80 / 155.06 | True |
| scenario_decision-catboost-17 | 773.6522 / 837.4502 | 948.1304 / 1008.9067 | 167.08 / 167.25 | True |

The short after-verification column starts after stdin decoding and hash/control verification, which also imports the shared evaluation verification helper and reads the historical constructor Git object. It includes the candidate module/model load and its first actual response. Do not call that column total Python startup. The whole-process column includes interpreter/benchmark stdlib imports, stdin transfer/decode, source verification, candidate import/load/first response, output and process exit. JSON records additionally separate candidate import/model load, first response, hash-verification cost and input-decode cost. Source verification alone has median about 26–27 ms per worker. No archive gzip or collector runs in any worker. OS file caches are retained; RSS includes dependencies and verification metadata.

The first common input is unavailable for v1/v2, so their cold response is the genuine adapter-unavailable UNKNOWN and no original binary guard executes. Their tiny after-verification values are not claimed as full original-guard latency. v3/v4.2 execute their frozen wrappers. Native methods are pure guard probes here, not cold FinBot startup.

## Actual native P4 working latency

The additional requirement is now measured directly, without adding an estimated state cost to ready-row timing. The NEW benchmark injects a verified callback into unchanged `replay.native_profile_trial`; `replay.py` and its old source receipts remain unchanged. Before loading models, this phase verifies current 4be593… ML source and frozen weight hashes. It replaces only the older guard-loader dependency (whose unrelated f8c09e… ML pin was never executed), not native interception, snapshot collection, STOP persistence, scripts or diagnosis behavior.

Five callbacks run on the same declared approved-safe/mismatch fixtures: native_core, raw LR17, raw Cat17, standalone calibrated LR17, standalone calibrated Cat17. Raw classifiers call the frozen probability function and its original deterministic argmax; calibrated callbacks call frozen `Predictor.predict(native_gate=False, placement="p4")` and select calibrated_decision. No native gate is silently added to a raw classifier. Each actual path is direct `run_payments_agent → get_invoice_for_payment → actual FinStripe P4 interception → bookkeeping/completion if allowed`, with a scripted client, fresh isolated native DB and real in-process MCP.

30 shuffled rounds per method × two fixtures × diagnosis on/off: 600 scripted chains, 300 paired comparisons, exactly two authored fixture states rather than 600 independent archive cases. All 300 diagnosis pairs retain identical verdicts, effects, STOP reasons and scripted-call sequences. Every actual STOP has zero local transfer records, a persisted STOP and blocked subsequent model/direct-native attempts. All 600 sidecar cleanup readbacks and the source DB removal readback are true. No cold measurements were repeated.

P4 decision-ready below is the actual complete guard work excluding optional JSON diagnosis: reused current-state bridge snapshot, fresh common-row/native DB snapshot and provenance, selected callback, required working-store reads and STOP persistence where applicable. The extra reused bridge snapshot is part of this implementation, not an estimated optimized adapter. Diagnosis serializes after the measured decision-ready boundary. Model weights load before the chain; cold loading remains separately measured above.

| Callback / fixture, diagnosis off | Actual P4 verdict | Completed / STOP | Full P4 work, p50 / p95 ms | Fresh common-row state | Callback only | Successful chain | Time to STOP |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| native_core / safe | ALLOW | 30 / 0 | 0.957 / 1.030 | 0.295 / 0.331 | 0.060 / 0.063 | 21.271 / 25.051 | — |
| native_core / amount_mismatch | BLOCK | 0 / 30 | 1.521 / 1.939 | 0.297 / 0.352 | 0.060 / 0.065 | — | 13.351 / 15.961 |
| lr17_raw / safe | ALLOW | 30 / 0 | 1.343 / 1.413 | 0.300 / 0.331 | 0.442 / 0.472 | 21.388 / 24.308 | — |
| lr17_raw / amount_mismatch | ALLOW | 30 / 0 | 1.358 / 1.441 | 0.302 / 0.348 | 0.439 / 0.465 | 21.790 / 25.267 | — |
| cat17_raw / safe | BLOCK | 0 / 30 | 1.899 / 2.139 | 0.299 / 0.338 | 0.435 / 0.488 | — | 13.928 / 15.658 |
| cat17_raw / amount_mismatch | BLOCK | 0 / 30 | 1.940 / 2.387 | 0.300 / 0.343 | 0.439 / 0.531 | — | 14.043 / 16.891 |
| lr17_calibrated / safe | UNKNOWN | 0 / 30 | 1.902 / 2.162 | 0.295 / 0.322 | 0.435 / 0.463 | — | 13.664 / 15.969 |
| lr17_calibrated / amount_mismatch | UNKNOWN | 0 / 30 | 1.936 / 2.453 | 0.305 / 0.348 | 0.443 / 0.495 | — | 14.175 / 15.501 |
| cat17_calibrated / safe | UNKNOWN | 0 / 30 | 1.892 / 2.431 | 0.300 / 0.333 | 0.437 / 0.480 | — | 13.867 / 16.220 |
| cat17_calibrated / amount_mismatch | UNKNOWN | 0 / 30 | 1.896 / 2.357 | 0.305 / 0.331 | 0.435 / 0.457 | — | 13.811 / 16.187 |

Behavior matters when reading these times: raw LR17 allows both fixtures, including the amount-mismatch attempt that reaches one local transfer record and invoice paid. Raw Cat17 blocks both, interrupting the structurally safe task. Both standalone calibrated variants return UNKNOWN and stop both fixtures because their frozen P4 operating point is INFEASIBLE; they still compute actual model probabilities first. Native_core allows the safe fixture and blocks the mismatch. These controlled results do not estimate archive error rates and triggered no source, model, threshold or selection repair. Faster time to a wrong action or an interrupted safe task is not successful task performance.

Raw records separately retain actual working-store call counts/per-trial p50/p95 (`stopped`, `events`, `record_event`, `mark_stop`, etc.), SQL BEGIN IMMEDIATE waits, bridge snapshots and optional JSON-diagnosis times. Required timing components overlap and are not additive. The native profile is structural: no semantic Fraud/tax/exception compliance, full orchestrator recipe, adaptive LLM behavior, bank atomicity or production exactly-once guarantee is established. Full gated ML-in-hook variants and seed29/43 hooks remain unmeasured; their ready-row calls are measured in the earlier table.

Current hook benchmark source SHA256: `9aaced44c208837797e45747b61b3b9e22d9728d43ae8fb309ac41513d796798`; test SHA256: `748d2af4bc294f6478b5261a1f0a98c3f7d75009895203e66aee7e4f54c38e70`; unchanged replay helper SHA256: `11e8b50d4a62540a4776e4a128e21d570e014f71db00e3d6815e5d3dbe9d702a`. The original ready-observation/cold stage remains bound to its earlier source hash; exact prior benchmark/test texts are preserved under `ready_observation_source_snapshot` in JSON, and their hashes were rechecked. This avoids attributing old timings to the appended callback code.

## Validation, read provenance and limitation

Fresh final command in the existing native Python environment: `python -m unittest experiments.local_guards_archive_comparison.tests.test_benchmark -v`: 4 tests passed. The checks exercise deterministic P4-only selection independent of file row order, unavailable old-adapter timing without false zeros, frozen ML probability/combined parity, and actual selected-callback P4 ALLOW/BLOCK/UNKNOWN enforcement before effects. JSON verification confirms 30 identical input identities for every method, 900 calls each, 270 cold workers with one canonical input hash, all 5,400 ML probability pairs equal, null guard time for unavailable controls, and preserved original stage/current hook source hashes, all 600 native-hook chains and 300 matching diagnosis pairs.

Author read-scope deviation: during interface inspection, `results/ml-release-v2/scenario_decision-lr-17.cal.json` was opened expecting frozen thresholds, but it also embedded CAL prediction/target-label rows; part was exposed in tool output. A short prefix of `results/rule-calibration.json` containing aggregate CAL metrics was also inspected. This was reported to the coordinator immediately. No selected evaluation rows were read for this task. The TRAIN selection rule had already been fixed by the coordinator; there was no model/source/configuration/selection adjustment, label-dependent timing selection or refit. Do not describe this authoring phase as never having viewed CAL-label artifacts. Those CAL rows were not benchmark inputs or used for scoring. Subsequent metadata reads projected only frozen source/model identities and operating-point metadata.

Other reads: current `evaluation.py`/`ml.py`/methods interfaces, methods-freeze and ML freeze-manifest metadata, released TRAIN rows, existing control manifests/source files and source-pinned historical constructor. Runtime prediction loads operating points from the hash-verified joblib payload; separate `.cal.json` files are not opened by benchmark.py. There is no request to an inference API, external executor API, remote Git or external knowledge source. Socket connections are rejected during measured runs.

This phase does not rerun or revise older replay receipts. Their f8c09e… ML source was only hashed and never executed; it must not be presented as the source used for this new matrix. The old 37-test receipt belongs to its earlier source phase, not a fresh check after the current ML update. No cold full-application, adaptive cascade, cloud LLM or production throughput result is inferred.

Original ready-observation stage benchmark source SHA256: `d90265515a4bfd1f39737f72d3595a6da04f487f08f09d398c3373dd5d2298bb`. Its test source SHA256: `26f30f956db43b00c10be6ded0f4043cc2c7d4f3ec4c2aa02b83494ef0b596aa`. Result SHA256: `53baf83785abe838394f0d4cde37c7c3de4a1b5c9b2631f792d64d5e0fe35e72`; compact JSON bytes: 6169362. The JSON was compacted without removing or changing any payload value.
