"""
Согласие двух разметчиков (Cohen's κ) по разметке `annotation/v1/sample_v1.csv` — кодбук `annotation/КОДБУК_v1.md`.

Сравниваются только шаги, размеченные обоими (непустая колонка «ошибка» у обоих). Значения приводятся к нижнему
регистру и без пробелов по краям.

Только stdlib:  python3 code/kappa.py A.csv B.csv
"""
from __future__ import annotations
import csv
import sys
from collections import Counter

FIELDS = ["ошибка (да/нет/не уверена)", "класс MAST", "класс FinBot (FB-…)", "Evidence: тип основания",
          "Decision (решение)", "передача сигнала"]


def load(path):
    rows = csv.DictReader(open(path, encoding="utf-8-sig"))
    return {r["id"]: {f: (r.get(f) or "").strip().lower() for f in FIELDS} for r in rows}


def kappa(pairs):
    n = len(pairs)
    if n == 0:
        return float("nan"), 0.0
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0, po


def main(a_path, b_path):
    a, b = load(a_path), load(b_path)
    common = [i for i in a if i in b and a[i][FIELDS[0]] and b[i][FIELDS[0]]]
    print(f"шагов, размеченных обоими: {len(common)}")
    for f in FIELDS:
        pairs = [(a[i][f], b[i][f]) for i in common]
        k, po = kappa(pairs)
        print(f"  {f:28} κ = {k:.2f}   совпадение {po:.0%}")
    diff = [i for i in common if a[i][FIELDS[0]] != b[i][FIELDS[0]] or a[i]["класс MAST"] != b[i]["класс MAST"]]
    if diff:
        print("расхождения (ошибка / MAST) — обсудить:", ", ".join(diff))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
