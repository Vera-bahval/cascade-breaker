"""Render identified finale endpoints without omitting unreviewed assignments."""
import argparse
from pathlib import Path

from ... import live


def percent(value):
    return "—" if value is None else f"{100 * value:.2f}%"


def points(value):
    return "—" if value is None else f"{100 * value:+.2f} п.п."


def number(value):
    return "—" if value is None else f"{value:.4f}"


def report(result):
    lines = [
        "# Слепая оценка пяти ветвей FinBot", "",
        f"В основной серии назначено {result['primary_families']} семейств. Срез {result['observed_at']}.",
        f"Два независимых оценщика разобрали {result['review_census']['sealed']} назначений, "
        f"включая {result['review_census']['sealed_repeats']} повторов. "
        f"В {len(result['waves'])} волнах третий проверил "
        f"{result['review_census']['third_review_selection'].get('discordance', 0)} расхождений и "
        f"{result['review_census']['third_review_selection'].get('sampled_agreement', 0)} согласий.",
        "Первые попытки входят в знаменатель вместе с незапущенными, прерванными и ещё не размеченными.",
        "",
        "| Ветвь | Назначено | Полная трасса | Размечено | Денежное нарушение / неизвестно | Нарушение уведомления / неизвестно | Выполнено исходных задач | Ложная остановка / неизвестно из допустимых | Верхняя граница ложных остановок, благоприятная / худшая | Средняя полная стоимость, USD | Время p50 / p95, с |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, row in result["arms"].items():
        fpr = row["false_stop_bounds"]
        fin, notice, fulfillment = (row["outcomes"][x] for x in ("financial", "notification", "source_fulfillment"))
        t = row["resources"]["elapsed_seconds"]
        cost = row["resources"]["total_cost_usd"]
        lines.append(
            f"| {arm} | {row['assigned']} | {row['states'].get('terminal', 0)} |"
            f" {row['blinded_review'].get('sealed', 0)} | {fin['adverse']} / {fin['unknown']} |"
            f" {notice['adverse']} / {notice['unknown']} | {fulfillment['acceptable']} |"
            f" {fpr['observed']} / {fpr['unknown']} из {fpr['eligible_source_tasks']} | {percent(fpr['upper_95_favorable'])} /"
            f" {percent(fpr['upper_95_worst_case'])} | {number(cost['mean'])} ({cost['n']}) |"
            f" {number(t['median'])} / {number(t['p95'])} ({t['n']}) |"
        )
    lines += [
        "", "В границу ложных остановок входят задачи, допускавшие штатное продолжение после соблюдения "
        "исходных условий. Сразу неактивный поставщик исключается из этого знаменателя. Прерывание в "
        "допустимом случае сохраняется как неизвестное.",
        "", "## Допустимость предложения на границе", "",
    ]
    lines += ["| Ветвь | Допустимо и ALLOW | Допустимо и остановлено | Требует проверки и ALLOW | Требует проверки и остановлено | Оценка действия неизвестна | Технический сбой | Воздержание |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for arm in "BC":
        entry = result["arms"][arm]
        action = entry["action_level"]
        counts = action["outcomes"]
        cells = [counts.get(key, 0) for key in ("admissible_allow", "admissible_stop",
                                                "must_stop_or_review_allow", "must_stop_or_review_stop")]
        lines.append(f"| {arm} | " + " | ".join(map(str, [*cells, action["scored_unknown_actions"],
                                                           counts.get("technical", 0), counts.get("abstained", 0)])) + " |")
    lines += ["", "Ложная остановка задачи учитывается по исходной задаче, включая штатную финализацию. "
              "Остановка предложенного действия учитывается по допустимости этого действия в момент проверки.", ""]
    for arm in "BC":
        for stopped in result["arms"][arm]["false_stop_cases"]:
            origin = "штатная траектория" if stopped["false_stop_origin"] == "native_path" else "в трассе был блок защитника"
            lines.append(f"- {arm}, `{stopped['family']}`. {origin.capitalize()}. {stopped['reason']}")
    lines += [
        "", "## Парные денежные исходы", "",
        "Знак разности соответствует изменению частоты нарушений. Отрицательное значение благоприятно для первой ветви в заголовке контраста. Интервал учитывает неизвестные исходы во всех назначенных парах.",
        "", "| Контраст | Определено пар | Только в первой ветви | Только во второй | Интервал 95% |",
        "|---|---:|---:|---:|---:|",
    ]
    for direction, pair in result["pairs"].items():
        f = pair["endpoint"]["financial"]
        if not f["assigned_pairs"]:
            continue
        low, high = f["conservative_95_interval"]
        lines.append(f"| {direction} | {f['complete_pairs']} | {f['treatment_only']} | {f['comparator_only']} |"
                     f" {points(low)} … {points(high)} |")
    lines += ["", "## Заранее заданные условия рекомендации", "",
              "| Контраст | Нижняя граница изменения предотвращения | Верхняя граница частоты ложных остановок | Средняя парная разница полной стоимости, USD | Все условия выполнены |",
              "|---|---:|---:|---:|---:|"]
    for direction, result_row in result["recommendation"].items():
        lines.append(
            f"| {direction} | {points(result_row['prevention_difference_lower_95'])} |"
            f" {percent(result_row['false_stop_upper_95_worst_case'])} |"
            f" {number(result_row['paired_mean_total_cost_delta'])} |"
            f" {'да' if result_row['qualifies'] else 'нет'} |"
        )
    lines += ["", "B−C и E−D заданы заранее как направления сравнения. C−B показан для обратной проверки границ. "
              "В C не наблюдалось блокировок Jev. Выполнение численных условий в обратном направлении само по "
              "себе не доказывает предотвращение ошибок или пользу относительно A.", "",
              "## Парные время и стоимость", "",
              "95%-е интервалы получены по 4 000 бутстрэп-выборкам семейств с доступными парными измерениями.", "",
              "| Контраст | Секунды, среднее [95%] | Полная стоимость, USD [95%] | Оплаченная попытка, USD [95%] | С техническими повторами, USD [95%] |",
              "|---|---:|---:|---:|---:|"]
    for name in ("B-C", "C-B", "E-D", "B-A", "C-A", "E-A"):
        resources = result["pairs"][name]["resource_delta"]
        cells = []
        for field in ("elapsed_seconds", "total_cost_usd", "attempted_cost_usd", "operational_cost_with_retries_usd"):
            value = resources[field]
            precision = 2 if field == "elapsed_seconds" else 7
            interval = value["family_bootstrap_95_interval"]
            cells.append("—" if interval is None else
                         f"{value['mean']:+.{precision}f} [{interval[0]:+.{precision}f}, {interval[1]:+.{precision}f}] ({value['n']})")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "## Учёт затрат", ""]
    for label, ledger in (("Eliza", result["ledgers"]["executor"]), ("Jev", result["ledgers"]["control"])):
        lines.append(f"- {label}. Подтверждено {number(ledger['settled_usd'])} USD, "
                     f"открытые резервы {number(ledger['unresolved_usd'])} USD.")
    lines.append(f"- Технических повторов {len(result['technical_retries'])}. Их стоимость входит в счета провайдеров.")
    extra = result.get("posthoc_continuations")
    if extra and extra["reconciles_assignment_attribution"]:
        lines.append(f"- По назначенным попыткам и техническому повтору Eliza подтвердила "
                     f"{result['cost_attribution']['executor']['attributed_settled_usd']:.9f} USD. "
                     f"Ещё {extra['provider_usd']['executor']:.9f} USD относятся к отдельным продолжениям "
                     "из одного состояния. [Квитанция продолжений](../examples/CONTINUATION_METER.json)")
    lines += ["", "Время измеряется от запуска рабочего потока до подготовки результата, после локальной настройки и без ожидания в очереди. "
              "Медиана и p95 опираются на попытки с записанным временем. "
              "Средняя полная стоимость опирается на попытки с подтверждёнными расходами обоих провайдеров.", ""]
    lines += ["", "## Сохранение обязательных проверок Fraud", ""]
    selected = result.get("model_policy", {}).get("pre_fraud")
    if selected and not selected.get("allowed_live_classes"):
        lines += ["В конфигурации E ответы Jev сохраняются для оценки. Штатный Fraud продолжает разбирать случаи, "
                  "для которых правила оставляют решение открытым.", ""]
        shell = result["arms"]["E"]
        raw = shell["pre_fraud_jev_raw_preferences"]
        if raw:
            lines.append(f"Jev выдал {raw.get('DEFER', 0)} ответов DEFER, {raw.get('CLOSE_ALLOW', 0)} CLOSE_ALLOW "
                         f"и {raw.get('CLOSE_STOP', 0)} CLOSE_STOP. "
                         f"Фактически Jev закрыл {shell['applied_model_review_closures']} проверок.")
            for item in shell["pre_fraud_jev_raw_non_defer_cases"]:
                for receipt in item["pre_fraud_jev_raw_non_defer"]:
                    score = receipt["probabilities"][receipt["decision"]]
                    lines.append(f"- `{item['family']}`. Сырой ответ {receipt['decision']} с вероятностью {percent(score)}. "
                                 f"Выполнено решение {receipt['effective_action']}. {item['reason']}")
    for arm in "DE":
        v = result["arms"][arm]["mandatory_pre_fraud"]
        lines.append(f"- {arm}. Обязательных проверок по сверенным записям {v['receipts']}. "
                     f"Передано штатному маршруту {v['deferred']}. "
                     f"Инструментальное чтение конкретного счёта Fraud наблюдалось в {v['native_fraud_scope_evidence']}.")
    correction = result["structured_review_reconciliation"]
    if correction["revised"]:
        lines += ["", f"Отдельно пересмотрено {correction['revised']} закрытий проверки. "
                  "Добавлены фактические сведения о выполненной проверке и её привязке к счёту. "
                  "Первоначальные метки сохранены в реестре.", ""]
    duties = result["mandatory_duty_reconciliation"]
    if duties["revised"]:
        lines += ["", f"Покрытие обязательных проверок независимо пересмотрено в {duties['revised']} случаях. "
                  "Вызов штатной модели Fraud учитывается отдельно. Процедурная оценка зависит от содержательной "
                  "независимой проверки требования по тому же счёту до платежа.", ""]
    common = result["common_state_de"]
    lines.extend([
        "", f"В D и E восстановлены оба первых входа в {common['states_available_in_both']} семействах. "
        f"При воздержании правил совпал {len(common['families'])} вход с учётом текста поручения. "
        f"Если сопоставлять структурированные данные правил без текста поручения, совпало "
        f"{len(common['matching_structured_state_regardless_of_proposed_wording'])} семейств, "
        f"из них Jev имел право дать оценку в "
        f"{len(common['model_eligible_on_common_structured_state'])}. "
        "Это условное сравнение достигнутой границы.",
        "", "## Повторные исполнения", "",
    ])
    for arm, trial in result["repeats"].items():
        count = len(trial["family_outcomes"])
        lines.append(f"- {arm}. {count} семейств, {trial['attempts']['assigned']} дополнительных назначений. "
                     f"Завершилось {trial['attempts']['states'].get('terminal', 0)}.")
    lines.extend(["", "| Семейство | Ветвь | Прогоны с первой попыткой | Денежное нарушение | Неопределённо | Интервал 95% |",
                  "|---|---|---:|---:|---:|---:|"])
    for arm, trial in result["repeats"].items():
        for row in trial["family_outcomes"]:
            bounds = row["same_family_rate_including_first"]["financial"]
            lo, hi = bounds["conservative_95_interval"]
            lines.append(f"| {row['family']} | {arm} | {bounds['assigned']} | {bounds['observed']} |"
                         f" {bounds['unknown']} | {percent(lo)} … {percent(hi)} |")
    lines.extend(["", "Парная сводка, интервалы по выбранным семьям и построчные исходы доступны в "
                  "[результатах](results.json) и [реестре](assignment_outcomes.json).", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    folder = parser.parse_args().directory
    (folder / "RESULTS.md").write_text(report(live.read(folder / "results.json")))
