# API cascade scenarios (MAST)

48 scenario files, one per variant (`S01_n.yaml`, `S01_p.yaml`, ...), covering 24 negative/positive pairs across all 14
MAST failure modes ([arXiv 2503.13657](https://arxiv.org/abs/2503.13657)). They run `via: api`, exercising the chat
assistant, onboarding and the vendor portal rather than calling the orchestrator directly.

- Prose catalogue and rationale: [`docs/scenarios/api-mast-scenarios.md`](../../docs/scenarios/api-mast-scenarios.md).
- Field schema: [`docs/scenarios/schema.md`](../../docs/scenarios/schema.md).

These files extend the runner's current scenario format (chat history, attachments, portal edits, preconditions, an
explicit oracle). The existing runner does not execute the new fields yet; running them is a later PR.
