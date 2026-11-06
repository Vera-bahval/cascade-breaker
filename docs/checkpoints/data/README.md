# Baseline data

`baseline-ds1`: FinBot on DeepSeek Flash (`deepseek/deepseek-v4.1-flash-1017` through OpenRouter, provider
`deepinfra/fp8`, temperature 0, seed 7, reasoning off), 2026-11-06. Direct: `core` x3 and `honest` x1, 402 runs.
API: `core` and the API pairs x3, `honest` x1, 510 runs.

- `baseline-ds1-report.md`: the metrics report.
- `baseline-ds1-runs.csv`: one row per run (outcome, failed checks, agent path, fraud flag, cost, LLM calls, time).

Both are written by `scenarios/analyze_unified.py`:

```bash
python3 scenarios/analyze_unified.py scenarios/results/unified/direct/baseline-ds1 \
    scenarios/results/unified/api/baseline-ds1 --list \
    --out docs/checkpoints/data/baseline-ds1-report.md --csv docs/checkpoints/data/baseline-ds1-runs.csv
```

The raw results with full traces (about 1 GB) are not in git; they live in `scenarios/results/unified/` on the
machine that ran them.
