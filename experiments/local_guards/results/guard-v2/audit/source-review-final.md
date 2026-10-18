# Final source audit before label disclosure

No hidden observations, hidden labels or external metrics were read. No model inference was run and this auditor did not edit any of the 47 METHOD_FREEZE_04 files. The root later paused its processes, preserved04, and separately authorized05 migration by the module owners.

## integrity-before-unblind

Classification: actual_validation_gap. Source: `cascade_guard/v2_eval.py:455-460`.

Scorer does not revalidate rows/record hashes or methods-freeze hash against prediction freeze.

New external read-only v2_preunblind validator checks all recorded hashes and exact observation/prediction/available-arm identities; frozen evaluator unchanged.

## pair-check-before-write

Classification: actual_failure_atomicity_gap. Source: `cascade_guard/v2_eval.py:476-482`.

Metrics are written before mandatory pair validation; a pair error can leave partial unblinded artifacts.

Authorized external validator reads labels only after explicit root marker, validates complete joins/pairs before scorer invocation; existing metrics block retry.

## jev-evaluator-envelope

Classification: actual_interface_bug. Source: `cascade_guard/v2_jev.py:215-223; cascade_guard/cheap_eval.py:38-41`.

Jev feature exports omit required memory/window_count fields.

Independent evaluator owner preparing blind metadata-only adapter; preserve scientific exports and 47 frozen files. Coverage count must mean checkpoint inputs, not text windows; memory unmeasured.

## base-policy-currency

Classification: setup_semantics_adaptation. Source: `vendor/finbot/finbot/probe/policy.py:16-22; cascade_guard/v2_hidden_dataset.py:16,51-54`.

FinBot source has USD thresholds; synthetic v2 states major currency units and checks normalized ORIGINAL invoice currency amount without USD conversion. JPY thresholds are therefore synthetic local-major-unit thresholds.

Do not describe inherited policy as literally unchanged FinBot. Freeze remains unchanged; report synthetic task interpretation.

## threshold-coverage

Classification: known_coverage_limitation. Source: `cascade_guard/v2_hidden_dataset.py:166-168`.

Declared generator formula yields original amount120..367; 5000/10000/50000 boundaries and human review applicability are not exercised by this design.

No boundary correctness/generalization claim from240. No new cases or threshold changes after freeze.

## partial-base-policy

Classification: task_contract_interaction. Source: `cascade_guard/v2_hidden_dataset.py:23,54-63`.

Partial settlement explicitly replaces original-full-amount and one-transfer rules. Review/reject thresholds remain applied to original invoice amount, not residual or FX transfer amount.

Keep this original-obligation policy interpretation separate from residual arithmetic; signed registry alone is not substituted for human_cleared above threshold.

## sequence-artificial-staging

Classification: known_external_validity_limitation. Source: `cascade_guard/v2_hidden_dataset.py:245-266`.

All case states authored upfront then revealed in prescribed cumulative native snapshots. No source evidence of future-event leakage: P1 invoice; P2 vendor/compliance/ledger/attempts/backend; P3 validation/registry/budget/FX; P4 proposal plus later revisions.

Call synthetic native stage snapshots, not real LLM trajectories or adaptive cascade prevention. Older timestamps revealed later are delayed observations; scheduled effective timestamps are not automatically future events.

## probability-target

Classification: correct_target_separation. Source: `cascade_guard/v2_eval.py:414-429`.

External intervention target differs from archive harm-risk; external probability metrics are intentionally suppressed. Modeled backend diagnostic is not observed loss.

Do not pool targets or infer actual FinBot harm prevention.

## train-cal-control

Classification: checked_source_design. Source: `cascade_guard/v2_eval.py:282-353`.

Candidate selection uses TRAIN inner grouped OOF. Exact fold0 TRAIN model is serialized, thresholded on held-out CAL and reused without refitting. A/B2/Blegacy/C remain separate; reached-safe is primary denominator.

Verify fitted model/training IDs/calibration IDs and thresholds against this design before external predictions.

## New read-only pre-unblind gate

`cascade_guard/v2_preunblind.py` has 15 passing synthetic tamper tests. It verifies every recorded source/model/training/row/record/prediction hash, exact available-model/control arm set, per-arm prefix/episode/cutoff identity and feature coverage. It does not import models or alter experiment artifacts. The optional scorer path invokes the unchanged evaluator only after authorized complete label/pair validation.

Root marker schema: `{"authorization":"UNBLIND","predictions_freeze_sha256":"<exact PREDICTIONS_FROZEN.json hash>","labels_sha256":"<sealed label file hash>"}`. Root must obtain the label hash from the sealed generation manifest, not from a preauthorization label read.

## Checks after the one-time unblind

1. After all model processes exit, verify METHOD_FREEZE_04 and JEV_INPUT_FREEZE hashes, required feature coverage and declared availability before any fit.
2. Verify TRAIN/CAL episode/group disjointness; selected config comes only from TRAIN inner OOF; final model is exact stored TRAIN fit with no post-CAL refit.
3. Before label authorization, run read-only validator on each prediction destination with expected observation count, all pinned hashes, complete expected arms, matching prefix/episode/cutoff sets.
4. Root writes explicit UNBLIND marker binding exact prediction-freeze SHA and sealed label SHA; before this marker never hash/parse hidden labels.
5. After authorization, prevalidate exact label joins, boolean contract targets, 120 opposite-target pair groups and six families of40 for independent240; only then invoke immutable scorer once.
6. Record counts k/n, all240 observations and120paired groups; do not multiply sample size by seeds or claim120distinct mechanisms.
7. Report intervention recall, compliant STOP FPR and UNKNOWN STOP separately; report per-family and matched-pair outcomes, including method availability and source-blind extra contract control.
8. Keep archive harm-risk metrics, static contract intervention metrics and local backend potential policy-violating new-effect diagnostic separate; preserve null uncertain backend outcomes.
9. Check all scored predictions retain frozen thresholds/configs; no tuning, reruns, case removal, method selection or oracle edits after labels.
10. If scorer fails after opening labels, preserve partial outputs and marker; reconcile same frozen predictions rather than refit or rerun model inference.
11. Read back exported report against frozen metrics: primary A, C/B sensitivity names, reached-safe versus legacy calibration denominators, known limits on FX/JPY and absent approval boundaries.
12. Record observed cache-assisted runtimes, checkpoint-total versus final-incremental latency, cold/warm status, unmeasured memory and overlapping source computation semantics.

Pending: source review of external evaluation runner and Jev metadata compatibility adapter.

Archive allocation check (existing archive metadata only): each fold0 has 148 TRAIN and 66 CAL outcomes, with 36 and 12 groups. Episode/group partitions are disjoint; both inner partitions cover TRAIN exactly and are disjoint. Splits differ across seeds. The phrase two-thirds archive is approximate in episode count, not group fraction; new-test sample size is never multiplied by seeds.

## External orchestration and metadata envelope

Source-only review confirms sequential barriers, explicit model unload, exclusive global heavy lock, archive-only collection-specific training, both model freezes before external ML prediction, and no score/label path. N/M local/full/facts projections are fixed key selections; UNKNOWN propagates and full scalar uses the predeclared four-claim formula. Original extractor cost is retained. Jev compatibility adds unmeasured memory and actual recorded checkpoint-input count without modifying scientific features, probabilities, input hash or latency. Structurally absent raw/partial timelines are omitted rather than advertised as all-STOP methods.

Before launch, the owner was asked to close provenance gaps in the new outer glue: bind completed runtime states to the current method/Jev freeze hashes, verify recorded Jev export checksums before normalization, and enforce exact collection prefix inventories/model-block identity before fitting. These are new-addon repairs; the 47 frozen files remain unchanged. Addon final gate is pending the repaired source review.

## AMEND05: stop and repair false trusted predicates

The root stopped its inference/watchers and preserves partial04. The summary derivation is an actual feature-semantics error: raw amount equality is not normalized obligation equality, and an arbitrary ledger settlement is not a duplicate of the current invoice. A disclaimer is insufficient while these values remain trusted predicates.

The reviewed05 draft removes full-native auto-summary generation entirely. Raw and matched-partial legacy observations remain literal source reports with explicit provenance and are excluded from trusted/local NLI evidence. Native boolean HOLD normalization is also repaired: a constructed public fixture now makes both R1 and R2 stop an explicit unresolved hold. No hidden instance or label informed these corrections.

One source-level risk remains to resolve before05 exports: full-archive hold still copied an older derived fraud_action whose producer ignores nested output errors or flagged=False. Confirmed native flag commits must not be contradicted by a falsely authoritative old summary. The auditor has not measured archive incidence or read hidden cases.

The external addon provenance repairs pass source review and four independent new synthetic tamper tests. The next freeze must refresh runner/input paths and addon protocols for05. No restarted inference is approved by this audit until the remaining native-hold issue and05 freeze are resolved.

## Authorized known-archive native flag impact check

The root explicitly authorized an event audit of the known archive, with no hidden-data access. All234 baseline strict outcomes reproduced exactly. The109 native flag events all have explicit flagged=True without top-level or nested errors; confirmed FALSE and UNKNOWN counts are both zero. Replacing old flag admission with confirmed-only admission or an UNKNOWN-stop bound changes no episode label, strict-harm sequence or reason. Strict harm remains91/234 overall and83/214 nonambiguous.

New diagnostic outputs are in `audit/archive-flag-diagnostic/`: native event evidence with episode ID/sequence/native event hash, confirmed-commit outcomes, UNKNOWN-stop-bound outcomes, and summary. Existing234/214 outcome artifacts are untouched. Two new public fixtures distinguish TRUE/FALSE/UNKNOWN and prove missing confirmation is not treated as failed. This resolves actual archive incidence; the general source-level bug still warrants05 tri-state native admission to avoid false facts on other inputs.

## Final AMEND05 source gate

PASS source design, pending fresh immutable v5 exports/admission and the root05 freeze. Full-native automatic summary predicates are gone. Limited literal source reports carry explicit provenance and are excluded from all trusted/local NLI premises. Missing raw arguments never become a match. Full native HOLD uses explicit confirmation with current-invoice argument/result binding; missing or conflicting commitment/binding remains UNKNOWN, and another invoice is not treated as the current hold. Boolean hold values normalize correctly for legacy rules. Typed identity aliases preserve nonidentity primitives and prose.

Known-archive evidence confirms all109 native flag outputs contain invoice_id and both argument/result subjects match the current invoice. The corrected admission therefore preserves all observed archive flag states and changes no234/214 strict outcomes. No hidden instance or label was read to establish this gate. Current reviewed source hashes are recorded in source-review-final.json.

Restart still requires new v5 exports and root05 admission/freezes; old04 partial outputs remain preserved. The new outer evaluation glue must switch its fixed manifest/input/output paths and refresh its addon protocol before launch. No old evidence is retroactively relabeled as05.

## Generation05 fresh orchestration: final source gate

PASS for fresh watcher launch under pinned05 manifests. The model runner enforces the prospective clock and runs PG22, PG86, N, M in order. The external Jev clock guard binds exact MF05 and checks explicit timezones, the unchanged inference cutoff and the absolute deadline before executing the frozen base watcher.

The evaluation barrier now recognizes actual terminal enums, requires both watchers unloaded, and checks process absence plus the global lease. Before21:39:58 UTC it waits for all six models; afterwards it admits only exactly complete models. A COMPLETE per-model manifest and all720 prefix/input-hash identities are required. Empty, missing or partial exit0 artifacts cannot exclude healthy completed models by crashing the barrier. Jev availability checks all five collection identities and actual attempted checkpoint coverage. Zero completed pretrained models still allow the predeclared tabular/text/rule controls with an empty records file; no scores are invented.

Eight independent new synthetic addon tests pass, including actual cutoff enums, unload requirements, partial/missing exit0 artifacts, zero-model plans, stale freezes, export tampering and wrong model/collection identities. Only new glue tests were run; frozen scientific tests were not repeated. Current reviewed hashes are recorded in source-review-final.json, and this auditor did not edit any of the54 MF05-pinned files.

Resume limitation: the frozen Jev base restores stages but not completed exports at startup. Fresh launch is reviewed. A post-cutoff restart must not overwrite preserved completed-export metadata; an external guard refusal or verified metadata-only resume path was requested. The root must pin the final external addon/guard source after that handling. No hidden observations, labels or risk values were opened in this source review.
