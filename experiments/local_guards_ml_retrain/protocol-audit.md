# Independent P2 protocol and methodology audit

Date: 2026-11-01. Scope: copied v4 4.1 policy/schema, frozen feature/gate implementation, independent development oracle, three safe CAL P2 observations and one in-memory counterfactual. No closed-test observations, gold, predictions, author, results, or other-thread v4.2 materials were opened. No model fitting, API calls, method edits, or full evaluation runs were performed. The task-provided aggregate counts and rates were not independently recomputed and are not the basis of this ruling.

## Ruling

**High severity for validity of a policy-faithful, same-information ML comparison; high confidence.** The frozen pipeline has an implementation/representation defect at P2. The mandatory gate's equality requirement between the current call ID and the completed delegation ID is an additional conservative restriction not required by copied A04. It can be conservative operationally while still being wrong as an implementation of the stated contract. This is not evidence of a financial safety exploit; it produces unjustified stops in the inspected safe cases.

A trusted completion proof may legitimately identify `context.delegation_call_id` while `context.call_id` identifies a different current checking call. Distinct values alone must not forbid continuation. They are not enough to establish safety either: successful completion, parent/child and subject linkage, trusted source, scope, prior event order, and applicable requirements must still be proven.

The prose could be made more explicit with a fact-specific equality table; its phrase “applicable ... call_id” does not itself spell out every equation. That documentation gap does not establish an obligation to equate two fields whose stated meanings differ. The development oracle consistently implements the completed-delegation interpretation, and the bounded CAL samples represent it explicitly.

## Source evidence

- `v4-POLICY.md:11-12`: P2 is after successful delegated completion and before downstream model/tool work, with scoped delegation linkage; technical completion is distinct from business fraud review.
- `v4-POLICY.md:45`: `call_id` and `delegation_call_id` mean “actual current call and completed delegation linkage.”
- `v4-POLICY.md:67,71,79`: `delegation_subject_matches` describes the actual completed child retaining parent scope, subject and attachment linkage; evidence requires applicable IDs, prior sequence and matching scope; its accepted attester is the server dispatcher/runner adapter observing actual parent/child execution. A model summary is not proof.
- `v4-policy.json:273-283` (A04): require the same scoped delegated subject, parent relation and successful technical completion before downstream inference/tool calls. No equality of current and delegated call IDs is specified.
- `v4-schema.json`, `$defs.context.properties.call_id` and `delegation_call_id`: separately declared nullable nonempty strings; the schema contains no equality constraint. Shape validation does not authenticate either value.
- `oracle.py:149-152`: comparison proof for `delegation_subject_matches` binds to `context.delegation_call_id`; other comparison facts use the current call. `oracle.py:317-324` requires completion, parent/delegation/actor linkage and attested subject, with actor/tool consistency.
- `features.py:101,116`: both tool-scope and delegation-scope proofs instead bind to current `context.call_id`; this rejects the legitimate delegation evidence before newest-proof selection.
- `features.py:167,170-178`: features retain current-versus-delegation equality and proof-versus-current-call relations, but not proof-versus-completed-delegation equality.
- `features.py:255-263`: P2 gate independently requires `context.call_id == context.delegation_call_id`, making a feature-only fix insufficient.

Inspected `features.py` SHA-256: `06bff0aa070c89fda38d2ff61ba03940f72521c02ae9a5fe837be05650719c7b`.

## Bounded verification

Prepared metadata was filtered to CAL/P2. An initial bounded archive selection yielded no inspected safe distinct-ID examples. Then the first 40 non-archive CAL/P2 metadata IDs were selected; ten had A=ALLOW. Only three qualifying safe distinct-ID observations were inspected, all labelled A=ALLOW and B=ALLOW:

| Prepared prefix | Delegated actor | Current and delegation IDs | Proof linkage | A oracle | A mandatory gate |
| --- | --- | --- | --- | --- | --- |
| `synthetic:p-00cc4763733aaa886a` | fraud | distinct | completed delegation | ALLOW | reject |
| `synthetic:p-ac4bb406c493c6cdb6` | invoice | distinct | completed delegation | ALLOW | reject |
| `synthetic:p-862d35659912b2d034` | invoice | distinct | completed delegation | ALLOW | reject |

In all three, the only gate reasons were `delegation_call_linkage_unavailable_or_mismatched` and `mandatory_proof_unavailable:delegation_subject_matches`. The proofs came from `server_context`, had `subject_matches=true`, `value=true`, and operation `typed_snapshot_compare`; the independent oracle found the applicable A requirements satisfied. These are declared synthetic producer observations, not proof that arbitrary JSON can authenticate a real execution.

One focused in-memory counterfactual used the first row: only `provenance.delegation_subject_matches[*].call_id` was changed from the completed delegation ID to an unrelated string different from both context IDs. The unchanged original oracle returned ALLOW; the foreign-proof oracle returned UNKNOWN, specifically A04.subject unknown. **The entire `features(row, 'new')` dictionary was exactly identical for the legitimate and foreign observations.** Frozen `evidence(..., 'delegation_subject_matches')` reported invalid for both; the mandatory gate returned the same rejection reasons for both.

This demonstrates actual information loss relevant to the policy. A classifier receiving this feature representation cannot distinguish this pair, regardless of model family, fitting or threshold. It does not prove that every observed error has this cause or that repairing this distinction will make the model safe.

The focused check used the existing Python environment at `/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv/bin/python`, with bytecode writes disabled. No packages were installed. Two preliminary interpreter attempts failed on missing NumPy/CatBoost before evaluating samples.

## Minimal correct relation and validation needed

For `delegation_subject_matches`, require a present completed delegation ID and `proof.call_id == context.delegation_call_id`. Keep `tool_scope_matches` bound to `context.call_id`. Remove the unconditional equality requirement between these two context IDs at P2; retain all other applicable proof and completion requirements. The producer must attest that the completed delegation is the actual relevant parent/child continuation, rather than allowing an arbitrary old delegation merely because its ID matches a supplied field. The pure guard assumes that trusted producer boundary; this change must not weaken it.

A future feature version should expose the correct fact-specific call relation (or explicit separate current/delegation relations), preserve same-scope/newest-record rules, and make legitimate versus foreign delegation evidence distinguishable. Changing only the gate cannot restore information already lost by the fitted model's feature view. Changing only the feature relation leaves the gate's unconditional distinct-ID stop in place.

Before a corrected version is frozen, validate at least: equal-ID and distinct-ID legitimate completions; proof matching current but not completed delegation; proof matching neither; missing delegation ID; unsuccessful completion; wrong parent/subject/session/workflow; untrusted or future proof; newest conflicting proof; and unchanged current-call binding for tool-scope facts. Confirm actor/tool linkage separately. If training features change, retraining and fresh CAL calibration are a new method version. No such changes were made in this audit.

## Honest completion of the current study

Preserve the original frozen methods, predictions, hashes and closed-test results as the result of the pipeline actually tested. Qualify the negative result: it evaluates this representation and conservative gate, and contains a demonstrated P2 policy-mapping defect. Do not present it as a clean determination that ML inherently cannot match the mandatory proofs, nor as a policy-equivalent same-information comparison. Giving both methods the same observation JSON does not remedy deletion of a decisive relation from one method's feature view.

The reduced false-ALLOW count remains an empirical property of the frozen pipeline, but cannot alone justify the equality rule or its safe-case stop cost. Raw model output is not a compliant substitute merely because its safe FPR is lower; mandatory policy proofs remain required.

This qualification is the smallest honest completion now. Do not silently patch, re-label the existing evaluation, select a corrected method using its released outcomes, or replace the original result. If a policy-faithful comparison is required as an additional deliverable, make a separately named corrected version, validate and freeze it before a newly authored independent closed test. Results of a correction on the already released 1200 cases would be explicitly retrospective/exploratory, not a fresh confirmatory result. Existing pre-release predictions retain their original temporal validity; discovering the defect does not retroactively imply test leakage.
