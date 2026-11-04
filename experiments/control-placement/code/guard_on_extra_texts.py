"""
LLM-охранник v2 (вид «вход»: только текст счёта) на текстах, у которых ещё нет вердикта: 150 обычных честных счетов
(v6, Llama 3.3 70B), тексты матрицы и эксперимента «пары» без вердикта (уже проверенные пропускаются). Тот же промпт, поставщик и 3 повтора с большинством голосов,
что и в guard_on_texts.py.

Пишет code/runs/guard_extra_<ts>.json (отдельное имя — чтобы скрипты, читающие последний guard_texts_*.json,
не подхватили неполный набор). scorecard.py читает оба файла.

Запуск:  .venv/bin/python code/guard_on_extra_texts.py [--repeats 3] [--budget 0.10]
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import time

from llm_guardrail import Guard, GUARDRAIL_PROMPT_V2, invoice_block
from levels_detector import UNTRUSTED

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = "Northlight Equipment Rentals LLC"


def collect() -> list[dict]:
    have = set()
    for f in sorted(glob.glob(os.path.join(HERE, "runs", "guard_texts_*.json")))[-1:] + sorted(glob.glob(os.path.join(HERE, "runs", "guard_extra_*.json"))):
        have |= {(float(x["amount"]), x["desc"]) for x in json.load(open(f, encoding="utf-8"))["items"]}
    out, seen = [], set(have)
    for path in ("v6_honest_scenarios.json", "matrix_scenarios.json", "pairs_scenarios.json"):
        for s in json.load(open(os.path.join(HERE, "finbot477", path), encoding="utf-8")):
            key = (float(s["amount"]), s["desc"])
            if key not in seen:
                seen.add(key)
                out.append(dict(src=path.split("_")[0], id=s["id"], truth=s["truth"], amount=float(s["amount"]), desc=s["desc"]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--budget", type=float, default=0.10)
    args = ap.parse_args()
    scs = collect()
    print(f"текстов без вердикта: {len(scs)}")
    g = Guard()
    t0 = time.time()
    for s in scs:
        ctx = UNTRUSTED + invoice_block(VENDOR, s["amount"], s["desc"])
        votes = [g.check(ctx, prompt=GUARDRAIL_PROMPT_V2, budget=args.budget) for _ in range(args.repeats)]
        s["blocks"] = sum(v["block"] for v in votes)
        s["block"] = s["blocks"] * 2 > args.repeats
        s["reason"] = next((v["reason"] for v in votes if v["block"] == s["block"]), None)
        s["latency_s"] = round(sum(v["latency_s"] for v in votes) / len(votes), 3)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(HERE, "runs", f"guard_extra_{ts}.json")
    json.dump(dict(timestamp=ts, prompt="v2", view="input", vendor=VENDOR, repeats=args.repeats,
                   spent_usd=round(g.spent, 4), calls=g.calls, parse_errors=g.errors, seconds=round(time.time() - t0),
                   items=scs), open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{path}\nвызовов {g.calls}, ошибок разбора {g.errors}, ${g.spent:.4f}, {time.time() - t0:.0f} с")
    for src in dict.fromkeys(s["src"] for s in scs):
        part = [s for s in scs if s["src"] == src]
        for t in dict.fromkeys(s["truth"] for s in part):
            b = sum(s["block"] for s in part if s["truth"] == t)
            n = sum(1 for s in part if s["truth"] == t)
            print(f"  {src:7} {t:10} тревога {b:3} / {n:3}")
    print(f"  нестабильных (голоса разошлись): {sum(0 < s['blocks'] < args.repeats for s in scs)} из {len(scs)}")


if __name__ == "__main__":
    main()
