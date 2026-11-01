"""
Набор для ручной разметки ошибок FinBot (open coding по методике MAST) — без вызовов модели.

Отбирает из записанных живых прогонов "плохие" трейсы:
  - естественные вредные (деньги ушли зря) — по одному на сценарий;
  - с подложенной ошибкой — по одному на сценарий (и дошедшие до денег, и исправленные системой).
Создаёт в annotation/:
  traces.html  — удобное чтение: счёт → что получил и ответил каждый бот → чем кончилось;
  traces.csv   — список трейсов с тем, что известно автоматически;
  events.csv   — таблица для разметки (одна строка = одно событие ошибки), часть полей предзаполнена.
Классы ошибок размечает человек по annotation/КОДБУК_v0.md.

Только stdlib:  python3.11 code/make_annotation_kit.py
"""
from __future__ import annotations
import csv
import glob
import html
import json
import os

from llm_guardrail import loose_json

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "annotation")
SKIP = {"stand_live_20260926_141935.json", "stand_live_20260926_142318.json"}
STEP_RU = {"validator": "Validator", "risk": "RiskAnalyzer", "approval": "Approval"}
EVENT_FIELDS = ["trace_id", "event_no", "mast_class", "other_note", "agent", "stage",
                "status_next", "propagation_path", "detected_at", "final_impact",
                "confidence_1to3", "annotator", "comment"]


def between(text, a, b):
    i = text.find(a)
    if i < 0:
        return ""
    i += len(a)
    j = text.find(b, i)
    return text[i:j if j >= 0 else None].strip()


def select():
    picked, seen = [], set()
    for path in sorted(glob.glob(os.path.join(HERE, "runs", "stand_live_*.json"))):
        if os.path.basename(path) in SKIP:
            continue
        for r in json.load(open(path)):
            if r["fallback_agents"] or r["llm_errors"]:
                continue
            injected = bool(r.get("fault_applied"))
            natural_harm = r["group"] == "cascade" and not injected
            if not (injected or natural_harm):
                continue
            key = (os.path.basename(path), r["id"])
            if key in seen:
                continue
            seen.add(key)
            r["_file"] = os.path.basename(path)
            picked.append(r)
    for i, r in enumerate(picked, 1):
        r["_tid"] = f"T{i:03d}"
    return picked


def step(r, agent):
    return next((s for s in r["trace"]["steps"] if s["agent"] == agent), None)


def card(r):
    p = r["prompts"]["validator"]
    desc = between(p, "Description:", "\nVendor:")
    vendor = between(p, "Vendor:", "\nTrust Level:")
    v, k, a = (loose_json(r["responses"].get(x)) for x in ("validator", "risk", "approval"))
    pay = step(r, "PaymentProcessor") or {"data": {}, "errors": []}
    fs = r.get("fault_step")
    orig = loose_json(r.get("fault_original")) if r.get("fault_original") else {}
    e = html.escape

    def injected_note(role):
        if fs != role:
            return ""
        keys = {"validator": ("valid", "issues", "normalized_data"),
                "risk": ("risk_level", "risk_score", "fraud_indicators"),
                "approval": ("decision", "requires_human")}[role]
        o = ", ".join(f"{x}={orig.get(x)}" for x in keys)
        return (f"<div class='inj'>⚠ ПОДЛОЖЕНО ({e(r['fault'])}). Настоящий ответ модели был: {e(o)}; "
                f"пояснение: «{e(str(orig.get('reasoning', ''))[:300])}»</div>")

    rows = []
    rows.append(f"<div class='agent'><b>Validator</b>{injected_note('validator')}"
                f"<div>valid=<b>{e(str(v.get('valid')))}</b>, confidence={e(str(v.get('confidence')))}, "
                f"issues={e(str(v.get('issues')))}, сумма у валидатора={e(str((v.get('normalized_data') or {}).get('amount')))}</div>"
                f"<div class='why'>«{e(str(v.get('reasoning', '')))}»</div></div>")
    if k:
        rows.append(f"<div class='agent'><b>RiskAnalyzer</b>{injected_note('risk')}"
                    f"<div>risk_level=<b>{e(str(k.get('risk_level')))}</b>, score={e(str(k.get('risk_score')))}, "
                    f"признаки={e(str(k.get('fraud_indicators')))}, инъекция={e(str(k.get('prompt_injection_detected')))}</div>"
                    f"<div class='why'>«{e(str(k.get('reasoning', '')))}»</div></div>")
    else:
        rows.append("<div class='agent muted'><b>RiskAnalyzer</b> не запускался (валидатор остановил цепочку)</div>")
    if a:
        rows.append(f"<div class='agent'><b>Approval</b>{injected_note('approval')}"
                    f"<div>decision=<b>{e(str(a.get('decision')))}</b>, requires_human={e(str(a.get('requires_human')))}, "
                    f"confidence={e(str(a.get('confidence')))}</div>"
                    f"<div class='why'>«{e(str(a.get('reasoning', '')))}»</div>"
                    f"<div class='note'>вход одобрения видит описание, обрезанное до 100 символов</div></div>")
    else:
        rows.append("<div class='agent muted'><b>Approval</b> не запускался</div>")
    rows.append(f"<div class='agent'><b>Payment</b> оплачено=<b>{e(str(pay['data'].get('payment_processed')))}</b>"
                f" {e(', '.join(pay.get('errors') or []))}</div>")
    outcome = "ДЕНЬГИ УШЛИ" if r["paid"] else "остановлено"
    origin = f"подложено на шаге {STEP_RU.get(fs, fs)}" if fs else "естественный каскад"
    return (f"<section id='{r['_tid']}'><h2>{r['_tid']} · {e(r['title'])}</h2>"
            f"<div class='meta'>{e(r['_file'])} · сценарий {e(r['id'])} · правда: {e(r['truth'])} · "
            f"{origin} · итог: <b>{outcome}</b> ({e(r['status'])})</div>"
            f"<div class='inv'><b>Счёт</b>: ${r['trace']['amount']} · {e(vendor)}<br>«{e(desc)}»</div>"
            + "".join(rows) + "</section>")


PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Трейсы FinBot для разметки</title>
<style>
:root{--bg:#fafaf8;--fg:#1d1d1b;--muted:#77756f;--card:#fff;--line:#e3e1db;--inj:#fff1d6;--injline:#e0a33a}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1a;--fg:#ecebe6;--muted:#9a978f;--card:#252523;--line:#3a3936;--inj:#3a2f1a;--injline:#c48a2a}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif;margin:0;padding:16px;max-width:900px;margin:auto}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}
h1{font-size:20px}h2{font-size:16px;margin:0 0 4px}.meta,.muted,.note{color:var(--muted);font-size:13px}
.inv{margin:8px 0;padding:8px;border-left:3px solid var(--line)}.agent{margin:8px 0 0;padding-top:6px;border-top:1px dashed var(--line)}
.why{font-style:italic;color:var(--muted)}.inj{background:var(--inj);border-left:3px solid var(--injline);padding:6px 8px;margin:4px 0;font-size:13px}
nav a{margin-right:8px;font-size:13px}
</style></head><body><h1>Трейсы FinBot для разметки ошибок</h1>
<p class="meta">Как размечать — annotation/КОДБУК_v0.md. Разметку вносить в annotation/events.csv (одна строка = одно событие ошибки).</p>
<nav>NAV</nav>CARDS</body></html>"""


def main():
    rows = select()
    os.makedirs(OUT, exist_ok=True)
    nav = " ".join(f"<a href='#{r['_tid']}'>{r['_tid']}</a>" for r in rows)
    with open(os.path.join(OUT, "traces.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("NAV", nav).replace("CARDS", "".join(card(r) for r in rows)))
    with open(os.path.join(OUT, "traces.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["trace_id", "source_file", "scenario", "title", "truth", "amount",
                    "injected_fault", "injected_step", "paid", "status"])
        for r in rows:
            w.writerow([r["_tid"], r["_file"], r["id"], r["title"], r["truth"], r["trace"]["amount"],
                        r.get("fault") or "", STEP_RU.get(r.get("fault_step"), "") if r.get("fault_step") else "",
                        r["paid"], r["status"]])
    events = os.path.join(OUT, "events.csv")
    if os.path.exists(events):
        print("events.csv уже есть — не перезаписываю (там может быть разметка)")
    else:
        with open(events, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
            w.writeheader()
            for r in rows:
                fs = r.get("fault_step")
                w.writerow(dict(trace_id=r["_tid"], event_no=1,
                                agent=STEP_RU.get(fs, "") if fs else "",
                                status_next="", final_impact="yes" if r["paid"] else "no",
                                comment="источник подложен" if fs else ""))
    nat = sum(1 for r in rows if not r.get("fault_applied"))
    print(f"трейсов: {len(rows)} (естественных вредных {nat}, с подложенной ошибкой {len(rows) - nat}, "
          f"из них дошли до денег {sum(r['paid'] for r in rows if r.get('fault_applied'))})")
    print("созданы: annotation/traces.html, annotation/traces.csv, annotation/events.csv")


if __name__ == "__main__":
    main()
