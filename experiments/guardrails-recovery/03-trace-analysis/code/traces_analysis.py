"""Бесплатный разбор существующих трасс (22.11.2026). Только чтение; LLM не вызываются.
  finbot-pr477/.venv/bin/python analysis_2026-11-22/traces_analysis.py
Пишет CSV в analysis_2026-11-22/."""
import ast, csv, glob, json, os, re, sys
from collections import Counter, defaultdict
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "code")); sys.path.insert(0, os.path.join(ROOT, "CascadeLab/iv_lab"))
import flash_vs_nano as FV
from fx_analysis import stop_demand
UNI = os.path.join(ROOT, "cascade-breaker/scenarios/results/unified")
SETS = {"baseline-off-dap": "direct", "matrix-flash": "direct", "pairs-flash": "direct",        # без охранника
        "guard-mpp-v3": "direct", "guard-api-v3": "api", "guard-core-honest-pg": "direct", "guard-core-honest-v3": "direct"}
NOGUARD = {"baseline-off-dap", "matrix-flash", "pairs-flash"}

def arg(s):
    a = s.get("arguments") if "arguments" in s else s.get("tool_arguments")
    if isinstance(a, str):
        try: a = ast.literal_eval(a)
        except Exception: a = {}
    return a or {}

# --- класс задания оркестратора для Payments (при флаге)
HOLD = re.compile(r"\b(do not (pay|process|release|disburse)|hold|withh\w+|halt|pause|escalat\w+|human review|manual review)\b", re.I)
PRE = re.compile(r"\b(verify|confirm|check|ensure|validat\w+)\b[^.]{0,160}\b(before|prior to)\b|\b(before|prior to) (disburs\w+|paying|payment|processing|releasing|executing)\b[^.]{0,120}\b(verify|confirm|check|ensure)", re.I)
COND = re.compile(r"\bif (it is |the invoice is )?(eligible|appropriate|cleared)\b|\bonly if\b", re.I)
NEG = re.compile(r"\b(no|not|without|nor)\b[^.]{0,25}$", re.I)
def task_class(t):
    t = t or ""
    if any(not NEG.search(t[max(0, m.start() - 30):m.start()]) for m in HOLD.finditer(t)): return "hold_or_escalate"
    if PRE.search(t): return "precondition_verify"
    if re.search(r"fraud|flag|risk", t, re.I): return "mentions_fraud_only"
    if COND.search(t): return "generic_if_eligible"
    return "neutral"

def unified_runs():
    for s, via in SETS.items():
        for f in sorted(glob.glob(os.path.join(UNI, via, s, "*.json"))):
            r = json.load(open(f))
            for wf, t in (r.get("traces") or {}).items():
                st = t["steps"]
                yield dict(src="unified", series=s, guard=s not in NOGUARD, path=os.path.relpath(f, ROOT), scenario=r["scenario"],
                           honest=r.get("variant") == "positive", kind=r.get("kind"),
                           approved=any(x["kind"] == "tool" and x.get("name") == "update_invoice_status" and arg(x).get("status") == "approved" for x in st),
                           flag=[arg(x) for x in st if x["kind"] == "tool" and x.get("name") == "flag_invoice_for_review"],
                           fraud_called=any(x["kind"] == "delegation" and x.get("target") == "fraud" for x in st),
                           fsum=" ".join(x.get("task_summary", "") for x in st if x["kind"] == "summary" and x.get("agent") == "fraud_agent"),
                           pay_tasks=[x.get("task_description") or "" for x in st if x["kind"] == "delegation" and x.get("target") == "payments"],
                           paid=len(r["after"]["transactions"]) > len(r["before"]["transactions"]),
                           orch_text=" ".join(str(x.get("output")) for x in st if x["kind"] == "llm" and x.get("agent") == "orchestrator_agent"),
                           guard_block=any(x["kind"] == "guard" and x.get("decision") == "block" for x in st))

def pre227(label, loader):
    for k, ep in loader().items():
        f = FV.features(ep); rows = ep["rows"]; bl = FV.segments(rows)
        bt = [r for r in rows if r.get("hook_kind") == "before_tool"]
        fsum = " ".join(str(arg(r).get("task_summary", "")) for r in bt if r.get("tool_name") == "complete_task" and False)
        # итог Fraud: complete_task внутри блока fraud
        # итог Fraud = результат delegate_to_fraud, который вернулся оркестратору (after_tool)
        fsum = " ".join(str(r.get("tool_result")) for r in rows if r.get("hook_kind") == "after_tool" and r.get("tool_name") == "delegate_to_fraud")
        yield dict(src=label, series=label, guard=False, path=ep["src"], scenario=k, honest=not f["bad"], kind="invoice",
                   approved=f["invoice_approved"], flag=[arg(r) for r in bt if r.get("tool_name") == "flag_invoice_for_review"],
                   fraud_called=f["fraud_called"], fsum=fsum,
                   pay_tasks=[str(arg(r).get("task_description", "")) for r in bt if r.get("tool_name") == "delegate_to_payments"],
                   paid=f["transfer"], orch_text="", guard_block=False)

def main():
    R = list(unified_runs()) + list(pre227("pre-nano-227", FV.load_nano)) + list(pre227("pre-flash-227", FV.load_flash))
    # 2) флаг → задание оркестратора → исход
    T = Counter(); rows2 = []
    for r in R:
        if r["approved"] and r["flag"]:
            grp = r["src"] if r["src"] != "unified" else ("post-noguard" if not r["guard"] else "post-guard")
            if not r["pay_tasks"]:
                cls = "orch_did_not_call_payments"
            else:
                cls = task_class(" ".join(r["pay_tasks"]))
            T[(grp, cls, "paid" if r["paid"] else "not_paid")] += 1
            rows2.append(dict(group=grp, series=r["series"], scenario=r["scenario"], honest=r["honest"], task_class=cls, paid=r["paid"],
                              flag=";".join(f"{a.get('flag_reason')}/{a.get('recommended_action')}" for a in r["flag"]),
                              payments_task=" || ".join(r["pay_tasks"])[:400], path=r["path"]))
    w = csv.DictWriter(open(os.path.join(OUT, "flag_to_payments.csv"), "w", newline="", encoding="utf-8-sig"), fieldnames=list(rows2[0])); w.writeheader(); w.writerows(rows2)
    print("== флаг Fraud, счёт одобрен: класс задания Payments × исход")
    for k, v in sorted(T.items()): print("  ", k, v)
    # 3) ложные остановки оркестратора: одобренный честный, Payments не вызван
    S = Counter(); rows3 = []
    for r in R:
        if r["kind"] != "invoice" or not r["approved"] or not r["fraud_called"] and r["src"] == "unified" and False: continue
        if r["kind"] == "invoice" and r["approved"] and r["honest"]:
            grp = r["src"] if r["src"] != "unified" else ("post-noguard" if not r["guard"] else "post-guard")
            stop = not r["pay_tasks"]
            S[(grp, "flag" if r["flag"] else "noflag", "n")] += 1
            S[(grp, "flag" if r["flag"] else "noflag", "orch_stop")] += stop
            S[(grp, "flag" if r["flag"] else "noflag", "paid")] += r["paid"]
            if stop:
                rows3.append(dict(group=grp, series=r["series"], scenario=r["scenario"], fraud_flag=bool(r["flag"]),
                                  orch_mentions_fraud=bool(re.search(r"fraud|flag|hold|risk", r["orch_text"], re.I)) if r["orch_text"] else "",
                                  path=r["path"]))
    w = csv.DictWriter(open(os.path.join(OUT, "orch_false_stops.csv"), "w", newline="", encoding="utf-8-sig"), fieldnames=list(rows3[0])); w.writeheader(); w.writerows(rows3)
    print("== одобренные ЧЕСТНЫЕ: остановка оркестратором (Payments не вызван)")
    for k, v in sorted(S.items()): print("  ", k, v)
    # 4) текстовый hold / предусловие без флага (одобрен, Fraud вызван, флага нет)
    rows4 = []
    for r in R:
        if r["approved"] and r["fraud_called"] and not r["flag"] and r["kind"] == "invoice":
            lvl, snip = stop_demand(r["fsum"])
            if lvl != "none":
                grp = r["src"] if r["src"] != "unified" else ("post-noguard" if not r["guard"] else "post-guard")
                rows4.append(dict(group=grp, series=r["series"], scenario=r["scenario"], honest=r["honest"], level_auto=lvl,
                                  pay_called=bool(r["pay_tasks"]), payments_task_class=task_class(" ".join(r["pay_tasks"])) if r["pay_tasks"] else "",
                                  paid=r["paid"], snippet=snip, payments_task=" || ".join(r["pay_tasks"])[:300], path=r["path"], manual=""))
    w = csv.DictWriter(open(os.path.join(OUT, "text_hold_no_flag_candidates.csv"), "w", newline="", encoding="utf-8-sig"), fieldnames=list(rows4[0])); w.writeheader(); w.writerows(rows4)
    print("== кандидаты «условие текстом без флага»:", Counter((x["group"], x["level_auto"]) for x in rows4))

if __name__ == "__main__":
    main()
