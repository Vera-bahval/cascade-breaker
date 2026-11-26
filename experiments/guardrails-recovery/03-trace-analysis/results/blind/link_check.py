"""Риск узнавания одинаковых трасс между парными листами (A1↔A2, B1↔B2): для каждой строки первого листа ищем строку
второго с максимальным пересечением «отпечатков» (числа, даты, суммы, коды). Считаем, сколько строк находят пару
однозначно и верно. Только чтение листов и ключа."""
import csv, re, sys
key = {r["blind_id"]: r for r in csv.DictReader(open("KEY_CLOSED/key.csv", encoding="utf-8-sig"))}
load = lambda n: list(csv.DictReader(open(f"sheets/{n}.csv", encoding="utf-8-sig")))
KINDS = {"даты": r"\b\d{4}-\d{2}-\d{2}\b", "суммы": r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d+\.\d{1,2}\b|\b\d{1,3}(?:,\d{3})+\b",
         "id и коды": r"\b(?:[A-Z]{1,6}[#-]?)?\d{3,}(?:[-/][A-Z0-9]+)*\b|\btr_[0-9a-f]{8,}\b",
         "все числа": r"\$?\b[\w-]*\d[\w.,-]*\b"}
def toks(t, pat): return {m.replace(",", "").rstrip(".0") for m in re.findall(pat, t)} - {""}
def link(a, b, fa, fb, pat):
    A, B = load(a), load(b); run = lambda r: key[r["id"]]["path"] + "|" + key[r["id"]]["scenario"]
    TB = [(run(r), toks(" ".join(r[f] for f in fb), pat)) for r in B]
    uniq = ok = 0; partners = 0
    for r in A:
        if not any(run(r) == rb for rb, _ in TB): continue
        partners += 1
        ta = toks(" ".join(r[f] for f in fa), pat)
        sc = [(len(ta & tb), rb) for rb, tb in TB]; m = max(s for s, _ in sc)
        top = [rb for s, rb in sc if s == m and m > 0]
        if len(top) == 1:
            uniq += 1; ok += top[0] == run(r)
    return f"{ok}/{partners} верно однозначно (однозначных {uniq})"
for k, pat in KINDS.items():
    print(f"{k:10s} A1→A2:", link("A1_transfer", "A2_payments", ["fraud_flag", "fraud_summary", "orchestrator_task_for_payments"], ["payments_input", "payments_steps"], pat),
          "| B1→B2:", link("B1_fraud_text", "B2_delivery", ["fraud_summary"], ["condition_from_fraud", "payments_input"], pat))
