# Fresh archive-native methods: code-ready, awaiting release

No real TRAIN/CAL rows, labels, raw archives, selected views, old methods, gold/reference implementation or predictions have been read. No real-data fit/prediction has run. Implementation derives from POLICY.md, policy.json, schema.json, task3-methods.md and INPUT_INTERFACE.md only. All tests use authored tiny fixtures and are implementation checks, not benchmark cases.

## Deterministic interface

`methods.guard(input, profile='native')` returns `decision`, `reasons`, `evidence` source references and `timing_ms`. Declared profiles are `native_core`, `native`, `constant_allow`, `constant_block`, `constant_unknown`.

`native_core` checks provenance-backed source/subject binding and known foreign namespace; P4 N02–N07; and actual ordered Invoice then Fraud delegate pairs for an evidenced invoice recipe. A Fraud call takes vendor_id and inherits the already bound invoice task. An unpaired recorded proposal does not establish execution. Its matching actual successful return establishes invocation; proposal time is only a lower bound on actual start. Invoice completion before a Fraud proposal therefore establishes correct order; overlapping proposal times remain UNKNOWN unless actual dispatch establishes the order. Literal JSON/Python result objects are parsed without execution. Successful pairs accept the native task_status=success contract (task_summary remains untrusted text), success=true or status success/completed/complete, and reject explicit task_status/status failed/error or failure; other return shapes remain unknown. Provenance-backed invoice approval/completion facts are also required for the invoice recipe. P2 does not demand future payment fields. Known violations outrank unknown evidence. Latest unknown/conflicting provenance cannot fall back to older convenient state.

`native` additionally pauses on current provenance-backed native recommended_action hold/reject/escalate; it does not infer recommendations or clearance from free text. These are structural/minimal typed-flag controls, not full semantic native_action adjudicators. Manual-review business exceptions, contextual fraud/compliance review and conditional TaxCalc verification remain outside these deterministic profiles. Neither structural ALLOW nor ML native_core ALLOW establishes source authenticity, full fraud safety or original-source security-target satisfaction. No invoice currency, immutable-initial account, universal human registry, new claim/version gate or sticky human-only clearance protocol is synthesized.

## Structural ML interface

`ml.fit_release(train_rows, train_labels, train_meta, cal_rows, cal_labels, cal_meta, output)` expects normalized input rows with join-only prefix_id/episode_id outside features; label records with `scenario_decision` and `native_core`; metadata with `base_group_id`, optionally prefix_id/episode_id. Label and metadata collections may be parallel lists, prefix_id-keyed mappings, or record lists carrying prefix_id. Source annotation UNKNOWN/unavailable is excluded from the supervised scenario target. Native_core UNKNOWN is a supervised class.

Twelve configurations are two target heads × LR/CatBoost × seeds 17/29/43. LR is C=1/L2/max_iter=2000; CatBoost is 200/depth3/lr.03/L2=5/threads2, with no dependency installation. TRAIN-only DictVectorizer uses whitelisted finite enums, missing/invalid states, finite numeric/log/delta features, opaque equality/missing indicators, history counts, evidence-quality counts and complete-prefix state. No ID values, text, source paths, actor names, case/split labels, guard verdicts or oracle fields enter features. Group weights give each base_group_id equal total mass and normalize mean sample weight to one. No/one-class fallbacks are explicit. TRAIN/CAL episode and base-group overlap is rejected.

CAL independently chooses P4-only and reachable joint P2→P4 per-checkpoint threshold sets over the declared grid. Equivalent prediction vectors are deduplicated, preserving the simpler threshold representation. Objective: maximize correct decisive episodes subject to zero observed unsafe ALLOW against that head's review target and <=5% gold-ALLOW episode interruptions; UNKNOWN/BLOCK both stop the episode. Ties minimize errors then threshold sum and lexicographic tuple. Source-unknown annotations cannot certify legitimate or correct coverage. A P2 guard-label miss remains a miss even if P4 later stops money movement; archived transfer-prevention counterfactuals belong to the coordinator's separate evaluation. INFEASIBLE preserves raw classifier probabilities and explicitly yields constant-UNKNOWN selective output. No post-CAL refit occurs.

Output directory is new (existing path rejected), containing copied method/policy sources, one joblib model and CAL raw-probability JSON per fit, plus freeze-manifest.json with method/input/config/model SHA256 and operating-point feasibility. Input hashes cover canonical JSON content; root retains released package file hashes separately. `ml.load('.../scenario_decision-lr-17.joblib').predict(input, placement='p4')` returns raw probabilities, raw_decision, calibrated_decision and feasibility. `placement='joint'` selects joint thresholds. Optional `native_gate=True` separately returns the structural gate, gated_decision and gate_forced; it is never silently credited to raw ML.

After explicit coordinator release, root command (replace the six package paths/output and token):

```sh
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_archive_comparison/ml.py --train-rows TRAIN_ROWS.jsonl --train-labels TRAIN_LABELS.jsonl --train-meta TRAIN_META.jsonl --cal-rows CAL_ROWS.jsonl --cal-labels CAL_LABELS.jsonl --cal-meta CAL_META.jsonl --output NEW_MODEL_DIRECTORY --release-token COORDINATOR_RELEASE_TOKEN
```

## Verification and remaining acceptance

```sh
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python -m unittest discover -s experiments/local_guards_archive_comparison/tests -p 'test_m*.py' -v
```

Result after interface/causality corrections: 22 tests passed, suite 0.024 seconds (process ~1.45 seconds). Cases cover hard-violation priority, positive native transfer including exactly 50000 and explicit non-USD, missing versus false, typed Fraud flags versus text, P2 future-field exclusion, actual/foreign/failed delegate pairing and source-causal proposal/dispatch ordering, opaque-ID/text invariance, latest unknown provenance, finite amount type validation, feature leakage, TRAIN-only vocabulary, constant/unavailable fallback, a tiny synthetic LR probability fit, equal group weights, CAL infeasibility, UNKNOWN interruption and distinct placement thresholds. Installed sklearn emits a deprecation warning for explicit penalty='l2'; the requested configuration remains effective.

Remaining before real fitting: independent code/interface review; coordinator final TRAIN/CAL package paths and release token; the released input package must implement the documented canonical proof-key and delegate-result contracts. No CatBoost fit or archive benchmark has run. Threshold search runtime on real CAL is not yet measured; equivalent-output deduplication preserves the exact specified grid. No commits or API calls were made.

## Interface correction before release

The coordinator identified two interface mismatches without exposing target results: fact proof-map keys are bare (`invoice_amount`) while proposal/context keys retain full paths; native delegate results expose `task_status: success/failed/error`. `evidenced()` now applies that exact key mapping and requires each latest proof's field to match the canonical key, so an unrelated proof cannot authenticate a fact. Both guards and ML consume this shared corrected evidence adapter. Own fixture production was changed to emit canonical bare fact keys. Native task_status is now recognized, and failed/error statuses cannot establish completion. Ambiguous or missing legacy workflow order remains UNKNOWN, not an invented known violation.

TDD evidence: the new emitted-key, mismatched-field and task_status success tests first failed against the previous implementation (eight failures total after canonicalizing the fixture), then all 19 own tests passed after the minimal fixes. The new tests exercise structured fields only; task_summary wording is not parsed. No data was read or fitted.

## Source-causality correction before release

The successful actual return can establish an invocation originally recorded as a model proposal, without establishing that proposal time equals actual start. The guard now uses this distinction: a completed Invoice followed by a later Fraud proposal paired to actual success proves correct recipe order; an overlapping proposal alone leaves order UNKNOWN; a paired actual Fraud dispatch before the observed Invoice completion establishes a known ordering violation. A real dispatch can supersede its prior proposal; repeated unresolved proposals/dispatches without unique pairing remain ambiguous. The implementation does not infer execution order from proposal-batch order.

TDD evidence: new tests first produced the expected two failures (later paired proposal incorrectly unknown; actual known misorder incorrectly unknown), while the overlapping-proposals test already returned UNKNOWN. After correction all 22 synthetic tests passed. No archive/data/labels read and no real fitting occurred.
