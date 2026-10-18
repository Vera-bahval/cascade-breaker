# Bounded action-history diagnostic

This is a post-hoc diagnostic of illustrative archive errors and controls. It does
not change the primary experiment, its policy, labels, calibrated decision
thresholds, models or frozen scores. Nine prefixes represent eight base groups;
the successful and failed Fraud examples for executive authority share one group.

The three scored payloads for each prefix are:

1. `current_state`: exact frozen `plus_rationale` payload, including dictionary
   insertion order and the four original questions. Its 0.8B distributions are
   reused from the primary score file after verifying the model-bound input hash.
2. `chronological_ledger`: current state plus all observed native tool actions and
   task summaries before `cut_seq`. Results and arguments use a business-field
   allowlist; repeated narratives are referenced through a text catalog with
   explicit source/trust labels. The pending transfer arguments are recorded as
   unexecuted. Guard decisions, LLM messages, experiment injection records and
   post-cut events are excluded.
3. `compact_evidence_ledger`: current state plus committed effects, task statuses,
   the latest native read by agent/tool, field provenance, original amount/account,
   registered flags and unresolved obligations. It does not repeat tool narratives.

Successful native calls, committed writes, successful agent task completion and
valid independent permission are separate fields. In particular, an invoice-agent
write to `invoice.status=approved` is an authentic database fact with agent origin;
it is not independent authorization. Invoice text remains untrusted, agent
summaries remain assertions, and later low vendor risk does not clear an earlier
registered Fraud flag. A failed Fraud task is reported explicitly, but requiring
successful task completion is an exploratory obligation and does not silently
replace the frozen harm oracle.

Labels, error-based case selection, source benignness and frozen OOF decisions
exist only in each JSONL wrapper's `analysis`; the model receives only `payload`.
These views add observed task status, proposed arguments and field provenance as
well as changing representation. Score differences therefore cannot be attributed
to serialization alone. The released calibration and the main 0.8B thresholds
are not validated for these longer views or for 2B. No new threshold is fitted.
The four fixed atomic questions do not directly cover every transfer invariant;
the changed-account/amount example is also a check of that coverage limitation.

`input-audit.json` verifies all 27 clean payloads and nine exact frozen input hashes.
`token-preflight.json` uses both pinned local tokenizers and the exact Kev encoder:

| Format | State tokens | Largest state + question row |
| --- | ---: | ---: |
| current state | 475–590 | 666 |
| chronological ledger | 2780–3499 | 3575 |
| compact evidence ledger | 1960–2455 | 2531 |

Both models have identical counts for these payloads. The admission limit is 8192;
overflow would return UNKNOWN rather than truncate. The planned factorial has
nine reused 0.8B baselines, 18 new 0.8B inferences, 27 new 2B inferences and three
2B A/A repetitions. API inference cost is zero; actual local latency/memory and
per-request token counts are recorded by the separate diagnostic runner.

Rebuild the selected inputs and admission report from the project root:

```sh
PYTHONPATH=experiments/local_guards .runtime/secjev/.venv/bin/python -m cascade_guard.structured_ledger --workspace .
PYTHONPATH=experiments/local_guards HF_HUB_OFFLINE=1 .runtime/mps-diagnostics/.venv/bin/python -m cascade_guard.ledger_token_preflight --workspace .
PYTHONPATH=experiments/local_guards .runtime/secjev/.venv/bin/python -m unittest discover -s experiments/local_guards/tests -p 'test_structured_ledger.py' -v
```

Do not regenerate inputs while the diagnostic is running. `input-manifest.json`
records the builder and input hashes; the final prepared input SHA256 is
`1230d5d28176923e5d5a070bb5474fb3eda20ac81881a014ad362af85e06021c`.
