"""
Кривая trade-off по инварианту №4 (порог накопленной confidence).

Остальные правила (все, кроме №4) фиксированы. Свипаем порог №4 и смотрим рабочую
точку всей связки: recall (предотвращённые каскады) против FPR (ложные блоки
исправных платежей). Это ROC-подобная кривая "контроль vs ложные срабатывания" —
ровно тот график из ТЗ.

Порог задаёт срабатывание №4: fired, если произведение confidence < threshold.
Выше порог -> №4 ловит больше (↑recall), но и чаще блокирует честных (↑FPR).

Метрики берём для уровня, СПОСОБНОГО предотвращать (between/orchestrator);
на финале recall_prev = 0 при любом пороге, поэтому кривую строим для превенции.

Выбор рабочей точки: минимизируем ожидаемую цену
    cost = C * (пропущенные каскады) + 1 * (ложные блоки),
где C = стоимость пропуска каскада / стоимость ложного блока. В антифроде
пропущенный фрод обычно дороже ложного блока -> C > 1.

Запуск:  python3.11 sweep_conf.py            (seed=502, n=800)
         python3.11 sweep_conf.py --n 2000 --seed 7
"""
from __future__ import annotations
import argparse
import csv
import os
from checks import REGISTRY, check_cumulative_confidence
import sim

# Все правила, кроме №4: их срабатывание от порога не зависит.
OTHER_RULES = [fn for name, (fn, _) in REGISTRY.items() if name != "cumulative_confidence"]


def flagged(trace, conf_threshold):
    """Сработала ли хоть одна проверка связки при данном пороге №4."""
    if any(fn(trace).fired for fn in OTHER_RULES):
        return True
    return check_cumulative_confidence(trace, threshold=conf_threshold).fired


def measure(traces, conf_threshold):
    casc = [t for t in traces if t.is_cascade]
    ctrl = [t for t in traces if (not t.is_cascade) and t.group == "control"]
    ctrl_paid = [t for t in ctrl if t.paid()]   # честные счета, реально шедшие в оплату
    tp = sum(1 for t in casc if flagged(t, conf_threshold))
    fp = sum(1 for t in ctrl if flagged(t, conf_threshold))
    return {
        "threshold": conf_threshold,
        "recall": tp / len(casc),
        "fpr": fp / len(ctrl),
        # FPR среди честных АВТО-ПЛАТЕЖЕЙ: доля честных платежей, которые ложно заблокированы.
        # Это и есть "ложный блок честного платежа"; обычный FPR его разбавляет счетами,
        # ушедшими на review (их проверки платежа не могут заблокировать в принципе).
        "fpr_paid": fp / len(ctrl_paid) if ctrl_paid else 0.0,
        "tp": tp, "fp": fp,
        "missed": len(casc) - tp,
        "n_casc": len(casc), "n_ctrl": len(ctrl), "n_ctrl_paid": len(ctrl_paid),
    }


def ascii_curve(rows):
    """Компактный ASCII-график: recall (Y) против FPR (X)."""
    W, H = 40, 12
    grid = [[" "] * (W + 1) for _ in range(H + 1)]
    for r in rows:
        x = min(W, round(r["fpr"] * W / max(0.001, max(rr["fpr"] for rr in rows))))
        y = min(H, round(r["recall"] * H))
        grid[H - y][x] = "*"
    lines = []
    for j, row in enumerate(grid):
        rec = (H - j) / H
        lines.append(f"{rec:4.0%} |" + "".join(row))
    xmax = max(rr["fpr"] for rr in rows)
    lines.append("     +" + "-" * (W + 1))
    lines.append(f"      0%{' ' * (W - 6)}FPR->{xmax:.0%}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=502)
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--costs", type=float, nargs="*", default=[2, 5, 10, 20],
                    help="значения C = цена(пропуск каскада)/цена(ложный блок)")
    ap.add_argument("--extras", action="store_true",
                    help="добавить режимы отказа, невозможные на стенде Веры")
    ap.add_argument("--no-gate", action="store_true",
                    help="выключить встроенный стоп стенда (approval.confidence < 0.3)")
    args = ap.parse_args()

    params = sim.SimParams(extras=args.extras, vera_gate=not args.no_gate)
    traces = sim.make_dataset(seed=args.seed, n=args.n, params=params)
    thresholds = [round(0.30 + 0.05 * k, 2) for k in range(0, 14)]  # 0.30 .. 0.95
    rows = [measure(traces, th) for th in thresholds]

    # Базовая линия: только структурные инварианты (порог №4 отключён -> 0.0).
    base = measure(traces, 0.0)

    print(f"\nДатасет sim (seed={args.seed}, n={args.n}): "
          f"каскады={base['n_casc']}, контроль={base['n_ctrl']}")
    print(f"  из контроля реально шли в оплату (честные авто-платежи): {base['n_ctrl_paid']}")
    print(f"База (все правила, кроме №4): recall={base['recall']:.1%}, FPR={base['fpr']:.1%}\n")

    print(f"{'thr №4':>7}{'recall':>9}{'FPR':>8}{'FPR_paid':>10}{'TP':>6}{'FP':>6}{'missed':>8}")
    print("-" * 54)
    for r in rows:
        print(f"{r['threshold']:>7.2f}{r['recall']:>9.1%}{r['fpr']:>8.1%}{r['fpr_paid']:>10.1%}"
              f"{r['tp']:>6}{r['fp']:>6}{r['missed']:>8}")

    print("\nКривая recall vs FPR:")
    print(ascii_curve(rows))

    # Рекомендация по бизнес-цене (prevalence-aware, как в антифроде).
    # Ожидаемая цена на один счёт:
    #   cost = prevalence*(1-recall)*C + (1-prevalence)*FPR
    # где C = цена(пропуск каскада)/цена(ложный блок). При редких каскадах
    # (низкий prevalence) FPR начинает доминировать -> порог опускается.
    def rec(prevalence, C):
        return min(rows, key=lambda r: prevalence * (1 - r["recall"]) * C
                   + (1 - prevalence) * r["fpr"])

    dataset_prev = base["n_casc"] / (base["n_casc"] + base["n_ctrl"])
    print(f"\nВыбор порога по ожидаемой цене на счёт "
          f"(cost = π*(1-recall)*C + (1-π)*FPR):")
    print(f"  π — доля каскадов; в этом датасете π={dataset_prev:.0%} (нереалистично высокая)")
    prevalences = [dataset_prev, 0.05, 0.01]
    corner = "π / C"
    header = "".join(f"{'C=' + str(int(C)):>18}" for C in args.costs)
    print(f"\n  {corner:>8}" + header)
    for prevalence in prevalences:
        cells = []
        for C in args.costs:
            b = rec(prevalence, C)
            cells.append(f"{b['threshold']:.2f} ({b['recall']:.0%}/{b['fpr_paid']:.0%})")
        print(f"  {prevalence:>8.0%}" + "".join(f"{c:>18}" for c in cells))
    print("  в ячейке: порог (recall / FPR_paid)")

    # CSV для последующего построения графика.
    out = os.path.join(os.path.dirname(__file__), "sweep_conf.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["threshold", "recall", "fpr", "fpr_paid", "tp", "fp", "missed"])
        for r in rows:
            w.writerow([r["threshold"], f"{r['recall']:.4f}", f"{r['fpr']:.4f}",
                        f"{r['fpr_paid']:.4f}", r["tp"], r["fp"], r["missed"]])
    print(f"\nCSV сохранён: {out}")


if __name__ == "__main__":
    main()
