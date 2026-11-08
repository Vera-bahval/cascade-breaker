# General guard developer report

Implemented a stdlib-only `guard(observation, policy=None)` and
`required_missing(observation, policy=None)`. No structural feature function was
added; the independent ML implementation does not need coupling to this guard.

The method uses typed, attributed facts only. Accepted provenance requires a
recognized source, exact current-subject match and an integer sequence strictly
before the observation cut. Human approval and human hold clearance require
`independent_registry` evidence and remain separate obligations. Currency uses
case/whitespace normalization. Payment amounts use finite Decimal values from
strings; booleans and non-finite or invalid strings cannot authorize payment.
Whitespace-only proposed currency is missing proof rather than a proven currency
violation. For each fact the latest valid scoped provenance is selected. An
independent clearance is usable only strictly after the latest binding HOLD;
stale clearance cannot release a newly observed hold.

P0/P1 and other early actions return provisional ALLOW when well formed. P2's
completed Fraud boundary blocks an established unresolved hold. P3 approval
blocks its known hold/amount/vendor violations. Full P4 requires the recognized
`finstripe__create_transfer` boundary and the frozen payment obligations. Known
violations block despite unrelated absent/null evidence; unavailable mandatory
proof otherwise returns UNKNOWN. The shared mandatory-proof gate requires
positive independent authorization above the automatic limit, including when
explicit denial is observed, and positive current clearance at applicable
P2 Fraud/P3 approval/P4 hold stages. A BLOCK still takes precedence over these
unavailable positive proofs. Present non-null malformed typed values return
UNKNOWN at every stage. P5 returns UNKNOWN with a detection-only reason and is
not a prevention claim. `required_missing` returns unavailable/invalid proof
names, not known-violation reasons; P5 has no missing pre-action proof list.

## Verification and submitted method hashes

Final verification: **109 passed in 0.05s**, exit 0, with this isolated command:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv/bin/python -m pytest -q -c /dev/null -p no:cacheprovider --confcutdir=experiments/local_guards_v3/tests experiments/local_guards_v3/tests/test_rules_v3.py
```

Tests were written first from the frozen policy. The first run failed because
the new implementation did not exist; the UNKNOWN skeleton then produced the
expected ALLOW assertion failure. Subsequent regressions were observed failing
before their fixes: six failures for P2/P5/malformed container handling, nine for
present malformed fields at early stages, and six for pre-freeze root-review
corrections (P0, native USD casing and the actual P4 transfer boundary). Final
independent review produced six failing regressions for unavailable positive
authorization/clearance and stale/latest clearance, followed by one failing
regression for whitespace-only proposed currency. Each was fixed before the
final 109-test verification.

Tests cover trusted and invalid provenance, missing proof, obligation violations,
amount limits and malformed values, independent authorization/clearance, stage
applicability, known violations with unrelated null evidence, and no-read traps
for raw text, identifiers and outcome fields. No archive-derived examples or
train records were used. No other suite was run because the explicit source-read
boundary excludes other code and tests. No inference API, subagent, git history,
commit or network operation was used.

Submitted SHA-256 (global freeze remains controlled by root):

- `rules_v3.py`: `279a3b8bfc37f4244e67696eba0150c84ed71d67a0f6b527dc32279c002bf38b`
- `tests/test_rules_v3.py`: `01a8b8c19f88d4c921c82f90789601f733a75b129ec3aceba27bb0b408ba5680`
- `policy.json`: `bdaaffe0715d7b7233cc40e1ce7f6ada7989bac927269998aa5827d385f65c85`
- Current root-approved `schema.json`: `62efd6d8ec3b1dced204d3705c9c2691b7e9af1d503c4327ce388e1e6be84711`

The schema read at task start had approved SHA
`215506a77682b69645e0c50c9c9f2b7aa6e32739d2b07117a5cab5d4ede2fa2f`.
A later hash check detected a shared-filesystem amendment. Root explicitly
approved the current schema hash before method freeze and supplied the
boundary clarification; its amended contents were not reread. Policy hash
remained unchanged. Root review corrections above were applied before freeze.

## Complete task-source read allowlist

Research sources read (paths relative to this worktree):

- `experiments/local_guards_v3/policy.json`
- `experiments/local_guards_v3/schema.json` (initial approved contents only;
  current version hashed only)
- `experiments/local_guards_v3/POLICY.md`
- `experiments/local_guards_v3/rules_v3.py` (own source, including test imports)
- `experiments/local_guards_v3/tests/test_rules_v3.py` (own test source)
- `experiments/local_guards_v3/rules-developer-report.md` (own report, revised after review)

Installed skill sources read:

- `/Users/proskurin-dmi/.codex-igaming/plugins/cache/openai-curated-remote/superpowers/7.0.1/skills/test-driven-development/SKILL.md`
- `/Users/proskurin-dmi/.codex-igaming/plugins/cache/openai-curated-remote/superpowers/7.0.1/skills/test-driven-development/writing-good-tests.md`
- `/Users/proskurin-dmi/.codex-igaming/plugins/cache/openai-curated-remote/superpowers/7.0.1/skills/verification-before-completion/SKILL.md`
- `/Users/proskurin-dmi/.codex-igaming/plugins/cache/openai-curated-remote/superpowers/7.0.1/skills/receiving-code-review/SKILL.md`

This list excludes ordinary installed interpreter/stdlib/pytest runtime loading.
No train-package file, old rule, repository history, data source, custodian
source/report/test, other model/evaluation source, comparison, case or other
agent's test output was read. Only the three owned deliverables were authored.
