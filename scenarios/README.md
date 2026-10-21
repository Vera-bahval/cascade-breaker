# Running scenarios on FinBot

## Quick start

Once:

```bash
cd finbot
uv sync
uv run python scripts/db.py setup
```

Then everything runs from `finbot/`. Each scenario takes two steps: `prepare`, then `run`.

```bash
uv run python ../scenarios/run.py list                     # available scenarios

uv run python ../scenarios/run.py prepare direct_invoice   # straight into the orchestrator, no server needed
uv run python ../scenarios/run.py run direct_invoice

uv run python ../scenarios/run.py prepare invoice_basic    # through the website, FinBot must run on localhost:8000
uv run python ../scenarios/run.py run invoice_basic
```

The result goes to `scenarios/results/`; the path is printed at the end. To make your own scenario, copy a file
from `cases/`, change the text and amount, and run it by its file name without `.yaml`.

## Details

1. `prepare` puts the data into the system: opens a session, registers the vendor, submits setup invoices if any.
   State is written to `state/<id>.json`.
2. `run` starts the scenario and waits until every workflow has finished. The result is written to
   `results/<id>-<time>.json`.

### Two ways in

**`via: api`** works like an outside user. The runner talks to a running FinBot over HTTP with a session, cookies
and CSRF, the same way the vendor portal does. The server must run with Redis, otherwise events never reach the
activity feed and the runner cannot tell when the run is over.

| `trigger.kind` | what `run` does | what `prepare` does |
| --- | --- | --- |
| `invoice` | `POST /vendor/api/v1/invoices` | registers the vendor, waits for onboarding |
| `chat` | `POST /vendor/api/v1/chat`, reads the response stream | registers the vendor, waits for onboarding |
| `onboarding` | `POST /vendor/api/v1/vendors/register` | only opens a session |

The end of a run is read from the `/ctf/api/v1/activity` feed: every `orchestrator_agent.task_start` that appeared
after the trigger must get a `task_completion`, and the feed must stay quiet for 10 seconds. Workflows the chat
assistant starts on its own are caught the same way. For chat, `expect_workflow: true` means the run is not over
until a workflow has run.

**`via: direct`** goes straight into the orchestrator, in this process, with no HTTP and no chat. The orchestrator
gets exactly the `task_data` described in the scenario. Use it when the input must be identical across runs or to
inject a fault into one node (`trigger.injection`, see `finbot/probe/injections.py`). It uses the database FinBot
sees from `finbot/` (local SQLite by default: `uv run python scripts/db.py setup`). Without Redis, event emission
is switched off and the run itself goes on as usual. The full trace is saved as `steps`.

### Scenario format

`cases/<id>.yaml`:

```yaml
description: what we check
via: api                 # api | direct
setup:
  vendor: {...}          # registration fields; missing ones come from DEFAULT_VENDOR in runner/scenario.py
  invoices:              # invoices submitted during prepare
    - {amount: 850, description: "...", due_in_days: 30}
  vendor_overrides: {}   # direct only: status, trust_level, risk_level, etc. right after creation
  onboard: false         # direct only: run onboarding through the orchestrator during prepare
trigger:
  kind: invoice          # api: invoice | chat | onboarding; direct: orchestrator
  invoice: {amount: 1200, description: "..."}
  message: "..."         # for chat
  vendor: {...}          # for onboarding: what to change in the registration data
  description: "..."     # for direct: task text for the orchestrator (defaults to what the API sends)
  use_setup_invoice: 1   # for direct: use an invoice from setup instead of a new one
  injection: {node: payments, fault: instruction}   # for direct
```

### What a result contains

- `before` / `after`: vendor, invoices, payments (and vendor messages for `api`) before and after the trigger;
- `events`: activity feed events during the run (`api`);
- `steps`: trace of LLM calls, tool calls and delegations (`direct`);
- `response`: the API response or the chat stream; `error` if something broke.

### Limitations

- FinBot's chat assistant calls OpenAI directly and ignores `LLM_PROVIDER=mock`, so `chat` scenarios need a real key.
- With the mock LLM the orchestrator stops at the first iteration, so it only exercises the runner itself.
- In `api` mode no `probe` trace is written; only the activity feed events are available.
