"""
Измерительный харнесс: прогоняет проверки на 3 уровнях и считает recall / FPR / latency.

Уровни размещения контроля (это и есть предмет проекта):
  between      — проверка стоит ПОСЛЕ КАЖДОГО агента; цепочка обрывается на самой
                 ранней границе, где сработал инвариант. Платёж предотвращён,
                 оставшиеся шаги пропущены (экономия latency).
  orchestrator — все проверки прогоняются один раз после сборки цепочки, но ДО
                 исполнения платежа. Платёж предотвращён, но агенты уже отработали.
  final        — проверки на финальном ответе, ПОСЛЕ исполнения платежа.
                 Каскад можно только зафиксировать (detected), но не предотвратить.

Метрики (по каждому уровню):
  recall_prevented — доля вредных каскадов, ОБОРВАННЫХ до платежа (главное число);
  recall_detected  — доля вредных каскадов, хотя бы замеченных;
  FPR              — доля ИСПРАВНЫХ прогонов (контроль), где проверка сработала зря;
  FPR_paid         — то же, но только среди честных счетов, которые шли в оплату
                     (FPR разбавлен счетами на review: их блокировать нечего);
  overhead_ms      — средняя стоимость самих проверок на прогон;
  saved_ms         — средняя сэкономленная latency на предотвращённых каскадах
                     (из STEP_LATENCY — допущения, не замеры).

ОГРАНИЧЕНИЕ ТЕКУЩЕЙ МОДЕЛИ УРОВНЕЙ: все три уровня видят ВЕСЬ трейс; различаются
только моментом (раньше/позже, до/после платежа). В реальности уровни различаются
ещё и тем, что видно проверке: граница — одно сообщение между агентами, оркестратор —
всю цепочку, финальный ответ — только итоговое решение. Поэтому recall между
between и orchestrator здесь совпадает по построению.

Правила №2/№3 требуют вывода платёжного агента; "предотвращение" для них
предполагает, что платёж сначала вычисляется, а исполняется после проверки.

Типы каскадов — по классификации Веры (см. sim.py).

Запуск:  python3.11 harness.py                 (как на стенде Веры)
         python3.11 harness.py --extras        (+ режимы отказа, которых у Веры нет)
         python3.11 harness.py --no-gate       (без встроенного стопа стенда)
"""
from __future__ import annotations
import argparse
from collections import Counter
from agent_trace import AGENTS, STEP_LATENCY
from checks import REGISTRY, RULE_NO
import sim

CHECK_COST_S = 0.0005   # стоимость одной структурной проверки (правило, ~микросекунды-мс)


def _boundary(agent_name: str) -> int:
    return AGENTS.index(agent_name)


def evaluate(trace, checks):
    """Возвращает: сработавшие проверки и самую раннюю границу срабатывания."""
    fired = {}
    earliest = None
    for name in checks:
        fn, earliest_agent = REGISTRY[name]
        out = fn(trace)
        if out.fired:
            fired[name] = out.reason
            b = _boundary(earliest_agent)
            earliest = b if earliest is None else min(earliest, b)
    return fired, earliest


def saved_latency(earliest_boundary: int) -> float:
    """Latency шагов ПОСЛЕ границы обрыва (их можно не выполнять)."""
    if earliest_boundary is None:
        return 0.0
    return sum(STEP_LATENCY[AGENTS[i]] for i in range(earliest_boundary + 1, len(AGENTS)))


def run_level(level, traces, checks):
    casc = [t for t in traces if t.is_cascade]
    control = [t for t in traces if t.group == "control"]
    n_ctrl_paid = sum(1 for t in control if t.paid())

    prevented = detected = fp = 0
    saved_total = 0.0
    overhead_total = 0.0

    for t in traces:
        fired, earliest = evaluate(t, checks)
        overhead_total += len(checks) * CHECK_COST_S
        flagged = bool(fired)

        if t.is_cascade:
            if flagged:
                detected += 1
                if level in ("between", "orchestrator"):   # до исполнения платежа
                    prevented += 1
                    if level == "between":
                        saved_total += saved_latency(earliest)
        elif t.group == "control":          # FPR только на исправной контрольной группе
            if flagged:
                fp += 1

    n_casc = len(casc) or 1
    n_ctrl = len(control) or 1
    return {
        "level": level,
        "recall_prevented": prevented / n_casc,
        "recall_detected": detected / n_casc,
        "fpr": fp / n_ctrl,
        "fpr_paid": fp / n_ctrl_paid if n_ctrl_paid else 0.0,
        "overhead_ms": (overhead_total / len(traces)) * 1000,
        "saved_ms": (saved_total / prevented) * 1000 if prevented else 0.0,
    }


def per_check_breakdown(traces, checks):
    casc = [t for t in traces if t.is_cascade]
    control = [t for t in traces if t.group == "control"]
    rows = []
    for name in checks:
        fn, _ = REGISTRY[name]
        tp = sum(1 for t in casc if fn(t).fired)
        fp = sum(1 for t in control if fn(t).fired)
        rows.append((name, tp, fp))
    return rows


def _vera_tag(ctype):
    return "" if ctype in sim.VERA_TYPES else "  (вне классификации Веры)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=502)
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--extras", action="store_true",
                    help="добавить режимы отказа, невозможные на стенде Веры")
    ap.add_argument("--no-gate", action="store_true",
                    help="выключить встроенный стоп стенда (approval.confidence < 0.3)")
    args = ap.parse_args()

    params = sim.SimParams(extras=args.extras, vera_gate=not args.no_gate)
    traces = sim.make_dataset(seed=args.seed, n=args.n, params=params)
    checks = list(REGISTRY.keys())
    by_type = Counter(t.cascade_type for t in traces if t.group != "control")
    n_casc = sum(1 for t in traces if t.is_cascade)
    n_ctrl = sum(1 for t in traces if t.group == "control")
    n_handled = sum(1 for t in traces if t.group == "handled_bad")

    mode = []
    if args.extras:
        mode.append("+extras")
    if args.no_gate:
        mode.append("без встроенного стопа")
    print(f"\nТренажёр (seed={args.seed}, n={len(traces)}"
          f"{', ' + ', '.join(mode) if mode else ', как на стенде Веры'})")
    print(f"  честные счета (контроль, для FPR): {n_ctrl}")
    print(f"  вредные каскады (деньги ушли, для recall): {n_casc}")
    for ct in sim.HARMFUL_VERA + sim.HARMFUL_EXTRA:
        if by_type[ct]:
            print(f"      {ct:<17}{by_type[ct]:>5}{_vera_tag(ct)}")
    print(f"  плохие счета, остановленные системой сама: {n_handled}")
    for ct in sim.HARMLESS_VERA + sim.HARMLESS_EXTRA + ["none"]:
        if by_type[ct]:
            label = "обычный отказ, не каскад" if ct == "none" else ""
            print(f"      {ct:<17}{by_type[ct]:>5}{_vera_tag(ct) if ct != 'none' else '  (' + label + ')'}")
    print(f"Проверки: {', '.join(checks)}\n")

    print("=" * 88)
    print(f"{'Уровень':<14}{'recall_prev':>12}{'recall_det':>12}{'FPR':>9}{'FPR_paid':>10}"
          f"{'overhead_ms':>13}{'saved_ms':>10}")
    print("-" * 88)
    for level in ("between", "orchestrator", "final"):
        r = run_level(level, traces, checks)
        print(f"{r['level']:<14}{r['recall_prevented']:>12.2%}{r['recall_detected']:>12.2%}"
              f"{r['fpr']:>9.2%}{r['fpr_paid']:>10.2%}{r['overhead_ms']:>13.3f}{r['saved_ms']:>10.1f}")
    print("=" * 88)

    print("\nПо проверкам:")
    print(f"  {'правило':<28}{'стоит после':<18}{'поймано (TP)':>13}{'ложняков (FP)':>15}")
    for name, tp, fp in per_check_breakdown(traces, checks):
        label = f"№{RULE_NO[name]} {name}"
        print(f"  {label:<28}{REGISTRY[name][1]:<18}{tp:>13}{fp:>15}")

    print("\nRecall по типам вредных каскадов (любой проверкой):")
    for ct in sim.HARMFUL_VERA + sim.HARMFUL_EXTRA:
        subset = [t for t in traces if t.is_cascade and t.cascade_type == ct]
        if not subset:
            continue
        caught = sum(1 for t in subset if evaluate(t, checks)[0])
        print(f"  {ct:<14}{caught:>4}/{len(subset):<4} = {caught / len(subset):>6.1%}{_vera_tag(ct)}")
    print()


if __name__ == "__main__":
    main()
