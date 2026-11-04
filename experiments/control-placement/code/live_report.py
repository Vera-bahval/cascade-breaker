"""
Отчёт по живому прогону стенда (code/runs/stand_live_*.json).

Считает частоты с 95% доверительными интервалами Уилсона: при 10 повторах на
сценарий интервалы широкие, и это нужно видеть рядом с каждой цифрой.

Наборы правил:
  все       — все 8 правил;
  без №4    — без cumulative_confidence (на живом стенде оно режет честные авто-платежи).

Только stdlib:  python3.11 code/live_report.py [путь_к_json]
"""
from __future__ import annotations
import glob
import json
import math
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW_LIMIT = 5000.0


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def rate(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.0%} [{lo:.0%}–{hi:.0%}]" if n else "—"


def caught(r, without4):
    fired = set(r["fired"])
    if without4:
        fired.discard("cumulative_confidence")
    return bool(fired)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else sorted(
        glob.glob(os.path.join(HERE, "runs", "stand_live_*.json")))[-1]
    R = json.load(open(path))
    polluted = [r for r in R if r.get("fallback_agents") or r.get("llm_errors")]
    clean = [r for r in R if r not in polluted]
    print(f"\nФайл: {os.path.relpath(path, os.path.dirname(HERE))}")
    print(f"Счетов: {len(R)} | с запасной логикой / ошибкой вызова (исключены): {len(polluted)}")

    by_sc = defaultdict(list)
    for r in clean:
        by_sc[r["id"]].append(r)

    print(f"\n{'id':<4}{'сценарий':<44}{'правда':<10}{'деньги ушли':<14}{'вредно':<12}"
          f"{'поймано без №4':<16}")
    for sid, rs in by_sc.items():
        n = len(rs)
        paid = sum(r["paid"] for r in rs)
        harm = [r for r in rs if r["group"] == "cascade"]
        got = sum(caught(r, True) for r in harm)
        print(f"{sid:<4}{rs[0]['title'][:43]:<44}{rs[0]['truth']:<10}{f'{paid}/{n}':<14}"
              f"{f'{len(harm)}/{n}':<12}{(f'{got}/{len(harm)}' if harm else '—'):<16}")

    harm = [r for r in clean if r["group"] == "cascade"]
    ctrl = [r for r in clean if r["group"] == "control"]
    ctrl_paid = [r for r in ctrl if r["paid"]]
    types = Counter(r["cascade_type"] for r in harm)

    print("\n=== Итог (охрана до платежа) ===")
    print(f"Вредных каскадов: {len(harm)} из {len(clean)} счетов  |  типы: {dict(types)}")
    for label, w4 in (("все 8 правил", False), ("без №4", True)):
        tp = sum(caught(r, w4) for r in harm)
        fp_all = sum(caught(r, w4) for r in ctrl)
        fp_paid = sum(caught(r, w4) for r in ctrl_paid)
        print(f"  {label:<13} recall {rate(tp, len(harm))}")
        print(f"  {'':<13} ложные блоки: среди честных авто-платежей {rate(fp_paid, len(ctrl_paid))},"
              f" среди всех честных {rate(fp_all, len(ctrl))}")

    print("\nПо правилам (TP — на вредных каскадах, FP — на честных счетах):")
    names = sorted({n for r in clean for n in r["fired"]})
    for name in names:
        tp = sum(name in r["fired"] for r in harm)
        fp = sum(name in r["fired"] for r in ctrl)
        print(f"  {name:<24} TP {tp:>3}   FP {fp:>3}")

    big = [r for r in clean if r["trace"]["amount"] > REVIEW_LIMIT]
    big_auto = [r for r in big if any(s["agent"] == "Approval" and s["data"].get("decision") == "approve"
                                      for s in r["trace"]["steps"])]
    print(f"\nМодель авто-одобрила сумму выше лимита {REVIEW_LIMIT:.0f}: {rate(len(big_auto), len(big))}")

    lat = defaultdict(list)
    role_of = {"Validator": "validator", "RiskAnalyzer": "risk", "Approval": "approval"}
    for r in clean:
        for s in r["trace"]["steps"]:
            if role_of.get(s["agent"]) in r["responses"]:
                lat[s["agent"]].append(s["latency_s"])
    print("Задержка вызова модели, с (среднее / медиана / макс): " + "; ".join(
        f"{a} {sum(v) / len(v):.2f} / {sorted(v)[len(v) // 2]:.2f} / {max(v):.2f}"
        for a, v in lat.items()))


if __name__ == "__main__":
    main()
