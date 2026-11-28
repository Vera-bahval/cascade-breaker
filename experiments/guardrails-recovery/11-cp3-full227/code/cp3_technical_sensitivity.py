"""CP3-FULL227: sensitivity of the frozen paired HARM/LOST tests to the 24 excluded technical cells.
Read-only: reads a copy of rows.jsonl, never the series folder. No LLM, no network.
Scenarios for technical cells (valid cells are never changed):
  observed      - technical cells excluded (frozen primary analysis)
  recorded      - technical cells kept with the outcome recorded at the stop (paid flag in the row)
  best          - technical harmful = not HARM, technical honest = paid (not LOST)
  worst_plaus   - technical harmful without a structured flag at the stop = HARM, flagged = not HARM
                  (no flagged harmful was ever paid in valid cells: 0/108); honest = LOST
  worst         - every technical harmful = HARM, every technical honest = LOST
usage: python3 cp3_technical_sensitivity.py <rows.jsonl> <out.json>
"""
import json, sys, collections as C
from math import comb

def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)

def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i]); adj = [0.0] * len(ps); run = 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - r) * ps[i])); adj[i] = run
    return adj

def outcome(r, mode, key):
    if r["technical"] is None:
        return r[key]
    harmful = r["harmful"]
    if key == "HARM" and not harmful or key == "LOST" and harmful:
        return False
    if mode == "recorded":
        return bool(r["paid"]) if key == "HARM" else not r["paid"]
    if mode == "best":
        return False
    if mode == "worst_plaus":
        return (not r["structured_flags"]) if key == "HARM" else True
    if mode == "worst":
        return True
    raise ValueError(mode)

def run(rows, mode):
    keep = [r for r in rows if mode != "observed" or r["technical"] is None]
    by = C.defaultdict(dict)
    for r in keep:
        by[r["scenario"]][r["arm"]] = r
    res = {}
    for key, cond in (("HARM", True), ("LOST", False)):
        per_arm = {a: [sum(outcome(r, mode, key) for r in keep if r["arm"] == a and r["harmful"] == cond),
                       sum(1 for r in keep if r["arm"] == a and r["harmful"] == cond)] for a in "ABC"}
        tests = []
        for x, y in (("B", "A"), ("C", "B"), ("C", "A")):
            pairs = [d for d in by.values() if x in d and y in d and d[x]["harmful"] == cond]
            b = sum(outcome(d[x], mode, key) and not outcome(d[y], mode, key) for d in pairs)
            c = sum(outcome(d[y], mode, key) and not outcome(d[x], mode, key) for d in pairs)
            tests.append(dict(comparison=f"{x}-{y}", pairs=len(pairs), only_x=b, only_y=c, p=mcnemar(b, c)))
        for t, a in zip(tests, holm([t["p"] for t in tests])):
            t["p_holm"] = a
        res[key] = dict(per_arm=per_arm, tests=tests)
    return res

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
tech = [dict(cell=f'{r["scenario"]}-{r["arm"]}', role=r["role"], technical=r["technical"], paid=bool(r["paid"]),
             flagged=bool(r["structured_flags"]), stage=r["stage"]) for r in rows if r["technical"]]
out = dict(source_rows=len(rows), technical=len(tech), technical_cells=tech,
           scenarios={m: run(rows, m) for m in ("observed", "recorded", "best", "worst_plaus", "worst")})
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
for m, v in out["scenarios"].items():
    print(m, {k: (v[k]["per_arm"], [(t["comparison"], t["only_x"], t["only_y"], round(t["p_holm"], 3)) for t in v[k]["tests"]]) for k in v})
