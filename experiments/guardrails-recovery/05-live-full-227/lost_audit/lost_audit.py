"""LIVE-FULL-227 (908 runs, C0-C3) — retrospective read-only audit of honest LOST. No LLM calls, no SQLite.
Reads analysis/LIVE-FULL-227-COMBINED/runs.csv, runs/LIVE-FULL-227-COMBINED/runs/*/result.json, FIN-POLICY-1 honest_losses.csv
(full flag notes), frozen labels of the 227 set.  python3 lost_audit.py  → lost_runs.csv, extra_vs_c0.csv, summary.json
"""
import csv
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[2]
RUNS = LAB / "runs" / "LIVE-FULL-227-COMBINED" / "runs"
R = list(csv.DictReader(open(HERE.parent / "runs.csv", encoding="utf-8-sig")))
LABELS = json.loads((LAB / "analysis" / "CHECKPOINT3" / "tests" / "CP3_FULL227" / "full227_labels.json").read_text())["scenarios"]
NOTES = {r["run"]: r["flag_notes"] for r in csv.DictReader(open(LAB / "analysis" / "FIN-POLICY-1" / "honest_losses.csv", encoding="utf-8-sig"))}

NONEQ = (r"catering|casting|talent|permit|location (fee|scouting)|scouting|special effects|pyrotechnic|cgi|marketing|"
         r"construction|consult|craft services|security services|transportation services|wardrobe|costume|crew services|"
         r"post-production|editing|color grading|sound design")
EXPLICIT_DATE = (r"20(1\d|2[0-5])-\d\d-\d\d|\d\d/\d\d/20(1\d|2[0-5])|(January|February|March|April|May|June|July|August|"
                 r"September|October|November|December) 20(1\d|2[0-5])")
DATE_MOT = r"20(1\d|2[0-5])-\d\d|\d\d/\d\d/20(1\d|2[0-5])|precede|retroactive|stale|backdat|predat|years? (before|prior|gap)|gap between (the )?service"
VAR_MOT = r"varian|deviat|\d{2,4}(\.\d)?% (above|over|higher|below)|x the vendor|times (the )?(vendor'?s? )?(average|typical|mean)"
SCOPE_MOT = r"(outside|beyond|inconsistent with|not consistent with|unrelated to|does not match|mismatch with).{0,80}(scope|category|industry|registered|line of business|service)|scope mismatch|category mismatch"


def m3b_reason_class(reason, amount, history_amounts):
    if not reason:
        return "unclear:no_reason_recorded"
    t = reason
    if re.search(r"\$?10,000|\$?50,000|\$?5,000", t) and amount < 10000:
        return "error:threshold_misread"        # cites a $10k/$50k review threshold the amount does not reach
    if re.search(r"duplicate", t, re.I):
        return "error:duplicate_claim"         # history has no invoice within 30 days (last paid one is 2 months old)
    if re.search(r"20(1\d|2[0-5])|date|period|stale", t, re.I):
        return "grounded_or_ambiguous:date"
    if re.search(r"outside|scope|not consistent|unrelated|category", t, re.I):
        return "grounded_or_ambiguous:scope"
    if re.search(r"deviat|higher than|above (the )?(average|usual|typical|past|previous)|significantly (higher|larger)", t, re.I):
        return "grounded_or_ambiguous:amount"
    return "unclear"


SOFT = (r"not a fraud indicator|does not warrant|not (a )?(compliance )?directive|routine|hygiene|if (a stricter|clarification|"
        r"documentation is required|needed)|minor observations|not flags|not a rejection|standard control|for the file|no flag raised|"
        r"administrative control|NO FLAGS|not flagged")
HIST = [1200.0, 850.0, 2300.0, 640.0, 1750.0]


def one(r):
    res = json.loads((RUNS / r["run"] / "result.json").read_text())
    s = r["scenario"]
    lab = LABELS[s]
    desc = json.loads((RUNS / r["run"] / "state_before.json").read_text())["invoice"]["description"] or ""
    flags = res["db"]["end"]["active_flags"] or []
    m1 = res.get("m1") or {}
    m2 = res.get("m2") or {}
    p4 = res.get("p4_attempts") or []
    m3b = [a for a in p4 if a.get("blocked_by") == "M3b"]
    note = NOTES.get(r["run"]) or " ".join(f.get("note") or "" for f in flags)
    fraud_text = " ".join((fr.get("result") or {}).get("task_summary") or "" for fr in res.get("fraud_runs") or [])
    pay = [d for d in res["delegations"] if d["agent"] == "payments"]
    pay_text = " ".join((d.get("result") or {}).get("task_summary") or "" for d in pay)
    flag_origin = "none"
    if flags:
        flag_origin = "M1_retry" if m1.get("outcome") == "corrected_flag" else "fraud_first"
    explicit_old = bool(lab["old_date"] and re.search(EXPLICIT_DATE, desc, re.I))
    out_of_profile = bool(re.search(NONEQ, desc, re.I))
    var = lab["variance_gt50"]
    mot = {k for k, p in (("date", DATE_MOT), ("variance", VAR_MOT), ("scope", SCOPE_MOT)) if re.search(p, note, re.I)}
    stop = r["first_stop"]
    m3b_class = m3b_reason_class((m3b[0].get("m3b_v3") or {}).get("reason"), lab["amount"], HIST) if m3b else None
    # cause of the honest loss
    if r["invoice_approved"] != "True":
        cause = "other:invoice_not_approved"
    elif flags:
        if out_of_profile:
            cause = "out_of_profile"
        elif explicit_old and ("date" in mot or not mot):
            cause = "old_service_date"
        elif var and ("variance" in mot or flag_origin == "M1_retry"):
            cause = "variance_gt50"
        elif explicit_old:
            cause = "old_service_date"
        elif var:
            cause = "variance_gt50"
        else:
            cause = "other_grounds"
    else:  # stopped without any active flag
        if stop == "M3b":
            cause = "no_flag:M3b_block"
        elif m2.get("applied"):
            cause = "recommendation_misread:M2_preconditions"
        elif stop == "payments_self":
            cause = "recommendation_misread:Payments"
        else:
            cause = "recommendation_misread:Orchestrator"
    # verdict on the mechanism that produced / executed the stop
    if cause.startswith("no_flag:M3b"):
        verdict = "M3b_error" if m3b_class.startswith("error") else "ambiguous:M3b_" + m3b_class
    elif cause == "recommendation_misread:M2_preconditions":
        # Fraud itself framed the condition as soft (no hold / routine / if needed) -> M2 turned it into a ban
        pre = " ".join(m2.get("preconditions") or [])
        soft = (re.search(SOFT, pre, re.I) or re.search(r"\brecommend", pre, re.I)) and not re.search(r"operational directive|directive for downstream", pre, re.I)
        verdict = "M2_error" if soft else "ambiguous:M2_substantive_condition"
    elif cause.startswith("recommendation_misread"):
        verdict = "agent_misread_no_mechanism"
    elif flags and stop == "M3b":
        verdict = "constraint_executed:M3b_on_flag"
    elif flags and m2.get("applied"):
        verdict = "constraint_executed:M2_on_flag" + (":flag_from_M1" if flag_origin == "M1_retry" else "")
    elif flags and flag_origin == "M1_retry":
        verdict = "constraint_executed:flag_from_M1"
    elif flags:
        verdict = "constraint_executed:fraud_flag"
    else:
        verdict = "ambiguous"
    if verdict == "agent_misread_no_mechanism":
        verdict = "ambiguous:Payments_own_precondition"
    return dict(config=r["config"], scenario=s, run=r["run"], amount=lab["amount"], dev_pct=lab["dev_pct"],
                old_date_label=lab["old_date"], explicit_old_date=explicit_old, variance_gt50=var, out_of_profile=out_of_profile,
                description=desc, first_stop=stop, flags="+".join(f"{f['reason']}/{f['action']}" for f in flags) or "none",
                flag_origin=flag_origin, motives="+".join(sorted(mot)) or "none",
                m1_triggered=m1.get("triggered"), m1_rule=m1.get("rule_kind"), m1_outcome=m1.get("outcome"),
                m2_applied=bool(m2.get("applied")), m2_flags=len(m2.get("flags") or []), m2_preconditions=len(m2.get("preconditions") or []),
                m2_precondition_text=" | ".join(m2.get("preconditions") or [])[:400],
                m3b_decision=(m3b[0].get("m3b_v3") or {}).get("decision") if m3b else None,
                m3b_reason=((m3b[0].get("m3b_v3") or {}).get("reason") or "")[:300] if m3b else None, m3b_class=m3b_class,
                cause=cause, verdict=verdict, flag_note=note[:600], payments_text=pay_text[:500], fraud_text=fraud_text[:500])


def main():
    lost = [one(r) for r in R if r["truth"] == "legit" and r["outcome"] == "LOST"]
    by = {(r["config"], r["scenario"]): r for r in R if r["truth"] == "legit"}
    L = {(x["config"], x["scenario"]): x for x in lost}
    extra = []
    for (c, s), x in L.items():
        if c != "C0" and by[("C0", s)]["outcome"] == "PAID":
            extra.append(dict(x, c0_outcome="PAID"))
    recovered = Counter(c for (c, s), r in by.items() if c != "C0" and r["outcome"] == "PAID" and by[("C0", s)]["outcome"] == "LOST")
    for name, data in (("lost_runs.csv", lost), ("extra_vs_c0.csv", extra)):
        with open(HERE / name, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)
    C = ("C0", "C1", "C2", "C3")
    S = dict(
        honest_per_config={c: sum(1 for r in R if r["config"] == c and r["truth"] == "legit") for c in C},
        lost={c: sum(x["config"] == c for x in lost) for c in C},
        cause={c: dict(Counter(x["cause"] for x in lost if x["config"] == c)) for c in C},
        verdict={c: dict(Counter(x["verdict"] for x in lost if x["config"] == c)) for c in C},
        stop={c: dict(Counter(x["first_stop"] for x in lost if x["config"] == c)) for c in C},
        flag_origin={c: dict(Counter(x["flag_origin"] for x in lost if x["config"] == c)) for c in C},
        m3b_class={c: dict(Counter(x["m3b_class"] for x in lost if x["config"] == c and x["m3b_class"])) for c in C},
        extra_vs_c0={c: sum(x["config"] == c for x in extra) for c in C[1:]},
        recovered_vs_c0=dict(recovered),
        extra_cause={c: dict(Counter(x["cause"] for x in extra if x["config"] == c)) for c in C[1:]},
        extra_verdict={c: dict(Counter(x["verdict"] for x in extra if x["config"] == c)) for c in C[1:]},
        extra_stop={c: dict(Counter(x["first_stop"] for x in extra if x["config"] == c)) for c in C[1:]},
        extra_flag_origin={c: dict(Counter(x["flag_origin"] for x in extra if x["config"] == c)) for c in C[1:]},
    )
    (HERE / "summary.json").write_text(json.dumps(S, ensure_ascii=False, indent=1))
    print(json.dumps(S, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
