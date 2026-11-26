"""
Судьи на P4 в трёх представлениях контекста × двух конфигурациях FinBot (агенты nano / Flash). ПЛАТНО — только по «ок».

Этапы (каждый — свой предохранитель бюджета):
  raw    — P4 как есть (orchestrator_view: текст счёта + действия и заметки Invoice/Fraud), агенты Flash
           (для nano вердикты raw уже есть с 16.11 — code/runs/judges_nano_full_20261116.json);
  struct — факты + состояние конвейера перечислениями + вычисленные проверки, без прозы агентов; nano и Flash;
  facts  — текст счёта + запись поставщика + прошлые счета; одинаков для nano и Flash → один прогон на обе.

Одинаково во всех вариантах и с прогоном 16.11: промпт GUARDRAIL_PROMPT_V2 + контекст в одном user-сообщении,
temperature=0, остальные параметры генерации по умолчанию (как 16.11), те же 6 моделей через OpenRouter.
Полный запрос (модель + параметры + сообщения) хэшируется; одинаковый запрос отправляется один раз, вердикт
переиспользуется (так struct nano/Flash совпадает в 82 случаях, facts — во всех 227).

Записывается по каждому запросу: токены вход/выход/рассуждения, стоимость (OpenRouter usage.cost), задержка, ответ.
Сохранение каждые 20 запросов. Стоп этапа: бюджет; >10 % неразобранного JSON у судьи; 5 ошибок HTTP подряд.

  .venv/bin/python code/judges_run_variants.py --stage raw    [--dry]
  .venv/bin/python code/judges_run_variants.py --stage struct [--dry]
  .venv/bin/python code/judges_run_variants.py --stage facts  [--dry]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "code"))
from llm_guardrail import GUARDRAIL_PROMPT_V2, loose_json, load_key  # noqa: E402

MODELS = {   # как 16.11
    "nano":    "openai/gpt-5-nano",
    "qwen9b":  "qwen/qwen3.5-9b",
    "flash":   "deepseek/deepseek-v4.1-flash-1017",
    "dschat":  "deepseek/deepseek-chat-v3.1",
    "mistral": "mistralai/mistral-small-3.2-24b-instruct",
    "llama70": "meta-llama/llama-3.3-70b-instruct",
}
TEMPERATURE = 0
BUDGET = {"raw": 1.60, "struct": 2.50, "facts": 1.50}
D = os.path.join(ROOT, "code/runs/flash_vs_nano_20261118")
OUT = os.path.join(ROOT, "code/runs/judges_variants_20261118.json")
WORKERS = 6


def jobs(stage):
    """→ список (variant, agents, case_id, context)."""
    if stage == "raw":
        cs = json.load(open(os.path.join(D, "cases_flash.json"), encoding="utf-8"))
        return [("raw", "flash", c["id"], c["p4"]) for c in cs if c["p4"]]
    out = []
    for agents in ("nano", "flash"):
        cs = json.load(open(os.path.join(D, f"cases_struct_{agents}.json"), encoding="utf-8"))
        key = "p4_struct" if stage == "struct" else "p4_facts"
        out += [(stage, agents if stage == "struct" else "both", c["id"], c[key]) for c in cs]
    if stage == "facts":   # одинаковы для nano и Flash — оставить одну копию
        seen, uniq = set(), []
        for j in out:
            if j[2] not in seen:
                seen.add(j[2]); uniq.append(j)
        out = uniq
    return out


RX = re.compile(r'"block"\s*:\s*(true|false)', re.I)


def parse_kind(txt, out):
    """json — разобрано как 16.11; regex — JSON битый, но поле block читается; empty — пустой ответ
    (обычно рассуждения упёрлись в предел токенов); none — не читается вовсе.
    Правило вердикта как 16.11: block берётся из JSON; не разобрано → «пропустить». block_regex — для проверки
    чувствительности."""
    if "block" in out:
        return "json", None
    if not txt.strip():
        return "empty", None
    m = RX.search(txt)
    return ("regex", m.group(1).lower() == "true") if m else ("none", None)


def request(model_id, context):
    return dict(model=model_id, temperature=TEMPERATURE,
                messages=[{"role": "user", "content": GUARDRAIL_PROMPT_V2 + context}])


def rkey(req):
    return hashlib.sha256(json.dumps(req, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load_state():
    if os.path.exists(OUT):
        return json.load(open(OUT, encoding="utf-8"))
    return dict(calls={}, verdicts={}, spent={}, params=dict(prompt_sha=hashlib.sha256(GUARDRAIL_PROMPT_V2.encode()).hexdigest(),
                                                            temperature=TEMPERATURE, models=MODELS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=list(BUDGET))
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    S = load_state()
    assert S["params"]["prompt_sha"] == hashlib.sha256(GUARDRAIL_PROMPT_V2.encode()).hexdigest(), "промпт изменился"
    J = jobs(a.stage)
    plan = {}
    for m, mid in MODELS.items():
        for v, ag, cid, ctx in J:
            req = request(mid, ctx)
            plan.setdefault(m, {}).setdefault(rkey(req), (req, []))[1].append((v, ag, cid))
    uniq = sum(len(x) for x in plan.values())
    todo = {m: {k: x for k, x in p.items() if k not in S["calls"] or "error" in S["calls"][k]} for m, p in plan.items()}
    ntodo = sum(map(len, todo.values()))
    chars = sum(len(x[0]["messages"][0]["content"]) for p in todo.values() for x in p.values())
    print(f"этап {a.stage}: заданий {len(J)}×6 = {len(J) * 6} · уникальных запросов {uniq} "
          f"(переиспользовано {len(J) * 6 - uniq}) · к отправке {ntodo} · ~{chars / 4 / 1e6:.2f} млн вх. токенов "
          f"· предохранитель ${BUDGET[a.stage]}")
    if a.dry:
        return
    from openai import OpenAI
    client = OpenAI(api_key=load_key(), base_url="https://openrouter.ai/api/v1", max_retries=1, timeout=180)
    lock = threading.Lock()
    spent = [S["spent"].get(a.stage, 0.0)]
    stop = [None]
    done = [0]

    def save():
        S["spent"][a.stage] = spent[0]
        tmp = OUT + ".tmp"
        json.dump(S, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, OUT)

    def attach(m, k, uses):
        for v, ag, cid in uses:
            S["verdicts"].setdefault(v, {}).setdefault(ag, {}).setdefault(m, {})[cid] = k

    for m, p in plan.items():          # переиспользованные (уже есть в кэше) — сразу привязать
        for k, (req, uses) in p.items():
            if k in S["calls"] and "error" not in S["calls"][k]:
                attach(m, k, uses)

    for m in MODELS:
        if stop[0]:
            break
        items = list(todo[m].items())
        print(f"— {m}: {len(items)} запросов", flush=True)
        stats = dict(n=0, unparsed=0, empty=0, http_streak=0)

        def one(item):
            k, (req, uses) = item
            if stop[0]:
                return
            with lock:
                if spent[0] >= BUDGET[a.stage]:
                    stop[0] = f"бюджет этапа ${BUDGET[a.stage]} (потрачено ${spent[0]:.4f})"
                    return
            t0 = time.time()
            try:
                r = client.chat.completions.create(**req, extra_body={"usage": {"include": True}})
                lat = time.time() - t0
                u = r.usage
                det = getattr(u, "completion_tokens_details", None)
                cost = getattr(u, "cost", None)
                txt = r.choices[0].message.content or ""
                out = loose_json(txt)
                kind, breg = parse_kind(txt, out)
                rec = dict(judge=m, model=req["model"], block=bool(out.get("block")), reason=out.get("reason"),
                           parse_kind=kind, block_regex=breg,
                           confidence=out.get("confidence"), parsed="block" in out, raw=txt[:600],
                           tokens_in=u.prompt_tokens, tokens_out=u.completion_tokens,
                           tokens_reasoning=getattr(det, "reasoning_tokens", None) if det else None,
                           cost=cost, cost_kind="openrouter" if cost is not None else "missing",
                           latency_s=round(lat, 3), served_model=getattr(r, "model", None), utc=time.time())
                with lock:
                    spent[0] += cost or 0.0
                    stats["http_streak"] = 0
                    stats["n"] += 1
                    stats["unparsed"] += kind == "none"
                    stats["empty"] += kind == "empty"
            except Exception as e:
                rec = dict(judge=m, model=req["model"], error=str(e)[:200], latency_s=round(time.time() - t0, 3))
                with lock:
                    stats["http_streak"] += 1
                    if stats["http_streak"] >= 5:
                        stop[0] = f"5 ошибок HTTP подряд у {m}: {rec['error'][:80]}"
            with lock:
                S["calls"][k] = rec
                if "error" not in rec:
                    attach(m, k, uses)
                done[0] += 1
                if stats["n"] >= 30 and stats["unparsed"] / stats["n"] > 0.10:
                    stop[0] = f"у {m} нечитаемый ответ {stats['unparsed']}/{stats['n']}"
                if stats["n"] >= 30 and stats["empty"] / stats["n"] > 0.15:
                    stop[0] = f"у {m} пустые ответы (рассуждения до предела) {stats['empty']}/{stats['n']}"
                if done[0] % 20 == 0:
                    save()

        with ThreadPoolExecutor(WORKERS) as ex:
            list(ex.map(one, items))
        save()
        print(f"   {m}: ok {stats['n']}, нечитаемо {stats['unparsed']}, пустых {stats['empty']}, "
              f"потрачено на этапе ${spent[0]:.4f}", flush=True)
    save()
    print(("⛔ ОСТАНОВ: " + stop[0]) if stop[0] else f"Этап {a.stage} готов. Потрачено ${spent[0]:.4f} → {OUT}")


if __name__ == "__main__":
    main()
