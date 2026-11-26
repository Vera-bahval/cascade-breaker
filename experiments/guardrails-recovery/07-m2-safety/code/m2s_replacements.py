"""M2-SAFETY: three approved replacements of the 429-technical cells (TH606-B, FD55-B, TH606-C).

m2safety.py is NOT modified (its sha is protected by CP3). This wrapper only lowers the per-run cap to the remaining
approved budget, so that the three replacements together can never exceed $0.01 (pre-call worst case + billed cost,
the same check m2safety._child already performs). No retries: a replacement that is technical again stops the set.

  ../../finbot-pr477/.venv/bin/python -B analysis/CHECKPOINT3/m2s_replacements.py run      # from iv_lab, PAID
"""
import glob
import json
import os
import sys

LAB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, LAB)
import m2safety as M  # noqa: E402

BUDGET = 0.01
CELLS = (("TH606", "B"), ("FD55", "B"), ("TH606", "C"))
REPLACES = {("TH606", "B"): "TH606__B__live__232819", ("FD55", "B"): "FD55__B__live__232833",
            ("TH606", "C"): "TH606__C__live__232857"}
LOG = os.path.join(M.OUT, "replacements_20261126.json")
M.__file__ = os.path.abspath(__file__)          # run_arm spawns this wrapper for _child, so the lowered cap applies there
if os.environ.get("M2S_REPL_CAP"):
    M.LIVE_CAP = float(os.environ["M2S_REPL_CAP"])


def technical(arm_dir):
    out = open(os.path.join(arm_dir, "stdout.txt"), encoding="utf-8", errors="ignore").read()
    res = json.load(open(os.path.join(arm_dir, "result.json"), encoding="utf-8"))
    return "LLM call failed" in out or bool(res.get("cap_hit"))


def run():
    assert not os.path.exists(LOG), "replacement set already started; never resumed"
    before = {d: M.sha(os.path.join(d, "result.json")) for d in glob.glob(os.path.join(M.OUT, "*__live__*"))}
    spent, rows = 0.0, []
    for scn, arm in CELLS:
        cap = round(BUDGET - spent, 8)
        os.environ["M2S_REPL_CAP"] = str(cap)
        M.LIVE_CAP = cap
        os.environ["M2S_LIVE_OK"] = M.inputs_sha(scn)
        known = set(glob.glob(os.path.join(M.OUT, f"{scn}__{arm}__live__*")))
        M.live(scn, arm)
        new = sorted(set(glob.glob(os.path.join(M.OUT, f"{scn}__{arm}__live__*"))) - known)
        assert len(new) == 1, new
        res = json.load(open(os.path.join(new[0], "result.json"), encoding="utf-8"))
        spent += res["cost_usd"]
        row = dict(cell=f"{scn}-{arm}", replaces=REPLACES[(scn, arm)], run=os.path.basename(new[0]), cap_usd=cap,
                   cost_usd=res["cost_usd"], technical=technical(new[0]), paid=bool(res["db_after"]["transactions"]))
        rows.append(row)
        if row["technical"]:
            break
    unchanged = all(M.sha(os.path.join(d, "result.json")) == s for d, s in before.items())
    report = dict(budget_usd=BUDGET, spent_usd=round(spent, 8), rows=rows, earlier_results_unchanged=unchanged,
                  status="COMPLETE" if len(rows) == 3 and not any(r["technical"] for r in rows) else "STOPPED")
    json.dump(report, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "help"
    if mode == "_child":
        M._child(sys.argv[2], sys.argv[3])
    elif mode == "run":
        run()
    else:
        print(__doc__)
