# cascade-breaker

Research on where and how to place consistency checks so that cascading errors in a multi-agent LLM system are cut
off at acceptable latency and false positive rate. The test bed is FinBot (OWASP FinBot CTF).

This is research code, not a product.

| Path | What |
| --- | --- |
| `finbot/` | FinBot code: upstream [GenAI-Security-Project/finbot-ctf](https://github.com/GenAI-Security-Project/finbot-ctf) plus our changes |
| `scenarios/` | scenario runner: through the API, chat and onboarding, or straight into the orchestrator |
| [Four-model FinBot comparison](experiments/control-placement/four-model-comparison/REPORT.md) | GPT-4o mini, GPT-5 nano, DeepSeek Flash and GPT-6 Luna High: matched outcomes, guard checks, latency, costs and reproducible evidence |
| [Original control-placement research](experiments/control-placement/experiments.md) | Anastasia's method, analysis, code and archived runs from `research/control-placement` |

Getting started:

```bash
git clone https://github.com/Vera-bahval/cascade-breaker.git
cd cascade-breaker/finbot
uv sync
uv run python scripts/db.py setup
```

Then follow `scenarios/README.md`.

## FinBot inside this repository

`finbot/` is a `git subtree` of upstream FinBot, imported at `1450fc4`. It works like a fork: the code is ordinary
files in this repository, our changes are ordinary commits, and upstream changes are merged in from time to time.

Our FinBot changes (see `git log -- finbot/`):

| What | Where |
| --- | --- |
| OpenRouter: `OPENAI_BASE_URL`, provider pinning, `seed`; usage and cost in LLM metadata | `finbot/finbot/core/llm/` |
| spend ledger with stop conditions; role to model config | `finbot/finbot/probe/ledger.py`, `roles.py` |
| `agent_name` in the guardrail hook envelope | `finbot/finbot/guardrails/` |
| full run trace, control points P0–P5, `off` / `shadow` / `enforce` modes | `finbot/finbot/probe/trace.py`, `guards/` |
| fault injection and delegation tracing in `OrchestratorAgent` | `finbot/finbot/probe/injections.py`, `agents/orchestrator.py` |
| verifiers V1–V5, MAST annotator | `finbot/finbot/probe/guards/` |
| smoke test, V3 recheck, HTML trace viewer | `finbot/scripts/probe/` |

With no flags set FinBot behaves like upstream. `tests/unit/probe` passes with `LLM_PROVIDER=mock`.

To pull new upstream code (once per clone, add the remote first):

```bash
git remote add finbot-upstream https://github.com/GenAI-Security-Project/finbot-ctf.git
git subtree pull --prefix finbot finbot-upstream main --squash
```

This creates a merge commit; conflicts with our changes are resolved like in any merge.
