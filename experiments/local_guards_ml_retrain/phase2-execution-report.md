# Original assessment execution, version1

Original frozen sources/models/thresholds are unchanged. These results describe
the original implementation with the confirmed defective binding in features /
proof gate. They do not establish intrinsic ML failure. The final Russian report
and corrected-assessment interpretation are deferred.

Start HEAD: `4b40245f5a8d70b8111766f23a8c980acad42b29`.
Output root: `experiments/local_guards_ml_retrain/results/original-v1/`.
Every command uses native `.venv-finbot/bin/python` and
`OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2`.
The native, single and load commands ran sequentially; CPU-clear was sent before
any scoring or archive preparation. No remote inference API was called.

## Completed timing evidence

| Command | Evidence |
| --- | --- |
| `benchmark.py native --freeze experiments/local_guards_ml_retrain/frozen --output experiments/local_guards_ml_retrain/results/original-v1/native --repeats 5` | exit0;743 trials/shards:72×raw/gated×5,4 controls×5,3 explicit diagnostics |
| `benchmark.py single --freeze experiments/local_guards_ml_retrain/frozen --observations experiments/local_guards_ml_retrain/closed/observations.jsonl.gz --metadata experiments/local_guards_ml_retrain/closed/metadata.jsonl.gz --output experiments/local_guards_ml_retrain/results/original-v1/single --repeats 5 --limit 128` | exit0;94080 individual records;147 methods;128 applicable states per contract,5 passes |
| `benchmark.py load --freeze experiments/local_guards_ml_retrain/frozen --observations experiments/local_guards_ml_retrain/closed/observations.jsonl.gz --metadata experiments/local_guards_ml_retrain/closed/metadata.jsonl.gz --output experiments/local_guards_ml_retrain/results/original-v1/load` | exit0;72 fresh workers and72 response/RSS records |

Commands use `experiments/local_guards_ml_retrain/benchmark.py`. Each output
contains `summary.json`, raw gzip shards, source hashes, reproduction argv and
`artifact-hashes.json`. Native STOP/completed chain distributions remain separate;
load response availability and process teardown remain separate. Warm filesystem
and whole-process RSS caveats are retained. Logs are `native.log`, `single.log`
and `load.log` under the output root.

## Scoring and prediction evidence

All `evaluation.py score` commands use `--bootstrap 1000`. Predictions and complete
method-prefix coverage are verified before label/outcome IO. All ML streaming
predictions use `--freeze experiments/local_guards_ml_retrain/frozen
--batch-size 512`; they preserve raw, gated and separate argmax diagnostics.
Rule controls use `--contracts payment_v3 A B --tfidf`, except old320 which uses
`--contracts payment_v3 --tfidf`. Closed uses the already committed original
raw/gated file and three previously blinded rule controls.

| Dataset / output prefixes | Input directory | Completed readback |
| --- | --- | --- |
| `closed-scores` | `experiments/local_guards_ml_retrain/closed/` | exit0;219 all-slice methods;payment460,full A1200,full B1200 |
| `cal-inputs`, `cal-ml`, `cal-controls`, `cal-scores` | original `prepared/`, metadata split CAL | all exit0;20753 retained prefixes, original IDs;222 methods;payment1342 states/1342 episodes/616 safe;full A20719 states/2725 episodes/787 safe;full B20719 states/2725 episodes/501 safe;all-registry2725 for every contract |
| `old320-ml`, `old320-controls`, `old320-scores` | `experiments/local_guards_v3/closed-test/` | all exit0;76 methods;320 payment states |
| `old400-ml`, `old400-controls`, `old400-scores` | `experiments/local_guards_v4/closed/` | all exit0;222 methods;400 full A/B states,184 payment states |
| `archive-ml`, `archive-controls`, `archive-scores` | `experiments/local_guards_v4/data/` | all commands exit0;83099 input prefixes;216 ML streams/360 shards/12078792 records;222 scored methods;payment2051 and full A/B82855 eligible states;prefix-registry outcome denominator3373, with five zero-prefix episodes separately disclosed below |

Input basenames are `observations.jsonl.gz`, `metadata.jsonl.gz`,
`gold-actions.jsonl.gz`, `gold-outcomes.jsonl.gz`; old320 uses `.jsonl` without
`.gz`. CAL uses `cal-inputs/{observations,metadata,labels}.jsonl.gz` and no outcome
file. CAL observation/metadata selection used only original metadata split CAL;
its labels subset was written only after both prediction receipts existed.
`cal-inputs/input-receipt.json` and `label-subset-receipt.json` preserve selection,
source hashes and prediction receipt identities.

Closed scoring command:

```sh
$FINBOT_ML_PY experiments/local_guards_ml_retrain/evaluation.py score \
  --predictions experiments/local_guards_ml_retrain/results/closed-ml.jsonl.gz \
    experiments/local_guards_ml_retrain/results/closed-controls \
  --observations experiments/local_guards_ml_retrain/closed/observations.jsonl.gz \
  --metadata experiments/local_guards_ml_retrain/closed/metadata.jsonl.gz \
  --labels experiments/local_guards_ml_retrain/closed/gold-actions.jsonl.gz \
  --output experiments/local_guards_ml_retrain/results/original-v1/closed-scores \
  --bootstrap 1000
```

For every other dataset, the executed commands are the existing `evaluation.py`
`predict`, `controls`, `score` interfaces with the input directory and output
prefixes in the table; old320 alone limits ML and controls to payment_v3. CAL
score additionally uses `--split CAL`. Old320/old400/archive score includes its
original `--outcomes` file. Exact source identities and input SHA256 values are
in prediction receipts / metric JSON; every shard has its hash. Each completed
score directory contains `metrics.json`, `metrics.csv`,
`frozen-calibration.json`, `artifact-hashes.json`. Command stdout/stderr is saved
under the output root as `<output-prefix>.log`.

Closed payment460 is the primary all-state denominator, not460 independent
payment policy states. Original base/split-group intervals do not add the
post-release v3-obligation duplicate components; payment view-balanced/dedup
sensitivity and stronger clustering remain separate later postprocessing.
Historical320/400 and the complete archive are open diagnostics. Missing outcomes,
state/source evidence and original splits are retained; no outcome was supplied
as a feature. No new threshold or replacement operating point was selected.


## Final execution readback

All requested existing CLI runs completed with exit0. No source, model,
threshold or protected baseline file was edited. No additional tests, fits,
threshold searches or timing reruns were performed. No active compute remains.
`results/original-v1/execution-checks.json` records source/input identities,
method counts, receipts and final artifact-hash verification. Its SHA256 is
`6c8197395eac3432efe5cd07668c332220b2fef04d32192896ed74426f36fe39`.
All eight completed benchmark/score artifact hash tables match;72 frozen methods
and the protected baseline match. Largest saved file:18708826 bytes.

Final archive commands:

```sh
$FINBOT_ML_PY experiments/local_guards_ml_retrain/evaluation.py predict \
  --freeze experiments/local_guards_ml_retrain/frozen \
  --observations experiments/local_guards_v4/data/observations.jsonl.gz \
  --metadata experiments/local_guards_v4/data/metadata.jsonl.gz \
  --output experiments/local_guards_ml_retrain/results/original-v1/archive-ml \
  --batch-size 512
$FINBOT_ML_PY experiments/local_guards_ml_retrain/evaluation.py controls \
  --observations experiments/local_guards_v4/data/observations.jsonl.gz \
  --metadata experiments/local_guards_v4/data/metadata.jsonl.gz \
  --output experiments/local_guards_ml_retrain/results/original-v1/archive-controls \
  --contracts payment_v3 A B --tfidf
$FINBOT_ML_PY experiments/local_guards_ml_retrain/evaluation.py score \
  --predictions experiments/local_guards_ml_retrain/results/original-v1/archive-ml \
    experiments/local_guards_ml_retrain/results/original-v1/archive-controls \
  --observations experiments/local_guards_v4/data/observations.jsonl.gz \
  --metadata experiments/local_guards_v4/data/metadata.jsonl.gz \
  --labels experiments/local_guards_v4/data/gold-actions.jsonl.gz \
  --outcomes experiments/local_guards_v4/data/gold-outcomes.jsonl.gz \
  --output experiments/local_guards_ml_retrain/results/original-v1/archive-scores \
  --bootstrap 1000
```

### Existing CLI episode-universe limitation

Final readback expected3378 all-registry archive episodes but observed3373:
`assert ...['all_registry_episodes']==3378` failed. The scorer constructs this
population from prefix metadata and has no `--episodes` input. The five omitted
registry members are valid legacy_additional mini_old episodes with zero
prefixes: `old/cle-clean_03-9eb9a8`, `old/cle-clean_00-9cd83a`,
`old/cle-clean_02-efe42c`, `old/cle-clean_01-959186`,
`old/cle-clean_04-c7655c`. All five are source-legitimate and have
`continuation_harm=false`; four have a completed transfer. Three are TRAIN and
two CAL. Their exact episode/outcome records are retained in execution checks.

Thus archive action/reached metrics cover every compatible observation, and
harm114/unknown1309 are retained, but the saved all-registry point counts cover
3373 prefix-bearing episodes: known outcomes2064, not the complete registry's
2069. Its legitimate-all denominator excludes five episodes and completed-transfer
count excludes four. No source or prediction was repaired or manufactured, no
scoring rerun was performed, and the parent was notified with the exact failed
assertion. Any full3378-episode outcome postprocessing needs a separate scoped
repair/qualification. This limitation is independent of the defective binding
qualification on every original-v1 model result.
