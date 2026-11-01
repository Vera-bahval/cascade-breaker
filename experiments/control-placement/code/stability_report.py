"""
Стабильность охранника по нескольким прогонам guardrail_compare (runs/compare_*.json).

Зачем: даже при temperature 0 охранник на пограничных счетах иногда меняет решение.
Один прогон — это одна "монетка"; здесь видно, какие сценарии решаются стабильно, а какие "гуляют".

Считаем ПО СЦЕНАРИЯМ, а не по повторам одного счёта: повторы одинакового текста почти не
добавляют независимой информации, а раздувают выборку и сужают интервалы (ошибка ранних отчётов).

Только stdlib:  python3.11 code/stability_report.py
"""
from __future__ import annotations
import glob
import json
import math
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def ci(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} [{lo:.0%}–{hi:.0%}]"


def main():
    files = sorted(glob.glob(os.path.join(HERE, "runs", "compare_*.json")))
    runs = [json.load(open(f)) for f in files]
    hashes = {(r["prompts"]["v1"]["hash"], r["prompts"]["v2"]["hash"]) for r in runs}
    print(f"Прогонов: {len(runs)} ({', '.join(os.path.basename(f)[8:23] for f in files)})")
    if len(hashes) > 1:
        print("⚠ в прогонах разные версии промптов — сравнение смешанное:", hashes)

    # сценарий -> сводка
    sc = {}
    for r in runs:
        seen = set()
        for v in r["verdicts"]:
            key = (v["dataset"], v["id"])
            s = sc.setdefault(key, dict(title=v["title"], truth=v["truth"], harmful=False, honest_paid=False,
                                        v1=[], v2=[]))
            s["harmful"] |= v["group"] == "cascade"
            s["honest_paid"] |= (v["group"] == "control" and v["paid"])
            if key not in seen:              # один вердикт на сценарий за прогон (текст одинаковый)
                s["v1"].append(v["v1_block"])
                s["v2"].append(v["v2_block"])
                seen.add(key)

    R = len(runs)
    harm = {k: s for k, s in sc.items() if s["harmful"]}
    hon = {k: s for k, s in sc.items() if s["honest_paid"]}
    fresh = lambda d: {k: s for k, s in d.items() if k[0] != "S200"}

    for ver in ("v1", "v2"):
        print(f"\n=== Охранник {ver} на входе, {R} прогонов ===")
        for label, H, P in (("все наборы", harm, hon), ("без S200", fresh(harm), fresh(hon)),
                            ("v3 (отложенный для v2)", {k: s for k, s in harm.items() if k[0] == "v3"},
                             {k: s for k, s in hon.items() if k[0] == "v3"})):
            always = sum(all(s[ver]) for s in H.values())
            some = sum(any(s[ver]) and not all(s[ver]) for s in H.values())
            fp_any = sum(any(s[ver]) for s in P.values())
            fp_always = sum(all(s[ver]) for s in P.values())
            print(f"  {label:<24} вредных сценариев пойман ВСЕГДА {ci(always, len(H)):<18} "
                  f"иногда {some:<3} | честных сценариев останавливал ХОТЯ БЫ РАЗ {ci(fp_any, len(P)):<18}"
                  f" всегда {fp_always}")

    print("\nНестабильные сценарии (решение менялось между прогонами):")
    flaky = [(k, s) for k, s in sc.items() if len(set(s["v1"])) > 1 or len(set(s["v2"])) > 1]
    for (ds, sid), s in sorted(flaky):
        kind = "ВРЕДНЫЙ" if s["harmful"] else ("честн.оплач" if s["honest_paid"] else s["truth"])
        print(f"  {ds:<5}{sid:<5}{s['title'][:44]:<45}{kind:<12}"
              f"v1 блок {sum(s['v1'])}/{R}   v2 блок {sum(s['v2'])}/{R}")
    if not flaky:
        print("  нет")

    print("\nЧестные сценарии, которые v2 останавливает (хотя бы раз):")
    for (ds, sid), s in sorted(hon.items()):
        if any(s["v2"]):
            print(f"  {ds:<5}{sid:<5}{s['title'][:50]:<51}v2 блок {sum(s['v2'])}/{R}")

    out = os.path.join(HERE, "runs", "stability_summary.json")
    json.dump(dict(runs=[os.path.basename(f) for f in files],
                   scenarios={f"{k[0]}:{k[1]}": s for k, s in sc.items()}),
              open(out, "w"), ensure_ascii=False, indent=2)
    print(f"\nсохранено: {os.path.relpath(out, os.path.dirname(HERE))}")


if __name__ == "__main__":
    main()
