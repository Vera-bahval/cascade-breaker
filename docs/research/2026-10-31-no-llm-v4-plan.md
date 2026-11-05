# No-LLM FinBot v4 implementation plan

Approved specification: user's 2026-10-31 five-section plan in this session.
Goal: deterministic controls at P0/P1/P2/P3/P4 with original-policy and expanded-policy results separated, no UX/public API changes, no new inference API requests.

## Global constraints

- Baseline HEAD 750e2de; preserve every v3 byte except no edits are expected there. origin/main dd3983c and four-model branch 924e64b verified by fetch.
- Existing linked research worktree is isolated and reused; no merge, production or publication.
- BLOCK and UNKNOWN cause STOP before effect; STOP prevents later tools/model calls.
- Baseline P4 and fitted models remain immutable. No model training. No future-state facts, case/attack phrase rules, titles or invented trust thresholds.
- A implements evidenced existing obligations; B separately adds approval freshness, active workflow deduplication and vendor SystemUtils restriction. Conflicts remain explicit.
- All existing data and API-MAST are open/development data. Fresh policy-only author makes 400 paired cases only after method/configuration freeze; predictions before gold reveal.
- Grouped TRAIN/CAL 75/25 seed17, no Luna fit/CAL. Target whole-episode safe-stop FPR <=5% includes UNKNOWN. Archive counterfactual, synthetic and runtime claims stay separate.
- Scope technical agent permissions and typed effects; no semantic interpretation of free-text requests or subjective trust business decisions.

## Task 1: contract and interface

- [ ] Create local_guards_v4 policy registry, schema, source references and isolation package. Resolve source conflicts explicitly. Freeze before rules developer.
- [ ] Review contract for compatibility, provenance and native tool semantics.

## Task 2: general guard and isolated state

- [ ] Fresh allowlisted developer implements stdlib guard, typed provenance, A/B modules and SQLite evidence/claim store, with focused tests. No archive/test-result reads.
- [ ] Review implementation and address important defects before integration.

## Task 3: integration, data and evaluation

- [ ] Opt-in execution profile intercepts chat/workflow/native/MCP, persists scoped evidence/claims, fails closed and propagates STOP. Default off.
- [ ] Custodian inventory/extraction and independent action/outcome labeling, splits, configured comparisons, CAL selection, saved-only compatible ML controls; source freeze.
- [ ] API-free native scripted integration, identity/text invariance, full-check latency/memory.
- [ ] Independent task review and correction before global freeze.

## Task 4: sealed evaluation and report

- [ ] New policy/schema-only author generates 10 x20 pairs=400; separate reviewer checks gold/overlap; save predictions before opening gold.
- [ ] Score frozen methods; source harm, contract harm, benign interruptions, reached denominators, grouped intervals and per-family results.
- [ ] Russian concise report and technical reproduction appendix, API-MAST48 coverage, interpreted success/failure/UNKNOWN chains and limitations.
- [ ] Independent whole-branch audit, final verification, hashed artifacts and research commits.

## Rulings

- The specification is the approved conversation plan; this file is its recovery checklist. Task briefs carry detailed interfaces after contract review.
- Context/read allowlists are procedural, not OS isolation. Implementation workers do not spawn agents or commit shared changes; controller commits reviewed task boundaries.
- Original method selection cannot use newly exposed closed labels. Negative or infeasible outcomes are valid; missing evidence cannot be relabeled as safe.
