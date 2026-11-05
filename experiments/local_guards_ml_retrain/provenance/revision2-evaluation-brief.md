# Revision2 measurement adapter, no method changes

Repo /Users/proskurin-dmi/Documents/hw-itmo/cascades/research/finbot-general-guards.
Read this brief and REVISION_2_PLAN.md/P2_CALL_BINDING_CLARIFICATION.md.
Original evaluation.py/benchmark.py and accepted evaluation-report are interfaces;
features_revision2/models_revision2/experiment_revision2 are read-only methods.
No edits to any existing source/model/policy or old results/mainreport. No APIs,
subagents or commits. New own files evaluation_revision2.py,benchmark_revision2.py,
test_evaluation_revision2.py,revision2-evaluation-report.md/read-log.
Existing native Python: /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/
local_guards/.venv-finbot/bin/python; env OMP/OPENBLAS/VECLIBthreads2.

Create explicit versioned copies/adapters with minimal auditable delta. Use the
correct revision2 feature extraction/gate/model pipelines for all raw,precomputed,
single,cold/native paths; original FeatureBatch alias is shared. Default/receipt
verification uses frozen_revision2; all frozen72methodsxraw/gated and deterministic
argmaxdiagnostics. Old rulecontrols/TFIDF unchanged on SAME observations.
Keep original metric/reachability/denominator/bootstrap/IO semantics unchanged.
Do not fix model/feature/calibration methods; they are currently under finalfit.
Reused weights have NEW pipeline inference explicitly bound to revision2.

Common native producer: preserve fresh actual checking context.call_id. At P2
attest parent_workflow_id from actual _INVOKING parent, and completion proof
call_id from the actual completed delegation source (existing invocation).
Do not rewrite checkingcall ID to force equality. Change only an existing trusted
delegation attestation's callbinding; don't invent successful completion, source
IDs, missing permissions or human approval. Missing actual linkage staysunknown.
Record base snapshots plus exact enrichment, identically for rules and ML.
Old frozen ruleA/B can disagree with corrected source binding; preserve that
result, no per-method input fix. This is execution/profile clarification rather
than a new business requirement. V4.2/otherthread is not an input.

Own tests and bounded native smoke: correct distinct checking/source completion,
foreign/absent source proof, no calls afterSTOP; raw/precomputed identity for
versioned/reused pipelines; same snapshot for rules/ML, correct imported FinBot
path. It is okay to probe the proof component with an explicitly diagnostic
constant-classifier fixture while fitted revision2 models are not yet available;
that is not a benchmark or new qualitymethod. Actualfullmodels smoke can follow
fit. Do not claim timing under concurrent fit/scoring; full benchmarks later
onquietCPU. No archive/newtest prediction or fullruns now.

New CLOSED revision2 test does not exist yet; do not read original1200gold, source
or results while implementing. Existing ownfixture/legacy native tests are open
engineering fixtures. Report exact ownfixture commands/outputs/source deltas and
hashes; parent independentcode review before fullassessmentfreeze/testauthor.
Parent will run both v1/v2 on the new test beforegoldrelease in separate output
dirs to avoid method-name collisions. Old320/400/first1200 are open diagnostics,
never TRAIN. Original versions and every published result remain unchanged.
