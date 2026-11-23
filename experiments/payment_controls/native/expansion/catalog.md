# Опись дополнительных источников FinBot

У дополнительных каталогов найдено 40 отдельных счетов с авторским PAY и один демонстрационный PAY, совпадающий с Unified V1. У всех 41 есть записи прежнего исследования. Подтверждённых дополнительных независимых проблемных обязательств для закрытого прогона по этой описи **0**. Верхняя граница открытого holdout на начало текущего продолжения остаётся **16**. Из них 12 проверяют статус поставщика, ещё четыре требуют независимого разбора.

| Источник | Что нашлось | Вклад в закрытую оценку |
| --- | --- | --- |
| Unified | 1 243 определения из 262 исходных групп. Предыдущая опись перечисляет профильные варианты и отдельные генераторы. | 0 новых допущенных групп. |
| Источники FinBot477 | Девять файлов текущего checkout и два исходных шард-файла из соседнего checkout. Все ID входят в Unified после снятия повтора и учёта alias. Единственный ID, которого нет в основном поле, — `S15000-base`. Это явный alias `sweep:S15000-base` у `P15000-base@B`. | 0 дополнительных исходных счетов. |
| Vendor clean, seed 20261004 | 40 уникальных ID и 40 разных сочетаний суммы и текста. По обоим ключам совпадений с легитимными записями Unified нет. Все 40 ожидают PAY по авторскому эталону. У 12 авторская метка hard negative для детектора. | Все 40 ID есть в трёх наборах записей предыдущего исследования. Подходят для открытой проверки сохранения легитимных платежей. |
| Vendor cascade demos | Семь демонстрационных записей. Единственный явный обычный положительный пример `baseline_clean` совпадает по сумме и тексту с Unified V1 и встречается во всех трёх наборах прежнего исследования. Три служебных ID из security-каталога также встречаются во всех трёх наборах. | 0 дополнительных кандидатов. |
| Runner | Семь имён в рабочем checkout и в истории YAML/JSON. Пять входили в прошлый checkpoint. Две оставшиеся записи проверяют технический отказ Payments и повтор чата. | 0 новых проблемных договорных обязательств. |
| API-MAST и встроенный CTF | 68 определений API-MAST для 34 исходных ID и 19 записей встроенного CTF в описи checkpoint. Историческое переименование YAML/JSON сохранило ID. | Метаданные этих наборов учитываются в инвентаре. Закрытых договорных эталонов по ним не установлено. |
| Fixtures текущего исследования | 8 основных, 12 из mechanism study и 16 из overnight. | Фикстуры открытых экспериментов. |

Совпадение ID в структурированном артефакте устанавливает, что строку уже обрабатывали в исследовании. Это свидетельство об исходном счёте, а не о том, что конкретный человек видел каждый вариант. Пустой результат поиска сам по себе не устанавливал бы закрытость. Для сравнения содержимого обычных счетов использовали сумму и текст после удаления крайних пробелов, чтобы исключить повтор одного счёта при смене ID, профиля или канала. Это точная сверка, которая не выявляет близкие переформулировки.

## Проверенные ветки

Проверены семь рабочих деревьев Cascades и отдельный `vendor/finbot`, история локальных refs, деревья всех 15 веток `Vera-bahval/cascade-breaker`, две ветки исходного `GenAI-Security-Project/finbot-ctf` и три ветки связанного `Vera-bahval/finbot-ctf`. У `cascade-breaker` GitHub показал 0 форков. Источник `experiments/finbot-probe/data/cascade_clean_scenarios.json` в `research/first-prototype` совпадает побайтно с vendor-файлом, Git blob `9b569b7f08125a8d21c27622eebf5da64598c973`. Из деревьев исходного FinBot среди имён scenario, fixture, catalog, dataset и seed встретился `seed_analytics.py`. Скрипт создаёт данные аналитики. В связанной ветке `cascading_failures` найден тот же каталог демонстраций `cascade_scenarios.json`.

| Репозиторий | Проверенные ветки и SHA |
| --- | --- |
| `Vera-bahval/cascade-breaker` | `codex/finbot-four-model-report` 21ffcf1, `codex/mast-second-annotation` 12457d1, `fix/cascade-defects` a0f8f53, `main` e0251c8, `report/checkpoint-2` 4c7638c, `research/api-mast-scenarios` c55b66f, `research/cheap-guards-results-2026-10-18` ec93a1b, `research/control-placement` f461f24, `research/control-placement-guard` e2f4334, `research/finbot-payment-cascade-study` e94bb9e, `research/first-prototype` 2476ceb, `research/general-guards-v3-2026-10-31` 1e30ab8, `research/no-llm-v4-followup` be2b10d, `research/scenario-runs` 3d40277, `research/unified-scenarios` a825b0c. |
| `GenAI-Security-Project/finbot-ctf` | `main` 1450fc4, `labs/guardrails` 76c5b3b. |
| `Vera-bahval/finbot-ctf` | `main` 83e97a8, `cascading_failures` a7f6964, `feature/cascading_failures` 41547b6. |

## Воспроизведение

Из корня `cascade-breaker-publication`:

```sh
python3 experiments/payment_controls/native/expansion/catalog.py |
  diff -u experiments/payment_controls/native/expansion/catalog.json -
git worktree list
git log --all --format= --name-only -- scenarios
git ls-remote --heads https://github.com/Vera-bahval/cascade-breaker.git
git ls-remote --heads https://github.com/GenAI-Security-Project/finbot-ctf.git
git ls-remote --heads https://github.com/Vera-bahval/finbot-ctf.git
```

Удалённые деревья проверялись с помощью `git ls-tree -r` в отдельном bare clone или через GitHub API `/repos/{owner}/{repo}/git/trees/{sha}?recursive=1`. В `catalog.json` сохранены состав, счётчики по каждому файлу и SHA-256 локальных входов. Закрытые исходы и вызовы провайдеров не использовались.
