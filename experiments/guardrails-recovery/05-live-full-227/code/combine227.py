"""Единый набор LIVE-FULL-227 (908 назначений) = исходная серия + серия восстановления LIVE-FULL-227-REC. Только чтение.

  ../../finbot-pr477/.venv/bin/python combine227.py build      → runs/LIVE-FULL-227-COMBINED/ + analysis/LIVE-FULL-227-COMBINED/provenance.csv
  ../../finbot-pr477/.venv/bin/python combine227.py analyse    → замороженный план (full227_analysis.py, sha проверяется) на объединённом наборе

Правило: назначение берётся из REC (первый пригодный прогон цепочки __rec1 → __repl1 → __repl2), если оно было в списке
восстановления; иначе — использованный прогон исходной серии (как в full227_analysis.collect). Каждый выбранный прогон
повторно проверяется новой пригодностью (series_rec227.validate_rec). Исходные папки не меняются: в объединённой
папке — только символьные ссылки с именем назначения, журнал выбора и представление манифеста (view, не серия).
"""
import csv
import hashlib
import json
import os
import sys
from collections import Counter

LAB = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LAB)
import series_rec227 as R  # noqa: E402
from series_parallel import SF, _read_jsonl  # noqa: E402
import series_parallel as S  # noqa: E402

CID = "LIVE-FULL-227-COMBINED"
OUT = os.path.join(LAB, "runs", CID)
ADIR = os.path.join(LAB, "analysis", CID)
FROZEN_ANALYSIS_SHA = "308ce3618d05e7a7633e5261c768999214e5f989829b650beb88abbf414a6672"


def build():
    parent, used = R.parent_used_runs()
    psha = SF._sha(R.PARENT_MANIFEST)
    rec = json.load(open(R.MANIFEST, encoding="utf-8")); rsha = SF._sha(R.MANIFEST)
    rL = {r["run"]: r for r in _read_jsonl(os.path.join(rec["out_dir"], "series_log.jsonl"))}
    rres = S.load_resolutions(rec["out_dir"])
    rjobs = {j["assignment"]: j for j in rec["jobs"]}
    if os.path.exists(OUT):
        raise SystemExit(f"⛔ {OUT} уже существует — собирается один раз")
    os.makedirs(os.path.join(OUT, "runs")); os.makedirs(ADIR, exist_ok=True)
    prov, log, missing = [], [], []
    for j in parent["jobs"]:
        a = j["run"]
        if a in rjobs:
            pick = next((r for r in R.chain(rjobs[a]["run"]) if r in rL and S.effective(rL[r], rres) == "valid"), None)
            src = dict(series=R.SERIES_ID, manifest_sha256=rsha, run=pick, dir=os.path.join(rec["out_dir"], "runs", pick) if pick else None,
                       recover_reason=rjobs[a]["recover_reason"], replaced_parent_run=used.get(a),
                       attempts_in_rec=sum(r in rL for r in R.chain(rjobs[a]["run"])))
        else:
            pick = used.get(a)
            src = dict(series=R.PARENT_ID, manifest_sha256=psha, run=pick, dir=os.path.join(parent["out_dir"], "runs", pick) if pick else None,
                       recover_reason=None, replaced_parent_run=None, attempts_in_rec=0)
        if not pick:
            missing.append(a); continue
        st, why, notes, f = R.validate_rec(src["dir"], None)
        if st != "valid":
            missing.append(a); print("⛔ не прошёл новую пригодность:", a, src["run"], why); continue
        os.symlink(src["dir"], os.path.join(OUT, "runs", a))
        rsha_ = hashlib.sha256(open(os.path.join(src["dir"], "result.json"), "rb").read()).hexdigest()
        log.append(dict(run=a, validity="valid", reasons=[], source_series=src["series"], source_run=src["run"], notes=notes))
        prov.append(dict(assignment=a, scenario=j["scenario"], config=j["config"], source_series=src["series"],
                         source_manifest_sha256=src["manifest_sha256"][:16], source_run=src["run"], recover_reason=src["recover_reason"] or "",
                         replaced_parent_run=src["replaced_parent_run"] or "", attempts_in_rec=src["attempts_in_rec"],
                         result_sha256=rsha_[:16], notes="; ".join(notes)))
    with open(os.path.join(OUT, "series_log.jsonl"), "w", encoding="utf-8") as fh:
        for r in log:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    view = dict(parent, series_id=CID, kind="view: объединённый набор (не серия, вызовов не делалось)", out_dir=OUT,
                sources={R.PARENT_ID: psha, R.SERIES_ID: rsha}, built_by="combine227.py", jobs=parent["jobs"])
    json.dump(view, open(os.path.join(OUT, "view_manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    w = csv.DictWriter(open(os.path.join(ADIR, "provenance.csv"), "w", newline="", encoding="utf-8-sig"), fieldnames=list(prov[0]))
    w.writeheader(); w.writerows(prov)
    s = dict(assignments=len(parent["jobs"]), combined=len(log), missing=missing, by_source=dict(Counter(p["source_series"] for p in prov)),
             by_source_config=dict(Counter(f"{p['source_series']} {p['config']}" for p in prov)),
             rec_reason=dict(Counter(p["recover_reason"] for p in prov if p["recover_reason"])),
             rec_attempts=dict(Counter(p["attempts_in_rec"] for p in prov if p["source_series"] == R.SERIES_ID)))
    json.dump(s, open(os.path.join(ADIR, "combine_summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(s, ensure_ascii=False, indent=1))
    return s


def analyse():
    sha = SF._sha(os.path.join(LAB, "full227_analysis.py"))
    if sha != FROZEN_ANALYSIS_SHA:
        raise SystemExit(f"⛔ full227_analysis.py изменён: {sha[:16]}")
    import full227_analysis as FA
    rep = FA.analyse(os.path.join(OUT, "view_manifest.json"), ADIR)
    print(json.dumps(rep, ensure_ascii=False, indent=1)[:8000])


if __name__ == "__main__":
    {"build": build, "analyse": analyse}[sys.argv[1]]()
