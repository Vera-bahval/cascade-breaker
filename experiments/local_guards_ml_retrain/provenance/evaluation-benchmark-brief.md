# Task 4: post-freeze evaluation and performance appendix (release later)

Implement only new experiment files, not any frozen method helper/code/model/
threshold or prior artifact/main report. No subagents/commits/API calls. Native
Python has all packages. Read PLAN and frozen manifest; use model inference APIs
provided by Task2 without changing them. Prior v4 latency/native fixtures may be
read as exposed development fixtures. New gold only AFTER receipt/release.

Evaluate72 models×raw/gated separately, contracts payment_v3/A/B, seed17 main,
29/43 sensitivity without choosing best test seed. Rule controls frozen v3 and
v4A/B receive same observations/producer enrichment; TFIDF unchanged diagnostic
only, preserve text-unavailable UNKNOWN. Old320 payment-only and400 multisite
are open diagnostics, not train or closed novel data. Archive full compatible
registry: respect missing/state/source versions and existing split, not outcomes
as features. Predict all eligible observations before loading outcome labels.

Metrics per contract/source/checkpoint/family: count/all eligible, decisive,
correct decisive/all, full3way confusion, falseALLOW vs both BLOCK andUNKNOWN,
known BLOCK stopped (BLOCK andUNKNOWN separate), false safe STOP includingUNKNOWN,
UNKNOWN, gate-changed decisions and standalone contribution, CAL infeasibility.
Episode metrics replay to firstSTOP; no later-action credit. Archive actual harm
' stopped would ' versus attempts/completions and legitimate-task interruption,
reached+all denominators, missing outcomes unknown; source intent not actiongold.
Intervals bootstrap1000 seed17 by original archive base groups or synthetic
split_group_id/collision components; descriptive only, not task-population CI.
If modelCAL infeasible, retain abstention fallback and show unconstrained
argmax diagnostic separately; don't call allSTOP high recall improvement.

Native benchmark through actual FinBot chat/child/tool paths, scripted client,
isolatedDBs, no external sockets. Common adapter source/state collection same
for rule/ML controls. Measure full Runtime.check including reads/writes and
whole chain separately; classifier feature/proba, proof gate, load andRSS cost
separate. Each72 model and both raw/gated modes, plus off/rule controls,5repeats
randomized order; raw mode diagnostic only on isolated fixtures. Payment/control
contract head only applies its own cuts. Record payments/status/modelstub calls,
checks and stop reasons; successful versus stopped chain times separate.
Existing native Runtime.shared-owner parent ID is empty. If enriched for valid
producer proof, derive explicit parent from real _INVOKING/parent agent workflow
context for BOTH rules and ML, disclose new benchmark adapter and retain at
least a baseline old-observation diagnostic. Never manufacture human permission.
Declared test USD ledger/initial noHOLD okay only with explicit fixture contract;
fraud review in positive chain must be produced by actual native reads/completion.

Single-call latency per model: deterministic stratified sample of up to128
new-test states per contract ×5 passes, individual inference (no batch-amortized
latency), raw and gate cost separated. Eligibility/no-check not folded into
applicable latency. Full native check includes shared adapter cost even if
method applies only atP4; no claim optimal integration comparison.
Load/startup/RSS: fresh worker per model, verify pickle hash, load and first
applicable response. Record first-response availability separately from process
teardown (parent pipe/timestamp), warm filesystem caveat;1sample/model is not
stable tail estimate. Avoid conflating RSS Python/dependencies with model size.

Write raw gzip timing/predictions JSONL, metrics JSON/CSV, hashes and reproduction
commands plus concise Russian REPORT.md appendix emphasizing feature×data ablation
and CAL feasibility. What changed forML; does correct coverage improve relative
to rules; mistakes and gate contribution; local full-chain cost; unresolved
realLLM adaptive/latency/cost claims. Main experiments/NO_LLM_REPORT.md stays
unchanged. No winner by rawcoverage or recall alone. Final independent audit to
be run by parent, not by implementer.

Interpretability check fixed before closed test: retain feature-collisions.json.
Identical feature vectors with different independent labels demonstrate lost
information in that representation; report this limit rather than changing the
features after seeing evaluation. No-safe-CAL flags cannot establish measured
FPR<=5%; preserve null denominator. Predict receipt labels_opened=false refers
to prediction-dataset gold; integrity hashes may read historical CAL bytes.

Storage: all archive method/action predictions may exceed a GitHub100MB file.
Stream and shard deterministic gzip outputs by contract/method or <50MB per
compressed shard; preserve all records and hash every shard plus input receipt.
Do not silently sample the archive to reduce artifact size. No upload of secrets.

Use one declared latency quantile convention consistently (nearest-rank p50/p95
recommended, matching prior follow-up). Never mix even-n statistical median with
nearest-rank p50 under the same label. Preserve raw timings for recomputation.

Local numerical runtime for the accepted fit is capped uniformly:
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2.
Use the same environment for model benchmarks and rule/native controls; report
it with OS/Python/library versions. This changes compute parallelism, no model
hyperparameter or data. CatBoost still uses its fixed thread_count=2.

Unit audit: synthetic variants are independent one-state episodes; base groups
and duplicate collision components still cluster splits/weights/CI. Archive
episodes remain genuine prefixes. Shared corrected CAL: payment1342episodes/
616safe;A2725episodes/787safe;B2725episodes/501safe. Full-v4 safe denominators
come from synthetic states, not complete archive safety proofs; do not claim
calibrated <=5% interruptions of real honest tasks from this condition.

Assess unchanged rule controls on the SAME corrected CAL as well: disclose
falseALLOW/safe-stop rates and whether they themselves satisfy the predeclared
conditions. They have no tuned thresholds; do not imply the rule baseline has
met calibration constraints merely because classifiers must pass them.
