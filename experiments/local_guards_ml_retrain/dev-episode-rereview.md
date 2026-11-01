# Task 1 experimental-unit fix re-review

Reviewed the supplied `review-4dcf31e..26774d2.diff`, the appended author report, and the changed generator/tests/manifest/read-log at HEAD `26774d2e6abefb2c652eba47ccbdc81ca9f0d9a4`. Scope is the independent-state episode correction and its preservation of scientific inputs. No broad re-review, suite rerun, model/API call, subagent or commit was performed.

**Status: ADDRESSED. Spec compliance: PASS. Code/data quality: PASS within this fix scope. No new material defect found.**

The original four variants in a base group are alternative counterfactual states at the same position, rather than a chronological execution. Replaying them under one episode ID conflated dependency grouping with execution identity. In particular, an unsafe alternative could erase a safe alternative from the fully-safe episode denominator. This was an experimental-unit defect; the previous review's grouping checks did not establish correctness of replay grouping.

`generate_dev.py:447` now derives each synthetic episode ID from its existing distinct prefix ID. This is a deterministic change to metadata identity, with no dependency on labels, predictions or fitted performance. Four counterfactual variants retain their original common `group_id`; collision-connected groups retain `split_group_id` and their original TRAIN/CAL assignments. The fix therefore separates three different units correctly: an independent one-state synthetic episode, a base group for fitting weights, and a collision component for split/bootstrap clustering. It does not pretend that these synthetic states are full observed execution trajectories.

The manifest records 8000 independent-state episodes and the 6000 TRAIN/2000 CAL split (`generate_dev.py:483–484`); the read log records the same unit distinction. The held-out author/reviewer brief amendments carry this interpretation forward and still permit episode sharing for genuine sequential steps.

The new tests exercise the actual defect: 8000 distinct one-prefix episodes, four episode IDs per base group, the absence of fake temporal ordering, and equality of safe synthetic CAL episode/action denominators for A/B. A separate regression invokes the canonical generator with publication captured in memory and compares exact published metadata, manifest and read-log bytes. This is meaningful coverage of the generator interface rather than a standalone metadata rewrite. The author records two failed-first tests, then 31 passing own tests and exact canonical regeneration; these are author-run results reviewed here, not reviewer reruns.

## Preservation readback

A bounded reviewer byte/metadata comparison against `4dcf31e` independently confirmed:

- Old and new metadata each contain 8000 rows; row-by-row, every field except `episode_id` is exactly equal. Prefix order, base groups, families, source, checkpoint, split and collision-component IDs are preserved.
- New metadata has 8000 distinct episode IDs: 6000 TRAIN and 2000 CAL.
- Observation gzip bytes, complete gold gzip bytes and oracle source bytes are unchanged from the pre-fix revision.
- Published stream hashes match the current manifest.

The generator diff changes only episode identity and its descriptive manifest/read-log fields. Scenario generation, labels, monetary/proof values, normalized signatures, collision splitting and source policies are unchanged. The author reports safe CAL denominators of 787 for A and 501 for B, matching existing safe action counts. Those positive denominators make the constraint evaluable; they do not establish model feasibility, safety performance, or a successful calibration result.

The abort receipt records the partial 66-model run as `ABORTED_BEFORE_METHOD_FREEZE_AND_TEST`, preserves artifact hashes and its reproduction revision, and states that no models/thresholds were selected from it. Removing the invalid prepared copy is consistent with preventing stale metadata reuse. These are orchestration/provenance actions, not evidence of changing the data method or model settings. This re-review does not independently audit those models, scratch retention or future rebuilt prepared inputs. The parent must use newly prepared inputs and a fresh accepted calibration/freeze rather than treating the abandoned run as valid evidence.

Acceptance closes the scoped episode-unit defect. The prior reviews' producer-bound trust, structural deduplication and downstream weighting limitations remain; later training/evaluation must preserve base-group weights and collision-component bootstrap clustering despite the now distinct episode IDs. Only this re-review report was written.
