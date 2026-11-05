# Independent closed test custody review

Worktree /Users/proskurin-dmi/Documents/hw-itmo/cascades/research/finbot-general-guards.
Fresh context: audit all 400 newly authored contract cases BEFORE target predictions and gold release. No inference APIs, no subagents, no Git mutation. Do not run/import the guard, evaluator, runtime, old rules or old test code. Do not read predictions/results.

Read allowlist:
- this brief;
- experiments/local_guards_v4/POLICY.md, policy.json, schema.json;
- experiments/local_guards_v4/make_closed_test.py;
- experiments/local_guards_v4/closed/*;
- experiments/local_guards_v4/closed-author-report.md, closed-author-read-log.jsonl;
- experiments/local_guards_v4/data/observations.jsonl.gz and train-package/observations.jsonl.gz (overlap comparison ONLY, not method inspection);
- experiments/local_guards_v3/closed-test/observations.jsonl and data/observations.jsonl (overlap comparison ONLY).

Write only closed_review.py, closed-review-report.md, closed-review.json and closed-review-read-log.jsonl under experiments/local_guards_v4/. No changes to author package; report any fixes to controller, who will route to original author. Supplied interpreter with jsonschema4.26.0: /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python. Stdlib and jsonschema only; log explicit reads/imports.

Check source hashes against contract, deterministic package joins, exactly ten prescribed families x20 safe/unsafe pairs, one prefix per episode, opaque observation IDs/no class/title/gold leakage, trusted fixture producer/proof consistency, time/source/scope/material version semantics, all twelve requirement labels and aggregate targets. Adjudicate from contract independently, never by calling target method. Safe means A+B compliant; missing evidence is UNKNOWN, verified violation BLOCK. Check A03 actor/tool matrix, A04 successful linkage, A05 current canonical status/reapproval, A07 exact transfer then bookkeeping, A08 payment obligations and A09 legacy cut applicability. Deliberate malformed-envelope cases should be labelled by explicit validator semantics rather than pretend parsed scalar types are trusted. Inspect every case, not just generator comments.

Audit author reads and timing. Determine exact and normalized overlaps within400 and with the allowed old observation packages. Normalization should remove arbitrary identity spelling while preserving equality classes, fact values, proof source/order, tool/actor and applicability. Report unique normalized views and distinguish unavoidable common contract states from identical prior cases. This is a fresh synthetic contract test over known mechanism families; it is NOT new real attacks or new semantic families.

Report spec compliance PASS/FAIL and data-quality PASS/FAIL, concrete required fixes with IDs/contract rationale, counts, overlap denominators, limits and source hashes. Do not read any outputs created later by controller. Return concise status/counts and paths only; report carries details. No need rerun author generator unless its determinism/schema claim is in doubt; independently checking payloads is required.
