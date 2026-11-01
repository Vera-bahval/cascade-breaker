# Raw archive collector and split receipt

Task 2 is complete for the existing 3,378-episode registry. This collector reads raw archives and initial fixtures again; it never imports an old observation reducer, detector, action oracle, or inference client. Previous strict episode/metadata files serve only as inventory and join indexes. Source outcomes are a separate, explicitly unverified old-target sidecar.

## Interface and artifacts

`data/historical/observations.jsonl.gz` contains 5,410 canonical schema rows. Each has `prefix_id`, `episode_id`, `checkpoint`, `event_seq`, `observation`, `raw_context`, `evidence_status`, and `mode`. All rows use schema representation `mode=reconstructed_state`; historical versus instrumented is the directory variant, not an invented schema enum. `data/instrumented/observations.jsonl.gz` has the same rows and identical business facts, proposed actions and raw contexts. Only recorded technical call/source/parent links differ, with `instrumented` provenance. This is offline collector replay, not a new executor run or recovery of original authorization.

`data/split-metadata.jsonl.gz` joins prefix IDs to episode/executor/group/split/source provenance. These are audit fields, never model features. `data/split-episodes.jsonl.gz` preserves every registry episode, initial scenario lineage and availability, including episodes with no applicable cut. `data/group-lineage-receipts.jsonl.gz` records 3,089 union edges. `data/source-alias-receipts.jsonl.gz` records 640 byte-identical raw source aliases; aliases do not become extra episodes. Exact group membership, sizes, seed, selection strata and predeclared challenge mechanisms are in `data/split-manifest.json`.

Developer packages are `packages/TRAIN/` and `packages/CAL/`, each with compressed canonical observations, join-only metadata, policy/schema copies, and a **separate** unverified source-label sidecar. They contain no selected representative/challenge rows, archive outcomes, predictions or independent native-action gold. Source truth/old stop labels are never collector features or fitting targets. Independent labels must be provided separately before fitting.

`data/archive-outcomes-unverified.jsonl.gz` is evaluator-only copied historical outcome evidence under its old target. It is not a new native harm adjudication. P4 itself is before the proposed transfer result; successful transfer results enter a predictor row only when genuinely earlier than a later cut. There is no claim of measured prevention.

`provenance/collector-read-log.json` records exact raw member/Git blob hashes and roles. `data/collector-manifest.json` records inventory and omissions. `data/artifact-hashes.json` hashes generated data/packages; `data/verification.json` records the checks and principal hashes.

## Counts

| Partition | Groups | Episodes | P2_afterFraud | P4 | Rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| REPRESENTATIVE | 58 | 754 | 749 | 547 | 1,296 |
| CHALLENGE | 29 | 1,245 | 1,223 | 577 | 1,800 |
| TRAIN | 151 | 876 | 866 | 646 | 1,512 |
| CAL | 51 | 306 | 303 | 253 | 556 |
| HOLDOUT_LUNA | shared development groups, excluded from fitting | 197 | 195 | 51 | 246 |
| Total | 289 disjoint union groups | 3,378 | 3,336 | 2,074 | 5,410 |

All 3,378 episodes were resolved to raw bytes: 3,371 have a nonempty normalized raw prefix; seven legacy runs have no raw tool/model prefix and remain inventoried. Forty-three episodes have no P2/P4 cut (including those seven), which is not fabricated into a checkpoint. The five control-off episodes with zero old observations contain real raw events and now yield causally ordered cuts. Of the 3,336 Fraud boundaries, 3,303 have a paired same-subject success, 27 a paired failed return, and six incomplete/unmatched linkage. Failed returns are retained. Complete-prefix status is true for 5,401 rows and false for nine.

5,270 prefix IDs exactly join the previous strict metadata index. The remaining 140 are newly recovered/incomplete-return cuts; their `original_prefix_id` is null. The old v4 identity formula is reproduced, including its historical event sequence, rather than assuming the v3 prefix hash was retained.

The registry cohorts remain 1,352 original-main, 1,864 historical-additional, 108 censored-enforce, 32 pilot, 15 legacy-additional and seven partial episodes. Enforced/censored runs are usable only for their observed prefix; they are not unrestricted continuation evidence. Source revisions are verified from actual main manifests for 594 PR477 executions and directly recorded legacy revision receipts for 357 runs. The other 2,427 do not acquire a verified code revision merely from an old registry declaration.

## Reconstruction and selection

P4 is immediately before each recorded transfer proposal. Hook archives preserve actual one-based row indices and use `event_seq=2*index`; after-Fraud boundaries use the actual return row and `2*index+1`. Legacy logs retain source JSONL line plus exact `/steps/index` pointers and native step sequence. Where a legacy callback exists, it supplies the cut. Where control-off lacks callbacks, a recorded model `tool_calls` proposal supplies a derived cut, explicitly marked `recorded_model_proposal`; no historical before-tool hook is invented. A proposed call alone does not prove an attempt, completed transfer or harm.

State uses the latest causally relevant same-object successful observation. Native current invoice amounts and vendor accounts replace older observations. Negative amounts remain negative. Foreign workflow/session returns cannot complete another call; foreign namespace results cannot replace current object state. Opaque SystemUtils writes invalidate potentially changed state until observed again. Errors are raw evidence, not state. Initial transaction absence is used only when the initial collection was actually captured. Review/exception/HOLD summaries and source instructions remain raw semantic evidence; there are no `human_approved`, `binding_hold`, `legitimate_exception`, immutable-account or fake invoice-currency features. A pinned callable default is represented as a transfer default, not a USD-only business rule.

Raw contexts retain every pre-cut native argument/result, distinct user message, model output and observed callable availability/schema. Exact repeated user messages are explicit references to their earlier event, not character truncation. Provider/model identifiers, timestamps and repeated platform system boilerplate are omitted. Predictor views must exclude join/provenance IDs; some old native invoice numbers/namespaces themselves encode case slugs and require the same opaque equality-preserving identifier transformation for every method. Their original values remain in the custodian archive for audit.

Groups union explicit pair/base lineage, recognized base/control variants, exact normalized initial descriptions across executors regardless of amount, and repeats. No old amount/text fingerprint is reused. The largest group has 193 episodes. Groups are never cut to approach an episode percentage. Seed 17 selects `ceil(20% * 289)=58` representative groups with origin/verified-version-availability stratification, then `ceil(10% * 289)=29` challenge groups from the remainder by fixed HOLD/amountbounds/recipient/materialchange/access/delegation/SystemUtils/repeat coverage. This is 30% of groups, not 30% of episodes: selected groups contain 1,999 episodes. Remaining groups split 151 TRAIN / 51 CAL; Luna episodes are excluded from both packages. Selection never consults a new prediction, target decision or transfer result status.

Additional raw inventory contains four tar sources with no hook episodes and six unique Git hook candidates absent from the registry: four declared offline fixture replays and two saved continuations of existing incidents. They are explicitly classified rather than counted as independent historical executions. Missing on-disk sources were recovered with `git cat-file blob <oid>` using the source inventory strictly as a locator, with SHA-256 verification against raw bytes.

## Verification and reproduction

Twelve focused tests pass: latest amount/no future result, real negative value and no invented human/currency facts, paired failed Fraud/inherited subject, current account/foreign invoice, foreign workflow, truncated prefix, pair/repeat/executor grouping, Luna exclusion/deterministic selection, and the exact native `recommended_action` field without free-text keyword inference. Whole-artifact checks validated all 10,820 historical/instrumented rows against `schema.json`, unique IDs, all 3,378 episode identities, no future event/provenance sequence, identical business/raw information in both variants, disjoint group partitions, package membership, no Luna fitting/calibration, and final policy hash `31727d8173217fe269f4188635bc68757e3b063db626c4dc78e230b2a0909775`.

Run from the worktree root:

```sh
PYTHON=/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python
$PYTHON -m unittest discover -s experiments/local_guards_archive_comparison/tests -p 'test_collector.py'
$PYTHON -m unittest discover -s experiments/local_guards_archive_comparison/tests -p 'test_split.py'
$PYTHON experiments/local_guards_archive_comparison/collector.py
$PYTHON experiments/local_guards_archive_comparison/split.py
```

No fitting, benchmark, executor call, external API, commit or previous-experiment mutation was performed by this task. The archive remains previously exposed historical data, not a blind generalization sample.


## Source-field correction before method freeze

A source-field review found that `flag_invoice_for_review` uses the typed argument and return key `recommended_action`, not `action` or `recommendation`. The collector now reads exactly that field. The exact PR477 source is `a7f6964fbc60da807e2544d826a5b4e20eb0c5dc:finbot/tools/data/fraud.py` (signature and returned dictionary), and all 1,842 unique native flag returns visible before current cuts carry the native field in their arguments. For example, `finbot477_nanobase_fpr_20261020_203813/TH603-r1` has `recommended_action=escalate`; the source result likewise returns `recommended_action: escalate`. A focused test failed with missing recommendation, then passed after the one-line parser correction; a free-text occurrence of “reject” cannot create a typed recommendation.

Canonical rows, instrumented rows and TRAIN/CAL packages were regenerated before any fitting or inference. `data/recommended-action-correction.json` records source hash, actual event evidence examples and before/after field counts. All representative/challenge/TRAIN/CAL group lists, strata, mechanism sets, IDs, raw contexts, proposed actions and every other business fact are verified identical to the pre-correction artifact. The selection is unchanged; only the restored typed recommendation and its provenance/status differ. Current artifact hashes replace the earlier receipt in `data/verification.json` and `data/artifact-hashes.json`.

After correction the 5,410 predictor rows contain 1,179 `escalate`, 1,247 `hold`, 85 `reject`, and 2,899 unavailable typed recommendations. These are repeated cut observations of native fields, not counts of independent flags or binding-clearance labels.


## Paired-source correction before method freeze

A foreign workflow/session getter result can no longer replace native invoice/vendor state merely because its tool name and arguments match. Native result ingestion and opaque-script state invalidation require a valid paired source call. The focused corruption test first failed with a foreign result replacing the invoice amount; it now preserves the previous facts, marks the prefix incomplete and retains the foreign result as raw evidence.

A bounded archive check found no affected ordinary tar-hook ingestion. Legacy source logs additionally contain real saved model batches: for example `att-baseline_clean-f87408` has a Fraud model output at source step 39 with calls to risk profile, invoice details and invoice history, followed by actual sequential results at steps 40–42. Treating all proposals as a strict execution stack falsely made the first two returns unpaired. The collector now binds a return's original call ID when recorded, otherwise requires unique exact name/arguments and caller/workflow/session within that specific recorded model batch. Duplicate same-argument calls without distinguishing return IDs remain unresolved. Ordinary hooks and delegation maintain strict stack pairing. A model batch establishes a proposal set; state chronology follows the actual response events and never implies parallel dispatch or invented start timestamps.

Exactly one whole collector/split regeneration followed CPU-clear. The audit found 81 changed legacy rows in 47 episodes (38 P2 and 43 P4), with zero changed tar/direct rows. Only two fact fields changed in 72 rows: `fraud_delegate_completed` and `fraud_review_history`, from genuine newly linked Fraud return receipts. Caller actor/call ID were recovered in 38 P2 rows, and complete-prefix status changed false to true in 81 rows. Fraud success counts changed from 3,265 to 3,303; failed returns stayed 27; unresolved returns changed from 44 to six. Complete-prefix rows changed from 5,320 to 5,401. Every amount, account, status, typed recommendation, raw context and proposed action remains identical.

All original 5,410 row identities, group partitions, mechanisms, strata and four episode/metadata sidecar files are unchanged, with metadata proven byte-identical. `data/pairing-correction.json` records the complete per-row semantic deltas and metadata hashes; `data/pairing-before.json` is a hash-only baseline plus limited prior completion/context values. The regenerated canonical and developer package hashes are current in `data/verification.json` and `data/artifact-hashes.json`. All 10,820 schema rows and mode-equality/causality/package checks pass; ten collector tests and two split tests pass. No fitting, new prediction, raw extraction or source/status mutation was performed.
