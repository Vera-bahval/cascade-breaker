"""Build an offline, curator-admitted corpus; never import an executor or provider.

Private curation decisions and source cases stay outside the repository. Rebuild:
  python corpus.py --banks-root PATH --plan PATH --output PATH \
      --manifest corpus_manifest.json --report CORPUS.md
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path


BANKS = ("a2", "a3", "a4", "b2", "b3", "b4", "b5")
CHANNELS = ("direct", "portal", "chat", "onboarding")
PRESETS = {"p120_96": (120, 96), "p100_80": (100, 80), "p80_64": (80, 64)}
PAYLOAD_FIELDS = ("policy", "basis", "record", "trusted_test")
OUTCOMES = {"ALLOW": "pay", "BLOCK": "stop", "REVIEW": "review"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def lines(rows):
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def csv_text(rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=("case", "channel", "split"))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write(path, content, *, immutable=False, private=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists() and path.read_bytes() != content.encode():
        raise ValueError(f"Frozen calibration artifact changed: {path.name}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content)
    if private:
        temporary.chmod(0o600)
    temporary.replace(path)


class Groups:
    def __init__(self, keys):
        self.parent = {key: key for key in keys}

    def find(self, key):
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def merge(self, keys):
        root = min(self.find(key) for key in keys)
        for key in keys:
            self.parent[self.find(key)] = root


def choose(groups, decisions, wanted_allow, wanted_problem, seed):
    """Exact quota selection, at most one row in each dependency group."""
    if wanted_allow + wanted_problem > len(groups):
        return None
    states = {(0, 0): ()}
    ordered = sorted(groups.items(), key=lambda item: digest([seed, item[0]]))
    for _, keys in ordered:
        # Only the first deterministic representative of each class is needed.
        options = {}
        for key in sorted(keys, key=lambda key: digest([seed, "representative", key])):
            options.setdefault(decisions[key]["step"] == "ALLOW", key)
        updated = dict(states)
        for (allow, problem), selected in states.items():
            for is_allow, key in options.items():
                state = (allow + int(is_allow), problem + int(not is_allow))
                if state[0] <= wanted_allow and state[1] <= wanted_problem:
                    updated.setdefault(state, selected + (key,))
        states = updated
    return states.get((wanted_allow, wanted_problem))


def maximum(groups, decisions, seed):
    minimum_allow = sum(all(decisions[key]["step"] == "ALLOW" for key in keys)
                        for keys in groups.values())
    maximum_allow = sum(any(decisions[key]["step"] == "ALLOW" for key in keys)
                        for keys in groups.values())
    count = len(groups)
    target = max(minimum_allow, min(maximum_allow, round(count * 80 / 144)))
    selected = choose(groups, decisions, target, count - target, seed)
    assert selected is not None and len(selected) == count
    return selected


def schedule(keys, cases, split):
    # Neither original bank/channel/order nor gold is used in the reassignment.
    ordered = sorted(keys, key=lambda key: text_hash("channel-v1" + cases[key]["case"]))
    return [{"case": cases[key]["case"], "channel": CHANNELS[index % len(CHANNELS)], "split": split}
            for index, key in enumerate(ordered)]


def ordered_inputs(keys, cases):
    return [cases[key] for key in sorted(keys, key=lambda key: text_hash("order-v1" + cases[key]["case"]))]


def self_check():
    decisions = {"a": {"step": "ALLOW"}, "b": {"step": "BLOCK"},
                 "c": {"step": "REVIEW"}, "d": {"step": "ALLOW"}}
    groups = {"paired": ["a", "b"], "single": ["c"], "last": ["d"]}
    result = choose(groups, decisions, 1, 2, "test")
    assert result is not None and set(result) == {"b", "c", "d"}
    assert choose(groups, decisions, 2, 2, "test") is None
    assert len(maximum(groups, decisions, "test")) == 3
    assert schedule(["x"], {"x": {"case": "Qopaque"}}, "cal") == [
        {"case": "Qopaque", "channel": "direct", "split": "cal"}]


def build(args):
    self_check()
    plan = json.loads(args.plan.read_text())
    if tuple(plan["banks"]) != BANKS or set(plan["excluded_banks"]) != {"a", "b"}:
        raise ValueError("Unexpected bank admission list")
    for name, expected in plan["source_sha256"].items():
        path = args.banks_root / name
        if path.parts[-2] not in BANKS or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Curator source receipt changed: {name}")
    original = {}
    creator_references = {}
    independent_references = {}
    independent_ratings = {}
    for bank in BANKS:
        source = args.banks_root / bank
        for name in ("cases.jsonl", "gold.jsonl"):
            if f"{bank}/{name}" not in plan["source_sha256"]:
                raise ValueError("Missing mandatory source receipt")
        gold = {row["family"]: row for row in read_rows(source / "gold.jsonl")}
        rating_paths = sorted(source.glob("ratings_*.jsonl"))
        if any(f"{bank}/{path.name}" not in plan["source_sha256"] for path in rating_paths):
            raise ValueError("New independent rating requires curator re-admission")
        ratings = [read_rows(path) for path in rating_paths]
        if not ratings:
            raise ValueError(f"No independent rating: {bank}")
        independent_ratings[bank] = len(ratings)
        for row in read_rows(source / "cases.jsonl"):
            key = bank + "/" + row["family"]
            if key in original or row["family"] not in gold:
                raise ValueError("Duplicate source identity or missing gold")
            if any(sum(r["family"] == row["family"] for r in rating) != 1 for rating in ratings):
                raise ValueError("Independent rating coverage mismatch")
            original[key] = row
            creator_references[key] = gold[row["family"]]
            independent_references[key] = {
                path.name: next(r for r in rating if r["family"] == row["family"])
                for path, rating in zip(rating_paths, ratings)}
    decisions = plan["adjudications"]
    if set(original) != set(decisions):
        raise ValueError("Curator plan must account for every source row")
    if any(row["step"] not in ("ALLOW", "BLOCK", "REVIEW") or not row["evidence"]
           for row in decisions.values()):
        raise ValueError("Invalid adjudicated reference")

    lineage = defaultdict(list)
    for key, row in original.items():
        lineage[(key.split("/")[0], row["lineage"])].append(key)
    union = Groups(original)
    for keys in lineage.values():
        union.merge(keys)
    for dependency in plan["dependency_groups"]:
        union.merge(dependency["members"])
    cal = tuple(plan["calibration_keys"])
    if len(cal) != 16 or len({union.find(key) for key in cal}) != 16:
        raise ValueError("Calibration must contain16 distinct dependency groups")
    if any(key.split("/")[0] not in ("a2", "b2") or decisions[key]["exclude"] for key in cal):
        raise ValueError("Invalid calibration selection")
    cal_groups = {union.find(key) for key in cal}
    test_groups = defaultdict(list)
    lineage_only = defaultdict(list)
    cal_lineages = {(key.split("/")[0], original[key]["lineage"]) for key in cal}
    for key, row in original.items():
        source_lineage = (key.split("/")[0], row["lineage"])
        if decisions[key]["exclude"]:
            continue
        if source_lineage not in cal_lineages:
            lineage_only[source_lineage].append(key)
        if union.find(key) not in cal_groups:
            test_groups[union.find(key)].append(key)

    cases = {}
    for key, row in original.items():
        payload = {field: row[field] for field in PAYLOAD_FIELDS if field in row}
        cases[key] = {"case": "Q" + digest(payload)[:16], **payload}
    maximum_keys = maximum(test_groups, decisions, plan["seed"])
    selected = {"max": maximum_keys}
    candidates = {}
    alternative = {}
    # Candidate identity binds sources/curation/selection; verification-code changes
    # are recorded separately and do not rename identical experimental packets.
    fingerprint = digest(plan)
    for preset, (allow, problem) in PRESETS.items():
        keys = choose(test_groups, decisions, allow, problem, plan["seed"])
        alternative[preset] = choose(lineage_only, decisions, allow, problem, plan["seed"]) is not None
        candidate = "corpus-" + preset + "-" + digest([fingerprint, preset, keys])[:16]
        candidates[preset] = {"candidate_id": candidate, "required_allow": allow,
                              "required_problem": problem, "ready": keys is not None,
                              "schedule": f"schedule.{preset}.csv" if keys is not None else None,
                              "available_dependency_groups": len(test_groups),
                              "reason": None if keys is not None else "Insufficient independent curated groups or class composition"}
        if keys is not None:
            selected[preset] = keys
    chosen_preset = next((preset for preset in PRESETS if candidates[preset]["ready"]), "max")
    all_test = tuple(dict.fromkeys(key for keys in selected.values() for key in keys))
    all_keys = cal + all_test
    ids = [cases[key]["case"] for key in all_keys]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate or colliding neutral input identity")
    reference_audit = {}
    for key in all_keys:
        reference = decisions[key]
        comparisons = {"creator": creator_references[key], **independent_references[key]}
        audit = {}
        for origin, row in comparisons.items():
            if row.get("outcome") != OUTCOMES.get(row.get("step")):
                raise ValueError(f"Source step/outcome mismatch requires curator repair: {origin}")
            agrees = (row["step"], row["outcome"]) == (reference["step"], OUTCOMES[reference["step"]])
            if not agrees and reference["status"] != "curator_evidence_adjudication":
                raise ValueError("Unreconciled creator or independent-rater disagreement")
            audit[origin] = {"step": row["step"], "outcome": row["outcome"],
                             "step_outcome_consistent": True, "agrees_with_curator": agrees}
        reference_audit[key] = {"case": cases[key]["case"], "sources": audit,
                                "curator_step": reference["step"], "curator_outcome": OUTCOMES[reference["step"]],
                                "explicit_reconciliation": reference["status"] == "curator_evidence_adjudication",
                                "evidence": reference["evidence"]}

    def reference_summary(keys):
        summary = defaultdict(Counter)
        reconciled_cases = 0
        for key in keys:
            row = reference_audit[key]
            disagreement = False
            for origin, source in row["sources"].items():
                summary[origin]["records"] += 1
                summary[origin]["step_outcome_mismatches"] += int(not source["step_outcome_consistent"])
                summary[origin]["disagrees_with_curator"] += int(not source["agrees_with_curator"])
                disagreement |= not source["agrees_with_curator"]
            reconciled_cases += int(disagreement and row["explicit_reconciliation"])
        return {"curated_records": len(keys), "curator_step_outcome_mismatches": 0,
                "by_source": dict(summary), "explicitly_reconciled_cases": reconciled_cases,
                "unreconciled_cases": 0}
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.chmod(0o700)
    artifacts = {}

    def emit(name, content, immutable=False):
        write(args.output / name, content, immutable=immutable)
        artifacts[name] = text_hash(content)

    emit("inputs.cal.jsonl", lines(ordered_inputs(cal, cases)), True)
    emit("schedule.cal.csv", csv_text(schedule(cal, cases, "cal")), True)
    emit("inputs.test.jsonl", lines(ordered_inputs(selected[chosen_preset], cases)))
    emit("inputs.jsonl", lines(ordered_inputs(cal + selected[chosen_preset], cases)))
    for name, keys in selected.items():
        emit(f"schedule.{name}.csv", csv_text(schedule(cal, cases, "cal") + schedule(keys, cases, "test")))
        emit(f"inputs.{name}.jsonl", lines(ordered_inputs(cal + keys, cases)))
        assert len({union.find(key) for key in keys}) == len(keys)
        assert not {union.find(key) for key in keys} & cal_groups
    private_gold = [{"case": cases[key]["case"], "step": decisions[key]["step"],
                     "outcome": OUTCOMES[decisions[key]["step"]],
                     "evidence": decisions[key]["evidence"], "source_bank": key.split("/")[0],
                     "source_family": original[key]["family"], "source_lineage": original[key]["lineage"],
                     "dependency_group": union.find(key), "split": "cal" if key in cal else "test"}
                    for key in all_keys]
    chosen_ids = {cases[key]["case"] for key in cal + selected[chosen_preset]}
    emit("gold.private.jsonl", lines(row for row in private_gold if row["case"] in chosen_ids))
    emit("gold.all.private.jsonl", lines(private_gold))
    emit("reference_audit.private.jsonl", lines(reference_audit[key] for key in all_keys))
    exclusions = [{"source": key, "reason": row["exclude"]} for key, row in decisions.items() if row["exclude"]]
    emit("exclusions.private.jsonl", lines(exclusions))
    emit("selection.private.json", json.dumps({"selection": selected, "cal": cal,
         "dependency_groups": plan["dependency_groups"]}, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    count = lambda keys: dict(Counter(decisions[key]["step"] for key in keys))
    by_channel = defaultdict(Counter)
    neutral_to_key = {cases[key]["case"]: key for key in all_keys}
    for row in schedule(selected[chosen_preset], cases, "test"):
        by_channel[row["channel"]][decisions[neutral_to_key[row["case"]]]["step"]] += 1
    manifest = {"version": 1, "candidate_id": "corpus-max-" + digest([fingerprint, maximum_keys])[:16],
                "closed_run_results_read": False, "new_inference_calls": 0,
                "empirical_contract_origin_verified": False,
                "readiness_scope": "Corpus counts under explicit synthetic lineage/dependency grouping; channel acceptance is separate",
                "source_banks": list(BANKS), "excluded_banks": ["a", "b"],
                "source_sha256": plan["source_sha256"], "curation_sha256": digest(plan),
                "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "raw_rows": len(original), "declared_lineages": len(lineage),
                "excluded_rows": len(exclusions),
                "entirely_excluded_lineages": sum(all(decisions[key]["exclude"] for key in keys) for keys in lineage.values()),
                "cal_lineages": len(cal), "cal_counts": count(cal),
                "test_lineage_only_upper_bound": len(lineage_only),
                "test_dependency_groups": len(test_groups), "maximum_counts": count(maximum_keys),
                "selected_preset": chosen_preset, "selected_counts": count(selected[chosen_preset]),
                "reference_validation": {"selected": reference_summary(cal + selected[chosen_preset]),
                                         "maximum": reference_summary(cal + maximum_keys)},
                "selected_channel_counts": dict(by_channel), "candidates": candidates,
                "lineage_only_preset_feasibility": alternative,
                "independence_level": plan["independence"], "scope": plan["scope"],
                "reviewer_count_by_bank": independent_ratings,
                "private_artifacts_sha256": artifacts,
                "schedule_columns": ["case", "channel", "split"]}
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    write(args.output / "manifest.json", encoded)
    write(args.manifest, encoded, private=False)
    report = ["# Кураторский допуск корпуса", "",
              f"Сборка `{manifest['candidate_id']}` не читает closed run results и не выполняет inference.", "",
              f"Из {len(original)} строк получено {len(lineage)} заявленных lineage. Исключены {len(exclusions)} строк; целиком потеряны {manifest['entirely_excluded_lineages']} lineage. CAL:16 независимых по принятой группировке единиц a2/b2. TEST: верхняя оценка только по lineage — {len(lineage_only)}, после группировки соседних шаблонов — {len(test_groups)}.", "",
              "| Пресет ALLOW / проблемные | Готов | Candidate | Schedule |", "|---|---|---|---|"]
    for preset, item in candidates.items():
        report.append(f"| {item['required_allow']} / {item['required_problem']} | {'да' if item['ready'] else 'нет'} | `{item['candidate_id']}` | `{item['schedule'] or 'не создан: недостаточный пул'}` |")
    report.extend(["", f"Выбран `{chosen_preset}`: {count(selected[chosen_preset])}. Максимальный допустимый пул: {count(maximum_keys)}. CAL schedule: `schedule.cal.csv`; формат всех расписаний: `case,channel,split`.", "",
                   "Входы содержат только нейтральный case ID и policy/basis/record/optional trusted_test. Исходные IDs, lineage, split, channel, gold и порядок автора не передаются модели. ID получен из digest содержимого, порядок и каналы назначены отдельными label-independent перестановками. Каналы не увеличивают число независимых единиц.", "",
                   "Группировались явные парные lineage, документированные общие источники и соседние шаблоны: один lab protocol по согласованному sample/batch с заменённым материалом; проверка всех отрегулированных единиц с заменённым объектом; одинаковая приёмка royalty report; отсутствующая финальная проверка монтажа. Один лишь op ge/eq/le не являлся причиной объединения. Печать, лабораторная услуга, право использования и монтаж могут использовать одну операцию при различных договорных основаниях.", "",
                   "Альтернативный подсчёт только по заявленным lineage показывает верхний потолок, но игнорирует эти зависимости; он не выбран для основного результата. Более широкое объединение по механизму ещё сократит пул, однако одинаковый механизм сам по себе не доказывает один источник. Уникальный номер или переименованный заказ не доказывает независимое происхождение. Внешняя эмпирическая проверка договоров отсутствует: это специально созданные синтетические случаи с кураторской группировкой, не доказанная выборка независимых реальных клиентов.", "",
                   "Точные потери:64 парных варианта сверх одной строки на исходный lineage;12 исключённых строк, из которых4 lineage теряются целиком. В12 входят6 отрицательных contains без явной полноты списка,2 варианта неоднозначного exact/minimum у лицензии,2 условия проверки без требования успешного результата,1 plan versus as-built и1 противоречащий возвращённый deposit. После CAL остаётся180 заявленных TEST lineage; группировка соседних шаблонов и связанных источников уменьшает их ещё на32 до148. Выбор80/64 оставляет4 запасные единицы. Смысловые расхождения, разрешённые по первичному тексту, записаны только в отдельный private gold; исходные author gold и ratings не перезаписывались. Общая сумма480 USD и схожая языковая оболочка ограничивают разнообразие.", "",
                   "Допуск относится к локальному договорному основанию при прочих независимо подтверждённых предпосылках. Он не доказывает правильную сумму/получателя, отсутствие дубля и аутентификацию из одного текста. Эти поля и исполнительный эффект проверяются live harness в mock среде отдельно. Все четыре channel значения в schedule являются назначениями, а не свидетельством готовности канала или успешного живого исполнения.", "",
                   "CAL зафиксирован до запусков подвыборки. Код, private curation plan и hashes источников позволяют пересобрать те же inputs/gold/schedules. Частные артефакты хранятся во внешнем study-corpus; в репозитории опубликованы только этот санитарный отчёт, инструмент и manifest.", ""])
    write(args.report, "\n".join(report), private=False)
    print(json.dumps({key: manifest[key] for key in ("candidate_id", "raw_rows", "declared_lineages", "test_dependency_groups", "selected_preset", "selected_counts")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banks-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    build(parser.parse_args())
