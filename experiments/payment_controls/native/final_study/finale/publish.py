"""Build the standalone team graphic from the sealed primary analysis and reviewed notes."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = dict(A="Штатный FinBot", B="Jev перед поручением", C="Jev перед переводом",
            D="Правила, затем Fraud", E="Правила, Jev, затем Fraud")


def read(name):
    return json.loads((HERE / name).read_text())


def number(value, digits=0):
    return "—" if value is None else f"{value:.{digits}f}".replace(".", ",")


def count(item):
    known = item["adverse"] + item["acceptable"]
    return f"{item['adverse']} / {known}"


def assemble(corrected=False):
    data = read("highlights.json")
    original = read("review/results.json")
    live = read("correction/policy/results.json") if corrected else original
    archive = read("p4/summary.json")
    labels = archive["as_of_labels"]
    assert sum(labels.values()) == archive["strict_heldout_target"] == 1261
    data["recovered"] = [(k, labels.get(k, 0)) for k in ("ALLOW", "BLOCK", "REVIEW", "INSUFFICIENT")]
    assignments = read("review/assignment_outcomes.json")
    assert len(assignments) == 1297 and all(row["review"] == "sealed" for row in assignments)
    assert live["primary_families"] == 221
    direct = read("../paired_guard/results.json")["binary_stop_by_gold"]
    data["headtohead"] = [["Как выбирали ответ", "Замечено из 25 проблем", "Пропущено проблем", "Ошибочно остановлено из 100 допустимых"]]
    for title, method in [("Jev, собственный ответ", "jev"), ("DeepSeek Flash, собственный ответ", "eliza"),
                          ("Jev, порог остановки 0,97", "jev_threshold")]:
        caught = direct["1"][method]
        data["headtohead"].append([title, caught, 25 - caught, direct["0"][method]])
    prefraud = read("panel/low-probability.json")["groups"]["heldout_E_14"]
    data["lowprobs"] = [["Как решаем", "Верно закрыли из 10", "Ошибочно закрыли из 4", "Верно передали из 4", "Лишних расследований из 10"]]
    policies = [("Собственный ответ модели", prefraud["raw"])] + [
        ("Порог " + number(t, 2), prefraud["override_allow"][str(t)])
        for t in (.9, .52, .5, .45, .4, .35, .3)]
    for label, counts in policies:
        data["lowprobs"].append([label, counts["correct_close"], counts["incorrect_close"], counts["correct_defer"],
                                10 - counts["correct_close"]])
    groups = live["arms"]
    data["targetstops"] = [["Где спросили Jev", "Всего решений", "Требовалось вмешаться", "Верных остановок", "Пропущено проблем", "Ложных остановок"]]
    for arm, title in [("B","Перед поручением Payments"), ("C","Перед переводом FinStripe")]:
        level = groups[arm]["action_level"]
        stopped = level["outcomes"].get("must_stop_or_review_stop", 0)
        missed = level["missed_action_problems"]
        data["targetstops"].append([title, sum(level["outcomes"].values()), stopped+missed, stopped, missed, level["false_positive_actions"]])

    outcomes = [["Ветвь", "Назначено", "Полная трасса", "Денежное нарушение / известно",
                 "Нарушение в письме / известно"]]
    costs = [["Ветвь", "Полная цена, USD", "Время p50, с", "Время p95, с", "Задач с ценой"]]
    false = [["Версия", "Задач для оценки", "Наблюдали ложную остановку", "Исход неизвестен", "Верхняя граница частоты (95%)"]]
    for arm, title in ARMS.items():
        v = groups[arm]
        name = f"{arm} · {title}"
        outcomes.append([name, v["assigned"], v["states"].get("terminal", 0),
                         count(v["outcomes"]["financial"]), count(v["outcomes"]["notification"])])
        cost = v["resources"]["total_cost_usd"]
        elapsed = v["resources"]["elapsed_seconds"]
        costs.append([name, number(cost["mean"], 6), number(elapsed["median"], 1),
                      number(elapsed["p95"], 1), cost["n"]])
        f = v["false_stop_bounds"]
        false.append([name, f["eligible_source_tasks"], f["observed"], f["unknown"],
                      number(f["upper_95_worst_case"] * 100, 1) + "%"])
    data["live"] = {"Исходы": outcomes, "Стоимость и время": costs, "Ложные остановки": false}
    data["pairs"] = [["Ветви", "Определено пар", "Нарушение только в первой",
                      "Нарушение только во второй", "Неизвестно", "Δ цены задачи, USD", "Δ времени, с"]]
    data["forest"] = []
    for key in ("B-C", "B-A", "C-A", "E-D", "E-A"):
        f = live["pairs"][key]["endpoint"]["financial"]
        known = f["complete_pairs"]
        resources = live["pairs"][key]["resource_delta"]
        data["pairs"].append([key, known, f["treatment_only"], f["comparator_only"], f["unknown_pairs"],
                              number(resources["total_cost_usd"]["mean"], 6), number(resources["elapsed_seconds"]["mean"], 2)])
        lo, hi = f["conservative_95_interval"]
        est = (f["treatment_only"] - f["comparator_only"]) / known if known else None
        data["forest"].append([key, 100*lo, 100*hi, None if est is None else 100*est])
    archived = read("panel/historical-p1-metrics.json")["threshold_response"]
    comparison = {r["arm"]: r for r in archived if r["threshold"] == 0.97}
    variants = {
        "action_policy": "Поручение и политика",
        "records": "+ структурированные записи",
        "fraud": "+ отдельное заключение Fraud",
        "prose": "Те же сведения в тексте",
        "direct": "Те же сведения, прямой вопрос",
        "masked": "Убрано решающее свидетельство",
    }
    data["input"] = [["Пакет P1 при 0,97", "Обнаружено / требовалась проверка", "Ложные остановки / допустимые"]]
    for key, label in variants.items():
        item = comparison[key]
        data["input"].append([label, f"{item['detected']} / {item['known_intervention']}",
                              f"{item['false_stops']} / {item['known_safe']}"])
    curve = {}
    for key, variant, label in (("historical-p1", "records", "P1 · поручение и записи"),
                                ("historical-p4-wide", "scoped", "P4 · восстановленные сведения")):
        metrics = read(f"panel/{key}-metrics.json")
        for row in metrics["threshold_response"]:
            if row["arm"] == variant:
                view = curve.setdefault(str(row["threshold"]), [["Граница", "Распознано / проблемных", "Ложно остановлено / допустимых"]])
                view.append([label, f"{row['detected']} / {row['known_intervention']}",
                             f"{row['false_stops']} / {row['known_safe']}"])
    data["curve"] = curve
    data["reps"] = [["Счёт", "Версия FinBot", "Назначений с первым", "Денежных нарушений", "Неизвестно"]]
    case_names = {"TH614":"Аренда камер и света по договору со старыми датами",
                  "TH634":"Прокат операторской тележки, крана и генератора",
                  "clean_32":"Восемь комплектов средств защиты",
                  "clean_33":"Подшипники и ремни для конвейера"}
    for arm, s in original["repeats"].items():
        for row in s["family_outcomes"]:
            o = row["same_family_rate_including_first"]["financial"]
            data["reps"].append([case_names[row["family"]], ARMS[arm], o["assigned"], o["observed"], o["unknown"]])
    return data


def main():
    from corrected_view import decorate
    data = decorate(assemble(corrected=True))
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    template = (HERE / "team_report.html.in").read_text()
    assert template.count("__DATA__") == 1
    (HERE / "FINBOT_TEAM.html").write_text(template.replace("__DATA__", payload))


if __name__ == "__main__":
    main()
