# Revision2 execution evidence

`benchmark_revision2.py native --freeze experiments/local_guards_ml_retrain/frozen_revision2 --output experiments/local_guards_ml_retrain/results/revision2/native --repeats 5` completed with exit0:151 methods,743 native trials/shards. Numerical runtime used OMP/OPENBLAS/VECLIB thread limits2. No single/load/scoring was run by this worker during the native command. CPU-clear was sent immediately on completion.

**Timing qualification:** the controller subsequently reported that a CPU-heavy independent closed2 audit started before its hold arrived and overlapped this native run. Therefore `results/revision2/native` is preliminary and **excluded from primary latency evidence**. Effects/status evidence remains retained. The entire first output and log are preserved unchanged.

A later coordinated quiet window may repeat native into a new `native-quiet` directory, followed sequentially by single/load after observation acceptance. This repetition is justified by known CPU contention, not result selection. No further timing has been run under the present instruction. Source/method files and closed2 gold/source/report/manifest were not opened or changed by this worker.

## Coordinated quiet timing — completed

After explicit controller START, accepted source hashes matched:

```text
benchmark_revision2.py 455d72ee231ab4afc7fece0c31bb27d7081f72d288e9606d0a7c178cb779a79c
evaluation_revision2.py bca229e7075d38bae6ef77a64f12433ab37f375edf7a2860a2f119b3fb1b7e3c
replay_predictions.py 06d2eeb0d61a125af9ba8cff93d680600b6137de8b921564b9c38dcb661e85d4
```

The following ran sequentially under one quiet hold with numerical threads2,
using `frozen_revision2` and accepted `closed_revision2/observations.jsonl.gz` +
`metadata.jsonl.gz` for single/load. No gold was needed by timing:

| Output / command | Exit / workload |
| --- | --- |
| `native-quiet`: `benchmark_revision2.py native --repeats 5` |0;151 methods,743 trials/shards;37 completed,706 stopped|
| `single`: `benchmark_revision2.py single --repeats 5 --limit 128` |0;147 methods,94080 individual records,735 shards;128 states per contract×5|
| `load`: `benchmark_revision2.py load` |0;72 fresh workers/response records/shards|

Every command included explicit `--freeze frozen_revision2` and fresh `--output`;
exact argv, inputs, raw data, environment and hashes are in its summary/artifacts.
CPU-clear was sent immediately after load. No scoring/inference overlapped this
quiet sequence. Earlier `native` remains preserved and excluded from primary
latency due to its independently reported CPU contention. STOP/completion and
pre/post-transfer effects remain separate evidence; no STOP speedup is claimed.

## Released offline execution — completed

Only after controller CPU release, score the already committed NEW1200 original
and revision2 replay outputs against matching controls and explicit registry.
Gold release followed blind prediction commit
`b7afad7c7e2982fa95512d13bb2077e3c85c7b2a`. These two parent-owned predictions
were not duplicated. NEW1200 gold was read by the released score commands;
author/source/review content was not needed. Both primary scores completed first
and completion was sent immediately so the independent analysis writer could
work in parallel.

All scoring used `evaluation_revision2.py score`, bootstrap1000 and explicit
`--model-freeze frozen` for NEW1200 original versus `--model-freeze frozen_revision2`
for every revision2 score. CAL/archive used explicit2727/3378 episode registries.
Old320/first1200 metadata-only registries preserve all original IDs and have
separate receipts under `registries/`; old400 used its existing episode registry.

After primary scoring, accepted `replay_predictions.py --method-revision revision2
--freeze frozen_revision2 --batch-size 128` produced raw/gated/argmax streams for
CAL, old320, old400, first1200 and finally archive. Old320 alone restricted
`--contracts payment_v3`. Input paths and output roots are the prepared execution
plan's exact table, with fresh `*-ml-wrapper` destinations. Existing identical
rule/TFIDF controls were reused; none were rerun.

| Score output | Methods | Eligible states payment /A /B | Explicit registry |
| --- | --- | --- | --- |
| `results/closed2/original-scores` |219|460 /1180 /1180|1200|
| `results/closed2/revision2-scores` |219|460 /1180 /1180|1200|
| `results/revision2/cal-scores` |222|1342 /20719 /20719|2727|
| `results/revision2/old320-scores` |76|320 /not applied /not applied|320|
| `results/revision2/old400-scores` |222|184 /400 /400|400|
| `results/revision2/first1200-scores` |219|460 /1200 /1200|1200|
| `results/revision2/archive-scores` |222|2051 /82855 /82855|3378|

Every command exited0. CAL eligible/safe episode denominators remain
payment1342/616, A2725/787, B2725/501. New1200 includes20 episodes without an
applicable full-contract guard decision; all1200 input prefixes/registry members
remain retained. Unsupported ordering/method errors use the reviewed execution
policy; unassessed chronology does not earn prevention credit. No source,
feature, model, threshold, fit or new test was changed/run by this worker.

Final archive receipt:83099 input prefixes,216 method streams,360 deterministic
gzip shards and12078792 records; `labels_opened=false`.
Receipt SHA256:
`9b899574f43ef1a1a0d3a82b1c44d6e7245d5028b1e2d9b6031eb20df3ad9d89`.
Largest archive prediction shard2380675 bytes; every raw shard is below100MB.

## Storage and final identity checks

No manual full-input/output copies, deletions, restarts, unsafe signals or staging
were performed. Free disk was monitored before/during archive replay; the accepted
wrapper's temporary caches consumed about881MiB and cleared on successful exit.
The controller coordinated exact-commit, Git-retained V1 working-copy storage
relief separately and was notified immediately after cache-clear for restoration.
This worker did not stage/restore another owner's files. Free disk at archive
score completion was649MiB.

All seven prediction receipt shard sets and all ten quiet-timing/score artifact
hash tables match. Accepted source hashes remain exact. New gold hashes match
both released primary score inputs. Full counts, receipt/metric SHA256 values,
model-freeze identities and verification results are in `execution-checks.json`:
`f86a593ed3616a1752481b5b3c4fbf444f4a458702228d00df8022ca908ed074`.

All requested execution is complete and no compute remains. The analysis writer
owns interpretation/main reports. These execution records make no realLLM,
production safety, cost or generalization claim.
