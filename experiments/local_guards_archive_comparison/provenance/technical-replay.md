# Offline technical registry execution receipt

The separately added `technical_replay.py` executed one complete offline registry replay after CPU-clear. Every episode used its own real in-memory SQLite database, which was closed after a deterministic logical receipt. No database files, raw copies, executor reruns, new predictions or model-quality adjustments were produced. Frozen collector, canonical data, views and methods were not modified.

The server actually admitted 3,378 independent episode identities, registered 173,045 observed prefix/proposal events and 42,841 calls, and retained 159,647 latest native observation field-hash slots. The latter count is a state-store size, not a count of distinct mutations, approvals or payments. Native content was stored only as source-linked hashes after paired observed returns; the replay created no business authorization, human receipt, financial fact, clearance, HOLD lock or historical version identifier. Source event sequence controls the order. A recorded batch is a proposal set; actual response order controls updates. P4 registrations remain proposals with no invented future transfer result.

For 5,404 cuts the replay independently rederived the frozen `context.call_id`, `context.parent_workflow_id` and `context.source_binding`, then inserted and read back all three fields through SQLite: 16,212 registered technical links. Six unpaired legacy returns remain UNKNOWN, with their 18 fields not claimed backed. There were zero value/provenance discrepancies and zero repairs to frozen inputs. SQLite foreign keys enforce admission/call/link targets, and per-episode database isolation prevents cross-episode parent references in this execution. This is no claim about concurrency, production locks or historical authentication.

Two support tiers remain explicit. For 4,841 cuts the declared admission source is the literal first retained raw source anchor. Another 563 legacy cuts use a previously frozen declared local admission alias (for example an additional `#L1` after a JSONL line pointer); their actual first source anchor was recorded separately in SQLite. Their local task/call values are backed by actual local registry records, but the alias is not a literal historical admission receipt. None of these local IDs establish historical authority. Forty-three episodes have no retained P2/P4 prefix: they received identity-only local admissions, without invented source events or checkpoint claims.

All three replay inputs and the replay/test sources were hashed before and after execution and remained unchanged. The inventory loader extracts episode identity only; scenario labels and outcomes are not parsed or used. No selected gold, predictions or outcome files were loaded. Every technical decision here concerns source linkage, never a guard answer or action quality.

Five small tests pass: actual SQLite admission/call/native-observation registration and readback; unresolved return handling; tampered frozen ID detection without repair; rejection of future events with independent admission identities; and sequential P2-to-P4 proposal registration without a future payment result.

The full counters, six unresolved cuts, input hashes and 3,378 per-episode logical hashes are in `technical-replay.json`. The aggregate logical registry SHA-256 is:

`f38c7d73045603d9760257db0a648e4d45c54b6fbdd6cee68b2f679bea09b395`

Executed from the worktree root:

```sh
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python -m unittest discover -s experiments/local_guards_archive_comparison/tests -p test_technical_replay.py
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_archive_comparison/technical_replay.py
```

This receipt makes the local registry execution concrete. It does not improve native evidence quality or change any previously frozen prediction input by construction.
