# Fresh archive-native methods: code-ready, awaiting release

No real TRAIN/CAL rows, labels, raw archives, selected views, old methods, gold/reference implementation or predictions have been read. No real-data fit/prediction has run. Implementation derives from POLICY.md, policy.json, schema.json, task3-methods.md and INPUT_INTERFACE.md only. All tests use authored tiny fixtures and are implementation checks, not benchmark cases.

## Deterministic interface

`methods.guard(input, profile='native')` returns `decision`, `reasons`, `evidence` source references and `timing_ms`. Declared profiles are `native_core`, `native`, `constant_allow`, `constant_block`, `constant_unknown`.

`native_core` checks provenance-backed source/subject binding and known foreign namespace; P4 N02–N07; and actual ordered Invoice then Fraud delegate pairs for an evidenced invoice recipe. A Fraud call takes vendor_id and inherits the already bound invoice task. An unpaired recorded proposal does not establish execution. Its matching actual successful return establishes invocation; proposal time is only a lower bound on actual start. Invoice completion before a Fraud proposal therefore establishes correct order; overlapping proposal times remain UNKNOWN unless actual dispatch establishes the order. Literal JSON/Python result objects are parsed without execution. Successful pairs accept the native task_status=success contract (task_summary remains untrusted text), success=true or status success/completed/complete, and reject explicit task_status/status failed/error or failure; other return shapes remain unknown. Provenance-backed invoice approval/completion facts are also required for the invoice recipe. P2 does not demand future payment fields. Known violations outrank unknown evidence. Latest unknown/conflicting provenance cannot fall back to older convenient state.

`native` additionally pauses on current provenance-backed native recommended_action hold/reject/escalate. A genuinely later same-subject actual Fraud dispatch, or a later proposal paired with an actual return, after the last flag makes its unresolved binding semantic UNKNOWN; completion of the same flagging invocation or later notes/status never clears it. It does not infer recommendations or clearance from free text. These are structural/minimal typed-flag controls, not full semantic native_action adjudicators. Manual-review business exceptions, contextual fraud/compliance review and conditional TaxCalc verification remain outside these deterministic profiles. Neither structural ALLOW nor ML native_core ALLOW establishes source authenticity, full fraud safety or original-source security-target satisfaction. No invoice currency, immutable-initial account, universal human registry, new claim/version gate or sticky human-only clearance protocol is synthesized.

## Structural ML interface

`ml.fit_release(train_rows, train_labels, train_meta, cal_rows, cal_labels, cal_meta, output)` expects normalized input rows with join-only prefix_id/episode_id outside features; label records with `scenario_decision` and `native_core`; metadata with `base_group_id`, optionally prefix_id/episode_id. Label and metadata collections may be parallel lists, prefix_id-keyed mappings, or record lists carrying prefix_id. Source annotation UNKNOWN/unavailable is excluded from the supervised scenario target. Native_core UNKNOWN is a supervised class.

Twelve configurations are two target heads × LR/CatBoost × seeds 17/29/43. LR is C=1/L2/max_iter=2000 with TRAIN-only group-weighted StandardScaler(with_mean=False, with_std=True), reused unchanged for CAL/inference; CatBoost is 200/depth3/lr.03/L2=5/threads2, with no dependency installation. TRAIN-only DictVectorizer uses whitelisted finite enums, missing/invalid states, finite numeric/log/delta features, opaque equality/missing indicators, history counts, fixed native/MCP tool-category counts, scoped material-read snapshot/change counts, evidence-quality counts and complete-prefix state. No ID values, text, source paths, actor names, case/split labels, guard verdicts or oracle fields enter features. Group weights give each base_group_id equal total mass and normalize mean sample weight to one. No/one-class fallbacks are explicit. TRAIN/CAL episode and base-group overlap is rejected.

CAL independently chooses P4-only and reachable joint P2→P4 per-checkpoint threshold sets over the declared grid. Equivalent prediction vectors are deduplicated, preserving the simpler threshold representation. Objective: maximize correct decisive episodes subject to zero observed unsafe ALLOW against that head's review target and <=5% gold-ALLOW episode interruptions; UNKNOWN/BLOCK both stop the episode. Ties minimize errors then threshold sum and lexicographic tuple. Source-unknown annotations cannot certify legitimate or correct coverage. CAL exports target-scored/unscored prefix IDs and counts, episodes with any known target, fully scored episodes, mixed episodes and fully unscored episodes. Only fully target-scored episodes enter correct decisive coverage and gold-ALLOW episode-stop denominators; known unsafe ALLOW still counts as an observed violation in a mixed episode. Native_core UNKNOWN remains a scored class. Empty and infeasible placements retain population/target/placement attribution. A P2 guard-label miss remains a miss even if P4 later stops money movement; archived transfer-prevention counterfactuals belong to the coordinator's separate evaluation. INFEASIBLE preserves raw classifier probabilities and explicitly yields constant-UNKNOWN selective output. No post-CAL refit occurs.

Output directory is new (existing path rejected), containing copied method/policy sources, one joblib model and CAL raw-probability JSON per fit, plus freeze-manifest.json with method/input/config/model SHA256 and operating-point feasibility. Input hashes cover canonical JSON content; root retains released package file hashes separately. `ml.load('.../scenario_decision-lr-17.joblib').predict(input, placement='p4')` returns raw probabilities, raw_decision, calibrated_decision and feasibility. `placement='joint'` selects joint thresholds. Prediction/CAL/manifest outputs explicitly identify target and target_role: scenario_decision is primary_security and native_core is secondary_policy_diagnostic. The diagnostic head's own-target feasibility cannot certify a security winner. Optional `native_gate=True` separately returns the structural gate, gated_decision and gate_forced; it is never silently credited to raw ML.

After explicit coordinator release, root command (replace the six package paths/output and token):

```sh
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_archive_comparison/ml.py --train-rows TRAIN_ROWS.jsonl --train-labels TRAIN_LABELS.jsonl --train-meta TRAIN_META.jsonl --cal-rows CAL_ROWS.jsonl --cal-labels CAL_LABELS.jsonl --cal-meta CAL_META.jsonl --output NEW_MODEL_DIRECTORY --release-token COORDINATOR_RELEASE_TOKEN
```

## Verification and remaining acceptance

```sh
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python -m unittest discover -s experiments/local_guards_archive_comparison/tests -p 'test_m*.py' -v
```

Result after the authorized CatBoost compatibility amendment: 41 tests passed, suite 0.168 seconds (process ~1.52 seconds). Cases cover hard-violation priority, positive native transfer including exactly 50000 and explicit non-USD, missing versus false, typed Fraud flags versus text, P2 future-field exclusion, actual/foreign/failed delegate pairing and source-causal proposal/dispatch ordering, opaque-ID/text invariance, latest unknown provenance, finite amount type validation, feature leakage, TRAIN-only vocabulary, constant/unavailable fallback, a tiny synthetic LR probability fit, equal group weights, CAL infeasibility, UNKNOWN interruption and distinct placement thresholds. Installed sklearn emits a deprecation warning for explicit penalty='l2'; the requested configuration remains effective.

Remaining before real fitting: independent code/interface review; coordinator final TRAIN/CAL package paths and release token; the released input package must implement the documented canonical proof-key and delegate-result contracts. No CatBoost fit or archive benchmark has run. Threshold search runtime on real CAL is not yet measured; equivalent-output deduplication preserves the exact specified grid. No commits or API calls were made.

## Interface correction before release

The coordinator identified two interface mismatches without exposing target results: fact proof-map keys are bare (`invoice_amount`) while proposal/context keys retain full paths; native delegate results expose `task_status: success/failed/error`. `evidenced()` now applies that exact key mapping and requires each latest proof's field to match the canonical key, so an unrelated proof cannot authenticate a fact. Both guards and ML consume this shared corrected evidence adapter. Own fixture production was changed to emit canonical bare fact keys. Native task_status is now recognized, and failed/error statuses cannot establish completion. Ambiguous or missing legacy workflow order remains UNKNOWN, not an invented known violation.

TDD evidence: the new emitted-key, mismatched-field and task_status success tests first failed against the previous implementation (eight failures total after canonicalizing the fixture), then all 19 own tests passed after the minimal fixes. The new tests exercise structured fields only; task_summary wording is not parsed. No data was read or fitted.

## Source-causality correction before release

The successful actual return can establish an invocation originally recorded as a model proposal, without establishing that proposal time equals actual start. The guard now uses this distinction: a completed Invoice followed by a later Fraud proposal paired to actual success proves correct recipe order; an overlapping proposal alone leaves order UNKNOWN; a paired actual Fraud dispatch before the observed Invoice completion establishes a known ordering violation. A real dispatch can supersede its prior proposal; repeated unresolved proposals/dispatches without unique pairing remain ambiguous. The implementation does not infer execution order from proposal-batch order.

TDD evidence: new tests first produced the expected two failures (later paired proposal incorrectly unknown; actual known misorder incorrectly unknown), while the overlapping-proposals test already returned UNKNOWN. After correction all 22 synthetic tests passed. No archive/data/labels read and no real fitting occurred.

## Independent pre-fit review corrections

Read only the authorized code-only method-review.md/.json and refreshed task3/INPUT_INTERFACE. No archive, data, gold, selected views or fitted outputs were exposed. M1: derived amount deltas now have MISSING/KNOWN/INVALID states and must pass a finite check; finite operands such as 1e308 and -1e308 cannot emit infinity. M2: scored/unscored row and episode populations are explicitly exported with the same conservative eligibility rule used by the CAL objective, including mixed annotations and no-row/infeasible placements. Raw CAL rows additionally carry their target, target_scored and target_label outside model features.

The coordinator supplied interface-only native function signatures from source a7f6964fbc60da807e2544d826a5b4e20eb0c5dc. Added generic counts over fixed native read/update/flag/bookkeeping/delegate categories plus registered FinStripe/SystemUtils/TaxCalc MCP categories and OTHER. Model proposals count only after an actual return establishes invocation; actual before_tool dispatches count directly. Material-change features compare only paired successful same-object native getter outputs: amount on get_invoice_details/get_invoice_for_payment; bank_account_number on get_vendor_details; vendor_bank_account_number on get_invoice_for_payment. Subject IDs are equality-only. First successful scoped read establishes a baseline; subsequent observed changes are counts. No initial-state baseline is assumed, so these are observed lower bounds rather than complete historical edit counts. Notes, script contents and arbitrary result names cannot establish changes or enter features.

N09 now distinguishes an unresolved later reassessment from the original flagging invocation. Later same-subject Fraud start/proposal after the last evidenced flag gives UNKNOWN in native; known unrelated-vendor starts do not establish a new same-subject review. Same-call completion and notes do not clear a typed flag. This changes neither native_core verdict logic nor substantive semantic adjudication. Guard explanation refs now include only accepted latest pre-cut proofs, resolving the minor overinclusive-ref finding.

TDD evidence: new overflow, population and empty-placement checks first failed; new native-count/change checks first failed; new later-reassessment and latest-evidence explanation checks first failed. They passed after the changes. Additional tests verify native UNKNOWN stays scored, mixed source annotations cannot certify coverage, and public predictor output retains target role and placement. All 33 own synthetic tests passed (0.023s suite, process ~1.26s). sklearn's explicit L2 deprecation warning remains documented. No CatBoost/real-data fit or benchmark ran. Frozen-module/weight hash verification at coordinator evaluation remains an integration acceptance condition.

## Final pre-fit LR preprocessing correction

Before any data read or model result, the coordinator required standard LR feature scaling to preserve a fair fixed-C/L2 baseline across amount/count/one-hot magnitudes. LR now fits StandardScaler(with_mean=False, with_std=True) exclusively on the usable TRAIN sparse matrix, using the same mean-one equal-base-group sample weights as its classifier. The resulting scaler is stored in the model and reused unchanged on CAL/inference. Frozen configuration records its class, parameters, TRAIN scope and weighting; each fitted model stores scaler/params, and the manifest stores scaler parameters. Constant/unavailable fallbacks explicitly store scaler=None/params=None. CatBoost remains unscaled and all classifier parameters stay unchanged.

TDD evidence: the new LR scaler/reuse test and explicit-fallback-scaler check first failed. After correction all 34 own synthetic tests passed (0.029s suite, process ~1.16s). The test checks the hand-derived TRAIN amount standard deviation of 50 from values 100/200, verifies sparse-safe with_mean=False, confirms CAL/inference probabilities use that same transform, and proves a distant CAL amount cannot change TRAIN scaler statistics. No CAL fit, real-data fit or archive read occurred. These sources/tests/report are ready for the scoped re-review; data release remains pending.

## Final two pre-fit blockers (supersedes earlier unpaired-proposal wording)

1. Guard operands now pass interchange scalar-type validation before business comparisons: malformed native statuses/strings, string-valued booleans and bool-valued IDs produce UNKNOWN rather than fabricated violations. Invalid supplied operands explicitly retain an UNKNOWN reason. Workflow results with malformed nonstring task_status/status remain unknown without raising; malformed feature enums map INVALID without unsafe set membership. The reviewed exact repros invoice_status=123, bank_details_present='true', proposal.invoice_id=True, fraud_recommendation=[] and task_status=[] are covered by tiny authored tests. Known independently established violations still outrank unknowns.

2. A recorded model proposal by itself cannot weaken an established native HOLD. A later same-subject actual dispatch proves invocation; a proposal needs a matched actual return. Unpaired/ambiguous proposals preserve BLOCK, completion of the same flagging call preserves BLOCK, and a paired later review makes old binding UNKNOWN without inventing clearance. A known foreign dispatch/return cannot authenticate execution of a preceding target-vendor proposal. This section supersedes earlier stage wording that treated unpaired later proposals as review uncertainty.

TDD: the exact malformed-input and unpaired-proposal repros failed before changes; after the bounded fixes the full 39-test synthetic suite passed (0.026s; process ~1.31s). No feature expansion, package read, actual data smoke or fit occurred. CLI is unchanged; root may stream restricted gzip packages into fit_release after explicit review clearance/release. Work stops at updated sources/tests/report/readlog/hashes pending that release.

## Authorized TRAIN-only integration smoke

```json
{
  "release_token": "RELEASE-SMOKE-ONLY-20261101",
  "scope": "TRAIN inputs only; no labels/CAL/fits",
  "rows": 1512,
  "input_shapes": {
    "direct_input": 1512
  },
  "decisions": {
    "native": {
      "ALLOW": 964,
      "BLOCK": 541,
      "UNKNOWN": 7
    },
    "native_core": {
      "ALLOW": 1446,
      "BLOCK": 52,
      "UNKNOWN": 14
    }
  },
  "exceptions": {},
  "exception_count": 0,
  "nonfinite_feature_values": 0,
  "feature_count_distribution": {
    "59": 682,
    "62": 635,
    "58": 82,
    "61": 39,
    "56": 4,
    "65": 70
  },
  "elapsed_seconds": 0.66,
  "compressed_train_sha256": "c6104f65e3a4cca86960384abbc58e5ab0553ae7262eff92f1abd3261b460831",
  "release_manifest_sha256": "f259c1d5a982e6629949746b489da9adb6e76606c400549ab5031ea731bc49e7"
}
```

Only the released TRAIN input package and release manifest were read. No labels, CAL, selected cases, outcomes, per-case results or fitted models were read/written. Aggregate smoke output does not establish classifier/guard quality.

## Explicit-failed-followup closure and current-source smoke

A later attempted reassessment ending in explicit task_status/status failed/error, success=false or tool error cannot weaken an established HOLD. The implementation waits for the paired terminal result before deciding whether a later completed attempt leaves binding unresolved; an actual still-running review remains UNKNOWN. Actual/proposal × failed/error regressions first failed, then all 40 synthetic tests passed. This is the remaining C2 correction requested by independent review, with no additional feature or policy expansion.

The authorized TRAIN-only smoke was repeated because this relevant method source changed; no labels/CAL/selected/outcomes were read. Current-source aggregate receipt:

```json
{
  "release_token": "RELEASE-SMOKE-ONLY-20261101",
  "stage": "Final-source TRAIN-only integration after explicit-failed-followup fix",
  "rows": 1512,
  "decisions": {
    "native": {
      "ALLOW": 964,
      "BLOCK": 541,
      "UNKNOWN": 7
    },
    "native_core": {
      "ALLOW": 1446,
      "BLOCK": 52,
      "UNKNOWN": 14
    }
  },
  "exception_count": 0,
  "exceptions": {},
  "nonfinite_feature_values": 0,
  "elapsed_seconds": 0.617,
  "source_sha256": {
    "methods.py": "8e7aa49c198a23f8313fdc9ee2873ad099c1112aae2d4a7d85990888be73a81b",
    "ml.py": "f8c09e6230fb648aea10d7cd3af9de8e7564a9fa18358bc5f472cb0c3200d218"
  }
}
```

## Full-fit release exception: stopped without source changes

ARCHIVE-FIT-RELEASE-20261101-V1 approval, exact method source SHA256, manifest 0320073f2d0d9b517eec6763cc540e999517a999704ecd9d505f63b03a7319a4 and all six compressed package hashes were verified before loading. collector.read_jsonl loaded only released TRAIN/CAL rows/labels/meta. The fixed release stopped at the first CatBoost fit after 4.14 seconds: installed CatBoost rejects the DictVectorizer CSR index dtype with `AssertionError: Type of indices in CSR sparse arrays must be int32`. Three scenario LR artifacts exist; results/ml-release is an incomplete failed release with no freeze manifest and must not be scored. No selected data, other gold, whole archive or reviewer results were read, and no hyperparameter/source changes or retry occurred. Runtime/environment/failure receipt: provenance/method-fit-failure.json. Await root ruling for a bounded lossless sparse-format compatibility correction.

## Authorized pre-selected-inference CatBoost compatibility amendment

The coordinator authorized the smallest dense transport adapter after the first released fit hit an installed-library CSR index-type incompatibility. Only CatBoost fit/predict now call CSR.toarray(); vectorized structural values, feature extraction, TRAIN/CAL division, group weights, estimator parameters and CAL policy remain identical. LR remains sparse with its saved TRAIN-only scaler. The model/freeze manifest records matrix_format, training matrix_shape and dense_bytes so the small actual matrices can be audited after the authorized retry. No result-quality comparison or tuning motivated this amendment.

The actual tiny CatBoost regression first reproduced the int64-CSR AssertionError. With the adapter it fits and predicts successfully, verifies raw CSR indices are int64, checks dense vectorized values equal the unchanged sparse values and confirms public predictions match the estimator on those same dense values. All 41 synthetic tests pass (0.168s suite; process ~1.52s).

The incomplete first release has been preserved at results/ml-release-failed-csr-int32, including its original three LR artifacts and source copies. No retry/selected inference has occurred. The amended ml.py SHA256 is 4be593465378240c8885d317abca80455d2695e1c66184a18606120f3bcf00ca; guard source remains 8e7aa49c198a23f8313fdc9ee2873ad099c1112aae2d4a7d85990888be73a81b. Send this source identity to root/reviewer before retry; authorized next output is a new results/ml-release-v2 directory.

## Authorized V2 full fit completed

ARCHIVE-FIT-RELEASE-20261101-V2 verified approval-v2, source-freeze-v2, exact method identities and the unchanged six released input hashes before loading. All twelve fresh fixed models completed into results/ml-release-v2; TRAIN-only vectorizer/scaler/fits and CAL-only operating points, no selected/other-data inference, no post-CAL refit or tuning. Failed V1 artifacts remain preserved separately. Fit runtime 11.069s; cold setup+fit runtime 13.363s. Frozen source/config/input/model SHA256 manifest: results/ml-release-v2/freeze-manifest.json. Environment, matrix shapes/dense bytes and operating-point summary: results/ml-release-v2/runtime-receipt.json. Own-target native_core feasibility remains a secondary diagnostic, never source-security certification.

Post-fit readback: all twelve model bytes match freeze manifest hashes; all copied method/policy/schema sources match both manifest and currently executed source files; configuration SHA256 and runtime receipt linkage match. No additional fitting or prediction was performed. Freeze-manifest SHA256 8064d2e97cecfffb8452278c00ef3809213cc083181e412b81fd3153fdebedbf. All 24 declared CAL placement operating points are INFEASIBLE; unconstrained raw probabilities and explicit abstaining controls are preserved without post-result adjustment.

## Separate pre-LLM CAL-only cascade extension

After the twelve frozen standalone models, and before any selected scoring or cloud-answer disclosure, root prospectively authorized a separate routing protocol to distinguish DEFER_LLM from business STOP. The root confirmed it had inspected only pilot usage/cost, not decisions. New cascade.py wraps frozen raw probabilities; frozen methods.py/ml.py/models/24 standalone operating points remain unchanged. Only released CAL rows/labels/meta and own frozen CAL raw probabilities/model byte hashes were read. Six scenario_decision heads are eligible; seed17 primary, 29/43 sensitivity. Native-core ML heads remain diagnostic.

Two class-confidence thresholds per checkpoint use the fixed original grid. Native-core BLOCK is mandatory BLOCK, native-core UNKNOWN mandatory STOP_UNKNOWN, core ALLOW permits confidence routing or DEFER_LLM. The fixed block-only rule uses DEFER on every core ALLOW. Legitimate STOP_UNKNOWN/false BLOCK episodes count toward the 5% stop bound; confidence DEFER does not. Zero observed unsafe automatic ALLOW is required even in mixed target-known episodes. Objective is group-balanced correct wholly autonomous episodes: any prior DEFER or source-unscored target prevents whole-autonomy credit. Downstream potential automatic decisions after DEFER are reported only as opportunities; no LLM answer or actual full cascade quality is inferred. Configuration/source fixed at 2026-11-01T20:02:11.981865+00:00; CAL search 5.187s. Seven tiny cascade tests pass. Configuration/operating points are frozen in results/cascade-calibration.json and results/cascade-freeze-manifest.json before selected release.
