# Task 2: fair shared features, three-class models and frozen calibration

Worktree /Users/proskurin-dmi/Documents/hw-itmo/cascades/research/finbot-general-guards.
Read PLAN.md and this brief first. Implement only in experiments/local_guards_ml_retrain/. Do NOT change old v3/v4/FinBot/root README/main report. No subagents, no git commits, no model API calls, no fitting yet until data review accepted. Use installed ML Python: /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv/bin/python; native environment separate at .venv-finbot/bin/python same parent, both have sklearn1.9.1/catboost1.2.10. Stdlib+existing packages only. Parent will run full fitting after review. Own tests only, no broad discovery.

Allowed prior sources: copied policy/schema/POLICY in this experiment; existing v3/ml_v3.py for old feature definition (must remain unchanged); v4/evaluate.py and v4/prepare_data.py for row formats/representational projection and gold reducer only; data/gold/metadata TRAIN+CAL files in v3/v4, their manifests/splits. Prior400/320 test data/results must NOT be used during fit/CAL or feature development; new test does not exist. Record task file reads/hashes. No reports/evaluation outcomes or guarded model source imports as feature/label oracles. New local oracle.py is independent supervised labeling, not a feature source.

Interfaces:
features.py project_v3(row)->dict; features(row,mode='new')->dict; mandatory_proof_gate(row,contract)->dict{allow:bool,reasons:list[str]}.
models.py fit_model(family,rows,labels,weights,feature_mode,seed)->fittedPipeline; probabilities(model,rows)->list[dict ALLOW/BLOCK/UNKNOWN]. Missing trained classes map exactly0, all unknown probabilities not hallucinated. Unsupported no-class training produces explicit unavailable artifact, no fabricated fit.
experiment.py CLI prepare --output NEW_DIR; fit --data DATA --output NEW_FREEZE; predict --freeze FREEZE --observations PATH --metadata PATH --output NEW.jsonl.gz. Add pure helper functions for calibration/evaluation reuse. Predict must not read labels, outcomes, old test files. Immutable outputs/refuse-overwrite.

Features: old mode exactly frozen ml_v3.features(project_v3(row)). New mode extends old payment features with the existing v4 observation: typed session/context actor/tool/portal/target fields; access/relation booleans; delegation technical completion and linkage presence/equality; amount/currency/recipient relations; approval binding presence, amount/currency/ID/account/version equality, prior/non-revoked availability; active claim state, owner/key scope equality and timing. No raw IDs, accounts, records, generation/timestamps, case/family/executor/outcome/split/labels, model/rule predictions, requirement-state aggregates. ID relations only. Do not feed arbitrary operation/writer/reason strings: generated descriptive operation names can leak mutation labels. Allowed evidence features per fact: present/missing; known source kind; source permitted for fact; prior/future; same scope and subject; value matching; versions current; newest conflict; typed known/invalid/unknown. Recognized operation checks only where contract explicitly requires them (session_validate,currency_contract_attest); other operation text reduced to nonempty. Context canonical enum categories okay; unknown category gets explicit marker. Do not infer unknown to false. Exclude untrusted text from new structural models.

Mandatory-proof gate: independent input/evidence availability/permission validator, never invokes guards or oracle. Only invoked when classifier would ALLOW; failure replaces ALLOW with UNKNOWN, never creates a business BLOCK. Honor per-cut applicability and optional human approval/clearance: no payment prerequisites before P4, no optional human approval below/equal10000, no clearance without HOLD. Explicit denial of required technical/human permission must not be auto-approved. Clearly enumerate protected mandatory conditions, report raw classifier versus gate separately, don't attribute gate's effect to ML. Gate reasons excluded from model features. Preserve scope/type/source/time/version checks, not proof-source strings as authentication of arbitrary JSON. Treat observations as trusted producer outputs only.

Prepare archive rows from existing v4 data (prefix metadata split fixed; Luna not TRAIN/CAL; do NOT retain TEST in fitting data). Gold A/B via existing stored independent requirement labels reducer (BLOCK if violated, UNKNOWN if unknown/allN/A, ALLOW otherwise), never target guards. payment_v3 P4 uses stored A08 gold on compatible existing payment_baseline projection; explain if distinct scope. Main v3 historical labels/old320 diagnostic handled after freeze, not fit. Save observations, metadata, labels separated. Combine independently generated new8000 synthetic dataset, preserve group split; group IDs must be source-prefixed to avoid accidental collisions; keep all variant relatives together. CAL = same archive CAL+synthetic CAL for all arms per contract. No outcomes loaded.

Model list72: contracts payment_v3/A/B × features old/new × sources archive/mixed × family logistic/catboost × seed17/29/43. Three-class ALLOW/BLOCK/UNKNOWN. LR C=1,max_iter2000,L2 (sklearn1.9 l1_ratio0), CatBoost iterations200,depth3,learning_rate.03,l2_leaf_reg5,thread_count2,verboseFalse,random_seed,allow_writing_filesFalse. No hyperparameter search/refit after CAL. Fit DictVectorizer+scaling inside TRAIN. If useful precompute feature dicts once, preserving sklearn pipeline API/metadata; don't let full-CAL categories enter vectorizer. Weights: each source total half in mixed, uniform mass per base group inside source (all prefixes/variants share its mass); scale total weights to number of training rows. Archive-only similarly group weights mean1. Record class counts/weights/features/provenance/source hashes per artifact.

Calibration: align3-class probs; grid of observed CAL per-class confidence quantiles (41 points), .5 and >1 sentinel. ALLOW iff pA>=threshold_A and strictly exceeds other class probs, BLOCK likewise pB, ties/other UNKNOWN. Optimize on CAL correct decisive EPISODE coverage with no observed false ALLOW on any gold!=ALLOW, <=.05 stop FPR on episodes with all applicable goldALLOW, including UNKNOWN stops. Raw and gated variants calibrated separately on same CAL. Deterministic tie: coverage, fewer false safe stops, larger confidence thresholds. If infeasible, abstain thresholds>1 and explicitly report infeasible + unconstrained argmax diagnostics; don't silently select test-tuned thresholds. Zero observed CAL errors is no test guarantee. Eligibility payment_v3 P4transfer, A/B P0-P4. No-check produces decisionNone and is not autonomous. Replay until first stop; don't count future unreached state; falseALLOW counts per reached action. Episode correctly solved if all reached eligible decisions correct and either every eligible action ALLOW through end or first stop is correctly BLOCK; UNKNOWN unresolved. Also report per-action confusion/correct coverage so synthetic one-state and archive episodes distinct. Bootstrap grouping later.

Fit output: pickles, model manifest (parameters,class counts,preprocessing train-only fingerprints,weights,availableclasses,training timings), thresholds JSON for raw/gated, CAL decisions/metrics, source/data hashes. Frozen manifest includes ALL method/helper feature/gate/inference sources and config, models, thresholds. Canonical deterministic JSON/gzip. Prediction output rows method(contract/arm/family/seed/raw|gated),prefix_id,decision,raw_decision,gate_changed/reasons,probabilities,timing,checked,event_seq. Threshold loaded strictly frozen; class probabilities are model score, not guard output. Full model pipeline load hash checked before pickle deserialization. Don't read test gold. Parent will commit freeze before any test creation.

Tests: different new features with same old vector; IDs/text/metadata renames invariant; changed trusted proof affects features/gate; absent class prob0; TRAIN-only category fit; equal source/group weights; no-Luna; group overlaps rejected; mixed BLOCK+UNKNOWN; optional human authority; episode UNKNOWN/stop timing and CAL infeasibility. Smoke fit on small fixtures and validate predict doesn't open gold using read guard. Full report tests, interfaces, read audit and limitations in features-training-report.md. No full72 fits until parent approval of task/data review (parent controls timing, not user confirmation).

Additional preflight rulings: raw proof operation/writer strings must not be
features or lexical 'failed/error/truncated' heuristics. Native_tool may attest
currency if actually available; missing native Invoice field does not globally
forbid other genuine currency sources. For source/timing/version compatibility
follow existing contracts, not empirical generator markers. Record any ambiguity.
Optional native benchmark enrichment after freeze may populate explicit parent
ID from actual runner _INVOKING/agent workflow context (same enrichment for
rules and ML); it must be separately declared and not a fabricated model claim.
No existing native runtime file is changed; a legacy-observation run should
remain as diagnostic if strict gate cannot use its missing explicit parent.

Dataset split contract update: synthetic metadata keeps original group_id for
2000 base tasks and adds split_group_id for connected components of normalized
observation collisions. Split only those components; actual ratio may differ
slightly from75/25. Preserve group_id for fit equal-base weighting, use
split_group_id for disjointness and clustered uncertainty. Never assume fixed
6000/2000 row counts if connected split requires different counts. Independent
data manifest is authoritative.

Efficiency: archive has55492 TRAIN and18753 CAL prefixes, plus synthetic6000/2000.
Precompute feature/probability/gate arrays and episode grouping once; don't
materialize/call Python episode replay for every row of every41x41 threshold grid.
Vectorized masks/reduceat/chunking are appropriate. Preserve exact first-STOP
semantics and test fast calibration against a small straightforward oracle.
Zero false allows counts reached actions (gold!=ALLOW); episode safe-stop uses
all-gold-ALLOW episodes. Correct episode coverage cannot credit a later stop
when earlier ALLOW was wrong or UNKNOWN already stopped execution.

JSON thresholds may use finite >1 sentinel1.000001 for abstain; avoid nonstandard
Infinity/NaN in exported JSON. State exact conventions in manifest.
