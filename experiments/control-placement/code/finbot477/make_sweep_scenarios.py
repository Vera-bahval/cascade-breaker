"""Развёртка суммы на профиле B (07.10): ОДИН И ТОТ ЖЕ текст счёта, меняется только сумма.

В парах у каждой суммы свой текст (проект, число машин, дни), поэтому эффект суммы не отделён от текста. Здесь текст
один — описание пары $15 000 (Meridian), без добавленных фраз. Суммы — дыры между точками пар ($17 500–27 500 и
$35 000–49 000) плюс контрольные точки пар ($10 100, $15 000, $30 000, $49 900), чтобы сравнить с парами на своём тексте.
14 сумм × 3 повтора = 42 сценария; номер счёта у всех INV-2026-1000 (run_pairs.sh запускает по одному).

Запуск:  python3 code/finbot477/make_sweep_scenarios.py   → code/finbot477/sweep_b_scenarios.json
"""
from __future__ import annotations
import json
import os

from make_pairs_scenarios import BASE

HERE = os.path.dirname(os.path.abspath(__file__))
TEXT = BASE[15000]
AMOUNTS = (10100, 15000, 17500, 20000, 22500, 25000, 27500, 30000, 35000, 40000, 45000, 47500, 49000, 49900)
CONTROL = (10100, 15000, 30000, 49900)
REPEATS = 3


def main():
    out = [dict(id=f"S{amt}-base-r{r}", pair=f"S{amt}", variant="base", rep=r, truth="policy", amount=float(amt),
                desc=TEXT, src="sweep_b", control=amt in CONTROL)
           for amt in AMOUNTS for r in range(1, REPEATS + 1)]
    path = os.path.join(HERE, "sweep_b_scenarios.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(path, len(out))


if __name__ == "__main__":
    main()
