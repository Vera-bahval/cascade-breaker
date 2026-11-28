"""Replay DECISION-VALIDATOR-1 from exported inputs (facts.csv, fraud_texts.jsonl) + rows.jsonl + labels and check that
every per_run.csv field is reproduced. Uses the unmodified decision_validator.py source (rules and regexes are taken
from it; only its LABELS path is pointed at the given labels file). Writes nothing next to the validator.
usage: python3 -I dv_replay.py <decision_validator.py> <labels.json> <rows.jsonl> <facts.csv> <fraud_texts.jsonl> <per_run.csv>
"""
import csv, json, re, sys
from pathlib import Path

dv, labels, rows_p, facts_p, texts_p, per_run_p = map(Path, sys.argv[1:7])
src = dv.read_text()
line = 'LABELS = json.loads((CP3 / "full227_labels.json").read_text())["scenarios"]'
assert src.count(line) == 1
ns = {"__name__": "dv_replay", "__file__": str(dv)}
exec(compile(src.replace(line, f"LABELS = json.loads(open({str(labels)!r}).read())['scenarios']"), str(dv), "exec"), ns)
L = ns["LABELS"]
num = lambda v: None if v in ("", "None") else float(v)
F = {}
for r in csv.DictReader(open(facts_p, encoding="utf-8")):
    F[r["scenario"]] = dict(r, amount=float(r["amount"]), prior_mean=num(r["prior_mean"]), terms_days=int(r["terms_days"]),
                            holder_differs=r["holder_differs"] == "True", vendor_age_days=int(r["vendor_age_days"]),
                            dup_amount=r["dup_amount"] == "True")
T = {j["run_dir"]: j["fraud_task_summary"] for j in map(json.loads, open(texts_p, encoding="utf-8"))}
R = {s: ns["rules_for"](f) for s, f in F.items()}
old = {s for s, f in F.items() if re.search(ns["EXPLICIT_DATE"], f["description"], re.I)}
v5 = {s for s in F if s.startswith("TH5") and L[s]["role"] == "legit" and R[s]["R2"]}
want = {(r["scenario"], r["arm"]): r for r in csv.DictReader(open(per_run_p, encoding="utf-8-sig"))}
bad = 0; n = 0
for r in map(json.loads, open(rows_p)):
    if r["technical"] is not None:
        continue
    s = r["scenario"]; txt = T[r["run_dir"]]; m = re.search(ns["R4_TXT"], txt, re.I)
    fraud = bool(r["structured_flags"])
    got = dict(harmful=L[s]["role"] != "legit", fraud=fraud, R4=(not fraud) and bool(m),
               explicit_old_date=s in old, v5_out_of_profile_honest=s in v5,
               **{k: R[s][k] for k in ("dev_pct", "R1", "R2", "R3", "R3a", "R3b", "R3c", "R5", "V", "V_core")})
    w = want[(s, r["arm"])]; n += 1
    for k, v in got.items():
        if str(v) != w[k]:
            bad += 1; print("DIFF", s, r["arm"], k, v, w[k])
print(f"replayed {n} runs, field mismatches {bad}")
sys.exit(1 if bad or n != 657 else 0)
