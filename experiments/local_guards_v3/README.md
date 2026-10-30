# General FinBot guards v3

[Краткий отчёт](REPORT.md). Research prototype: typed policy verification and fixed non-LLM baselines, no inference API calls. Preserve frozen data, models, prediction receipts and separate source/contract outcomes. This experiment does not repair or deploy FinBot.

Python 3.12 with [requirements.txt](requirements.txt). FinBot integration uses the existing separate Python 3.13 runtime described below. From the repository root:

```sh
python3.12 -m venv .venv-v3
.venv-v3/bin/pip install -r experiments/local_guards_v3/requirements.txt
```

## Recompute metrics without fitting or inference APIs

```sh
.venv-v3/bin/python experiments/local_guards_v3/evaluate_v3.py evaluate \
  --predictions experiments/local_guards_v3/results/archive-predictions.jsonl.gz \
  --gold-actions experiments/local_guards_v3/data/gold-actions.jsonl \
  --gold-outcomes experiments/local_guards_v3/data/gold-outcomes.jsonl \
  --metadata experiments/local_guards_v3/data/metadata.jsonl --output /tmp/v3-archive-recheck
.venv-v3/bin/python experiments/local_guards_v3/evaluate_v3.py evaluate \
  --predictions experiments/local_guards_v3/results/closed-predictions.jsonl.gz \
  --gold-actions experiments/local_guards_v3/closed-test/gold-actions.jsonl \
  --gold-outcomes experiments/local_guards_v3/closed-test/gold-outcomes.jsonl \
  --metadata experiments/local_guards_v3/closed-test/metadata.jsonl --output /tmp/v3-closed-recheck
.venv-v3/bin/python experiments/local_guards_v3/build_report.py
```

For fresh frozen-model predictions, run `evaluate_v3.py predict --freeze experiments/local_guards_v3/results/frozen --observations PATH --metadata PATH --output NEW.jsonl.gz`. It never opens gold, refuses to overwrite, and verifies source/model integrity. Both observations and metadata must be complete. Repeated timing fields can differ; numeric scores/decisions should agree. Fit is a separate command `train_freeze --data experiments/local_guards_v3/data --output NEW_EMPTY_DIR`; it uses known TRAIN action labels and CAL only, never refits afterward. The published run uses seed17 as primary and 29/43 for sensitivity.

The test scripts run **without arguments**:

```sh
.venv-v3/bin/python experiments/local_guards_v3/generate_closed_test.py
.venv-v3/bin/python experiments/local_guards_v3/closed-test-review.py
```

The generator verifies existing sealed bytes and refuses to replace them with different content. The independent reviewer writes `closed-test/review.json` and `review.md`; use a copy of the experiment if those published reports must stay untouched. Neither script implements a `--help` option. These artifacts already exist and are no longer a fresh test for later work. The independent author saw policy/schema only. `results/pre-test-freeze.json` predates their creation; receipts and `closed-gold-release.json` record prediction-before-reveal. Shared filesystem access was controlled procedurally by fresh contexts, file allowlists and read audits, not an OS security boundary.

## Source extraction and runtime

`prepare_data.py --old-root PATH --comparison-root PATH --output NEW_DIR` reconstructs data from the existing old workspace archive and four-model public artifacts. [source-manifest.json](data/source-manifest.json) records exact archive/member/source hashes and [custodian-report.md](custodian-report.md) explains fresh-creation and complete-journal evidence. Missing source paths require obtaining the pinned historical branches; derived files in `data/` are sufficient for metric reproduction. Final database snapshots are outcome-only. Old synthetic policy-extension tests are recorded as developer-exposed historical data, not admitted native-policy observations.

The native integration runner expects the supplied cascades workspace's `experiments/local_guards/.venv-finbot/bin/python` (Python 3.13 with the existing FinBot lock environment). Run `integration_replay.py --output NEW_DIRECTORY` using the ML Python. Each case spawns a fresh SQLite worker and uses this repository's native runtime and FinStripe MCP server; outgoing socket connections are blocked. From another layout, run its `--case CASE --database NEW.sqlite --output RESULT.json` worker directly with a compatible FinBot Python. Only serial enforcement is tested; the adapter maps UNKNOWN and exceptions to a native blocking verdict.

`benchmark.py --freeze ... --observations data/train-package/observations.jsonl --output NEW.json` measures single-prefix JSON+features+proof processing. `diagnostics.py` checks post-freeze text/identity invariance. `saved_fallback.py --self-test` checks its pure prefix renderer and proof/chronology handling; full saved-context reconstruction additionally needs the pinned four-model artifacts.

## Verification and artifact map

- `python -m pytest experiments/local_guards_v3/tests -q` — 157 pre-freeze tests; native integration requires its separate runtime.
- `results/frozen/`: verified local fitted pickles and policy. Deserialization is restricted to local artifacts matching the manifest hash.
- `results/{archive,closed,contract}-evaluation/`: aggregate metrics, grouped intervals, paired comparisons and compressed episode decisions.
- `results/latency.json`, `results/native-replay/summary.json`, `results/invariance.json`: actual measured or checked diagnostics.
- `final-audit.md` and `results/final-integrity.json`: independent final recount, prediction-before-gold validation, unchanged method/model hashes and documented limitations.
- Original scenario harm, strict-contract harm, action gold and source intent are distinct. UNKNOWN stops, and unavailable evidence is not false or zero cost. Conditional saved-LLM views are outcome-dependent and cannot establish population FPR or complete cascade cost.
