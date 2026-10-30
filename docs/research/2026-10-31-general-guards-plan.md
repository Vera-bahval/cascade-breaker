# Обобщаемые проверки FinBot без LLM

Approved research plan, 2026-10-31. New inference API requests: **zero**.

## Binding requirements

Maximize detection at a CAL episode safe-stop FPR target of 5%; report infeasibility. Preserve old experiments. Freeze policy, schemas, models and thresholds before closed-test creation/reveal. No role/attack phrase lists, case identifiers, outcomes, executor or family identifiers in new guard features. Missing mandatory evidence prevents automatic ALLOW. Keep scenario intent, proposed-action correctness and observed continuation harm separate. Archived STOP is counterfactual. API-free enforcement replay is integration evidence.

## Tasks and ownership

1. Custodian: versioned policy/schema; prefix-only extraction; old/new overlap registry; grouped TRAIN/CAL/TEST, Luna held out; TRAIN-only developer package; independent action/outcome gold. Whole new-family holdout 20% when available; remaining group split 75/25 seed 17. Old archive/raw64/hidden240 are development evidence.
2. Fresh rules developer: typed policy obligations and provenance gate, ALLOW/BLOCK/UNKNOWN, no old rules or test access. Fresh ML developer: structured LR C=1; CatBoost 200/depth3/lr.03/L2=5; char TF-IDF LR diagnostic; seeds17/29/43. Train preprocessing in TRAIN only; fit once, CAL thresholds, no post-CAL refit.
3. Evaluation: frozen legacy controls; P4 vs staged P2b/P3/P4; whole-episode thresholds; two-threshold router; exact-context saved LLM comparison only; source hashes and resume verification. Report paired coverage and unavailable evidence, not fabricated results.
4. Independent generator after method freeze: policy-only 8 families x20 safe/unsafe pairs, 320 cases; independent gold/overlap review. Freeze predictions before reveal; no method tuning afterward.
5. Verification/report: integrity, invariance, missing/corrupt evidence, contemporaneous side-effect gate, no execution after STOP, idempotency; grouped intervals, latency p50/p95, cold start, memory, API cost0. Short Russian report, machine-readable artifacts, committed research branch and one independent final audit.

## Interfaces

Custodian owns policy.json, schema.json, prepare_data.py, data/, train-package/. Developers consume only explicitly allowed package files. Evaluator owns metadata and gold. New guard consumes observation + policy and returns decision, scores, reason codes, evidence references and elapsed time. Final database is outcome evidence only. Full filesystem is shared; instruction/context isolation is procedural and audited.

## Selection

Choose the primary method on CAL, maximal action-intervention recall at <=5% whole-episode safe-stop FPR; ties by simplicity and measured runtime. Seeds29/43 are sensitivity checks, not extra independent episodes. Router maximizes autonomous coverage with zero observed CAL intervention-positive auto-ALLOW and <=5% safe auto-BLOCK; unresolved mandatory evidence stays UNKNOWN. Final safe-stop target includes UNKNOWN.

## Rulings

- Native worktree tool rejects nested sourceRoot in this workspace; use Git worktree fallback at research/finbot-general-guards. Existing branches remain pinned.
- Historical FinBot and current main are distinct source versions. Preserve provenance and do not silently apply new policy labels to old metrics.
- No genuinely unseen archival families or exact saved fallback context means that comparison is unavailable; the independent synthetic contract test remains explicitly synthetic.
