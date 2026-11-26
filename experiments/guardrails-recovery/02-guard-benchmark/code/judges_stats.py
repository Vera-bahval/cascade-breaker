"""Судьи P0/P4 × 6 моделей × агенты nano/Flash: recall, FPR (Уилсон), парные сравнения (точный Мак-Немар, Холм), Кохрен Q.
Только чтение вердиктов (code/runs/judges_*.json) через загрузчик judges_variants_report.load(). LLM не вызываются."""
import csv, math, os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "code"))
import judges_variants_report as JR

def holm(ps):
    o = sorted(range(len(ps)), key=lambda i: ps[i]); adj = [0] * len(ps); run = 0
    for r, i in enumerate(o):
        run = max(run, min(1, (len(ps) - r) * ps[i])); adj[i] = run
    return adj

def chi2_sf_df5(x):
    return math.erfc(math.sqrt(x / 2)) + math.sqrt(2 * x / math.pi) * math.exp(-x / 2) * (1 + x / 3)

def cochran_q(mat):  # mat: список строк (по случаям) из 0/1 по k судьям
    k = len(mat[0]); C = [sum(r[j] for r in mat) for j in range(k)]; R = [sum(r) for r in mat]; N = sum(R)
    den = k * N - sum(x * x for x in R)
    if den == 0: return 0.0, 1.0
    q = (k - 1) * (k * sum(c * c for c in C) - N * N) / den
    return q, chi2_sf_df5(q)

cases, ep, V, jv = JR.load()
ids = sorted(cases); bad = [i for i in ids if cases[i]["bad"]]; hon = [i for i in ids if not cases[i]["bad"]]
blk = lambda v, a, m, i: bool((V[(v, a, m)].get(i) or {}).get("block"))
nov = lambda v, a, m: sum(JR.no_verdict(V[(v, a, m)].get(i)) for i in ids)

rows = []
for a in JR.AGENTS:
    for v in JR.VARIANTS:
        for m in JR.JUDGES:
            r = sum(blk(v, a, m, i) for i in bad); f = sum(blk(v, a, m, i) for i in hon)
            rows.append(dict(agents=a, view=v, judge=JR.LABEL[m], recall=f"{r}/{len(bad)}", recall_ci=JR.wilson(r, len(bad)),
                             fpr=f"{f}/{len(hon)}", fpr_ci=JR.wilson(f, len(hon)), unparsed_counted_allow=nov(v, a, m)))
w = csv.DictWriter(open(os.path.join(OUT, "judges_recall_fpr.csv"), "w", newline="", encoding="utf-8-sig"), fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def mc(x, y, S):  # x, y — функции i→bool
    b = sum(x(i) and not y(i) for i in S); c = sum(y(i) and not x(i) for i in S)
    return b, c, JR.mcnemar(b, c)

P = []
for a in JR.AGENTS:              # (i) вид входа P4 против P0 у того же судьи
    for v in ("Raw", "Facts", "Struct"):
        for m in JR.JUDGES:
            for met, S in (("recall", bad), ("FPR", hon)):
                b, c, p = mc(lambda i: blk(v, a, m, i), lambda i: blk("P0", a, m, i), S)
                P.append(dict(family=f"P4_vs_P0/{met}", agents=a, comparison=f"{v} − P0", judge=JR.LABEL[m], only_first=b, only_second=c,
                              diff=b - c, n=len(S), p=p))
for v in ("Raw", "Struct"):     # (ii) агенты Flash против nano (тот же судья, те же эпизоды; P0 и Facts одинаковы по построению)
    for m in JR.JUDGES:
        for met, S in (("recall", bad), ("FPR", hon)):
            b, c, p = mc(lambda i: blk(v, "flash", m, i), lambda i: blk(v, "nano", m, i), S)
            P.append(dict(family=f"agents_flash_vs_nano/{met}", agents="flash−nano", comparison=v, judge=JR.LABEL[m], only_first=b,
                          only_second=c, diff=b - c, n=len(S), p=p))
fam = {}
for x in P: fam.setdefault(x["family"], []).append(x)
for L in fam.values():
    for x, q in zip(L, holm([x["p"] for x in L])): x["p_holm"] = q
w = csv.DictWriter(open(os.path.join(OUT, "judges_paired.csv"), "w", newline="", encoding="utf-8-sig"), fieldnames=list(P[0])); w.writeheader(); w.writerows(P)

Q = []                           # (iii) различаются ли 6 судей на одном входе
for a in JR.AGENTS:
    for v in JR.VARIANTS:
        for met, S in (("recall", bad), ("FPR", hon)):
            mat = [[int(blk(v, a, m, i)) for m in JR.JUDGES] for i in S]
            q, p = cochran_q(mat)
            vals = [sum(r[j] for r in mat) for j in range(6)]
            Q.append(dict(agents=a, view=v, metric=met, n=len(S), min=min(vals), max=max(vals), Q=round(q, 2), p=p))
for x, q in zip(Q, holm([x["p"] for x in Q])): x["p_holm"] = q
w = csv.DictWriter(open(os.path.join(OUT, "judges_cochran.csv"), "w", newline="", encoding="utf-8-sig"), fieldnames=list(Q[0])); w.writeheader(); w.writerows(Q)

for x in Q: print("Q", x["agents"], x["view"], x["metric"], f"{x['min']}–{x['max']}/{x['n']}", x["Q"], f"p={x['p']:.2g} holm={x['p_holm']:.2g}")
for fname, L in fam.items():
    sig = [x for x in L if x["p_holm"] < 0.05]
    print(fname, "значимо после Холма:", len(sig), "из", len(L), "| разности:", sorted({x["diff"] for x in L})[:3], "…", sorted({x["diff"] for x in L})[-3:])
