"""Check private pilot receipts and export only analytic fields for the public report."""
import csv
import hashlib
import json
import sqlite3
import statistics
from collections import Counter
from pathlib import Path

from experiments.payment_controls.pilot import HERE, packets
from experiments.payment_controls.probe_models import request_body
from experiments.payment_controls.question_control import controls, DECODING

PROVIDERS = {"jev": "https://api.typesafe.ai/v1/systemone", "eliza": "https://api.eliza.yandex.net/deepseek/chat/completions"}
ACTIONS = {"active_hold": "BLOCK", "no_active_hold": "ALLOW", "insufficient_records": "REVIEW"}


def collect(provider):
    folder = HERE.parents[1] / ".runtime" / "payment-controls-chp3" / provider
    observations = json.loads((folder / "observations.json").read_text())
    control = json.loads((folder / "question_control_observations.json").read_text())
    observations = [dict(r, phase="primary") for r in observations] + [dict(r, phase="control") for r in control]
    mapping = {(r["phase"], r["case_id"], r["summary"], r["form"]): r["receipt"] for r in observations}
    mast = {r["case_id"]: r for r in json.loads((HERE / "mast_pilot_v2.json").read_text())}
    rows = []
    paid = {}
    for phase, case in [("primary", r) for r in packets()] + [("control", r) for r in controls()]:
        key = (case["case_id"], case["summary"], case["form"])
        query = mapping.pop((phase, *key))
        identity = {"url": PROVIDERS[provider], "body": request_body(provider, case["input"])}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        receipt = json.loads((folder / (query + ".json")).read_text())
        if query != digest or receipt["request_hash"] != digest or receipt["request"] != identity["body"]:
            raise ValueError("Receipt/input identity mismatch")
        picked = receipt["selected"]
        decision = (DECODING if phase == "control" else ACTIONS).get(picked, picked) if receipt["valid"] else "UNPARSEABLE"
        usage = receipt["usage"]
        paid[query] = receipt["cost_usd"]
        rows.append(dict(phase=phase, provider=provider, model=receipt["response_model"], case_id=key[0], family=case["family"],
                         summary=int(key[1]), form=key[2], mast=mast[key[0]]["primary_target"],
                         gold=case["expected"], decision=decision, correct=int(decision == case["expected"]),
                         input_tokens=usage["input_tokens" if provider == "jev" else "prompt_tokens"],
                         output_tokens=usage["output_tokens" if provider == "jev" else "completion_tokens"],
                         seconds=receipt["elapsed_seconds"], cost_usd=receipt["cost_usd"],
                         cost_basis=receipt["cost_basis"], request_hash=query))
    with sqlite3.connect(f"file:{folder / 'ledger.sqlite'}?mode=ro", uri=True) as db:
        ledger = {k: c for k, c, status in db.execute("SELECT id,cost,status FROM requests") if status == "complete"}
        total = db.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    if mapping or len(observations) != len(rows) or paid != ledger or total != len(paid):
        raise ValueError("Ledger/mapping reconciliation failed")
    return rows


def write_summary(rows):
    primary = [r for r in rows if r["phase"] == "primary"]
    def secs(r):
        times = sorted(x["seconds"] for x in r)
        return f"{statistics.median(times):.3f} / {statistics.quantiles(times, n=20, method='inclusive')[18]:.3f}"
    text = ["# Результаты диагностического пилота", "",
            "12 первичных документов, шесть парных семейств. Каждый документ оценён с резюме и без него, с прямым вопросом и вопросом о свидетельстве. Единица качества в каждой строке — документ. Ошибочный BLOCK считается среди четырёх документов с эталоном ALLOW. Передача на разбор учитывается отдельно. Случай HOLD проверяется после Fraud.", "",
            "| Провайдер | Резюме | Вопрос | Верно / 12 | Ложный BLOCK / ALLOW | Ложный ALLOW / BLOCK | Время p50 / p95, с | Стоимость, $ |",
            "|---|---|---|---:|---:|---:|---:|---:|"]
    for provider in PROVIDERS:
        for summary in (0, 1):
            for form in ("decision", "evidence"):
                group = [r for r in primary if (r["provider"],r["summary"],r["form"]) == (provider,summary,form)]
                gold = Counter(r["gold"] for r in group)
                fb = sum(r["decision"] == "BLOCK" and r["gold"] == "ALLOW" for r in group)
                fa = sum(r["decision"] == "ALLOW" and r["gold"] == "BLOCK" for r in group)
                text.append(f"| {provider} | {'да' if summary else 'нет'} | {form} | {sum(r['correct'] for r in group)} / {len(group)} | {fb} / {gold['ALLOW']} | {fa} / {gold['BLOCK']} | {secs(group)} | {sum(r['cost_usd'] for r in group):.9f} |")
    text.extend(["", "Все ошибки исходной серии представляли собой передачу на разбор. Jev в прямом вопросе отправил на разбор три из пяти действующих HOLD вместо BLOCK. У DeepSeek таких случаев четыре из пяти, плюс одно лишнее направление на разбор среди четырёх допустимых счетов при добавлении резюме. Ни одного ошибочного автоматического разрешения на пяти BLOCK и трёх REVIEW в каждом варианте. Разница в точной классификации ещё не доказывает разницу в предотвращении переводов.", "",
                 "### Контроль критериев выбора", "",
                 "В дополнительном тесте на шести выбранных после первичного прогона документах между вариантами менялось только предложение вопроса. Одинаковые A/B/C имели полные определения. Резюме агента не подавалось.", "",
                 "| Модель | Прямой вопрос | Вопрос о свидетельстве | Несовпадения решений |",
                 "|---|---:|---:|---:|"])
    for provider in PROVIDERS:
        group = [r for r in rows if r["phase"] == "control" and r["provider"] == provider]
        forms = {f: {r["case_id"]:r for r in group if r["form"] == f} for f in ("decision","evidence")}
        a, b = forms.values()
        text.append(f"| {provider} | {sum(r['correct'] for r in a.values())}/6 | {sum(r['correct'] for r in b.values())}/6 | {sum(a[k]['decision'] != b[k]['decision'] for k in a)} |")
    text.extend(["", "### Сверка расходов за обе серии", ""])
    for provider in PROVIDERS:
        sample = [r for r in rows if r["provider"] == provider]
        unique = {r["request_hash"]: r for r in sample}.values()
        text.append(f"- {provider}, {sample[0]['model']} — {len(unique)} запросов, {sum(r['input_tokens'] for r in unique)} входных и {sum(r['output_tokens'] for r in unique)} выходных токенов, {sum(r['cost_usd'] for r in unique):.9f} доллара.")
    text.extend(["", "Eliza вернула сумму каждого списания. Для Jev указана оценка по usage и опубликованному тарифу. Журналы расходов сверены с идентификаторами отправленных тел. Время включает HTTP-цикл с точки зрения клиента. Эти измерения относятся к проверке документа. Экономия на полном workflow, системный FPR и число предотвращённых переводов требуют живых эпизодов FinBot.", ""])
    text.extend(["## Проверка в FinBot", "",
                 "В четырёх отдельных direct-workflow прошли проверки БД. На обычном счёте $480 переведено ровно один раз при налоге $39.60. При неизвестной юрисдикции TaxCalc потребовал разбора, переводов нет. При активном HOLD Jev остановил выполнение на выходе Fraud до вызова FinStripe; при снятом HOLD пропустил к оплате. [Длительности и расходы исполнителя](live_pilot_results.csv) · [BI по ответам](pilot.html).", "",
                 "Для следующего этапа сравнивать доступные первичные документы на P2b и P4 при одинаковых вариантах ответа. В документах, где состояние нельзя установить, отдельно считать стоимость REVIEW. У Jev в дополнительном диагностическом контроле эффект смены вопроса исчез при унификации вариантов; у DeepSeek изменилось решение на одном случае. Выборки малы и включают документы, отобранные после первичного теста.", ""])
    (HERE / "PILOT_RESULTS.md").write_text("\n".join(text))


if __name__ == "__main__":
    results = [r for provider in PROVIDERS for r in collect(provider)]
    with (HERE / "pilot_results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    write_summary(results)
