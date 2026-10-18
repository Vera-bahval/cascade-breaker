# Manual scoring recovery 05

This addendum authorizes only the frozen scorer's JSONL path type adapter. No scientific method, weights, fitted classifiers, thresholds, predictions, labels, frozen sources, diagnostic contracts or report implementation may change. The original method freeze and original authorization plan remain authoritative.

Original one-shot completion stopped before any metrics were written: the frozen evaluator passes the JSON string `rows_file.path` into `dataset.read_jsonl`, which calls `path.open`. The pinned transcribed exception/source excerpt is supplemental root evidence, explicitly not a byte-for-byte complete execution log. The public synthetic end-to-end test independently reproduces the exact AttributeError using the unmodified real scorer, then obtains metrics, paired metrics and UNBLINDED with only the Path adapter.

The new protocol pins this runner, its public tests, this protocol text, original STARTED/FAILED receipts, and the supplemental excerpt. The root launcher must independently pin the JSON recovery protocol SHA and pass it on the command line. The original authorization plan SHA is hard-coded. Original authorization()/deadline()/source checks are reused; original complete() is never called. The deadline remains 2026-10-15T22:59:58.072112+00:00 and is enforced in the scorer process and diagnostic child processes. No automatic retry or deadline extension is allowed.

`--check` verifies authorization, exact prior failure state, frozen source/model/prediction hashes, and all four existing ROOT_UNBLIND commitments. It never opens label files or runs label joins or scorers. `--execute` is reserved for the root launcher: all four original preunblind label-join/pair validations run before any scorer. Then the same frozen `run_score` runs four times with a process-local `read_jsonl(path)` binding delegating to frozen `dataset.read_jsonl(Path(path))`; the original binding is restored in finally. The same external diagnostics CLI, independent control arguments and original report run afterward.

Sources, classifiers, sealed predictions, inputs, original STARTED/FAILED and root markers are hashed before and after. A mismatch fails manual recovery. Success records MANUAL_RECOVERY_RECEIPT.json and COMPLETE.json with recovery provenance and hashes; failure records MANUAL_RECOVERY_FAILED.json and preserves all existing evidence. Any partial output or prior manual start/failure blocks another attempt.

Public checks (no actual labels, model fits, inference or API access):

```
PYTHONPATH=experiments/local_guards experiments/local_guards/.venv-finbot/bin/python -m pytest -q experiments/local_guards/tests/test_v2_scoring_recovery.py
```

Root-only CLI:

```
experiments/local_guards/.venv-finbot/bin/python experiments/local_guards/scripts/recover_guard_v2_scoring_05.py --authorization-plan experiments/local_guards/results/guard-v2/ROOT_AUTHORIZATION_PLAN_05.json --recovery-protocol experiments/local_guards/results/guard-v2/SCORING_RECOVERY_PROTOCOL_05.json --recovery-protocol-sha256 ROOT_REVIEWED_SHA --check
```

Replace `--check` with `--execute` only in the explicitly root-authorized launcher after source review. This file and the JSON protocol do not extend the deadline or authorize an agent's actual scoring run.
