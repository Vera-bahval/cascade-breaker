"""Export the exact inputs DECISION-VALIDATOR-1 reads from raw CP3-FULL227 files, so the validator can be replayed
without the 629 MB of traces. Read-only: snapshots and result.json are COPIED to <work> first, SQLite opened mode=ro.
  facts.csv           227 rows: the per-scenario facts returned by decision_validator.facts()
  fraud_texts.jsonl   657 rows: run_dir + concatenated Fraud task_summary (the only R4 input)
usage: python3 -I dv_export_inputs.py <decision_validator.py> <series_dir> <work> <out_dir>
"""
import csv, json, shutil, sys
from pathlib import Path

dv_path, series, work, out = map(Path, sys.argv[1:5])
ns = {"__name__": "dv_export", "__file__": str(dv_path)}
exec(compile(dv_path.read_text(), str(dv_path), "exec"), ns)      # same facts() and regexes, main() not run
work.mkdir(parents=True, exist_ok=True); out.mkdir(parents=True, exist_ok=True)
for d in sorted((series / "snapshots").iterdir()):
    t = work / "snap" / d.name; t.mkdir(parents=True, exist_ok=True)
    for f in d.iterdir():
        shutil.copyfile(f, t / f.name)
F = [ns["facts"](d) for d in sorted((work / "snap").iterdir())]
assert len(F) == 227
with open(out / "facts.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(F[0])); w.writeheader(); w.writerows(F)
rows = [json.loads(x) for x in (series / "rows.jsonl").read_text().splitlines() if x.strip()]
n = 0
with open(out / "fraud_texts.jsonl", "w", encoding="utf-8") as fh:
    for r in rows:
        if r["technical"] is None:
            res = json.loads((series / "runs" / r["run_dir"] / "result.json").read_text())
            txt = " ".join(((fr.get("result") or {}).get("task_summary") or "") for fr in res.get("fraud_runs") or [])
            fh.write(json.dumps(dict(run_dir=r["run_dir"], fraud_task_summary=txt), ensure_ascii=False) + "\n"); n += 1
assert n == 657
print("facts", len(F), "fraud_texts", n)
