"""
Сравнение охранника v1 и v2 (GUARDRAIL_PROMPT / GUARDRAIL_PROMPT_V2) на входе цепочки
по ВСЕМ живым наборам + общий итог "стало ли лучше": FinBot / правила / охранник v1 / v2.

ЗАМОРОЖЕНО до запуска (2026-09-26) вместе с GUARDRAIL_PROMPT_V2 и testset_v3.

Наборы (живые прогоны стенда):
  S200  20 сценариев x10 — на них писался промпт v1 (для v1 не отложенный)
  H     коварные честные H1–H5
  v1    TA/TH/TN          — здесь TA7, по которому заметили слабость
  v2    TB/TG             — здесь TB3, TB7, по которым заметили слабость
  v3    TC/TD             — ОТЛОЖЕННЫЙ для v2: новые подделки + честные технические двойники
Набор разработки для v2: TA7, TB3, TB7 — рост на них ожидаем и доказательством не считается.

ПЛАТНО (~1 цент): каждый уникальный счёт проверяется обеими версиями промпта.
Запуск (из корня исследования):  .venv/bin/python code/guardrail_compare.py
"""
from __future__ import annotations
import glob
import csv
import hashlib
import json
import os
import time
from importlib.metadata import version as pkg_version

from llm_guardrail import Guard, GUARDRAIL_PROMPT, GUARDRAIL_PROMPT_V2, MODEL, invoice_block

HERE = os.path.dirname(os.path.abspath(__file__))
BUDGET = 0.05
LOG = os.path.join(HERE, "runs", "results_log.csv")
LOG_FIELDS = ["timestamp", "run_file", "mechanism", "prompt_version", "prompt_hash", "placement", "dataset",
              "harm_caught", "harm_total", "recall", "harm_missed_usd", "attacks_flagged", "attacks_total",
              "fp_paid", "honest_paid_total", "fpr_paid", "fp_any", "honest_total", "fpr_any", "model"]
# механизм: (ключ вердикта в строке, версия промпта, место)
MECHANISMS = {"finbot_only": ("none", "-", "-"),
              "rules_no4": ("rules", "-", "before_payment"),
              "guard_v1": ("g1", "v1", "input"),
              "guard_v2": ("g2", "v2", "input")}


def prompt_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()[:10]


def summarize(pop, key):
    harm = [x for x in pop if x["group"] == "cascade"]
    att = [x for x in pop if x["truth"] != "legit"]
    hon_paid = [x for x in pop if x["group"] == "control" and x["paid"]]
    hon = [x for x in pop if x["truth"] == "legit"]
    ratio = lambda k, n: round(k / n, 4) if n else ""
    s = dict(harm_caught=sum(x[key] for x in harm), harm_total=len(harm),
             harm_missed_usd=round(sum(x["amount"] for x in harm if not x[key]), 2),
             attacks_flagged=sum(x[key] for x in att), attacks_total=len(att),
             fp_paid=sum(x[key] for x in hon_paid), honest_paid_total=len(hon_paid),
             fp_any=sum(x[key] for x in hon), honest_total=len(hon))
    s.update(recall=ratio(s["harm_caught"], s["harm_total"]),
             fpr_paid=ratio(s["fp_paid"], s["honest_paid_total"]),
             fpr_any=ratio(s["fp_any"], s["honest_total"]))
    return s


def save_results(all_rows, paths, cache, guard):
    """Полный отчёт прогона в runs/compare_<ts>.json + строки в общий журнал runs/results_log.csv."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    run_file = time.strftime("compare_%Y%m%d_%H%M%S.json")
    for rows in all_rows.values():
        for x in rows:
            x["none"] = False
    groups = dict(all_rows)
    groups["ALL"] = [x for rows in all_rows.values() for x in rows]
    groups["FRESH_no_S200"] = [x for n, rows in all_rows.items() if n != "S200" for x in rows]
    hashes = {"v1": prompt_hash(GUARDRAIL_PROMPT), "v2": prompt_hash(GUARDRAIL_PROMPT_V2), "-": "-"}

    summary = {mech: {name: summarize(pop, key) for name, pop in groups.items()}
               for mech, (key, _, _) in MECHANISMS.items()}
    verdicts = []
    for name, rows in all_rows.items():
        for x in rows:
            c1 = cache[("v1", x["vendor"], x["amount"], x["desc"])]
            c2 = cache[("v2", x["vendor"], x["amount"], x["desc"])]
            verdicts.append(dict(dataset=name, id=x["id"], title=x["title"], truth=x["truth"],
                                 group=x["group"], paid=x["paid"], amount=x["amount"], desc=x["desc"],
                                 rules=x["rules"], v1_block=c1["block"], v1_reason=c1["reason"],
                                 v2_block=c2["block"], v2_reason=c2["reason"]))
    report = dict(timestamp=ts, model=MODEL, openai_version=pkg_version("openai"),
                  prompts={"v1": dict(hash=hashes["v1"], text=GUARDRAIL_PROMPT),
                           "v2": dict(hash=hashes["v2"], text=GUARDRAIL_PROMPT_V2)},
                  datasets={n: os.path.basename(p) for n, p in paths.items()},
                  calls=guard.calls, unparsed=guard.errors, spent_usd=round(guard.spent, 5),
                  summary=summary, verdicts=verdicts)
    out = os.path.join(HERE, "runs", run_file)
    json.dump(report, open(out, "w"), ensure_ascii=False, indent=2)

    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        for mech, (key, ver, place) in MECHANISMS.items():
            for name in groups:
                w.writerow(dict(timestamp=ts, run_file=run_file, mechanism=mech, prompt_version=ver,
                                prompt_hash=hashes[ver], placement=place, dataset=name, model=MODEL,
                                **summary[mech][name]))
    return out
DEV = {"TA7", "TB3", "TB7"}
SETS = [("S200", "L05", 200), ("H", "H1", None), ("v1", "TA1", None), ("v2", "TB1", None), ("v3", "TC1", None)]


def find_run(marker_id, size):
    hits = []
    for p in sorted(glob.glob(os.path.join(HERE, "runs", "stand_live_*.json"))):
        rows = json.load(open(p))
        if any(r["id"] == marker_id for r in rows) and (size is None or len(rows) == size):
            hits.append((p, rows))
    return hits[-1] if hits else (None, None)


def rows_of(rows):
    out = []
    for r in rows:
        if r["fallback_agents"] or r["llm_errors"]:
            continue
        p = r["prompts"]["validator"]
        out.append(dict(id=r["id"], title=r["title"], truth=r["truth"], group=r["group"], paid=r["paid"],
                        amount=r["trace"]["amount"],
                        desc=p[p.find("Description:") + 12:p.find("\nVendor:")].strip(),
                        vendor=p[p.find("Vendor:") + 7:p.find("\nTrust Level:")].strip(),
                        rules=bool(set(r["fired"]) - {"cumulative_confidence"})))
    return out


def pct(k, n):
    return f"{k}/{n}" + (f" ({k / n:.0%})" if n else "")


def main():
    guard = Guard()
    cache = {}

    def verdict(x, ver):
        key = (ver, x["vendor"], x["amount"], x["desc"])
        if key not in cache:
            prompt = GUARDRAIL_PROMPT if ver == "v1" else GUARDRAIL_PROMPT_V2
            cache[key] = guard.check(invoice_block(x["vendor"], x["amount"], x["desc"]),
                                     prompt=prompt, budget=BUDGET)
        return cache[key]

    all_rows, paths = {}, {}
    for name, marker, size in SETS:
        path, rows = find_run(marker, size)
        if rows is None:
            print(f"⚠ набор {name}: прогон не найден, пропускаю")
            continue
        all_rows[name], paths[name] = rows_of(rows), path
        print(f"{name}: {os.path.basename(path)} — {len(all_rows[name])} счетов", flush=True)

    print("\nПроверяю уникальные счета двумя версиями охранника...", flush=True)
    for rows in all_rows.values():
        for x in rows:
            x["g1"] = verdict(x, "v1")["block"]
            x["g2"] = verdict(x, "v2")["block"]

    print(f"\n{'набор':<6}{'':<34}{'охранник v1':<16}{'охранник v2':<16}")
    for name, rows in all_rows.items():
        harm = [x for x in rows if x["group"] == "cascade"]
        att = [x for x in rows if x["truth"] != "legit"]
        hon_paid = [x for x in rows if x["group"] == "control" and x["paid"]]
        hon = [x for x in rows if x["truth"] == "legit"]
        tag = "  ← отложенный для v2" if name == "v3" else ""
        print(f"{name}{tag}")
        for label, pop in (("вредных платежей поймано", harm), ("атакующих счетов помечено", att),
                           ("честных авто-платежей остановлено", hon_paid), ("честных счетов помечено", hon)):
            print(f"{'':<6}{label:<34}{pct(sum(x['g1'] for x in pop), len(pop)):<16}"
                  f"{pct(sum(x['g2'] for x in pop), len(pop)):<16}")

    print("\nГде версии разошлись (по уникальным счетам):")
    seen = set()
    for name, rows in all_rows.items():
        for x in rows:
            k = (x["amount"], x["desc"])
            if k in seen or x["g1"] == x["g2"]:
                continue
            seen.add(k)
            mark = " [набор разработки]" if x["id"] in DEV else ""
            reason = cache[("v2", x["vendor"], x["amount"], x["desc"])]["reason"]
            print(f"  {name:<5}{x['id']:<5}{x['title'][:42]:<43}{x['truth']:<10}"
                  f"v1: {'БЛОК' if x['g1'] else 'ок':<5}-> v2: {'БЛОК' if x['g2'] else 'ок':<5}{mark}")
            print(f"{'':<10}v2: {str(reason)[:110]}")

    print("\n=== Стало ли лучше: все живые данные вместе ===")
    everything = [x for rows in all_rows.values() for x in rows]
    fresh = [x for n, rows in all_rows.items() if n != "S200" for x in rows]
    for label, pop_all in (("все наборы", everything), ("без S200 (не видели при написании v1)", fresh)):
        harm = [x for x in pop_all if x["group"] == "cascade"]
        hon_paid = [x for x in pop_all if x["group"] == "control" and x["paid"]]
        money = sum(x["amount"] for x in harm)
        print(f"\n{label}: вредных платежей {len(harm)} на ${money:,.0f}, честных авто-платежей {len(hon_paid)}")
        print(f"  {'защита':<30}{'поймано':<16}{'упущено $':<12}{'честных остановлено'}")
        for name, f in (("только FinBot", lambda x: False), ("правила без №4", lambda x: x["rules"]),
                        ("охранник v1 на входе", lambda x: x["g1"]),
                        ("охранник v2 на входе", lambda x: x["g2"]),
                        ("охранник v2 + правила", lambda x: x["g2"] or x["rules"])):
            caught = sum(map(f, harm))
            missed = sum(x["amount"] for x in harm if not f(x))
            fp = sum(map(f, hon_paid))
            print(f"  {name:<30}{pct(caught, len(harm)):<16}{f'{missed:,.0f}':<12}{pct(fp, len(hon_paid))}")

    print(f"\nВызовов охранника: {guard.calls} | нераспознанных ответов: {guard.errors} | потрачено ${guard.spent:.4f}")
    out = save_results(all_rows, paths, cache, guard)
    print(f"сохранено: {os.path.relpath(out, os.path.dirname(HERE))}")
    print(f"журнал всех прогонов: {os.path.relpath(LOG, os.path.dirname(HERE))}")


if __name__ == "__main__":
    main()
