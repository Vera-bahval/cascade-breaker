# Revision2 minimal feature/evidence correction

Repo /Users/proskurin-dmi/Documents/hw-itmo/cascades/research/finbot-general-guards.
Read this first and REVISION_2_PLAN.md; it is the scope. Only this new experiment
version is writable. No subagents/API/commits. Do not read closed*, original1200
test/labels/results/reports, prior320/400/otherthreadv4.2 or target rule code.
No test performance is needed. Allowed sources: six copied contracts; original
features.py/models.py/experiment.py; own fixture tests; old-v3 ml_v3.py only for
unchanged feature interface. CAL gold/data and oracle.py are not development
inputs; parent runs complete fitting after review. Explicit read log with hashes.

Defect determined from policy: for delegation_subject_matches proof.call_id binds
context.delegation_call_id (completed SOURCE invocation), not current checking
context.call_id. tool_scope_matches still binds checking call_id. Different IDs
do not inherently prohibit P2; missing/foreign source binding remains unavailable.
Fix both feature proof selection and mandatory gate. Retain original context ID
equality as an observable relation; never expose raw ID strings. No stage shortcut
that ignores unrelated source evidence merely to preserve a matrix.

Implement distinct module files features_revision2.py,models_revision2.py,
experiment_revision2.py in the experimentroot (so existing contract paths/HERE
resolve). Straightforward versioned copy with small auditable delta is acceptable
for frozen research; avoid hidden global monkeypatch/rewriting actual observations.
Preserve all original files byte-for-byte. Copied parameters/class handling/
TRAIN-only preprocessing/source weights/calibration search stay EXACTLY same.
Use shared original models.FeatureBatch type (and UnavailableModel if practical)
to keep reused original pickle/precomputed inference compatible; functions for
new fitted Pipeline raw inference must resolve explicitly to revision2 feature
extractor, never original extractor by generic module accident.

Fit interface same CLI --data prepared --output NEWDIR, default frozen_revision2.
Reuse original model weights ONLY after exact TRAIN AND CAL feature dictionary
fingerprints, rowID/labels/weights match original for that contract/mode/source.
Old feature modes should match (36models). New payment modes may or may not:
check actual matrices, do not assume irrelevance means bitwise equality. If they
differ refit same declared parameters. New-feature A/B refit. Reused model bytes
may be copied with provenance manifest explicitly linking originalsha/reason;
do not silently rewrite fitted provenance. New model manifests retain source
hashes, matrix/weight/class/preprocessing fingerprints. Recalibrate raw and gated
using corrected features/gate and SAME CAL, no refit afterward.

Freeze must include original inference sources for reused pickles, all new
revision2 sources/plan, unchanged six contracts/policy and every artifact/hash.
Generic verify_freeze must validate both original and revision2 artifacts without
editing original helper. New prediction CLI must remain labelblind and verify
before unpickle, support all72xraw/gated with receipts. Preserve absent classes0.

Own tests BEFORE full fit: different current/source IDs with correct completed
proof is available; foreign proof changes relation/feature and gateUNKNOWN;
missing source call; correct tool-check binding; same-call case; proof ordering/
newest foreign record semantics per policy; input IDs renamed invariance; no
original source mutation. Tiny raw-vsFeatureBatch/model-pickle probability parity
for new and reused original models. No copying policy gold into feature flags.

Report revision2-engine-report.md +revision2-read-log.json, exact testcommands/
outputs/source hashes and source-delta explanation. Do NOT fullfit or create new
test. Parent will freeze then dispatch fresh policy-only author1200 +reviewer.

Resource coordination: original-method latency measurements may be running.
You may read/write source now, but WAIT for parent CPU-clear before model-fit
tests or heavy data scans; tiny stdlib own fixtures are okay. Parent will notify.
