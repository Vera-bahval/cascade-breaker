"""Render the post-hoc threshold-policy comparison from saved evidence only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
from collections import defaultdict
from pathlib import Path

from .night_report import render_text

POLICIES = {
    "A_joint": "A: совместная, максимум обнаружения → минимум FP → высокий порог",
    "B_independent": "B: самостоятельный компонент, затем OR с rules",
    "C_lowest": "C: минимальный допустимый порог на полной сетке",
}
METRICS = (
    ("harm_prevented_counterfactual", "Опасные STOP /83"),
    ("raw_episode_fpr", "Безопасные STOP /131"),
    ("p4_reached_safe93_interruption", "Достигшие P4 безопасные STOP /93"),
    ("source_benign_stop", "Остановлены исходно честные /98"),
    ("source_benign_compliant_completion_counterfactual", "Корректные честные платежи /98"),
)


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    p = (len(values) - 1) * q
    lo = int(p)
    return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (p - lo)


def seed_values(rows, key, count=False):
    lookup = {r["seed"]: r for r in rows}
    result = []
    for seed in (17, 29, 43):
        row = lookup.get(seed)
        value = row.get(key) if row and row.get("complete", True) else None
        if count:
            value = value.get("k") if isinstance(value, dict) else None
        result.append("—" if value is None else str(value))
    return " / ".join(result)


def metric_table(rows, raw=False, risk=False):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["policy"], row["arm"])].append(row)
    metrics = (("TP", "Опасные STOP /32"), ("FP", "Допустимые STOP /32")) if raw else METRICS
    headings = ["Политика", "Метод"] + [label for _, label in metrics] + ["UNKNOWN"]
    if risk:
        headings += ["AP", "Brier", "Log loss", "Известные p(harm)"]
    out = ["<table><thead><tr>" + "".join("<th>" + html.escape(x) + "</th>" for x in headings) + "</tr></thead><tbody>"]
    for (policy, arm), records in sorted(grouped.items()):
        cells = [policy, arm] + [seed_values(records, k, count=not raw) for k, _ in metrics]
        cells += [seed_values(records, "unknown_stop")]
        if risk:
            for key in ("pr_auc", "brier", "log_loss"):
                lookup = {r["seed"]: r for r in records}
                cells.append(" / ".join(f"{lookup[s][key]:.4f}" if s in lookup and isinstance(lookup[s].get(key), (int, float)) else "—" for s in (17, 29, 43)))
            cells.append(seed_values(records, "calibration_probability_count"))
        out.append("<tr>" + "".join("<td>" + html.escape(str(x)) + "</td>" for x in cells) + "</tr>")
    return "".join(out) + "</tbody></table>"


def quality_latency_table(metrics, latency):
    lookup = {(r["evidence_set"], r["policy"], r["arm"], r["seed"]): r for r in latency}
    groups = defaultdict(list)
    for r in metrics:
        if r["evidence_set"] != "raw64" and "train_selected" in r["arm"] and r["arm"].endswith("original_rules"):
            groups[r["evidence_set"], r["policy"], r["arm"]].append(r)
    out = ["<table><thead><tr><th>Набор</th><th>Политика / метод + R1</th><th>TP /83</th><th>FP /131</th><th>Полный путь p50 / p95, мс: seeds 17;29;43</th></tr></thead><tbody>"]
    for (source, policy, arm), rows in sorted(groups.items()):
        times = []
        for seed in (17, 29, 43):
            cost = lookup.get((source, policy, arm, seed))
            times.append(f"{cost['p50_ms']:.1f} / {cost['p95_ms']:.1f}" if cost else "—")
        cells = [source, policy + " / " + arm, seed_values(rows, "harm_prevented_counterfactual", True), seed_values(rows, "raw_episode_fpr", True), "; ".join(times)]
        out.append("<tr>" + "".join("<td>" + html.escape(x) + "</td>" for x in cells) + "</tr>")
    return "".join(out) + "</tbody></table>"


def export_csv(path, rows):
    flat = []
    for row in rows:
        item = {}
        for key, value in row.items():
            if isinstance(value, dict):
                for suffix in ("k", "n", "rate"):
                    if suffix in value:
                        item[key + "_" + suffix] = value[suffix]
            elif not isinstance(value, (list, dict)):
                item[key] = value
        flat.append(item)
    keys = list(dict.fromkeys(k for row in flat for k in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(flat)


def representative(row):
    arm = row["arm"]
    return arm in ("NoDefense", "R1", "R2") or arm.startswith((
        "catboost:J_cur:", "catboost:J_seq:", "catboost:J_agg:",
        "catboost:J_dynamic:", "catboost:J_prior:", "catboost:G22:",
        "catboost:G86:", "catboost:N:", "catboost:M:",
        "catboost:tabular:", "tabular_logistic:", "scalar:compact_policy_facts:",
    )) or arm.startswith(("tfidf", "semantic_stack:"))


def per_group(records, outcomes, evidence_set):
    """Paired held-out-group counts; seeds remain separate, not independent trials."""
    truth = {r["episode_id"]: r for r in outcomes if not r.get("legacy_ambiguous")}
    populations = defaultdict(lambda: {"harm_n": 0, "safe_n": 0})
    for r in truth.values():
        populations[r["group_id"]]["harm_n" if r["strict_harm"] else "safe_n"] += 1
    rule = {(r["seed"], r["prefix_id"]): r for r in records if r["arm"] == "R1" and r["policy"] == "A_joint"}
    groups = {}
    for r in records:
        o = truth[r["episode_id"]]
        key = r["policy"], r["seed"], r["arm"], o["group_id"]
        if key not in groups:
            groups[key] = dict(evidence_set=evidence_set, policy=r["policy"], seed=r["seed"], arm=r["arm"], group_id=o["group_id"],
                               **populations[o["group_id"]], TP=0, FP=0, additional_TP_beyond_R1=0, additional_FP_beyond_R1=0, unknown_stop=0)
        g = groups[key]
        stopped = bool(r["block"])
        prevented = stopped and o["strict_harm"] and r["cut_seq"] < o["strict_harm_seq"]
        rr = rule.get((r["seed"], r["prefix_id"]))
        if rr is None:
            raise ValueError("Missing matched R1 for held-out-group comparison")
        rule_prevented = rr["block"] and o["strict_harm"] and rr["cut_seq"] < o["strict_harm_seq"]
        g["TP"] += int(prevented)
        g["FP"] += int(stopped and not o["strict_harm"])
        g["additional_TP_beyond_R1"] += int(prevented and not rule_prevented)
        g["additional_FP_beyond_R1"] += int(stopped and not o["strict_harm"] and not rr["block"])
        g["unknown_stop"] += int(r.get("unknown", False))
    return list(groups.values())


def refresh(base: Path):
    root = base / "results/policy-comparison"
    root.mkdir(parents=True, exist_ok=True)
    (base / "reports").mkdir(exist_ok=True)
    all_rows, sections, statuses, latency, grouped_rows, calibration_rows = [], [], [], [], [], []
    outcomes_path = base / "data/outcomes.jsonl"
    outcomes = [json.loads(x) for x in outcomes_path.read_text().splitlines()] if outcomes_path.exists() else []
    main_controls = []
    main_path = root / "main/predictions.jsonl"
    if main_path.exists():
        main_controls = [r for r in map(json.loads, main_path.read_text().splitlines()) if r["arm"] == "R1"]
    for directory, title, raw in (
        ("main", "Сохранённые оценки 0.8B, Prompt Guard, NLI, MiniCheck и табличных моделей", False),
        ("matched-reference", "SecJev 4B: согласованный контроль", False),
        ("text-reference-verified-final", "TF-IDF + Logistic Regression: восстановленный контроль", False),
        ("lr-stack-reference", "Logistic Regression: табличные признаки и четыре вероятности SecJev 0.8B", False),
        ("raw64", "Известный синтетический стресс-тест raw64", True),
    ):
        folder = root / directory
        data = read_json(folder / "metrics.json")
        if not data:
            statuses.append(f"{directory}: результаты пока отсутствуют")
            continue
        rows = [dict(r, evidence_set=directory) for r in data["aggregates"]]
        extra = read_json(folder / "selection-diagnostic/metrics.json", {})
        rows.extend(dict(r, evidence_set=directory, selection_variant="Blegacy_standalone_then_wrap") for r in extra.get("aggregates", []))
        all_rows.extend(rows)
        statuses.append(f"{directory}: {len(rows)} строк seed × policy × method")
        sections.append("<h2>" + html.escape(title) + "</h2>")
        if raw:
            sections.append("<p>raw64 уже известен исследователям и служит диагностикой переноса. Метки raw64 не выбирают пороги и конфигурации. Отсутствующие последовательности, табличные входы и оценки 4B не заменяются выдуманными значениями.</p>")
        else:
            selected = [r for r in rows if "train_selected" in r["arm"]]
            if selected:
                sections.append("<h3>Выбор метода только внутри обучения</h3>" + metric_table(selected))
            fixed = [r for r in rows if "train_selected" not in r["arm"] and representative(r)]
            sections.append("<h3>Фиксированные диагностические варианты</h3>" + metric_table(fixed))
        sections.append("<details><summary>Все методы, комбинации и оценки риска</summary>" + metric_table(rows, raw=raw, risk=not raw) + "</details>")
        for name in ("audit.json", "legacy-reproduction.json", "unsupported.json"):
            obj = read_json(folder / name)
            if obj is not None:
                sections.append("<details><summary>" + html.escape(directory + "/" + name) + "</summary><pre>" + html.escape(json.dumps(obj, ensure_ascii=False, indent=2)) + "</pre></details>")
        sections.append(f"<p><a href='../results/policy-comparison/{directory}/manifest.json'>Manifest</a> · <a href='../results/policy-comparison/{directory}/predictions.jsonl'>Внешние предсказания</a></p>")
        pred_path = folder / "predictions.jsonl"
        if pred_path.exists():
            groups = defaultdict(list)
            predictions = []
            for line in pred_path.open():
                r = json.loads(line)
                predictions.append(r)
                value = r.get("reconstructed_total_guard_ms")
                if isinstance(value, (float, int)) and math.isfinite(value):
                    groups[(r["policy"], r["arm"], r["seed"])].append(value)
            for (policy, arm, seed), values in groups.items():
                latency.append(dict(evidence_set=directory, policy=policy, arm=arm, seed=seed,
                                    prefixes=len(values), p50_ms=percentile(values, .5), p95_ms=percentile(values, .95)))
            if outcomes and not raw:
                grouped_rows.extend(per_group(predictions + ([] if directory == "main" else main_controls), outcomes, directory))
            extra_predictions = folder / "selection-diagnostic/predictions.jsonl"
            if extra_predictions.exists() and outcomes and not raw:
                extra_records = [json.loads(x) for x in extra_predictions.read_text().splitlines()]
                grouped_rows.extend(r for r in per_group(extra_records + main_controls, outcomes, directory) if r["arm"] != "R1")
                extra_groups = defaultdict(list)
                for r in extra_records:
                    value = r.get("reconstructed_total_guard_ms")
                    if isinstance(value, (float, int)) and math.isfinite(value):
                        extra_groups[r["policy"], r["arm"], r["seed"]].append(value)
                for (policy, arm, seed), values in extra_groups.items():
                    latency.append(dict(evidence_set=directory, policy=policy, arm=arm, seed=seed, prefixes=len(values), p50_ms=percentile(values, .5), p95_ms=percentile(values, .95)))
        for fold in read_json(folder / "folds.json", []):
            c = fold.get("calibration", {})
            metric = c.get("metrics", {}).get("raw_episode_fpr", {})
            selected = c.get("threshold_selection_metrics", {}).get("raw_episode_fpr", {})
            calibration_rows.append(dict(evidence_set=directory, policy=fold["policy"], seed=fold["seed"], outer_fold=fold["outer_fold"], arm=fold["arm"],
                threshold=fold.get("threshold"), threshold_infinite=fold.get("threshold") is None,
                selected_config=fold.get("selected_config", fold.get("selected_format")),
                threshold_constraint_scope=c.get("threshold_constraint_scope"), target_feasible=c.get("target_feasible"),
                final_system_target_feasible=c.get("final_system_target_feasible"), inner_final_FP=metric.get("k"),
                inner_safe_n=metric.get("n"), inner_component_FP=selected.get("k") if fold["policy"] == "B_independent" else None,
                **c.get("inner_false_stop_decomposition", {})))
    export_csv(root / "comparison.csv", all_rows)
    export_csv(root / "latency-comparison.csv", latency)
    export_csv(root / "per-group.csv", grouped_rows)
    export_csv(root / "calibration.csv", calibration_rows)
    intro = """<p class='note'><strong>POST-HOC: исследовательское сравнение после просмотра прежних результатов.</strong> Исходные оценки и результаты сохранены. Новые решения по порогам и выбору метода вычислены только по обучающим частям, но сами политики сформулированы после анализа архива. Это не независимое подтверждение улучшения.</p>
<p>Главный результат — остановка до первого вредного перевода в сохранённом продолжении (counterfactual), а не измеренное предотвращение в живой системе. Числа через косую черту соответствуют seeds 17 / 29 / 43. Это три переразбиения одних эпизодов, не три независимые выборки; их нельзя суммировать для доверительных интервалов.</p>
<p>В 176 достигших P4 префиксах: 83 опасных и 93 безопасных продолжения. Episode FPR учитывает все 131 безопасных эпизода, включая 38 не достигших P4. Отдельно показаны остановки и корректное завершение 98 исходно честных задач: часть таких задач сама создала опасное состояние. STOP не является восстановлением этой задачи.</p>"""
    policy_text = """<h2>Что именно меняется</h2><ul>
<li><strong>A_joint:</strong> максимум обнаружения опасных продолжений при внутреннем FPR ≤5%, затем минимум ложных остановок, затем максимальный порог. Rules входят в калибровку итогового решения.</li>
<li><strong>B_independent:</strong> тот же выбор порога для самостоятельного модельного компонента, затем OR с rules. У фиксированного метода внутренняя граница 5% относится к компоненту; итоговое OR может её превысить. Вариант B2 выбирает конфигурацию по итоговому wrapped inner решению: бюджет соблюдён, только если существует допустимый кандидат. Blegacy сначала выбирает самостоятельного победителя, затем добавляет rules; строки сохранены отдельно.</li>
<li><strong>C_lowest:</strong> минимальный допустимый порог на полной конечной сетке решений при внутреннем FPR итоговой системы ≤5%. Этот критерий может тратить бюджет ложных остановок без прироста обнаружения на обучении.</li></ul>
<p>Порог, выбранная комбинация и формат определяются по внутренним групповым OOF-оценкам; внешние эпизоды используются только для отчётных метрик. Проверка точного воспроизведения старого A отделена от нового сравнения на исправленной полной сетке: {+∞} и уникальные конечные наблюдавшиеся score, сравнение ≥. Она сохраняет состояния STOP при соседних float-значениях; фактическое влияние исправления приведено в audit. JSON null в порогах означает +∞.</p>
<p>Калибровка на одной совокупности не гарантирует внешнего FPR ≤5%. Вероятности отдельных ответов SecJev, Prompt Guard и NLI не объявляются вероятностью вреда. AP, Brier и log loss относятся только к обученным оценкам риска на достигших P4 эпизодах; OR с rules не заменяет их вероятностью 1.</p>"""
    findings = root / "findings.md"
    families = []
    review = root / "review"
    if review.exists():
        for p in sorted(review.glob("*.md")):
            families.append("<h3>" + html.escape(p.name) + "</h3>" + render_text(p.read_text()))
    resources = """<h2>Задержка и ресурсы</h2><p>Смена порога использует сохранённые оценки: новый inference защитников и платные API не выполнялись. Недостающие внутренние прогнозы отдельных контролей восстанавливаются локальным обучением по замороженным признакам; время и число fit-вызовов хранятся в соответствующих timings/manifest.</p>
<p><a href='../results/policy-comparison/latency-comparison.csv'>CSV полного пути p50/p95 по каждому методу, политике и seed</a>. Значения реконструированы из прежнего извлечения признаков и измеренного решения модели, без исполнения живого FinBot. Они не измеряют оптимизацию раннего выхода по rules. Для Jev отдельно учитывается сумма прежних вызовов, а не только дешёвое чтение кеша.</p>
<p>Холодная загрузка, память моделей, отдельные минимальные режимы NLI/MiniCheck и стоимость извлечения сохранены в <a href='cheap-report.html'>исходном отчёте</a>. RSS и Metal не суммируются как независимая физическая память. Денежная стоимость электричества и подписочные кредиты не вычислялись. Старый live LLM-защитник не имеет сопоставимых сохранённых оценок на этих групповых разбиениях и остаётся историческим наблюдением.</p>"""
    page = "<!doctype html><html lang='ru'><meta charset='utf-8'><title>Post-hoc: три политики контроля каскада</title><style>body{font:16px/1.5 system-ui;margin:32px;color:#18253b;max-width:1800px}table{border-collapse:collapse;font-size:12px;display:block;overflow:auto;margin:14px 0}td,th{border:1px solid #ccd4df;padding:6px;text-align:left}th{background:#ecf1f7}tr:nth-child(even){background:#f7f9fc}.note{background:#fff2d7;padding:16px;border-left:5px solid #d58b00}pre{white-space:pre-wrap;font-size:12px}details{margin:16px 0}summary{cursor:pointer;font-weight:600}a{color:#174ea6}</style><h1>Три политики: post-hoc сравнение на сохранённых оценках</h1>"
    page += intro + (render_text(findings.read_text()) if findings.exists() else "") + policy_text
    page += "<p>" + html.escape(" · ".join(statuses)) + "</p><h2>Качество и реконструированная задержка: train-only выбор с R1</h2>" + quality_latency_table(all_rows, latency) + "".join(sections) + resources
    page += "<h2>Разложение ошибок и зависимость от семейства</h2><p><a href='../results/policy-comparison/calibration.csv'>Все пороги и внутренняя калибровка</a>: отдельно final/component/rule FP и пересечение, достижимость общего ограничения. Невозможность соблюсти бюджет не скрывается fallback-порогом +∞.</p><p><a href='../results/policy-comparison/per-group.csv'>Метрики по каждому held-out group и seed</a>: опасные/безопасные знаменатели, TP/FP и дополнительные TP/FP относительно R1. Переразбиения и варианты одного механизма не суммируются как независимые свидетельства. В исходном архиве все пять пропусков R1 находятся в одной authority-группе d4bfdb1c9fe05332897b; в ней десять опасных эпизодов, пять уже закрыты R1. Улучшение на оставшихся пяти не доказывает перенос на несколько новых механизмов.</p>"
    page += "<h2>Независимое ревью и следующий проверочный набор</h2><p>Предложения ниже — дизайн будущей независимой проверки. Они не являются уже выполненным тестом обобщения. Известный raw64 остаётся отдельной диагностикой.</p>" + ("".join(families) or "<p>Ревью ещё не сохранено.</p>")
    audit = read_json(review / "final-audit.json")
    if audit:
        page += "<p>Независимая проверка реализации: <strong>" + html.escape(audit.get("status", "UNKNOWN")) + "</strong>. Точная область проверки и сохранённые hashes: <a href='../results/policy-comparison/review/final-audit.json'>final-audit.json</a>. Это аудит воспроизводимости и корректности, а не независимая проверка обобщения.</p>"
    page += "<h2>Данные и воспроизведение</h2><p><a href='../results/policy-comparison/comparison.csv'>Все метрики CSV</a> · <a href='../results/policy-comparison/report-manifest.json'>Manifest отчёта</a> · <a href='../results/policy-comparison/previous-report/cheap-report.html'>Снимок прежнего отчёта</a> · <a href='../POLICY-COMPARISON.md'>Команды и протокол</a></p></html>"
    output = base / "reports/cheap-policy-report.html"
    output.write_text(page)
    files = [output, root / "comparison.csv", root / "latency-comparison.csv", root / "per-group.csv", root / "calibration.csv", Path(__file__)]
    if findings.exists():
        files.append(findings)
    files += list(review.glob("*.md")) if review.exists() else []
    if (review / "final-audit.json").exists():
        files.append(review / "final-audit.json")
    manifest = {"role": "post-hoc presentation from saved scores; no inference", "metric_rows": len(all_rows),
                "sha256": {str(p.relative_to(base)) if p.is_relative_to(base) else str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    manifest["input_sha256"] = {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for directory in ("main", "matched-reference", "text-reference-verified-final", "lr-stack-reference", "raw64")
                                for name in ("metrics.json", "predictions.jsonl", "folds.json", "selection-diagnostic/metrics.json", "selection-diagnostic/predictions.jsonl")
                                if (p := root / directory / name).exists()}
    for p in (base / "POLICY-COMPARISON.md", base / "POLICY-RAW64.md"):
        if p.exists():
            manifest["input_sha256"][str(p.relative_to(base))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (root / "report-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(refresh(args.base.resolve()))


if __name__ == "__main__":
    main()
