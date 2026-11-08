# Independent pre-fit methods review

Status: changes requested before real fitting. No critical defect found; two important items remain. This review uses the current files, not a historical commit. No real data, archive, labels, gold, selected cases or results were read. No fitting, benchmark, API, git operation or subagent was used. Only this review and its JSON companion were written.

## Findings

1. **Important — finite feature contract breaks for derived deltas (`ml.py:60–61`).** Two finite float values can subtract to infinity. A narrow in-memory counterexample using the authored fixture, `proposal.amount=1e308` and `facts.invoice_amount=-1e308`, emitted `amount_delta=inf`. This can abort sklearn fit/predict despite both amounts having passed the finite operand check. Check the derived delta for finiteness and emit an explicit invalid/missing state instead of infinity. The check did not fit a model or access data.

2. **Important — source-unscored CAL population is not separately reported (`ml.py:155–185`).** A source UNKNOWN episode predicted ALLOW is counted in `episodes`, with zero unsafe ALLOW and zero errors, but no scored/unscored denominator. Source UNKNOWN is correctly excluded from source-head training and does not certify legitimate/correct coverage; the missing part is explicit separate reporting required for honest interpretation. Add scored/unscored episode and checkpoint counts, and declare eligibility for mixed known/unknown annotations. Never report these unknown cases as established source-safe successes.

## Specification assessment

The explicit P4 conditions correspond to N02–N07. The implementation does not synthesize an invoice currency, USD-only rule, immutable initial account, blanket human registry, version/claim gate or semantic TaxCalc receipt. Known hard violations dominate missing evidence. Bare fact proof keys and full proposal/context proof keys match the interface, and the latest conflicting/unknown proof cannot authenticate an older convenient value.

Workflow checks recognize native `task_status=success` and explicit failure, use Fraud's vendor argument rather than inventing invoice_id, distinguish model proposal time from actual dispatch, accept a later Fraud proposal paired with a return after Invoice completion, leave overlapping proposals unknown, and flag observed actual misordering. Pairing remains intentionally conservative when repeated unresolved calls are ambiguous. The implementation relies on the collector's documented source/subject binding; this review did not inspect the collector or independently authenticate archived provenance.

ML uses a structural whitelist, finite native enums and equality/missing states; IDs, source paths, free text, actor names and labels are not vectorized. TRAIN-only vectorizer fitting, mean-one equal base-group weights, the declared two families/two heads/three seeds, source UNKNOWN exclusion, native UNKNOWN class, no/one-class fallbacks, raw probability preservation, no CAL refit, and separate optional gated outputs are present. The numeric delta exception above is the concrete whitelist defect.

The root clarified the target roles prospectively in the brief before any real fit: `scenario_decision` is the primary security head; `native_core` is an own-target secondary implementation diagnostic. That resolves the initial concern that native-head CAL uses core labels. Its feasibility must never select or certify a security winner. Normal CAL records and model payloads retain target/placement; the no-rows INFEASIBLE branch should retain them too. Cross-target scoring and source-category interruption reporting remain evaluator responsibilities.

CAL orders checkpoints by local event_seq and stops at the first BLOCK/UNKNOWN. It preserves infeasibility and an explicit UNKNOWN selective control. The primary scenario constraints use scenario labels. No data-dependent quality claim follows from this code review.

## Search cost and freeze acceptance

After equivalent-output deduplication there are at most 81 prediction vectors per checkpoint: UNKNOWN's threshold cannot change an UNKNOWN prediction, leaving only two effective threshold axes. With two checkpoints joint search is at most 6,561 combinations per model, although generation enumerates up to 729 tuples per checkpoint. Each combination rebuilds and sorts episodes, yielding an O(6561 * N log N) bound per model. No timing benchmark was performed. Root should bound the smoke/full-fit process and retain candidate counts; repeated identical checkpoint sorting can be moved outside the candidate loop if necessary without changing the grid.

The release writes source copies and hashes of sources, inputs, configuration and model bytes. `Predictor` itself loads joblib without manifest validation and calls functions from the importing module. Root must run the copied frozen source or verify the executed module hashes and weight hash before scoring; copying files alone does not prove which code executed. This is an integration acceptance condition, not evidence that an existing artifact drifted. No frozen artifact yet exists in this review scope.

Minor provenance matters: the method read log still records an older INPUT_INTERFACE hash; refresh it before freeze. Guard explanation source refs include all supplied proofs for a supported field, not only the accepted latest proof, so explanations may be overinclusive even when the verdict is based on the right record.

## Evidence and limits

The author's reported 22 tiny tests were inspected and not rerun. A single new no-fit in-memory check substantiated the two findings. It imported only the permitted methods/ML modules and authored fixture plus installed libraries, with bytecode writes disabled. No CatBoost or archive fit was run.

Pinned implementation SHA256:

- methods.py: `748dcf161d39872397a11148129f44bd8c465ff1b0d55fddb4fd4977ab00d194`
- ml.py: `1dcaf74f59ed102507c7bcaf3abe5229f48701aa8fbd4a740856fdf4b35527ca`

All allowed reviewed file hashes, the updated pre-fit brief hash, findings and limits are recorded in `method-review.json`. Source authenticity, common-view sanitation, reviewed labels, real-data compatibility, model quality and evaluator correctness require their separate root-owned acceptance.
