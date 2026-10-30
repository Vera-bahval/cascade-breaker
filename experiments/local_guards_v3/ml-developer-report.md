# ML developer report

Implemented `ml_v3.py` and `tests/test_ml_v3.py` using only generic synthetic policy fixtures. No TRAIN package, CAL, TEST, archived episodes, other guards, custodian artifacts, repository history or inference APIs were accessed. No shared Git operations or subagents were used.

## Interface and frozen design

- `MODEL_NAMES = ("structured_logistic", "structured_catboost", "text_diagnostic")`.
- `features(observation) -> dict` uses only whitelisted checkpoint, proposal and facts fields. Nullable booleans/counts and amounts have missing indicators. Amounts are normalized by the frozen automatic limit 10000 and maximum amount 50000. Exact proposed/invoice decimal equality, same-currency equality and each currency's equality to frozen policy USD preserve unknowns. Currency comparison strips whitespace and ignores case. Categories use TRAIN-fitted one-hot encoding. Raw IDs, event order, provenance, arbitrary nested fields, labels, metadata and untrusted text do not enter structured features.
- `fit_model(name, rows, labels, seed=17, sample_weight=None)` returns a sklearn Pipeline. Callers supply TRAIN only. UNKNOWN and any other labels are rejected; both ALLOW and BLOCK are required. Optional external nonnegative finite row weights are passed to the classifier.
- `score_model(model, rows) -> list[float]` returns P(BLOCK), never fits or applies a decision threshold. Empty input returns an empty list. Calibration and evidence gates belong to the evaluator.
- Structured logistic: DictVectorizer, StandardScaler(with_mean=False), LogisticRegression(C=1, L2, max_iter=2000). sklearn 1.9 represents L2 with `l1_ratio=0.0`; the deprecated `penalty` argument is omitted. Solver is lbfgs and random_state is the supplied seed.
- Structured CatBoost: DictVectorizer, iterations=200, depth=3, learning_rate=0.03, l2_leaf_reg=5, allow_writing_files=False, verbose=False, thread_count=2, random_seed supplied seed.
- Text diagnostic: invoice and agent untrusted text only; char_wb TF-IDF ngrams 3..5, max_features=20000, min_df=2; the same fixed logistic classifier. No structured facts or metadata are included in this diagnostic.
- `model_provenance()` and fitted `model.provenance_` expose design, seed, frozen source hashes and installed library versions. Pipelines have a joblib round-trip test. Import `ml_v3` under that module name and keep its directory importable when deserializing, because FunctionTransformer references its top-level functions.

## Verification

TDD red: before creating the production module, the eight test cases failed with the expected assertion that the requested module did not exist (`8 failed in 0.19s`). Green after implementation: `8 passed in 1.95s`.

Pre-freeze review added two generic currency tests. Red confirmed raw `usd`/`USD` comparison was unequal and the two policy-currency feature keys were absent (`2 failed, 8 passed in 0.97s`). Currency normalization and nullable matches-policy features then made all ten pass. The approved schema semantics revision changed its hash without adding fields; the provenance constant was updated after checking the current schema file's SHA-256. No data were read for this correction.

Final isolated command (disables external pytest plugins, conftest discovery and cache/bytecode writes):

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv/bin/python -m pytest experiments/local_guards_v3/tests/test_ml_v3.py -q -p no:cacheprovider --noconftest
```

Result: **10 passed in 0.93s**. Tests cover structured exclusion of text/identity/audit metadata, finite null numeric behavior, distinctions between null/false/zero, all-null scoring, currency normalization, equal USD/USD versus EUR/EUR representation, fitting/scoring each model, novel scoring categories without vocabulary mutation, P(BLOCK) ordering on generic fixtures, joblib persistence, UNKNOWN/single-class rejection, weight length validation and provenance. The broader repository suite was not run because this task explicitly forbids reading other guard/evaluation tests. These tests establish software behavior, not empirical classification quality. No final research fits or calibration were performed.

Library versions: numpy 2.5.4, pandas 3.0.6, scikit-learn 1.9.1, CatBoost 1.2.10.

## Direct file-read audit

All project-relative paths below are under `/Users/proskurin-dmi/Documents/hw-itmo/cascades/research/finbot-general-guards/`:

- `experiments/local_guards_v3/policy.json`
- `experiments/local_guards_v3/schema.json`
- `experiments/local_guards_v3/POLICY.md`
- Own newly written `experiments/local_guards_v3/ml_v3.py` (execution/hash).
- Own newly written `experiments/local_guards_v3/tests/test_ml_v3.py` (execution/hash).

Installed instruction files read:

- `/Users/proskurin-dmi/.codex-igaming/plugins/cache/openai-curated-remote/superpowers/7.0.1/skills/using-superpowers/SKILL.md`
- `/Users/proskurin-dmi/.codex-igaming/plugins/cache/openai-curated-remote/superpowers/7.0.1/skills/test-driven-development/SKILL.md`
- `/Users/proskurin-dmi/.codex-igaming/plugins/cache/openai-curated-remote/superpowers/7.0.1/skills/test-driven-development/writing-good-tests.md`
- `/Users/proskurin-dmi/.codex-igaming/plugins/cache/openai-curated-remote/superpowers/7.0.1/skills/verification-before-completion/SKILL.md`
- `/Users/proskurin-dmi/.codex-igaming/plugins/cache/openai-curated-remote/superpowers/7.0.1/skills/receiving-code-review/SKILL.md`
- `/Users/proskurin-dmi/.codex-igaming/plugins/cache/openai-curated-remote/engineering-suite-ponytail/2.0.0/skills/entry-ponytail/SKILL.md`
- `/Users/proskurin-dmi/.codex-igaming/plugins/cache/openai-curated-remote/engineering-suite-ponytail/2.0.0/skills/ponytail/SKILL.md`

Additionally inspected the installed LogisticRegression signature through Python and package-version metadata. Runtime imports used the installed interpreter/libraries; no installed library source files were manually inspected. Tests created only temporary joblib files and ordinary runtime bytecode before the final no-bytecode run.

## SHA-256

| File | SHA-256 |
| --- | --- |
| policy.json | bdaaffe0715d7b7233cc40e1ce7f6ada7989bac927269998aa5827d385f65c85 |
| schema.json | 62efd6d8ec3b1dced204d3705c9c2691b7e9af1d503c4327ce388e1e6be84711 |
| ml_v3.py | 62651a89b6745e8e966b05f6b66962638b39cde8424563a1694cee410c6db485 |
| tests/test_ml_v3.py | ec37de337a67b7f5c4b59196cfa28f7c6857580ff4615d10f3bbab8d204980b5 |
