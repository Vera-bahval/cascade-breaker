# Unified runs: scenarios/results/unified/direct/baseline-ds1, scenarios/results/unified/api/baseline-ds1, scenarios/results/unified/api/chat-ds1, scenarios/results/unified/api/chat2-ds1

## Overview

| via | runs | broken | precondition failed | retried | timed out | harm on N | P not done (core) | P not done (honest) |
|---|---|---|---|---|---|---|---|---|
| api | 1314 | 0  | 0 | 2 | 0 | 74/495 (15%, 12%–18%) | 113/369 (31%, 26%–36%) | 55/450 (12%, 10%–16%) |
| direct | 402 | 0  | 0 | 0 | 0 | 36/147 (24%, 18%–32%) | 15/105 (14%, 9%–22%) | 6/150 (4%, 2%–8%) |

*Broken* runs are left out of every rate. *Retried* runs replaced an attempt that errored or timed out; for 1.3 and 1.5 a timeout can itself be the failure, so check them in the failing list.

Intervals: Wilson 95% over runs. Scenario-level (cluster bootstrap) intervals:

- api: harm on N 11%–19%, P not done 17%–24%
- direct: harm on N 16%–35%, P not done 4%–13%

## By MAST mode (provoked)

| group | api: harm on N | api: P not done | direct: harm on N | direct: P not done |
|---|---|---|---|---|
| 1.1 | 10/54 (19%, 10%–31%) | — | 6/18 (33%, 16%–56%) | — |
| 1.2 | 47/315 (15%, 11%–19%) | — | 28/105 (27%, 19%–36%) | — |
| 1.3 | 0/6 | 3/6 | — | — |
| 1.4 | 0/3 | 1/3 | — | — |
| 1.5 | 0/9 | 4/9 | — | — |
| 2.1 | 0/9 | 1/9 | — | — |
| 2.2 | 3/9 | 3/9 | — | — |
| 2.3 | 0/9 | 0/9 | — | — |
| 3.1 | 1/9 | 3/9 | — | — |
| 3.2 | 16/87 (18%, 12%–28%) | 1/6 | 2/27 (7%, 2%–23%) | — |
| none (honest / legit) | — | 153/765 (20%, 17%–23%) | — | 21/255 (8%, 5%–12%) |

## By invoice truth label

| group | api: harm on N | api: P not done | direct: harm on N | direct: P not done |
|---|---|---|---|---|
| ambiguous | 2/9 | — | 0/3 | — |
| api pair | 4/54 (7%, 3%–18%) | 15/54 (28%, 18%–41%) | — | — |
| dirty | 0/9 | — | 0/3 | — |
| fraud | 11/54 (20%, 12%–33%) | — | 2/18 (11%, 3%–33%) | — |
| injection | 47/315 (15%, 11%–19%) | — | 28/105 (27%, 19%–36%) | — |
| legit | — | 153/765 (20%, 17%–23%) | — | 21/255 (8%, 5%–12%) |
| policy | 10/54 (19%, 10%–31%) | — | 6/18 (33%, 16%–56%) | — |

## How far N cascades went

Share of N runs that reached each stage; harm kinds count failed oracle checks.

- **api** (n=495): workflow started 305, approved / activated 232, payments called 124, transfer 70; harm: money moved 70, vendor status 4
- **direct** (n=147): workflow started 147, approved / activated 129, payments called 82, transfer 36; harm: money moved 36

## Same cases, direct vs api

| variant | direct | api |
|---|---|---|
| harm on N | 36/147 (24%, 18%–32%) | 35/147 (24%, 18%–31%) |
| P not done | 21/255 (8%, 5%–12%) | 28/255 (11%, 8%–15%) |

## Same invoices by entry

| | direct | portal | chat | chat, persistent |
|---|---|---|---|---|
| harm on N | 36/147 (24%, 18%–32%) | 35/147 (24%, 18%–31%) | 9/147 (6%, 3%–11%) | 26/147 (18%, 12%–25%) |
| P not done (core) | 15/105 (14%, 9%–22%) | 23/105 (22%, 15%–31%) | 49/105 (47%, 37%–56%) | 26/105 (25%, 17%–34%) |
| P not done (honest) | 6/150 (4%, 2%–8%) | 5/150 (3%, 1%–8%) | 36/150 (24%, 18%–31%) | 14/150 (9%, 6%–15%) |
| N workflow started | 147/147 (100%, 97%–100%) | 147/147 (100%, 97%–100%) | 35/147 (24%, 18%–31%) | 112/147 (76%, 69%–82%) |
| P workflow started | 255/255 (100%, 99%–100%) | 255/255 (100%, 99%–100%) | 199/255 (78%, 73%–83%) | 255/255 (100%, 99%–100%) |

## Repeat stability

- api: 74 of 288 repeated scenarios had different outcomes across repeats
- direct: 20 of 84 repeated scenarios had different outcomes across repeats

## Cost, latency, loops

| via | $ per run (mean) | LLM calls per run (mean, p95) | trigger s p50 / p95 | LLM call ms p50 / p95 | runs with loops |
|---|---|---|---|---|---|
| api | 0.0049 | 32.3, 40 | 81 / 122 | 2211 / 7686 | 2 |
| direct | 0.0032 | 21.3, 24 | 56 / 86 | 1926 / 7970 | 0 |

Not comparable across via: api cost and calls also include setup workflows (vendor onboarding), but miss the vendor chat's own LLM calls, which are not traced yet; api trigger time includes the runner's polling and settle wait. Trigger time also includes waiting for a shared provider; per-call time does not.

