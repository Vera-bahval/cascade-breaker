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

PROVIDERS = {"jev": "https://api.typesafe.ai/v1/systemone", "eliza": "https://api.eliza.yandex.net/deepseek/chat/completions"}
ACTIONS = {"active_hold": "BLOCK", "no_active_hold": "ALLOW", "insufficient_records": "REVIEW"}


def collect(provider):
    folder = HERE.parents[1] / ".runtime" / "payment-controls-chp3" / provider
    observations = json.loads((folder / "observations.json").read_text())
    mapping = {(r["case_id"], r["summary"], r["form"]): r["receipt"] for r in observations}
    mast = {r["case_id"]: r for r in json.loads((HERE / "mast_pilot_v2.json").read_text())}
    rows = []
    paid = {}
    for case in packets():
        key = (case["case_id"], case["summary"], case["form"])
        query = mapping.pop(key)
        identity = {"url": PROVIDERS[provider], "body": request_body(provider, case["input"])}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        receipt = json.loads((folder / (query + ".json")).read_text())
        if query != digest or receipt["request_hash"] != digest or receipt["request"] != identity["body"]:
            raise ValueError("Receipt/input identity mismatch")
        picked = receipt["selected"]
        decision = ACTIONS.get(picked, picked) if receipt["valid"] else "UNPARSEABLE"
        usage = receipt["usage"]
        paid[query] = receipt["cost_usd"]
        rows.append(dict(provider=provider, model=receipt["response_model"], case_id=key[0], family=case["family"],
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
                group = [r for r in rows if (r["provider"],r["summary"],r["form"]) == (provider,summary,form)]
                gold = Counter(r["gold"] for r in group)
                fb = sum(r["decision"] == "BLOCK" and r["gold"] == "ALLOW" for r in group)
                fa = sum(r["decision"] == "ALLOW" and r["gold"] == "BLOCK" for r in group)
                text.append(f"| {provider} | {'да' if summary else 'нет'} | {form} | {sum(r['correct'] for r in group)} / {len(group)} | {fb} / {gold['ALLOW']} | {fa} / {gold['BLOCK']} | {secs(group)} | {sum(r['cost_usd'] for r in group):.9f} |")
    text.extend(["", "### Сверка расходов", ""])
    for provider in PROVIDERS:
        sample = [r for r in rows if r["provider"] == provider]
        unique = {r["request_hash"]: r for r in sample}.values()
        text.append(f"- {provider}, {sample[0]['model']} — {len(unique)} запросов, {sum(r['input_tokens'] for r in unique)} входных и {sum(r['output_tokens'] for r in unique)} выходных токенов, {sum(r['cost_usd'] for r in unique):.9f} доллара.")
    text.extend(["", "Eliza вернула сумму каждого списания. Для Jev указана оценка по usage и опубликованному тарифу. Журналы расходов сверены с идентификаторами отправленных тел. Время включает HTTP-цикл с точки зрения клиента. Эти измерения относятся к проверке документа. Экономия на полном workflow, системный FPR и число предотвращённых переводов требуют живых эпизодов FinBot.", ""])
    (HERE / "PILOT_RESULTS.md").write_text("\n".join(text))


if __name__ == "__main__":
    results = [r for provider in PROVIDERS for r in collect(provider)]
    with (HERE / "pilot_results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    write_summary(results)
