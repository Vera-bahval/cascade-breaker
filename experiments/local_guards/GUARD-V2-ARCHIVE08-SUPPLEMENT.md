# Prospective archive-only supplemental series

This is separate, post-hoc archive development analysis. It adds no model inference and makes no independent-test claim. The primary available block pool, selectors, models, thresholds, predictions, labels, and reports remain untouched.

Root may launch `scripts/run_guard_v2_archive08_supplement.py` only after the main completion transaction reports COMPLETE, with both inference runtimes unloaded and the shared heavy lock available. The script requires a pinned supplemental protocol and refuses an existing output directory. Deadline remains 2026-10-15T22:59:58.072112+00:00. There is no automatic watcher, restart, or extension.

The archive checkpoint population is fixed:704 inputs,176 episodes, four real checkpoints. The independently reviewed `audit_guard_v2_costs_05.py` lexical projection parser extracts only prefix_id before any full score deserialization. Nonarchive probabilities and other payloads are skipped lexically. Its exact source hash is pinned. Selection of source score rows uses only these frozen prefix identities; no partial independent population or score values influence selection. Every archive checkpoint must be present exactly once with status OK. Missing, duplicated, or UNKNOWN archive observations reject the export; no complete-case filtering. Frozen `v2_jev.feature_records` validates canonical/inference input hashes and model fingerprint, chronological stage joins, and constructs the five existing blocks. Frozen `normalize_jev_file` supplies the already approved metadata envelope. The output must contain880 OK records across176 P4 targets and exactly J_cur/J_seq/J_agg/J_dynamic/J_prior. Original source scores and all main directories remain unchanged. Main prediction files are hashed for identity only; their probabilities are never deserialized by this runner.

The global deadline is checked after snapshot, after feature construction, and immediately before its completion seal; expiry preserves partial artifacts with EXPORT_INCOMPLETE and prevents a false completion claim. Export is committed first, as `EXPORT_COMPLETE.json`, raw archive-only score snapshot,880 raw features, normalized `Jev-08.jsonl`, and hashes. If root requests export only or fewer than1200 seconds remain, CV is deferred with an explicit marker and export preserved. The1200-second reserve is an admission floor, not a runtime promise.

If admitted, only the frozen evaluator's archive train command runs in NEW `supplemental-archive08-v5/evaluation`. Its19 configurations are five fixed J representations each with scalar, CatBoost, and CatBoost+tabular; tabular CatBoost, tabular Logistic Regression, TF-IDF Logistic Regression; and Logistic Regression with tabular+J_cur. CatBoost remains200 trees/depth3/lr0.03/L2=5. Existing seeds17/29/43 and grouped outer3/inner2 allocations, four policies, three wrappers, reached-safe93 primary calibration and131 legacy diagnostics remain fixed. No new hyperparameter/representation search. Built-in selectors are descriptive supplemental archive selectors, not the main available-pool selectors.

The train command emits archive nested-CV predictions/metrics plus its normal final-model seals. The companion `SUPPLEMENTAL_SCOPE.json` explicitly records that main unblinding happened before this archive-only series. The evaluator's generic BEFORE_EXTERNAL seal must not be interpreted as an independent pre-unblind registration for this supplement. No predict or score phase is invoked and no external label file is read.

Timeout/interruption kills the CV process group and writes CV_INCOMPLETE; export survives. Existing partial CV is never retried automatically. A nonzero child exit is also explicitly INCOMPLETE. Root may inspect metadata first; quality inspection and any later project changes are outside this runner.

Prepared CLI, not launched:

```
experiments/local_guards/.venv-finbot/bin/python experiments/local_guards/scripts/run_guard_v2_archive08_supplement.py --protocol ABS/ARCHIVE08_SUPPLEMENT_PROTOCOL_05.json --protocol-sha256 PINNED_SHA --run-cv
```

Omit `--run-cv` to preserve only the complete archive export. Main jobs, order, deadlines, and57 pinned sources are not modified by this supplement.
