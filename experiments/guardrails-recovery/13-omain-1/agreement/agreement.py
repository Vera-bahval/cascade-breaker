"""Согласие разметчиков OMAIN-1 (только чтение размеченных файлов). Пишет agreement/*.csv и печатает свод."""
import csv, collections, os
HERE = os.path.dirname(os.path.abspath(__file__)); B = os.path.join(HERE, "../blind/")
K = list(csv.DictReader(open(os.path.join(HERE, "../KEY_CLOSED/key_blind_to_run.csv"), encoding="utf-8-sig")))
s2b = {k["second_id"]: k["blind_id"] for k in K if k["second_id"]}
g2f = {k["fraud_id"].replace("F", "G"): k["fraud_id"] for k in K if k["second_id"] and k["fraud_id"]}
meta = {k["blind_id"]: k for k in K}
C1 = {r["blind_id"]: r for r in csv.DictReader(open(B + "coder1_payments_FILLED.csv", encoding="utf-8-sig"))}
C2 = {r["blind_id"]: r for r in csv.DictReader(open(B + "coder2_payments_selfaudit.csv", encoding="utf-8-sig"))}
F1 = {r["blind_id"]: r for r in csv.DictReader(open(B + "coder1_fraud_FILLED.csv", encoding="utf-8-sig"))}
F2 = {r["blind_id"]: r for r in csv.DictReader(open(B + "coder2_fraud_selfaudit.csv", encoding="utf-8-sig"))}

def kappa(a, b):
    n = len(a); po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n / n
    return po, (po - pe) / (1 - pe) if pe < 1 else float("nan")

PQ = ["class_final", "q1_transfer", "q2_stop_signal", "q3_stop_reason", "q4_doubt_in_paid_report",
      "q5_fabricated_claim", "q6_report_contradicts_facts", "q7_repeats_no_anomaly", "q8_states_deviation", "q9_amplification_0_1_2"]
FQ = ["f1_flag_decision", "f2_own_history_check", "f3_relies_on_external_claim", "f4_states_correct_comparison"]
pairs = [(s2b[s], s) for s in sorted(C2)]
out = []
print("Payments, n =", len(pairs))
for q in PQ:
    a = [C1[b][q] for b, s in pairs]; c = [C2[s][q] for b, s in pairs]
    po, k = kappa(a, c); out.append(dict(table="payments", field=q, n=len(a), agree=round(po, 3), kappa=round(k, 3)))
    print(f"  {q:32s} agree {po:.3f}  kappa {k:.3f}")
fp = [(g2f[g], g) for g in sorted(F2)]
print("Fraud, n =", len(fp))
for q in FQ:
    a = [F1[f][q] for f, g in fp]; c = [F2[g][q] for f, g in fp]
    po, k = kappa(a, c); out.append(dict(table="fraud", field=q, n=len(a), agree=round(po, 3), kappa=round(k, 3)))
    print(f"  {q:32s} agree {po:.3f}  kappa {k:.3f}")
w = csv.DictWriter(open(os.path.join(HERE, "agreement_summary.csv"), "w", newline="", encoding="utf-8"), fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
# расхождения
D = []
for b, s in pairs:
    diff = [q for q in PQ if C1[b][q] != C2[s][q]]
    if diff:
        m = meta[b]
        D.append(dict(blind_id=b, second_id=s, model=m["model"], scenario=m["scenario"], intervention=m["intervention"], fields=";".join(diff),
                      **{f"c1_{q}": C1[b][q] for q in diff}, c1_expl=C1[b]["explanation"], c2_values="; ".join(f"{q}={C2[s][q]}" for q in diff),
                      c2_expl=C2[s]["explanation"], c2_conf=C2[s]["confidence_1_3"], c1_conf=C1[b]["confidence_1_3"]))
cols = sorted({k for d in D for k in d}, key=lambda x: (not x.startswith(("blind", "second", "model", "scen", "interv", "fields")), x))
w = csv.DictWriter(open(os.path.join(HERE, "disagreements_payments.csv"), "w", newline="", encoding="utf-8"), fieldnames=cols); w.writeheader(); w.writerows(D)
print("строк с расхождением (Payments):", len(D), collections.Counter(d["fields"] for d in D).most_common())
FD = []
for f, g in fp:
    diff = [q for q in FQ if F1[f][q] != F2[g][q]]
    if diff:
        FD.append(dict(fraud_id=f, second=g, fields=";".join(diff), c1="; ".join(f"{q}={F1[f][q]}" for q in diff), c2="; ".join(f"{q}={F2[g][q]}" for q in diff),
                       c1_expl=F1[f]["explanation"], c2_expl=F2[g]["explanation"], amount=F1[f]["invoice_amount_usd"]))
if FD:
    w = csv.DictWriter(open(os.path.join(HERE, "disagreements_fraud.csv"), "w", newline="", encoding="utf-8"), fieldnames=list(FD[0])); w.writeheader(); w.writerows(FD)
print("строк с расхождением (Fraud):", len(FD), collections.Counter(d["fields"] for d in FD).most_common())
print("классы: c1 vs c2", collections.Counter((C1[b]["class_final"], C2[s]["class_final"]) for b, s in pairs if C1[b]["class_final"] != C2[s]["class_final"]))
