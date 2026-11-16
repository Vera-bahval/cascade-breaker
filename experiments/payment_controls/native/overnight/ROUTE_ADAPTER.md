# Opt-in live pre-Fraud adapter

`live.py` wraps the actual `OrchestratorAgent.delegate_to_fraud` for one isolated process; no default FinBot module is edited. Four distinct arm IDs are `overnight-off-v1`, `overnight-rules-v1`, `overnight-model-v1`, `overnight-hybrid-v1`. Each attempt collects the same native inputs before any routing choice, including OFF, then writes private `route-packets.jsonl` as `{owner, packet}` and `route-decisions.jsonl` separately. Local raw packets contain synthetic banking/contact information; do not publish them. `provider.choose` must sanitize the packet before every network request.

Example launch, only when paid execution is authorized:

```
PYTHONPATH=finbot:scenarios:. finbot/.venv/bin/python -m experiments.payment_controls.native.overnight.live --channel direct --arm overnight-off-v1 --case CASE_ID --fixtures /absolute/path/fixtures.json
```

Fixtures follow `study.live`: a JSON array with unique `id`, `profile` and `invoice`. The executor uses the existing `study-live/executor.sqlite` cap 4.8 USD and metadata preflight in `live_smoke`; model/hybrid use provider's Jev ledger and 0.20 USD cap. Never infer successful completion from routing alone: check recorded Fraud outcome, invoice/transfer receipt, required note, notification and full workflow. The standard runner rejects nonempty destinations rather than retrying them. Reconcile a failed or uncertain reservation and charged requests before any new owner/run.

`DEFER`, input failure, and provider failure use the real saved delegate, with its normal attempt limit. `CLOSE_ALLOW` is subject to the fixed `MANDATORY_VETO` set in `route.py`, plus a nonpositive, nonfinite or above-50,000 amount and any paid/transaction state. A model may resolve a contextual DEFER such as amount variance or sparse comparable history when no mandatory veto applies. Raw model decisions and applied routing must be reported separately. The adapter records a source-labelled vendor note and emits `pre_fraud_router` context, never a fabricated `fraud_agent` summary. This may affect native guards that require a Fraud summary and must be counted as an outcome. `CLOSE_STOP` currently falls back to actual Fraud: safe completion and mandatory notification are not guaranteed by this adapter. This limitation applies even to a verified already-paid invoice.

The structured native baseline is a separate comparison: add `--structured` **only** to `overnight-off-v1`. It appends four requested fields to the ordinary Fraud prompt and uses the same native agent; it is neither a translator nor a schema guarantee. Its `structured-v1` outputs must stay separate from the main arms.

`native_reads` is a structured snapshot policy, not a document reader. Attachments or vendor notes force DEFER; it does not establish that unstructured invoice text lacks conditions or that an independently verified bank-change registry exists. Those are observability limitations, not evidence of absence. Caller task context must identify a single invoice and matching vendor; if the packet cannot be collected, routing falls back and records the reason. Tests use local mocks only: `PYTHONPATH=finbot:scenarios:. finbot/.venv/bin/python -m unittest experiments.payment_controls.native.overnight.test_route -v`.

The primary comparison uses the first pre-Fraud invocation. Further invocations fall back to native Fraud. The shared provider projection preserves the first task and the vendor record, removes historical invoice commentary and redacts routing identifiers and synthetic account values equally for both models. Raw packets remain local.
