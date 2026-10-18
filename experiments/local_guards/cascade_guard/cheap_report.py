"""Render the cheap guard series from saved evidence without rerunning models."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import math
from zoneinfo import ZoneInfo

from .night_report import render_text


def _percentile(values, probability):
    ordered = sorted(values)
    position = (len(ordered)-1)*probability
    low = int(position); high = min(low+1, len(ordered)-1)
    return ordered[low] + (ordered[high]-ordered[low])*(position-low)


def refresh(base: Path):
    root = base / "results/cheap-guards"
    run = json.loads((root / "run.json").read_text())
    unchanged = {p: hashlib.sha256((base / p).read_bytes()).hexdigest() == h for p, h in run["immutable_sha256"].items()}
    if not all(unchanged.values()):
        raise ValueError("Immutable baseline changed; inspect before publishing")
    sections = []
    findings_path = root / "findings.md"
    if findings_path.exists():
        sections.append("<h2>Что показала серия</h2>" + render_text(findings_path.read_text()))
    access_path = root / "promptguard/browser-access-status.json"
    if access_path.exists():
        access = json.loads(access_path.read_text())
        if access.get("status") == "REJECTED_BY_REPOSITORY_AUTHORS":
            pg_complete = all((root / "models" / f"{b}.jsonl").exists() and len((root / "models" / f"{b}.jsonl").read_text().splitlines()) == 176 for b in ("G22", "G86"))
            if pg_complete and (root / "promptguard/mirror-runtime-identity-proof.json").exists():
                sections.append("<p class='note'>Hugging Face отклонил заявку на Prompt Guard 2. По последующему указанию пользователя те же официальные 22M/86M checkpoint получены с ModelScope: веса сверены с официальными LFS SHA-256, остальные runtime-файлы — с Git blob ID закреплённых ревизий. Модели и научный протокол не заменялись. <a href='../results/cheap-guards/promptguard/mirror-runtime-identity-proof.json'>Доказательство идентичности</a>.</p>")
            else:
                sections.append("<p class='note'>Авторы официальных репозиториев Hugging Face отклонили заявку на доступ к Prompt Guard 2. По последующему указанию пользователя проверены копии тех же checkpoint с ModelScope; итоговую полноту прогона определяет таблица моделей ниже. <a href='../results/cheap-guards/promptguard/mirror-runtime-identity-proof.json'>Проверка файлов</a>.</p>")
    metric_file = root / "evaluation/metrics.json"
    manifest_file = root / "evaluation/manifest.json"
    if metric_file.exists():
        metrics = json.loads(metric_file.read_text())["aggregates"]
        grouped = defaultdict(list)
        for record in metrics:
            grouped[record["arm"]].append(record)
        flat = []
        for row in metrics:
            item = {k: row.get(k) for k in ("arm", "seed", "complete", "unknown_stop", "pr_auc", "brier", "log_loss")}
            for key, value in row.items():
                if isinstance(value, dict) and {"k", "n"} <= value.keys():
                    item[key + "_k"], item[key + "_n"] = value["k"], value["n"]
            flat.append(item)
        if flat:
            with (root / "comparison.csv").open("w", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=list(dict.fromkeys(k for r in flat for k in r)))
                writer.writeheader(); writer.writerows(flat)
        headings = ["| Метод | Вред STOP /83 | Безопасные STOP /131 | Достигшие P4 безопасные STOP /93 | Корректные честные платежи /98 | UNKNOWN |", "|---|---:|---:|---:|---:|---:|"]
        details = headings.copy()
        for arm, rows in grouped.items():
            rows.sort(key=lambda r: r["seed"])
            by_seed = {r["seed"]: r for r in rows}
            values = [" / ".join(str(by_seed[s][key]["k"]) if s in by_seed and by_seed[s].get("complete") else "—" for s in (17, 29, 43)) for key in ("harm_prevented_counterfactual", "raw_episode_fpr", "p4_reached_safe93_interruption", "source_benign_compliant_completion_counterfactual")]
            values.append(" / ".join(str(by_seed[s]["unknown_stop"]) if s in by_seed and by_seed[s].get("complete") else "—" for s in (17, 29, 43)))
            line = "| " + arm + " | " + " | ".join(values) + " |"
            details.append(line)
            if arm.startswith("train_selected_combo:") or any(f":{b}" in arm and "+" not in arm.split(":", 1)[1].split("|")[0] for b in ("J_cur", "J_seq", "J_agg", "J_dynamic", "J_prior", "G22", "G86", "N", "M")) or arm in ("NoDefense", "R1", "R2"):
                headings.append(line)
        sections.append("<h2>Основные сравнения</h2><p>Числа слева направо: seeds 17, 29, 43; — означает неполный или отсутствующий результат. Главная строка выбора — train_selected_combo:original_rules; выбор признаков и порога выполнен внутри обучения.</p>" + render_text("\n".join(headings)))
        sections.append("<details><summary>Все комбинации</summary>" + render_text("\n".join(details)) + "</details>")
        calibration = ["| Метод | Seed | PR-AUC (AP) | Brier | Log loss |", "|---|---:|---:|---:|---:|"]
        for row in metrics:
            if row.get("complete") and row.get("brier") is not None:
                auc = row.get("pr_auc")
                calibration.append(f"| {row['arm']} | {row['seed']} | {auc:.4f} | {row['brier']:.4f} | {row['log_loss']:.4f} |" if auc is not None else f"| {row['arm']} | {row['seed']} | — | {row['brier']:.4f} | {row['log_loss']:.4f} |")
        sections.append("<details><summary>Качество обученной оценки риска</summary><p>PR-AUC/AP, Brier и log loss считаются по известным оценкам риска на 176 P4-префиксах. Для 38 безопасных эпизодов, не достигших P4, вероятность не выдумывается; они входят только в соответствующие эпизодные показатели.</p>" + render_text("\n".join(calibration)) + "</details>")
    for directory, title, explanation in (
        ("matched-reference", "Контроль 4B с той же калибровкой", "Отдельный контроль по прежним кешированным оценкам 4B: те же групповые разбиения, параметры CatBoost, новая политика порогов и выбор формата только внутри обучения. Нового inference нет; основная серия не перезаписывалась."),
        ("protocol-diagnostic", "Post-hoc диагностика: независимый компонент OR R1", "После выявления потолка совместной калибровки отдельно зафиксирован диагностический план. Все прежние решения компонента :none объединены с R1; пороги, вероятности и выбранные внутри обучения конфигурации сохранены. Нового обучения, inference и выбора по внешним результатам нет. Это исследовательская диагностика, не подтверждающая замена основного протокола."),
    ):
        path = root / directory / "metrics.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        by_arm = defaultdict(list)
        for row in data["aggregates"]:
            by_arm[row["arm"]].append(row)
        table = ["| Метод | Вред STOP /83 | Безопасные STOP /131 | Корректные честные платежи /98 |", "|---|---:|---:|---:|"]
        all_rows = table.copy()
        for arm, rows in sorted(by_arm.items()):
            lookup = {r["seed"]: r for r in rows}
            values = [" / ".join(str(lookup[s][key]["k"]) if s in lookup and lookup[s].get("complete") else "—" for s in (17,29,43)) for key in ("harm_prevented_counterfactual", "raw_episode_fpr", "source_benign_compliant_completion_counterfactual")]
            line = "| " + arm + " | " + " | ".join(values) + " |"
            all_rows.append(line)
            if "train_selected" in arm:
                table.append(line)
        sections.append(f"<h2>{title}</h2><p>{explanation}</p>" + render_text("\n".join(table)) + "<details><summary>Все фиксированные варианты</summary>" + render_text("\n".join(all_rows)) + "</details>" + f"<p><a href='../results/cheap-guards/{directory}/manifest.json'>Manifest</a> · <a href='../results/cheap-guards/{directory}/predictions.jsonl'>Предсказания</a></p>")
        if data.get("raw_aggregates"):
            raw_table = ["| Диагностика raw64 | Seed | Опасные STOP /32 | Допустимые STOP /32 |", "|---|---:|---:|---:|"]
            for row in data["raw_aggregates"]:
                raw_table.append(f"| {row['arm']} | {row['seed']} | {row['TP']} | {row['FP']} |")
            sections.append("<details><summary>Post-hoc диагностика на известном raw64</summary>" + render_text("\n".join(raw_table)) + "</details>")
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text())
        sections.append("<h2>Полнота и ресурсы</h2><pre>" + html.escape(json.dumps({k: manifest.get(k) for k in ("status", "available_complete_blocks", "unavailable_main_blocks", "requested_matrix_complete", "resources_by_block")}, ensure_ascii=False, indent=2)) + "</pre>")
        resource_table = ["| Модель | Параметры, млн | Префиксы / окна | Холодный адаптер, с | Максимум RSS, ГБ | Наблюдаемый максимум Metal, ГБ |", "|---|---:|---:|---:|---:|---:|"]
        for block in ("G22", "G86", "N", "M"):
            path = root / "models" / f"{block}.jsonl"
            if not path.exists():
                continue
            rows = [json.loads(line) for line in path.read_text().splitlines() if line]
            cold = max((r.get("timing_ms", {}).get("cold_load", 0) for r in rows), default=0) / 1000
            rss = max((r.get("memory", {}).get("peak_rss_bytes", 0) for r in rows), default=0) / 1e9
            metal = max((max(r.get("memory", {}).get("mps_driver_allocated_bytes", 0), r.get("memory", {}).get("prefix_sampled_max", {}).get("mps_driver_allocated_bytes", 0)) for r in rows), default=0) / 1e9
            windows = sum(r.get("window_count", 0) for r in rows)
            parameter_count = next((r.get("model_metadata", {}).get("parameter_count") for r in rows if r.get("model_metadata", {}).get("parameter_count")), None)
            parameters = f"{parameter_count / 1e6:.2f}" if parameter_count is not None else "—"
            resource_table.append(f"| {block} | {parameters} | {len(rows)} / {windows} | {cold:.2f} | {rss:.2f} | {metal:.2f} |")
        sections.append(render_text("\n".join(resource_table)) + "<p>Холодный адаптер — измеренный этап создания адаптера с загрузкой весов и встроенной валидацией; у Prompt Guard он включает smoke. Отдельная проверка CPU/MPS, контрольные checksum до создания адаптера и скачивание в это число не включены. Память — наблюдаемый максимум, включая выборку каждые 50 мс; это не точный внутренний high-water mark аллокатора. NLI/MiniCheck timing.compute — полное время извлечения признаков, не время чистого GPU-ядра.</p>")
    predictions_file = root / "evaluation/predictions.jsonl"
    profile_table = ["| Минимальный скалярный режим | Префиксы / окна | p50 / p95 извлечения, с |", "|---|---:|---:|"]
    profiles_available = False
    for block in ("N", "M"):
        profile_path = root / "scalar-profiles" / f"{block}.jsonl"
        if profile_path.exists():
            profiles = [json.loads(x) for x in profile_path.read_text().splitlines() if x]
            costs = sorted(r["inference_cost_ms"] for r in profiles if r["status"] == "OK")
            if len(costs) == 176:
                def q(p):
                    position=(len(costs)-1)*p; low=int(position); high=min(low+1,len(costs)-1)
                    return (costs[low]+(costs[high]-costs[low])*(position-low))/1000
                profile_table.append(f"| {block}: fixed4 trusted_combined | {len(profiles)} / {sum(r['window_count'] for r in profiles)} | {q(.5):.3f} / {q(.95):.3f} |")
                profiles_available = True
    if profiles_available:
        sections.append("<h2>Скалярный сигнал без лишних признаков</h2>" + render_text("\n".join(profile_table)) + "<p>Отдельный замер вычисляет только четыре утверждения против trusted_combined с той же формулой и окнами. Скалярные оценки сверены с полным экстрактором на всех 176 префиксах (допуск 1e-4). Качество берётся из прежнего полного прогона; в CatBoost эти профили не поступают и не становятся дополнительными кандидатами. Строки общей CSV задержки используют полный общий экстрактор; минимальная самостоятельная реализация измерена этой таблицей.</p>")
    sequence_path = root / "sequence/features.jsonl"
    if sequence_path.exists():
        blocks = defaultdict(list)
        for row in map(json.loads, sequence_path.read_text().splitlines()):
            blocks[row["block"]].append(row)
        cache_table = ["| Jev | Кеш + признаки p50 / p95, мс | Прежний inference p50 / p95, с |", "|---|---:|---:|"]
        for block in ("J_cur", "J_prior", "J_seq", "J_agg", "J_dynamic"):
            rows = [r for r in blocks.get(block, []) if r["status"] == "OK"]
            if rows:
                cached = [r["timing_ms"]["cache_join"] + r["timing_ms"]["feature_extraction"] for r in rows]
                original = [r["inference_cost_ms"]/1000 for r in rows]
                cache_table.append(f"| {block} | {_percentile(cached,.5):.4f} / {_percentile(cached,.95):.4f} | {_percentile(original,.5):.3f} / {_percentile(original,.95):.3f} |")
        sections.append("<h2>Чтение кеша и стоимость мониторинга Jev</h2>" + render_text("\n".join(cache_table)) + "<p>Левая колонка — новый замер соединения сохранённых записей и построения признаков. Правая — реконструированная сумма прежних вызовов нужных этапов; нового inference Jev не было.</p>")
    for title, timing_path, nested in (("Обучение в групповой CV", root / "evaluation/timings.json", True), ("Финальная подгонка архивных моделей для raw64", root / "evaluation/raw64/timings.json", False)):
        if timing_path.exists():
            by_config = defaultdict(list)
            for row in json.loads(timing_path.read_text()):
                fits = row["fits"] if nested else [row["timing"]]
                by_config[row["config"]].extend(f["fit_ms"] for f in fits if f.get("fit_ms", 0) > 0)
            training_table = ["| Конфигурация | Fit-вызовы | Сумма, с | p50 / p95 одного fit, мс |", "|---|---:|---:|---:|"]
            for config, values in sorted(by_config.items()):
                if values:
                    training_table.append(f"| {config} | {len(values)} | {sum(values)/1000:.3f} | {_percentile(values,.5):.3f} / {_percentile(values,.95):.3f} |")
            sections.append(f"<details><summary>{title}</summary>" + render_text("\n".join(training_table)) + "<p>Измеренное wall time обучения, отдельно от предсказания. Одни fit и прогнозы переиспользованы тремя rules-вариантами и повторно не суммируются. Это стоимость экспериментальной оценки, не стоимость каждого рабочего эпизода.</p></details>")
    if predictions_file.exists():
        latency_groups = defaultdict(list)
        arm_components = defaultdict(set)
        with predictions_file.open() as file:
            for line in file:
                row = json.loads(line)
                config = row.get("selected_config", row["arm"])
                if ":" in config:
                    arm_components[row["arm"]].update(config.split(":")[1].split("+"))
                value = row.get("reconstructed_total_guard_ms")
                if isinstance(value, (int, float)) and math.isfinite(value):
                    latency_groups[(row["arm"], row["seed"])].append(value)
        table = ["| Метод | Seed | Полный путь p50 / p95, мс | Префиксы |", "|---|---:|---:|---:|"]
        exported = []
        def percentile(values, q):
            ordered = sorted(values); p = (len(ordered)-1)*q; lo = int(p); hi = min(lo+1, len(ordered)-1)
            return ordered[lo] + (ordered[hi]-ordered[lo])*(p-lo)
        for (arm, seed), values in sorted(latency_groups.items()):
            median, high = percentile(values, .5), percentile(values, .95)
            exported.append({"arm": arm, "seed": seed, "prefixes": len(values), "total_guard_p50_ms": median, "total_guard_p95_ms": high})
            if arm.startswith("train_selected_combo:") or arm in ("R1", "R2"):
                table.append(f"| {arm} | {seed} | {median:.3f} / {high:.3f} | {len(values)} |")
        if exported:
            with (root / "latency-comparison.csv").open("w", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=list(exported[0])); writer.writeheader(); writer.writerows(exported)
            sections.append("<h2>Полный путь до решения</h2>" + render_text("\n".join(table)) + "<p>Сумма извлечения признаков и измеренного одиночного вызова классификатора с rules. Для Jev извлечение реконструировано из прежних вызовов; для новых моделей измерено в этой серии. Это реконструкция последовательной цепочки, без измерения живого enforce-режима и без оптимизации пропуска модели после раннего BLOCK. <a href='../results/cheap-guards/latency-comparison.csv'>Все методы: CSV задержки</a>.</p>")
            peaks = {}
            for block in ("G22", "G86", "N", "M"):
                path = root / "models" / f"{block}.jsonl"
                if path.exists():
                    records = [json.loads(x) for x in path.read_text().splitlines() if x]
                    peaks[block] = max((max(r.get("memory", {}).get("mps_driver_allocated_bytes", 0), r.get("memory", {}).get("prefix_sampled_max", {}).get("mps_driver_allocated_bytes", 0)) for r in records), default=0) / 1e9
            compact = ["| Метод | Вред STOP /83 | Безопасные STOP /131 | p50 / p95 пути, с | Metal компонентов, ГБ |", "|---|---:|---:|---:|---:|"]
            compact_arms = ("R1", "R2", "catboost:tabular:original_rules", "tabular_logistic:tabular:original_rules", "catboost:J_cur:original_rules", "catboost:J_seq:original_rules", "catboost:J_dynamic:original_rules", "catboost:G22:original_rules", "catboost:G86:original_rules", "catboost:N:original_rules", "catboost:M:original_rules", "train_selected_combo:original_rules")
            def span(values, digits=0):
                low, high = min(values), max(values)
                return f"{low:.{digits}f}" if low == high else f"{low:.{digits}f}–{high:.{digits}f}"
            for arm in compact_arms:
                quality = [r for r in grouped.get(arm, []) if r.get("complete")]
                costs = [r for r in exported if r["arm"] == arm]
                if len(quality) != 3 or len(costs) != 3:
                    continue
                components = arm_components[arm]
                metal = "; ".join(f"{b}: {peaks[b]:.2f}" for b in sorted(components) if b in peaks) or "—"
                if any(b.startswith("J_") for b in components):
                    metal += "; Jev: прежний runtime"
                compact.append(f"| {arm} | {span([r['harm_prevented_counterfactual']['k'] for r in quality])} | {span([r['raw_episode_fpr']['k'] for r in quality])} | {span([r['total_guard_p50_ms']/1000 for r in costs], 3)} / {span([r['total_guard_p95_ms']/1000 for r in costs], 3)} | {metal} |")
            sections.append("<h2>Качество — задержка — ресурсы</h2>" + render_text("\n".join(compact)) + "<p>Диапазоны — минимум и максимум трёх seed. Задержки используют полный набор признаков. Память указана отдельно для каждого измеренного компонента; это не замер одновременно загруженной комбинации. Для архивного Jev новый замер памяти не выполнялся.</p>")
    for filename in ("quality-comparison.png", "feature-latency.png"):
        if (root / filename).exists():
            sections.append(f"<p><img style='max-width:100%' src='../results/cheap-guards/{filename}' alt='{filename}'></p>")
    previous = base / "results/night-4b/evaluation/metrics.json"
    if previous.exists():
        table = ["| Предыдущая серия | Seed | Вред /83 | Ложные STOP /131 |", "|---|---:|---:|---:|"]
        for row in json.loads(previous.read_text())["aggregates"]:
            if row["arm"] in ("Rules", "secjev:old08+rules", "prob_catboost:train_selected_format+rules"):
                table.append(f"| {row['arm']} | {row['seed']} | {row['harm_prevented_counterfactual']['k']} | {row['raw_episode_fpr']['k']} |")
        sections.append("<h2>Исторические результаты: другая калибровка</h2><p>Популяция, группы, seeds и параметры CatBoost совпадают, но исторический evaluator выбирал самый низкий допустимый порог. Основная новая серия при равном обнаружении минимизирует ложные STOP и выбирает самый высокий порог. Поэтому это исторический системный reference, не чистое сравнение моделей; matched-reference ниже использует новую политику калибровки.</p>" + render_text("\n".join(table)))
    for title, relative in (("Подробные метрики", "evaluation/report.md"), ("Дополнительный raw64 стресс-тест", "evaluation/raw64/report.md")):
        path = root / relative
        if path.exists():
            sections.append(f"<h2>{title}</h2><details><summary>Развернуть</summary>{render_text(path.read_text())}</details>")
    raw_metrics_path = root / "evaluation/raw64/metrics.json"
    if raw_metrics_path.exists():
        raw_metrics = json.loads(raw_metrics_path.read_text())["aggregates"]
        raw_headings = ["| Метод | Seed | Опасные STOP /32 | Допустимые STOP /32 | UNKNOWN |", "|---|---:|---:|---:|---:|"]
        raw_details = raw_headings.copy()
        for row in raw_metrics:
            if not row.get("complete"):
                continue
            line = f"| {row['arm']} | {row['seed']} | {row['TP']} | {row['FP']} | {row['unknown_stop']} |"
            raw_details.append(line)
            if row["arm"].startswith("train_selected") or row["arm"] in ("NoDefense", "R1", "R2"):
                raw_headings.append(line)
        sections.append("<h2>Известный raw64 стресс-тест</h2><p>32 допустимых и 32 опасных авторских случая. Обучение и пороги зафиксированы по архиву; raw-метки использованы только для описательной оценки.</p>" + render_text("\n".join(raw_headings)))
        sections.append("<details><summary>Все поддерживаемые методы raw64</summary>" + render_text("\n".join(raw_details)) + "</details>")
        unsupported_path = root / "evaluation/raw64/unsupported.json"
        if unsupported_path.exists():
            unsupported = json.loads(unsupported_path.read_text())
            selected_unsupported = [r for r in unsupported if r.get("arm", "").startswith("train_selected")]
            sections.append("<p>Конфигурации с отсутствующей последовательностью Jev или табличным состоянием не подменяются другими моделями. Полный победитель и отдельно выбранный по архиву raw-совместимый победитель показаны раздельно.</p><details><summary>Неподдерживаемые победители и конфигурации: " + str(len(unsupported)) + "</summary><pre>" + html.escape(json.dumps(selected_unsupported, ensure_ascii=False, indent=2)) + "</pre><a href='../results/cheap-guards/evaluation/raw64/unsupported.json'>Полный список</a></details>")
    pg = root / "promptguard/access-preflight.json"
    if pg.exists():
        sections.append("<p>Официальный доступ к Prompt Guard проверяется отдельно от входа в браузер. Первичный preflight сохранён как историческое свидетельство; итоговую доступность определяют manifest моделей и таблица полноты, а не этот первый ответ сервера.</p>")
    stamp = datetime.now(ZoneInfo("Europe/Moscow")).isoformat()
    page = "<!doctype html><html lang='ru'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Дешёвые защитники и динамика Jev</title><style>body{font:16px/1.55 system-ui;max-width:1250px;margin:36px auto;padding:0 24px;color:#18232d}table{border-collapse:collapse;font-size:14px;width:100%}td,th{padding:9px;border-bottom:1px solid #dce4e8;text-align:left;vertical-align:top}th{background:#eef4f6}.scroll{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:14px}a{color:#176a8b}.note{background:#fff3d8;padding:15px}</style><body><h1>Дешёвые защитники и динамика Jev</h1>"
    page += f"<p>Обновлено {stamp}. Статус серии: {html.escape(run['status'])}. <a href='night-report.html'>Предыдущая серия 4B</a>.</p>"
    page += "<p class='note'>Архивная оценка измеряет контрфактический STOP перед переводом, не предотвращение вживую. Рабочая модель архива — GPT-4o mini. Политика и разметка прежние. Вероятность prompt injection, entailment или поддержки утверждения не равна вероятности вреда. Brier/log loss относятся к обученному компоненту до переопределения rules.</p>"
    page += "<p>Групповые разбиения совпадают с предыдущей серией. Три seed используют те же эпизоды и не утраивают выборку. Rules_v2 ранее разрабатывались с учётом этого архива; их результаты показаны отдельно. Raw64 — уже известный синтетический стресс-тест, не новая независимая выборка. При фиксированных четырёх этапах сравнение последовательности и агрегатов совместно оценивает этапы и порядок.</p><p>Время чтения кеша Jev отделено от реконструированной суммы четырёх inference-вызовов. Задержки комбинаций складываются по использованным моделям; это оценка последовательного извлечения признаков, а не измерение оптимизированной живой цепочки.</p>"
    page += "<p>NLI/MiniCheck проверяются на структурированных JSON-свидетельствах. Максимальная поддержка по окнам — статистический признак, а не доказательство совместной истинности всех условий; неподдержанное утверждение не обязательно противоречиво. MiniCheck использует наш замороженный режим окон 512 токенов, а не воспроизведение всех настроек опубликованного программного пакета. Новые NLI/MiniCheck/Prompt Guard измеряются с batch=1; у архивного Jev сохранён прежний runtime. Стоимость полного набора признаков и минимального скалярного сигнала различается.</p>"
    page += "".join(sections)
    page += "<p><a href='../results/cheap-guards/comparison.csv'>CSV</a> · <a href='../results/cheap-guards/protocol.json'>Замороженный протокол</a> · <a href='../results/cheap-guards/report-manifest.json'>Manifest</a></p></body></html>"
    (base / "reports/cheap-report.html").write_text(page)
    evidence = {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file() and p.name not in ("report-manifest.json", "finalizer.json") and not p.name.endswith(".log")}
    evidence["reports/cheap-report.html"] = hashlib.sha256((base / "reports/cheap-report.html").read_bytes()).hexdigest()
    (root / "report-manifest.json").write_text(json.dumps({"generated_at": stamp, "baseline_unchanged": unchanged, "mutable_control_files_excluded": ["finalizer.json", "*.log"], "sha256": evidence}, indent=2) + "\n")
    return {"report": str(base / "reports/cheap-report.html"), "baseline_unchanged": True, "status": run["status"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[1])
    print(json.dumps(refresh(parser.parse_args().base)))
