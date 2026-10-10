"""
Сводка любого прогона FinBot (без вызовов LLM): сумма × вариант → решение Invoice, пометка Fraud, Payments, оплата.

Читает папку профиля (…/<имя>/<профиль>/) с файлами *.hooks.jsonl, *.db.json, *.out.txt и сценарии из
scenarios.json в этой папке (или файл, указанный вторым аргументом).

Запуск:  python3 code/summarize_run.py code/runs/finbot477_sweepF_t0_20261007/F
"""
from __future__ import annotations
import glob
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pairs_reasoning import load_run, money, DEC, VAR_RU  # noqa: E402


def summarize(prof_dir, scenarios=None):
    scenarios = scenarios or os.path.join(prof_dir, "scenarios.json")
    S = {s["id"]: s for s in json.load(open(scenarios, encoding="utf-8"))}
    rows = defaultdict(list)
    cost = 0.0
    for hp in sorted(glob.glob(os.path.join(prof_dir, "*.hooks.jsonl"))):
        sid = os.path.basename(hp)[:-12]
        if sid not in S or not os.path.exists(hp.replace(".hooks.jsonl", ".db.json")):
            continue
        sc = S[sid]
        rows[(sc["amount"], sc.get("variant", "base"))].append(load_run(hp))
        for l in open(hp.replace(".hooks.jsonl", ".out.txt"), encoding="utf-8", errors="replace"):
            if l.startswith("COST_USD"):
                cost += float(l.split()[1])
    n = sum(len(v) for v in rows.values())
    print(f"\n{prof_dir}: {n} прогонов из {len(S)} в сценариях, ≈ ${cost:.2f}\n")
    print("| Сумма | Вариант | Invoice | Fraud пометил | Payments позван | **Оплачено** |\n|---|---|---|---|---|---|")
    order = list(VAR_RU)
    for (amt, v) in sorted(rows, key=lambda k: (k[0], order.index(k[1]) if k[1] in order else 99)):
        rs = rows[(amt, v)]
        inv = ", ".join(f"{DEC.get(k, k)} {c}" for k, c in Counter(r["inv_status"] for r in rs).most_common())
        k = len(rs)
        print(f"| {money(amt)} | {VAR_RU.get(v, v)} | {inv} | {sum(bool(r['flags']) for r in rs)}/{k} | "
              f"{sum(r['pay_called'] for r in rs)}/{k} | **{sum(r['paid'] for r in rs)}/{k}** |")
    allr = [r for v in rows.values() for r in v]
    if allr:
        print(f"\nВсего: одобрено {sum(r['inv_status'] == 'approved' for r in allr)}/{n}, пометка Fraud "
              f"{sum(bool(r['flags']) for r in allr)}/{n}, **оплачено {sum(r['paid'] for r in allr)}/{n}**.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    summarize(sys.argv[1].rstrip("/"), sys.argv[2] if len(sys.argv) > 2 else None)
