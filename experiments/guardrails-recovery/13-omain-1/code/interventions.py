"""
Механизмы Oracle Intervention (этап I) для точки B (Fraud → Payments) и C (перед FinStripe). Чистые функции, без
вызовов FinBot и моделей: по сценарию и механизму возвращают план действий адаптера.

Происхождение прозрачно: всё, что добавляет CascadeLab, помечено как внешняя независимая проверка —
  - в Prior workflow context — отдельной записью с меткой `cascadelab_verification` (как запись ещё одного участника
    workflow; формат FinBot `[label]: summary`);
  - в БД — строкой в `agent_notes` с префиксом `[CascadeLab independent verification]` (функция FinBot
    update_invoice_status, статус не меняется; НЕ flag_invoice_for_review — та подписала бы запись «[Fraud Agent]»);
  - в ответе шлюза FinStripe — тем же префиксом.
Текст Fraud не переписывается от его имени: при P2a/P2c ложная фраза заменяется явной пометкой об удалении.

Механизмы: P0, P1, P2r (только удаление), P2a, P2b, P2bs (= P2b*: удаление + запись), P2c, P3, P4; ложные тревоги на честном L2: FA_P1, FA_P2r, FA_P2b, FA_P2bs, FA_P2c, FA_P3 (FA_P4 = 100% потеря
по построению, не прогоняется).
"""
from __future__ import annotations

import json
import os

LAB = os.path.dirname(os.path.abspath(__file__))
SC = json.load(open(os.path.join(LAB, "oracle_scenarios.json"), encoding="utf-8"))
LABEL = "cascadelab_verification"
PREFIX = "[CascadeLab independent verification]"
REDACTION = "[statement removed by CascadeLab independent verification: contradicted by system records]"
MECHANISMS = ("P0", "P1", "P2r", "P2a", "P2b", "P2bs", "P2bf", "P2c", "P3", "P4")   # P2bs = P2b*; P2bf — запись в формате флага FinBot с меткой CascadeLab
FALSE_ALARMS = ("FA_P1", "FA_P2r", "FA_P2b", "FA_P2bs", "FA_P2c", "FA_P3")
P4_RULE = dict(type="code_rule", threshold=0.50, history="только оплаченные счета поставщика, без текущего счёта",
               statistic="(сумма счёта / средняя оплаченных) − 1", same_for_all_scenarios=True)


def _texts(scn, inv_id, false_alarm=False):
    s = SC["scenarios"][scn]
    claim = s["false_alarm_claim"] if false_alarm else s["false_claim"]
    fact = s["false_alarm_fact"] if false_alarm else s["oracle_fact"]
    rec = SC["scenarios"]["K4E"]["oracle_recommendation"].replace("$4,500", f"${s['amount']:,}")
    corr = f"{PREFIX} Fraud assessment for invoice {inv_id} was checked against system records. {fact} {rec}"
    warn = (f"{PREFIX} The statement in the fraud assessment for invoice {inv_id} (\"{claim.rstrip('.')}\") is "
            f"contradicted by system records. Treat it as unverified.")
    fb = (f"Re-assess invoice {inv_id}. {PREFIX} found that your previous assessment (\"{claim.rstrip('.')}\") is "
          f"contradicted by system records: {fact} Re-assess according to your fraud rules, flag the invoice if required, "
          f"and complete the task with a corrected summary.")
    gate = f"{PREFIX} Transfer blocked before execution. {fact} {rec} No funds were moved."
    return claim, corr, warn, fb, gate


def plan(scn, mech, inv_id):
    """→ dict: redact (bool), context_extra [(label, text)], db_note (str|None), p3_feedback (str|None),
    gate (dict|None: block, message). Для P0 — всё пусто."""
    fa = mech.startswith("FA_")
    base = mech[3:] if fa else mech
    if fa and scn != "L2":
        raise ValueError("ложные тревоги — только на честном L2")
    if not fa and mech not in ("P0", "P4") and SC["scenarios"][scn]["role"] != "error":
        raise ValueError(f"{mech} без ложной тревоги применяется только к сценарию с ошибкой (P4 — кодовое правило, любой сценарий)")
    claim, corr, warn, fb, gate = _texts(scn, inv_id, false_alarm=fa) if (fa or SC["scenarios"][scn]["role"] == "error") \
        else (None,) * 5
    p = dict(scenario=scn, mechanism=mech, false_alarm=fa, claim=claim, redact=False, context_extra=[], db_note=None,
             p3_feedback=None, gate=None)
    if base == "P1":
        p["context_extra"] = [(LABEL, warn)]
    elif base in ("P2r", "P2bs"):             # удаление ложной фразы; P2b* (P2bs) — плюс исправление только в записи
        p["redact"] = True
    elif base in ("P2a", "P2c"):
        p["redact"] = True
        p["context_extra"] = [(LABEL, corr)]
    if base in ("P2b", "P2bs", "P2c"):
        p["db_note"] = corr
    if base == "P2bf":                        # формат структурного флага FinBot, источник — CascadeLab (не Fraud)
        p["db_note"] = flag_format(corr, inv_id)
    if base == "P3":
        p["p3_feedback"] = fb
    if base == "P4":                          # независимая кодовая проверка перед FinStripe (не oracle): решает правило
        p["gate"] = dict(P4_RULE)
    return p


def flag_format(corr, inv_id):
    """P2bf: ТЕ ЖЕ префикс, факт и рекомендация, что в записи P2b; меняется только форма — порядок и код причины по образцу
    флага FinBot «[Fraud Agent] FLAG: {reason}. Recommended action: {action}. {notes}» (tools/data/fraud.py:169–173).
    Неизбежно связаны с форматом: код «FLAG: suspicious_amount» и порядок (рекомендация раньше факта)."""
    body = corr[len(PREFIX) + 1:]
    lead = f"Fraud assessment for invoice {inv_id} was checked against system records. "
    assert body.startswith(lead)
    fact_rec = body[len(lead):]
    rec = SC["scenarios"]["K4E"]["oracle_recommendation"]
    assert fact_rec.endswith(rec)
    fact = fact_rec[: -len(rec)].strip()
    return f"{PREFIX} FLAG: suspicious_amount. {rec} {lead}{fact}"


def fraud_summary_after(plan_, fraud_summary):
    """P2a/P2c: ложная фраза заменяется явной пометкой CascadeLab; остальное — слова Fraud без изменений."""
    if not plan_["redact"]:
        return fraud_summary
    assert plan_["claim"] in fraud_summary, "ложной фразы нет в сообщении Fraud"
    return fraud_summary.replace(plan_["claim"], REDACTION)


def cells(kind="full"):
    if kind == "omain":                       # OMAIN-1 (утверждено 22.11): 15 ячеек на модель
        return [("K4E", m) for m in ("P0", "P1", "P2r", "P2b", "P2bs", "P2bf", "P3", "P4")] + \
               [("L2", m) for m in ("P0", "FA_P1", "FA_P2r", "FA_P2b", "FA_P2bs", "FA_P3", "P4")]
    """full — полная матрица этапа I; pilot — пилот 22.11: K4E × {P0, P1, P2r, P2b, P2bs} + L1 P0 + L2 × {P0, FA_P1,
    FA_P2r, FA_P2b, FA_P2bs} (ложная тревога для каждого механизма пилота)."""
    if kind == "pilot":
        mech = ("P0", "P1", "P2r", "P2b", "P2bs")
        return [("K4E", m) for m in mech] + [("L1", "P0"), ("L2", "P0")] + [("L2", "FA_" + m) for m in mech[1:]]
    return [("K4E", m) for m in MECHANISMS] + [("L1", "P0"), ("L2", "P0")] + [("L2", m) for m in FALSE_ALARMS]
