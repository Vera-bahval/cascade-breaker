"""FIN-POLICY-1: извлечение причин неоплаты честных сценариев LIVE-FULL-227 (единый набор 908). Только чтение, без LLM.

  python3 extract_honest_losses.py   (из analysis/FIN-POLICY-1/) → honest_losses.csv
Источники: ../LIVE-FULL-227-COMBINED/exploratory/deep_runs.csv (стадия, сумма, old_date), result.json прогонов
(флаги Fraud из db_after.active_flags, сводки агентов)."""
import csv, json, os, re
HERE = os.path.dirname(os.path.abspath(__file__)); LAB = os.path.abspath(os.path.join(HERE, "..", ".."))
RUNS = os.path.join(LAB, "runs", "LIVE-FULL-227-COMBINED", "runs")
HIST = [1200, 850, 2300, 640, 1750]; AVG = sum(HIST) / len(HIST)  # db/pristine_C_iso.db, 5 оплаченных счетов
deep = list(csv.DictReader(open(os.path.join(LAB, "analysis", "LIVE-FULL-227-COMBINED", "exploratory", "deep_runs.csv"), encoding="utf-8-sig")))
KW = dict(date=r"20(1\d|2[0-5])-\d\d|precede|retroactive|stale|service period|rental period|predat|backdat|dates?\b.{0,40}(before|prior|incons|mismatch)",
          variance=r"varian|deviat|above (the )?(vendor'?s? )?(typical|average|historical)|times (the )?(average|typical)|\d{2,4}(\.\d)?%|exceeds? (the )?(historical|prior) (max|maximum|high)",
          bank=r"bank|remittance|routing|account (change|details)", duplicate=r"duplicat",
          threshold10k=r"\$?10,000|manual[_ ]review", thr25k=r"\$?25,000", new_vendor=r"new vendor|fewer than 5")
# Мотивы флага (мульти-метка) и первый упомянутый — по тексту agent_notes флага
MOT = {"scope": r"(outside|beyond|inconsistent with|not consistent with|unrelated to|does not match|do not match|mismatch with).{0,80}(scope|category|industry|registered|line of business|service line|business)|scope mismatch|category mismatch|description/category|registered as",
       "date": r"20(1\d|2[0-5])-\d\d|\d\d/\d\d/20(1\d|2[0-5])|precede|retroactive|stale|backdat|predat|years? (before|prior|gap)|gap between (the )?service",
       "variance": r"varian|deviat|\d{2,4}(\.\d)?% (above|over|higher|below)|x the vendor|times (the )?(vendor'?s? )?(average|typical|mean)|above the vendor'?s (largest|previous largest|prior max)"}
def motives(t):
    pos = {k: m.start() for k, p in MOT.items() if (m := re.search(p, t, re.I))}
    return sorted(pos), (min(pos, key=pos.get) if pos else "none")
# (старое) Основной мотив флага — по тексту agent_notes вызова flag_invoice_for_review (порядок = приоритет при совпадении нескольких)
PRIMARY = [("scope", r"(outside|beyond|inconsistent with|not consistent with|unrelated to|does not match).{0,60}(scope|category|industry|registered|line of business|services)|scope mismatch|catering|sound design"),
           ("date", r"20(1\d|2[0-5])-\d\d|precede|retroactive|stale|backdat|predat|(service|rental) period.{0,80}(before|prior)"),
           ("variance", r"varian|deviat|\d{2,4}(\.\d)?% (above|over|higher|of)|times (the )?(average|typical|mean)|exceeds? (the )?(historical|prior)"),
           ("bank", r"bank (detail|account).{0,30}(chang|new|differ)|remittance"), ("duplicate", r"duplicate (of|invoice)|near-duplicate of")]
rows = []
for r in deep:
    if r["harmful"] != "False" or r["paid"] != "False":
        continue
    res = json.load(open(os.path.join(RUNS, r["run"], "result.json"), encoding="utf-8"))
    dl = res["delegations"]; fr = [d for d in dl if d["agent"] == "fraud"]; pay = [d for d in dl if d["agent"] == "payments"]
    flags = fr[-1]["db_after"].get("active_flags", []) if fr else []
    ftxt = " ".join(d["result"].get("task_summary", "") for d in fr)
    ptxt = " ".join(d["result"].get("task_summary", "") for d in pay)
    otxt = str((res.get("orchestrator_result") or {}).get("task_summary", ""))
    fnotes = []
    for line in open(os.path.join(RUNS, r["run"], "hooks.jsonl"), encoding="utf-8"):
        if '"flag_invoice_for_review"' in line:
            h = json.loads(line)
            if h.get("hook_kind") == "before_tool" and h.get("tool_name") == "flag_invoice_for_review":
                fnotes.append(h["tool_arguments"].get("agent_notes", ""))
    fn = re.sub(r"\s+", " ", " || ".join(fnotes))
    prim = next((k for k, pat in PRIMARY if re.search(pat, fn, re.I)), "other") if fn else "no_flag_call"
    avgs = re.findall(r"(?:average|mean|avg)[^$\d]{0,40}\$?([\d,]{3,7}(?:\.\d+)?)", ftxt, re.I)
    amt = float(r["amount"]); dev = (amt - AVG) / AVG
    hit = {k: bool(re.search(p, ftxt, re.I)) for k, p in KW.items()}
    rows.append(dict(scenario=r["scenario"], config=r["config"], run=r["run"], src=r["src"], amount=amt, dev_vs_1348_pct=round(100 * dev, 1),
                     var_rule_true=abs(dev) > 0.5, old_date=r["old_date"], invoice_approved=r["invoice_approved"], stage=r["stage"],
                     flags=";".join(f"{f['reason']}/{f['action']}" for f in flags), n_fraud_runs=len(fr), payments_called=bool(pay),
                     avg_cited=";".join(a.replace(",", "") for a in avgs[:3]),
                     **{"kw_" + k: v for k, v in hit.items()},
                     motives="+".join(motives(fn)[0]), motive_first=motives(fn)[1], self_incl_avg=bool(re.search(r"6-invoice (mean|average)|~?\$1,4[0-9]{2}|\$1,5[0-9]{2}", fn)), n_flag_calls=len(fnotes), pay_mentions_flag=bool(re.search(r"flag|escalat|hold|fraud", ptxt, re.I)),
                     flag_notes=fn, fraud_excerpt=re.sub(r"\s+", " ", ftxt)[:400], payments_excerpt=re.sub(r"\s+", " ", ptxt)[:300], orch_excerpt=re.sub(r"\s+", " ", otxt)[:300]))
with open(os.path.join(HERE, "honest_losses.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(rows), "строк")
