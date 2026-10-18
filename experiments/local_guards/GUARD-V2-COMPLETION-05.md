# Completion 05: preparation, no launch authorization

`finish_guard_v2_05.py` performs no model fitting, inference, API requests, or threshold changes. Root alone authors `results/guard-v2/ROOT_AUTHORIZATION_PLAN_05.json` after independent source review. The script is prepared; it has not been executed on real prediction/label data.

Root plan required fields:

- `authorization`: `COMPLETE_GUARD_V2_05_AND_UNBLIND`; `generation`: 5; `automatic_resume`: false.
- `root`: absolute `results/guard-v2`; `base`: absolute `experiments/local_guards`.
- `method_freeze_sha256`: `905199e01d99950fe905cb741d27bee56df5be745819d62d64820fb119747d44`.
- `completion_deadline_utc`: `2026-10-15T22:59:58.072112+00:00`. No extension or reset.
- `source_sha256`: absolute path/hash map pinning this runner, public tests (`test_v2_completion_runner.py` and independent `test_v2_completion_audit.py`), this protocol, preunblind, immutable evaluator, diagnostics module and its v2 protocol/tests, report, addon05, split05, Jev05 and guard protocol. All recorded MF05/addon input/source hashes are reverified too.
- `labels.independent`: `{path, sha256}` with commitment `89135d1002f0589e8818bc5673a6b1ba9c239cc0c4de5d94d9ac8077b9519dfa`.
- `labels.raw64`: `{path, sha256}` pointing to `raw64-labels.jsonl`, hash `4d4e0c590338a0b75257923429cb1d44b5ee22550a8b59d3d989875dde77407a`.
- `diagnostics_protocol`: absolute `external-diagnostics-protocol-v2.json`.
- `independent_control`: exact CLI flag/path map: `control-dir` (`contract-rules-control/v5`), `control-inputs`, `control-rows` (inputs-v5 independent P4), `control-method-freeze` (MF05), `control-source` (`v2_contract_rules.py`). These sources must also be pinned.

Future invocation by root, with the reviewed environment/PYTHONPATH:

```
python scripts/finish_guard_v2_05.py --authorization-plan ABS/ROOT_AUTHORIZATION_PLAN_05.json --authorization-sha256 ROOT_PLAN_SHA --wait --execute
```

Without `--execute`, validation remains read-only; no marker or label read. `--wait` waits only for absent/running prediction pipeline state, bounded by the original deadline. Failed/deadline pipeline stops immediately. Missing/corrupt seals after terminal success stop rather than being retried.

The fixed destinations are full independent240, full→raw64, matched partial→raw64-partial, and full→raw64-partial-shift. Both final model seals and source freeze identities must match successful prediction-run state. Every destination gets read-only preunblind validation before any marker. Existing metrics, pair metrics, diagnostic files, UNBLINDED, root marker, or transaction STARTED reject the run. Then an exclusive STARTED transaction is created, all four root markers bind their actual prediction seals to the precommitted label hashes, and all four authorized label joins are checked before the first scorer. Each immutable scorer is called once, followed by its descriptive diagnostics. Extension control is attached only to independent240. Report refresh runs last.

Failure after STARTED preserves artifacts and writes FAILED_MANUAL_RECOVERY_REQUIRED. No automatic resume/retry is supported, including missing artifacts or scorer errors. A root-authored manual recovery procedure must inspect what completed before acting; deleting a marker or changing the plan is not a supported automatic retry.

Known raw64 label export copies original authored `expected_block.base` only, with original source hash and reason. It labels static intervention requirements and does not claim observed harm, new independent validation, or infer labels from guard predictions. Hidden240 labels remain unread in preparation.
