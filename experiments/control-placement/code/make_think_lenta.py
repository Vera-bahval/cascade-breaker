"""
«Лента мыслей»: что каждый бот нового FinBot видел, что подумал и что сделал — по полным записям вызовов модели.

Данные: runs/finbot477_think_*/<модель>/<id>.calls.jsonl (каждый вызов: весь вход, все выходные элементы, usage) +
<id>.db.json (исход). Для gpt-5-nano в выходе есть пересказ рассуждений (reasoning summary); у gpt-4o-mini его нет —
видно только, что модель получила и что сделала.
Агент вызова — по системному заданию (первое сообщение входа). «Новое на входе» — сообщения, добавленные с прошлого
вызова того же агента (результаты инструментов).
Создаёт annotation/finbot477_think_lenta.html.

Только stdlib:  python3 code/make_think_lenta.py [папка_прогона]
"""
from __future__ import annotations
import glob
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "annotation", "finbot477_think_lenta.html")
AGENTS = [("workflow orchestrator", "Оркестратор"), ("invoice processing", "Invoice"),
          ("fraud and compliance", "Fraud/Compliance"), ("payment processing", "Payments"),
          ("communication assistant", "Communication"), ("onboarding", "Onboarding")]
KEY = {"update_invoice_status", "flag_invoice_for_review", "process_payment", "update_vendor_risk",
       "finstripe__create_transfer"}
BANK = re.compile(r"bank|account holder|holder name|routing|remittance|banking details|реквизит", re.I)
TRUTH = {"legit": "честный", "injection": "атака (текст)", "fraud": "фрод", "policy": "политика"}


def esc(x):
    return html.escape(str(x if x is not None else ""))


def agent_of(call):
    inp = call.get("input") or []
    first = inp[0] if inp and isinstance(inp[0], dict) else {}
    txt = str(first.get("content", ""))[:200].lower()
    return next((ru for key, ru in AGENTS if key in txt), "?")


def render_new(items):
    out = []
    for m in items:
        if not isinstance(m, dict):
            continue
        if m.get("type") == "function_call_output":
            out.append(f'<div class="in">← результат: {esc(str(m.get("output"))[:700])}</div>')
        elif m.get("role") == "user":
            out.append(f'<div class="in">← задание: {esc(str(m.get("content"))[:1200])}</div>')
    return "".join(out)


def render_invoice(sc, calls, db):
    paid = bool(db.get("payments"))
    bank_seen = False
    parts, prev_len = [], {}
    for c in calls:
        ag = agent_of(c)
        inp = c.get("input") or []
        start = prev_len.get(ag, 1)
        new = inp[start:] if len(inp) > start else []
        prev_len[ag] = len(inp)
        think, acts = [], []
        for o in c.get("output") or []:
            if not isinstance(o, dict):
                continue
            if o.get("type") == "reasoning":
                s = " ".join(x.get("text", "") for x in (o.get("summary") or []))
                if s.strip():
                    think.append(s)
            elif o.get("type") == "function_call":
                acts.append((o.get("name"), o.get("arguments")))
            elif o.get("type") == "message":
                txt = " ".join(x.get("text", "") for x in (o.get("content") or []) if isinstance(x, dict))
                if txt.strip():
                    acts.append(("(текст)", txt))
        bank_seen |= any(BANK.search(t) for t in think)
        th = "".join(f'<div class="think{" bank" if BANK.search(t) else ""}">💭 {esc(t)}</div>' for t in think)
        ac = "".join(f'<div class="act{" key" if n in KEY else ""}">→ <b>{esc(n)}</b> {esc(str(a)[:600])}</div>'
                     for n, a in acts)
        parts.append(f'<div class="call"><div class="who">{esc(ag)} · вызов {c.get("call")}</div>'
                     f'{render_new(new)}{th}{ac}</div>')
    head = (f'<details class="inv {"paid" if paid else "stop"}"><summary><b>{esc(sc["id"])}</b> · '
            f'{esc(TRUTH.get(sc["truth"], sc["truth"]))} · ${sc["amount"]:,.0f} · статус <b>{esc(db.get("invoice_status"))}</b>'
            f' · {"ОПЛАЧЕН" if paid else "не оплачен"} · вызовов {len(calls)}'
            f'{" · 💭 упоминал реквизиты" if bank_seen else ""}</summary>'
            f'<p class="desc"><b>Текст счёта:</b> {esc(sc["desc"])}</p>')
    return head + "".join(parts) + "</details>", paid, bank_seen


CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--mut:#666;--card:#f6f6f8;--bd:#ddd;--hl:#fff3c4;--th:#eef4ff;--bk:#ffe1e1}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--fg:#eee;--mut:#aaa;--card:#222226;--bd:#3a3a40;--hl:#4a3f10;--th:#1d2a40;--bk:#4a2020}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:16px}
.inv{border:1px solid var(--bd);border-radius:8px;margin:8px 0;padding:6px 10px;background:var(--card)}
.inv summary{cursor:pointer}.call{border-left:3px solid var(--bd);margin:8px 0 8px 4px;padding-left:10px}
.who{font-weight:700}.in{color:var(--mut);font-size:12px;white-space:pre-wrap}.think{background:var(--th);padding:4px 6px;border-radius:4px;margin:3px 0;white-space:pre-wrap}
.think.bank{background:var(--bk)}.act{margin:3px 0}.act.key{background:var(--hl);padding:2px 4px;border-radius:4px}h2{margin-top:28px}
"""


def main(run_dir=None):
    run_dir = run_dir or sorted(d for d in glob.glob(os.path.join(HERE, "runs", "finbot477_think_*")) if os.path.isdir(d))[-1]
    blocks = []
    for model_dir in sorted(d for d in glob.glob(os.path.join(run_dir, "*")) if os.path.isdir(d)):
        scs = json.load(open(os.path.join(model_dir, "scenarios.json"), encoding="utf-8"))
        items, n_paid, n_bank = [], 0, 0
        for sc in scs:
            cp, dp = (os.path.join(model_dir, f'{sc["id"]}.{x}') for x in ("calls.jsonl", "db.json"))
            if not (os.path.exists(cp) and os.path.exists(dp)):
                continue
            calls = [json.loads(l) for l in open(cp, encoding="utf-8")]
            try:
                db = json.load(open(dp, encoding="utf-8"))[0]
            except (json.JSONDecodeError, IndexError):
                db = {}
            h, paid, bank = render_invoice(sc, calls, db)
            items.append(h)
            n_paid += paid
            n_bank += bank
        blocks.append(f'<h2>{esc(os.path.basename(model_dir))}: {len(items)} счетов, оплачено {n_paid}, '
                      f'в рассуждениях упоминались реквизиты: {n_bank}</h2>' + "\n".join(items))
    page = (f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Лента мыслей FinBot</title><style>{CSS}</style></head><body>'
            f'<h1>Что думали боты — новый FinBot, профиль D (поставщик вчера сменил реквизиты)</h1>'
            f'<p>Прогон <code>{esc(os.path.basename(run_dir))}</code>. Для каждого вызова модели: ← что пришло нового, '
            f'💭 пересказ рассуждений (только gpt-5-nano; это пересказ, а не дословные мысли), → действие. '
            f'Красным — рассуждения, где упоминаются реквизиты/банк; жёлтым — ключевые действия.</p>'
            + "\n".join(blocks) + "</body></html>")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(page)
    print(OUT)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
