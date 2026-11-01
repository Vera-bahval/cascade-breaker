# ML comparison: evidence and reproduction

This directory is a frozen research comparison of correct ALLOW/BLOCK decisions
without an LLM. UNKNOWN is abstention; the execution profile stops on UNKNOWN.
The short Russian appendix is [REPORT.md](REPORT.md); definitions, full tables
and limits are in [APPENDIX.md](APPENDIX.md). Neither changes the main
`experiments/NO_LLM_REPORT.md`.

## Reproduce postprocessing

Use the complete pure-ML release commit pinned in the PR description, including
all manifest-bound data, before the later integration of the other chat's work.
The recorded checkout is
`/Users/proskurin-dmi/Documents/hw-itmo/cascades/research/finbot-general-guards`.
The commands below were validated in that macOS checkout and currently require
its absolute path layout and dependencies. Prediction receipts, score inputs and
freeze manifests retain absolute prediction, model and source paths; cloning
the files elsewhere is not sufficient. Reproduction from a relocated fresh clone
or another platform has not been demonstrated. Frozen receipts and manifests
have not been rewritten to suggest portability.

The recorded native/interval runtime is macOS 26.6.2 arm64, Python 3.13.15,
NumPy 2.5.4, scikit-learn 1.9.1, CatBoost 1.2.10, SQLAlchemy 2.0.46 and FastMCP
3.0.2; its exact executable and numerical thread settings are in
`results/revision2/native-quiet/summary.json`. Model/native reproduction also
requires the matching FinBot runtime and fixtures, including
`experiments/local_guards_v4/tests/test_runtime.py`, from that release context.
The standard-library analysis command was run with `/usr/bin/python3`.

After the later authorized integration changes the root `experiments/NO_LLM_REPORT.md`,
the analysis baseline guard is expected to reject that changed context. Use the
complete pure-ML release context identified by the PR, rather than disabling the
guard or changing frozen identities.

Run from the recorded absolute checkout, after measurement/scoring jobs have
finished and the controller has released the CPU hold:

```sh
/usr/bin/python3 experiments/local_guards_ml_retrain/analysis.py \
  --bootstrap 1000 \
  --output experiments/local_guards_ml_retrain/analysis
```

The script uses only the Python standard library. It reads saved predictions,
scores, review memberships and timing files. It does not import a model, feature
extractor, policy oracle or guard; it never fits, predicts, tunes or measures
latency. It overwrites only its generated output directory. Use a separate
`--output` directory for a fresh reproduction and compare the generated files.
Source hashes include exact compressed inputs and the analysis source itself.

Archive task-group intervals require this separate postprocessing command:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 \
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python \
  experiments/local_guards_ml_retrain/archive_intervals.py --bootstrap 1000 \
  --output experiments/local_guards_ml_retrain/analysis/archive-global-intervals.json
```

This command uses existing scoring/join/bootstrap helpers and installed NumPy;
it never constructs a model, unpickles, predicts or fits. It streams compact
source checkpoint/time records and the51 primary seed17 raw/gated/rule prediction
streams. It replaces only the analysis-local cluster key with exact global
`metadata.group_id` and asserts every point-summary section equals the original
score. Source-prefixed archive intervals in the original score files must not be
interpreted as task-group intervals. The new file supersedes51 all-source
intervals; other original archive intervals are withheld from report claims.

Scoring and measurement commands, exact input identities and qualifications are
preserved in [results/revision2/execution-plan.md](results/revision2/execution-plan.md)
and the final [execution report](results/revision2/execution-report.md).
Do not repeat those expensive commands to reproduce the report.

## Evidence map

| Question | Authoritative input |
| --- | --- |
| Fixed design and minimal correction | `PLAN.md`, `REVISION_2_PLAN.md`, `P2_CALL_BINDING_CLARIFICATION.md` |
| Primary method freeze | `model-freeze-revision2.json`, `frozen_revision2/freeze-manifest.json` |
| Retained first method, with P2 defect | `model-freeze.json`, `frozen/freeze-manifest.json` |
| Development authorship and split | `dev-author-report.md`, `dev-read-log.json`, `data/manifest.json`, `prepared/manifest.json` |
| Final new1200 labels and normalization | `closed_revision2/`, `closed2-rereview.{md,json}` |
| Unchanged full/common views and 31 components | `closed2-review.json`; final reuse is authorized by `closed2-rereview.json` |
| Exact independent normalizer recipe | `closed_review_revision2.py`, functions `normalize_full` and `common`; never import this side-effectful audit script |
| Predictions before label disclosure | `results/closed2/prediction-commitment.json`, `gold-release.json`, prediction commit `b7afad7c7e2982fa95512d13bb2077e3c85c7b2a` |
| New1200 original/corrected prediction bytes | `results/closed2/{original-replay,revision2-replay,controls}/receipt.json` and their shards |
| Primary/new1200 scores | `results/closed2/revision2-scores/metrics.json` |
| Original method on identical new1200 states | `results/closed2/original-scores/metrics.json` |
| Corrected CAL/archive/open diagnostics | `results/revision2/{cal,archive,old320,old400,first1200}-scores/` |
| Corrected full registry for original method | `results/original-v1-corrected-accounting/` |
| Primary timings | `results/revision2/{native-quiet,single,load}/` |
| Excluded timing run | `results/revision2/native/`, `native-preliminary-qualification.json` |
| Generic exception and unavailable-order policy | `replay-execution-policy-report.md`, `replay-execution-policy-rereview.md` |
| Preserved failed batch | `results/closed2/failed-batch-before-error-wrapper/` |
| Reproducible report numbers | `analysis/{summary,source-hashes,sensitivity,calibration,timings}.json`, CSV tables |

## Generated tables

`primary.csv` contains seed17 raw/gated methods and unchanged rules on the new
test. `all-scores.csv.gz` preserves every scored method and source/checkpoint/family/
split slice, including argmax and TFIDF diagnostics where available. Nested JSON
columns retain complete confusion, reachability, episode/outcome and registry
denominators rather than flattening away missingness.

`factorial-contrasts.csv` compares new/old features at fixed data, mixed/archive
training at fixed features, and the separately calibrated raw/gated operating
points. `gate-attribution.json` additionally holds thresholds fixed to the gated
configuration and compares its pre-gate decision with the actual gated result.
The gate changes ALLOW to UNKNOWN only, so it never earns a correct BLOCK.

`revision-contrasts.csv` compares the original frozen implementation with the
corrected frozen representation on the identical new1200 states. The original
P2 defect is retained and never used to claim an inherent ML limitation.

`sensitivity.json` includes raw-row, full-deduplicated, common-payment-balanced,
supplied-payment-balanced, development-overlap and temporal-projection slices.
Deduplication means reciprocal multiplicity weights; no representative row or
gold label is chosen. `state-memberships.csv` makes every weight/cluster auditable.
The 31-component bootstrap uses seed17 and 1000 descriptive resamples. The
payment subset can intersect fewer components. It is not an IID 1200-state
confidence interval and does not establish a population of new attack mechanisms.

`execution-errors.csv` separates checker exceptions from learned abstention.
`examples-index.csv.gz` contains every primary-seed decision, its pre-gate decision
and gate reasons, for tracing examples back to the unchanged observation/gold.
`timings.json` retains per-method single-call, full-check, completed/stopped chain,
one-worker cold response/exit/RSS and native transfer-effect counts. Cold results
are one gated response per model and are not tail latency estimates.

Large CSV tables use deterministic gzip to avoid duplicating tens of megabytes
of repeated registry details. Read them with `gzip.open(path, 'rt')` and
`csv.DictReader`; set `csv.field_size_limit(10_000_000)` for the complete nested
registry columns. No special analysis library is needed.

Missing required inputs are explicitly listed in `analysis/summary.json`; a
partial analysis must not be described as a completed comparison.
