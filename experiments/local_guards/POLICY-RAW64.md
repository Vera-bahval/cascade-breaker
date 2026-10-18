# Raw64 cached-score policy diagnostic

This is an explicitly post-hoc comparison on the already known authored raw64 stress cases. It does not constitute a new independent evaluation or native first-harm timeline measurement.

No feature inference, paid API requests, training, or raw-label threshold tuning occurs. Reuse the archived final-model raw64 probabilities, and calibrate each policy on the corresponding seed's full-archive three-fold grouped OOF probabilities. Compare all supported fixed methods under no rules, original rules, and frozen rules_v2. Missing four-checkpoint Jev features, exact tabular features, and 4B raw probabilities remain unsupported rather than being fabricated.

The shared policy helper defines A_joint, B_independent, and C_lowest on the exact observed-score grid and the `score >= threshold` comparator. The raw64 runner first reproduces the former legacy-grid calibration and decisions exactly. B_independent has two separately named model-selection procedures: `train_selected_combo_B2` selects using the final wrapped system's archive calibration metrics, while `train_selected_Blegacy_combo` selects the standalone component winner and then ORs the wrapper. Both the full candidate winner and the raw-compatible restricted winner are reported; they are different selection procedures and cannot substitute for each other silently.

Reproduction from workspace root (preserve existing results; use a fresh output directory):

```sh
PYTHONPATH=experiments/local_guards experiments/local_guards/.venv/bin/python -m cascade_guard.cheap_policy_raw --freeze-only --output /tmp/policy-raw64-reproduction
PYTHONPATH=experiments/local_guards experiments/local_guards/.venv/bin/python -m cascade_guard.cheap_policy_raw --output /tmp/policy-raw64-reproduction
PYTHONPATH=experiments/local_guards experiments/local_guards/.venv/bin/python -m pytest experiments/local_guards/tests/test_cheap_policy_raw.py -q
```

`input-freeze.json` hashes the implementation, shared policy helper, source predictions, archive labels, and raw stress labels before calculation. Labels for raw64 are read for scoring only after all thresholds, model choices, and predicted decisions have been assembled. The source labels are not feature inputs.

`legacy-reproduction.json` records exact old-calibration, old-selection, and old-decision checks. `calibration.json` stores training-only provenance, threshold constraint scope, threshold feasibility, and final-system feasibility. `unsupported.json` explicitly lists absent combinations. `predictions.jsonl` preserves learned risk or scalar score, UNKNOWN status, selected configuration, threshold, and reconstructed latency. `metrics.json` reports the authored raw64 confusion matrices and learned-component proper scores only; scalar values are not treated as harm probabilities.

The earlier implementation attempt is preserved under `results/policy-comparison/raw64-attempt01` with exact source/helper snapshots. It preceded presentation and validation changes to the shared helper and the addition of the explicitly named Blegacy/B2 nested-selection variants; its fixed-method results are not an additional independent experiment.
