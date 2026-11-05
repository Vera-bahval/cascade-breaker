# Replay and normalization implementation

Implemented only `replay.py`, `normalize.py`, `tests/test_replay.py`, and this report.
No frozen source was edited, no commit was made, and no model/API call or dependency
installation was used. No new guard/runtime implementation, their tests, ML files,
new800 cases, or target predictions were read. This is conditional offline state
replay, not a rerun of archived agents.

## Decision-input and audit interfaces

- `adapt_payment320(row)` returns only a v4 observation. `payment320_variant(row)`
  returns that observation, per-field assumptions, `original_prefix_id`, the original
  proof payloads, and a complete original `payment_baseline` for audit/control use.
  It selects only named original input fields; labels and metadata are not read.
- The old320 context is an explicitly declared isolated synthetic technical fixture.
  Access/session infrastructure is declared separately from original payment facts.
  Existing original fact keys, including null/false, remain unchanged. Original
  proof array order, event sequence, subject flags, operation and scoped values are
  preserved. Missing proof arrays are never replaced with positive payment evidence.
  The old synthetic `native_store` currency input is represented as declared fixture
  currency, preserving its original value and chronology; original source/writer
  payloads are retained in the sidecar. Non-USD is never replaced with USD.
- `adapt_v41_fixture(row)` returns an audit wrapper for open old400 inputs. It adds
  declared technical origin metadata, retaining every old field, invalid shape,
  contradiction and absence. A child identity is added only for an original
  successful, fully scoped delegation with an already known parent/actor/call and
  matching original server evidence. 36 old400 rows meet that condition. Missing
  parents and incomplete/foreign delegation evidence stay unproven.
- `project_v41(observation)` removes only v4.2 origin and tuple additions. All 400
  adapted old400 inputs project exactly back to their original observations.
- `archive_variant(row, metadata, mode, unknown_portal, registry=None)` returns
  `observation`, `assumptions`, and `original_prefix_id`, retaining any original
  `payment_baseline`. Strict mode deep-copies the original observation unchanged.
  Session mode fills only missing/null session/user/namespace/portal/record fields
  and a declared session validation fact/proof. Known contradictions and malformed
  contexts are preserved; access and payment facts are not filled. Unknown portal
  has explicit vendor/admin branches. Technical mode additionally records origins
  of already observed evidence. Native-tool event indices generate deterministic
  simulated producing-call IDs, logged as instrumentation assumptions rather than
  historical call IDs. Existing scoped proof values are never filled or repaired.
- A technical caller may explicitly supply `ArchiveReplayRegistry()` and feed
  original rows in event order. Original source-verified P0 scope may establish
  a declared counterfactual claim acquired before that entry. The same original
  namespace/session/workflow reuses its original root key, even if a later proposal
  targets another invoice. Another workflow or missing root gets no claim. There is
  no cross-episode state or concurrency. Episode metadata supplies only a join key.
  Independent row calls leave missing claims unknown. No approval binding, account,
  financial material, missing parent, or human decision is manufactured.

## Structural normalization

`normalization_version = "finbot-structural-v2"` is fixed. `normalize()` returns
canonical hashable JSON. It unwraps observation wrappers and strips root-level
join/source metadata, including nested input `prefix_id`; `proof.source` remains.
Arbitrary ID spelling is renamed in globally consistent equality classes, including
parent/child, source-call and snapshot IDs and structured claim keys. Scalar types,
invalid IDs and proof shapes remain distinguishable. Event ranks preserve relative
order/equality; proof and array order stay intact. Null/absent, facts, generation
values, tools, actors, operations, sources and origin categories remain visible.
Unlike the old audit normalizer, positive claim generations are not collapsed.

The raw v3 rows carry `prefix_id` and `untrusted_text` and lack `context` and
`schema_version`. Raw v4 adds scoped proof payloads and a technical context. v4.2
adds origin and delegation tuple fields. Those cross-version schema differences
survive normalization unless explicitly covered by the representation adapters;
different hashes alone do not establish semantic novelty or unseen mechanisms.

| Input | Rows | Episodes with prefixes | Groups | Exact unique views | Normalized unique views | Normalized duplicate groups | Rows in those groups |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| old320 | 320 | 320 | 160 | 320 | 239 | 50 | 131 |
| old400 | 400 | 400 | 200 | 400 | 341 | 29 | 88 |
| archive | 83099 | 3373 | 308 | 83099 | 21747 | 11084 | 72436 |

These are raw representation counts, not performance metrics. The archive outcomes
list 3,378 episodes, of which five have no prefix; all 83,099 available prefixes are
covered. Strict replay preserved every observation and all 2,051 payment baselines.
Both session portal branches changed 83,099 rows and logged 320,220 assumptions
per branch. Both independent technical branches logged 1,458,724 assumptions per
branch. The explicit stateful technical branch admitted 1,118 isolated episode roots
and supplied 30,692 claims/claim assumptions; unadmitted roots remain unknown. No
out-of-order source prefix was observed within an episode. These claims express
counterfactual recording infrastructure, not historical admission evidence.

## Verification and limits

`python3 -m unittest discover -s experiments/local_guards_v4_followup/tests -p test_replay.py`
passes 11 authored tests. They cover label-independent adaptation, source/currency
boundaries, missing/future/foreign proof preservation, strict immutability, session
limits and invalid values, missing parent and binding preservation, scoped fixture
delegation, counterfactual root admission/reuse, reversible v4.1 projection and
normalization equality/shape behavior. Modules also pass `py_compile`.

Full frozen-input checks established: all 320 original fact mappings preserved;
all 320 original proof time/subject/operation sequences preserved; complete original
payment baselines retained; all 400 adapted inputs project exactly to original;
all 83,099 strict observations unchanged. No guard prediction was used to choose
or tune a conversion. A general project suite was not run here because this
worker must not read or execute another worker's new guard/runtime/tests. The
controller owns method evaluation and full-contract sufficiency reporting.

Archive approval and material account bindings remain unavailable. A declared
admission does not establish approval, provenance completeness, production
atomicity, cross-workflow coordination, or actual native execution. None of the
representation statistics establishes autonomous business authorization.

## Source reads

Read the approved `PLAN.md` and `provenance/implementation-brief.md`, canonical
workspace `AGENTS.md`, and skill workflow documentation. The only frozen code read
was v3/v4 `prepare_data.py`, v3 schema/policy and source-selection lines in
`rules_v3.py`, v4 schema/policy, and the allowed old `closed_review.py` normalizer
source (the initial broad read also exposed surrounding audit code). Frozen input
reads are listed below; old400/old320 metadata was used only for join/group counts,
and archive outcomes only for episode IDs. No old action gold or predictions were
read. The native memory registry was briefly searched for general research
limitations before source inspection; it supplied no conversion facts or labels.

| Read path relative to worktree | SHA-256 |
| --- | --- |
| experiments/local_guards_v3/schema.json | `62efd6d8ec3b1dced204d3705c9c2691b7e9af1d503c4327ce388e1e6be84711` |
| experiments/local_guards_v3/policy.json | `bdaaffe0715d7b7233cc40e1ce7f6ada7989bac927269998aa5827d385f65c85` |
| experiments/local_guards_v3/prepare_data.py | `89490353defde60ab46136de29cf0f1ed12c23f85f56c5d1ede99b0c5bd584f9` |
| experiments/local_guards_v3/rules_v3.py | `279a3b8bfc37f4244e67696eba0150c84ed71d67a0f6b527dc32279c002bf38b` |
| experiments/local_guards_v3/closed-test/observations.jsonl | `51b33abbb8b7abf0785662a6dd32b358baa5383b10bfe7d91de73e89d9ac7c2d` |
| experiments/local_guards_v3/closed-test/metadata.jsonl | `3ff7488e627a720df70a433d839ac13c6855dc6c80584a0d9371da233c7fa952` |
| experiments/local_guards_v3/closed-test/manifest.json | `d959869b85d440de74b59e8e3b186ab6ccf0855db1fb8179841b41f6e06bca13` |
| experiments/local_guards_v4/schema.json | `9e75dd6e2ae4cfac702b706d1a2b5408f71d6525b40c4a4dee3fc8fbbc04a07b` |
| experiments/local_guards_v4/policy.json | `5456778530e32b508cbf5d4f9eab78d383d83a91c927fefdf5e8f2e6b04492ca` |
| experiments/local_guards_v4/prepare_data.py | `8a547a818d594a205697178245addae36d3a6e343255196e2ca855e77d13f14a` |
| experiments/local_guards_v4/closed_review.py | `4b48954c1c614260b5f1559dfb2dd4632827b7133be47b8889ac2e87ab9e2e26` |
| experiments/local_guards_v4/closed/observations.jsonl.gz | `c2b16024bbb4340bfffffb3f4dec22d43c4efe3462428ed694e75e56e7696431` |
| experiments/local_guards_v4/closed/metadata.jsonl.gz | `5abd56023d4995e217c957319105fceb527529d591ffb678bcf729c977cb18e3` |
| experiments/local_guards_v4/closed/manifest.json | `45d88f92388ca855ef708abb95bb1fe3fbf7645b4fe0ffc2c67e3167e269136c` |
| experiments/local_guards_v4/data/observations.jsonl.gz | `39750b329b3d676278c961893d60bab9b365c19fdf7f7eba9c01971ae0894945` |
| experiments/local_guards_v4/data/metadata.jsonl.gz | `0be15458667634576417d9b4805bf5c538b13a278628d2a620ed16eeac4e928b` |
| experiments/local_guards_v4/data/manifest.json | `166de9022fbf500edcd64ad886d4d65bdfec885bbe806b9c35bbad251072407c` |
| experiments/local_guards_v4/data/gold-outcomes.jsonl.gz | `6a27c16b35a1f4c9b240aeec76329dd64c516d1daf757dc20007f1ec2eb31b65` |
