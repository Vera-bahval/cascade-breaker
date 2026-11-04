"""
Воронка жизни ошибки на прогонах с ПОДЛОЖЕННЫМИ ошибками (автоматическая часть, без вызовов модели).

Для каждой подложенной ошибки известно, где она родилась (fault_step). Смотрим, что с ней стало дальше:
  поймана следующим ботом (исправлена системой) / принята и передана дальше / дошла до денег.
"Поймал" для бота FinBot:
  RiskAnalyzer — risk_level high/critical;   Approval — decision != approve;
  Payment — встроенный стоп (LOW_CUMULATIVE_CONFIDENCE).
Глубина = сколько ботов после источника приняли ошибку.

"Усилена" автоматически НЕ размечается: это решает человек по кодбуку (annotation/КОДБУК_v0.md).

Только stdlib:  python3.11 code/lifecycle_funnel.py
"""
from __future__ import annotations
import csv
import glob
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "annotation")
DOWNSTREAM = {"validator": ["RiskAnalyzer", "Approval", "PaymentProcessor"],
              "risk": ["Approval", "PaymentProcessor"],
              "approval": ["PaymentProcessor"]}
KIND_RU = {"val_pass": "валидатор пропустил проблему", "val_amount": "валидатор занизил сумму",
           "risk_underrate": "оценщик занизил риск", "appr_override": "одобрение вопреки политике"}


def caught(step):
    d = step["data"]
    if step["agent"] == "RiskAnalyzer":
        return (not step["success"]) or d.get("risk_level") in ("high", "critical")
    if step["agent"] == "Approval":
        return (not step["success"]) or d.get("decision") != "approve"
    if step["agent"] == "PaymentProcessor":
        return not d.get("payment_processed")
    return False


KEY_FIELDS = {"validator": ("valid", "normalized_data.amount"), "risk": ("risk_level",),
              "approval": ("decision",)}


def _get(d, dotted):
    for part in dotted.split("."):
        d = (d or {}).get(part) if isinstance(d, dict) else None
    return d


def effective(r):
    """Изменила ли подмена решение бота (ключевое поле), или ответ и так был таким."""
    from llm_guardrail import loose_json
    before = loose_json(r.get("fault_original"))
    after = loose_json(r["responses"].get(r["fault_step"]))
    return any(_get(before, k) != _get(after, k) for k in KEY_FIELDS[r["fault_step"]])


def lifecycle(r):
    steps = {s["agent"]: s for s in r["trace"]["steps"]}
    v = steps.get("Validator")
    if r["fault_step"] == "validator" and v is not None and not v["success"]:
        # валидатор всё равно отклонил счёт (подмена не сделала его "valid") — дальше никто не работал
        return dict(depth=0, recovered_by="Validator (сам отклонил)", final_impact=r["paid"],
                    path="validator ✋Validator")
    path, recovered_by = [], None
    for agent in DOWNSTREAM[r["fault_step"]]:
        s = steps.get(agent)
        if s is None:
            break
        if caught(s):
            recovered_by = agent
            break
        path.append(agent)
    return dict(depth=len(path), recovered_by=recovered_by or "-", final_impact=r["paid"],
                path=" → ".join([r["fault_step"]] + path) + (f" ✋{recovered_by}" if recovered_by else ""))


def main():
    files = [f for f in sorted(glob.glob(os.path.join(HERE, "runs", "stand_live_*.json")))
             if any(r.get("fault") for r in json.load(open(f)))]
    applied = [r for f in files for r in json.load(open(f)) if r.get("fault_applied")]
    rows = [r for r in applied if effective(r)]
    base = [r for f in files for r in json.load(open(f)) if r["id"].endswith("-none")]
    print(f"Файлы: {[os.path.basename(f) for f in files]}")
    print(f"Без подложенной ошибки FinBot заплатил: {sum(r['paid'] for r in base)}/{len(base)}")
    noeff = [r for r in applied if not effective(r)]
    print(f"Подмен применено {len(applied)}; не изменили решение бота (ответ и так был таким): {len(noeff)} "
          f"{sorted({r['id'] for r in noeff})} — исключены из воронки\n")

    agg = defaultdict(list)
    out = []
    for r in rows:
        lc = lifecycle(r)
        agg[r["fault"]].append(lc)
        out.append(dict(trace=f"{r['id']}#{r.get('repeat', 0)}", fault=r["fault"], origin=r["fault_step"], **lc))

    print(f"{'ошибка':<32}{'n':>3}{'  передана дальше':>18}{'  дошла до денег':>17}{'  ср. глубина':>14}   кто исправил")
    for kind in ("val_pass", "val_amount", "risk_underrate", "appr_override"):
        L = agg.get(kind, [])
        if not L:
            continue
        n = len(L)
        prop = sum(x["depth"] > 0 for x in L)
        imp = sum(x["final_impact"] for x in L)
        rec = defaultdict(int)
        for x in L:
            rec[x["recovered_by"]] += 1
        rec_s = ", ".join(f"{k}: {v}" for k, v in sorted(rec.items()) if k != "-") or "никто"
        print(f"{KIND_RU[kind]:<32}{n:>3}{prop:>12}/{n:<5}{imp:>11}/{n:<5}"
              f"{sum(x['depth'] for x in L) / n:>10.1f}     {rec_s}")

    all_prop = [x for L in agg.values() for x in L if x["depth"] > 0]
    print(f"\nP(дошла до денег | передана дальше) = {sum(x['final_impact'] for x in all_prop)}/{len(all_prop)}")

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "lifecycle_funnel.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"по каждому прогону: {os.path.relpath(path, os.path.dirname(HERE))}")


if __name__ == "__main__":
    main()
