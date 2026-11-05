# API cascade scenarios (MAST)

64 scenario files, one per variant (`S01_n.json`, `S01_p.json`, ...), covering 32 negative/positive pairs across all 14
MAST failure modes ([arXiv 2503.13657](https://arxiv.org/abs/2503.13657)). They run `via: api`, exercising the chat
assistant, onboarding and the vendor portal rather than calling the orchestrator directly.

- Prose catalogue and rationale: [`docs/scenarios/api-mast-scenarios.md`](../../docs/scenarios/api-mast-scenarios.md).
- Field schema: [`docs/scenarios/schema.md`](../../docs/scenarios/schema.md).

Each file is checked against [`scenarios/schema.json`](../schema.json) before a batch runs. Run them with
`run.py mast`, or as part of the unified set with `run.py unified`.
