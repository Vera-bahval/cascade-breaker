# Baseline data

`baseline-ds1`: FinBot on DeepSeek Flash (`deepseek/deepseek-v4.1-flash-1017` through OpenRouter, provider
`deepinfra/fp8`, temperature 0, seed 7, reasoning off), 2026-11-06. Direct: `core` x3 and `honest` x1, 402 runs.
API: `core` and the API pairs x3, `honest` x1, 510 runs.

- `baseline-ds1-report.md`: the metrics report.
- `baseline-ds1-runs.csv`: one row per run (outcome, failed checks, agent path, fraud flag, cost, LLM calls, time).

`chat-ds1`: the same `core` x3 and `honest` x1 invoices sent through the vendor chat instead of the portal (suites
`core_chat`, `honest_chat`): the invoice is seeded as `submitted` and one message asks the chat to process it. 402 runs.
14 runs interrupted by the laptop sleeping were rerun; the interrupted files are kept in `chat-ds1-slept/`.

- `chat-ds1-report.md`, `chat-ds1-runs.csv`: the same report and table for the chat runs.
- `by-entry-report.md`: all three batches together; the section "Same invoices by entry" compares direct, portal
  and chat on the same invoices.

`extra-ds1`: API pairs left out of the baseline because Nastya's set already covered their MAST mode, run to cover
invariants the baseline misses (S01, S02, S03, S15, S16, S17, S20, S21, S23), 3 repeats each, 54 runs.

- `extra-ds1-report.md`, `extra-ds1-runs.csv`.

All are written by `scenarios/analyze_unified.py`:

```bash
python3 scenarios/analyze_unified.py scenarios/results/unified/direct/baseline-ds1 \
    scenarios/results/unified/api/baseline-ds1 --list \
    --out docs/checkpoints/data/baseline-ds1-report.md --csv docs/checkpoints/data/baseline-ds1-runs.csv
```

The raw results with full traces (about 1 GB) are not in git; they live in `scenarios/results/unified/` on the
machine that ran them.
