"""CP3-FULL227 — interim read-only sensitivity of honest PAID/LOST and harmful HARM by arm (series still running).
Copies rows.jsonl (complete lines only) and the 227 frozen state_before.json to <workdir>; no SQLite, no LLM.
Filters are defined from the frozen invoice text only (labels untouched):
  all          — every scenario
  no_old_date  — drop explicit service dates 2010-2025 in the description (YYYY-MM-DD, MM/DD/YYYY, Month YYYY);
                 PO/contract numbers like Z2023-001 or #2023-004 are NOT dates and stay in
  no_old_no_oop — additionally drop services outside Northlight's profile (camera/grip/lighting rental)
  python3 full227_sensitivity_interim.py <workdir>  → <workdir>/sensitivity.json
"""
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERIES = HERE / "tests" / "CP3_FULL227" / "full227-v1"
LABELS = json.loads((HERE / "tests" / "CP3_FULL227" / "full227_labels.json").read_text())["scenarios"]
EXPLICIT_DATE = (r"20(1\d|2[0-5])-\d\d-\d\d|\d\d/\d\d/20(1\d|2[0-5])|(January|February|March|April|May|June|July|August|"
                 r"September|October|November|December) 20(1\d|2[0-5])")
NONEQ = (r"catering|casting|talent|permit|location (fee|scouting)|scouting|special effects|pyrotechnic|cgi|marketing|"
         r"construction|consult|craft services|security services|transportation services|wardrobe|costume|crew services|"
         r"post-production|editing|color grading|sound design")
ARMS = "ABC"
PAIRS = (("B", "A"), ("C", "B"), ("C", "A"))


def copy(work):
    work.mkdir(parents=True, exist_ok=True)
    raw = (SERIES / "rows.jsonl").read_bytes()
    lines = raw.split(b"\n")
    if not raw.endswith(b"\n"):
        lines = lines[:-1]          # a line being written right now is dropped
    (work / "rows.jsonl").write_bytes(b"\n".join(l for l in lines if l.strip()) + b"\n")
    for d in (SERIES / "snapshots").iterdir():
        if (d / "state_before.json").exists():
            (work / "snap").mkdir(exist_ok=True)
            shutil.copyfile(d / "state_before.json", work / "snap" / f"{d.name}.json")


def pct(a, b):
    return f"{a}/{b} ({100 * a / b:.1f}%)" if b else "0/0"


def main(work):
    work = Path(work)
    copy(work)
    rows = [json.loads(x) for x in (work / "rows.jsonl").read_text().splitlines() if x.strip()]
    desc = {json.loads(p.read_text())["scenario"]: json.loads(p.read_text())["invoice"]["description"] or ""
            for p in (work / "snap").glob("*.json")}
    assert len(desc) == 227
    old = {s for s, d in desc.items() if re.search(EXPLICIT_DATE, d, re.I)}
    oop = {s for s, d in desc.items() if re.search(NONEQ, d, re.I)}
    filters = dict(all=set(desc), no_old_date=set(desc) - old, no_old_no_oop=set(desc) - old - oop)
    valid = [r for r in rows if r["technical"] is None]
    out = dict(rows=len(rows), valid=len(valid),
               scenario_counts={k: dict(honest=sum(LABELS[s]["role"] == "legit" for s in v),
                                        harmful=sum(LABELS[s]["role"] != "legit" for s in v)) for k, v in filters.items()},
               excluded=dict(old_date_honest=sum(LABELS[s]["role"] == "legit" for s in old),
                             old_date_harmful=sum(LABELS[s]["role"] != "legit" for s in old),
                             oop_honest=sum(LABELS[s]["role"] == "legit" for s in oop - old),
                             oop_harmful=sum(LABELS[s]["role"] != "legit" for s in oop - old)),
               unpaired={}, paired={})
    by = {}
    for r in valid:
        by.setdefault(r["scenario"], {})[r["arm"]] = r
    full = {s for s, v in by.items() if len(v) == 3}
    for name, keep in filters.items():
        u = {}
        for arm in ARMS:
            h = [r for r in valid if r["arm"] == arm and r["scenario"] in keep and LABELS[r["scenario"]]["role"] == "legit"]
            e = [r for r in valid if r["arm"] == arm and r["scenario"] in keep and LABELS[r["scenario"]]["role"] != "legit"]
            u[arm] = dict(honest_paid=pct(sum(bool(r["paid"]) for r in h), len(h)), honest_lost=pct(sum(bool(r["LOST"]) for r in h), len(h)),
                          harm=pct(sum(bool(r["HARM"]) for r in e), len(e)))
        out["unpaired"][name] = u
        P = {}
        hs = sorted(s for s in full & keep if LABELS[s]["role"] == "legit")
        es = sorted(s for s in full & keep if LABELS[s]["role"] != "legit")
        P["n_scenarios"] = dict(honest=len(hs), harmful=len(es))
        P["per_arm"] = {a: dict(honest_paid=pct(sum(bool(by[s][a]["paid"]) for s in hs), len(hs)),
                                honest_lost=pct(sum(bool(by[s][a]["LOST"]) for s in hs), len(hs)),
                                harm=pct(sum(bool(by[s][a]["HARM"]) for s in es), len(es))) for a in ARMS}
        tr = {}
        for x, y in PAIRS:
            pl = [s for s in hs if by[s][y]["paid"] and by[s][x]["LOST"]]
            lp = [s for s in hs if by[s][y]["LOST"] and by[s][x]["paid"]]
            hh = [s for s in es if not by[s][y]["HARM"] and by[s][x]["HARM"]]
            hn = [s for s in es if by[s][y]["HARM"] and not by[s][x]["HARM"]]
            tr[f"{x} vs {y}"] = dict(honest_PAY_to_LOST=len(pl), honest_LOST_to_PAY=len(lp),
                                     honest_same=len(hs) - len(pl) - len(lp), PAY_to_LOST=pl, LOST_to_PAY=lp,
                                     harmful_safe_to_HARM=len(hh), harmful_HARM_to_safe=len(hn), safe_to_HARM=hh, HARM_to_safe=hn)
        P["transitions"] = tr
        out["paired"][name] = P
    (work / "sensitivity.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
