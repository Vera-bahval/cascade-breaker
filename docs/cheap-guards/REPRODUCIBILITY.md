# Артефакты и воспроизведение

## Что находится в ветке

`experiments/local_guards` содержит исходники экспериментального стенда, тесты, зависимости, метрики, предсказания и выбранные диагностические материалы. Итоговый текст находится в [главном документе](README.md). Исторические отчёты сохранены как материалы соответствующих серий и могут описывать состояние до исправлений.

Большие JSON, JSONL и CSV сжаты gzip. `PUBLICATION_EXPORT.json` для каждого перенесённого файла хранит исходный хеш, хеш содержимого после обезличивания локальных путей и хеш опубликованного файла. Сжатие детерминированное. Файл `archive-p4-labels.jsonl` содержит минимальное соединение идентификаторов и меток для проверки архивных таблиц; это производный публичный экспорт.

Ветка не содержит токенов авторизации, OAuth-сессий, локальных БД, нативных чатов, весов моделей, полных журналов запросов и бинарных обученных моделей. Лицензии и ограничения исходных моделей сохраняются; доступ к весам оформляется отдельно.

Полный исходный архив коллег не дублируется. Его закреплённый SHA-256 равен `0d16d93500789d716f0b07a2beab64e78af6deea03c072d66133b3480389c504`. Использованный прототип закреплялся на `2476ceb9d88d003ce86e106c7d1644151ec283c1`, FinBot на `a7f6964fbc60da807e2544d826a5b4e20eb0c5dc`. Конкретные model/revision/checksum содержатся в перенесённых runtime-метаданных и исходных заморозках.

## Проверка публикации без моделей и API

Из корня репозитория:

```sh
python3 tools/verify_research_snapshot.py
```

Проверка сверяет опубликованные хеши и заново считает основные результаты по сохранённым предсказаниям и меткам. Никакие запросы к моделям, загрузки весов и повторное обучение не выполняются. Результат независимого первоначального пересчёта сохранён в `results/guard-v2/audit/FINAL_INDEPENDENT_RECOUNT.json`.

Исторические абсолютные пути обезличены как `${ORIGINAL_WORKSPACE}` и `${LOCAL_HOME}`. Старые source-freeze manifest сохраняют исходные хеши и хронологию; использовать их как готовый переносимый валидатор файлов новой ветки нельзя. Для этой публикации действует `PUBLICATION_EXPORT.json` и отдельный `SNAPSHOT.json`.

## Исходный полный стенд

Пакет рассчитан на Python 3.12–3.13. Для ML использовались CatBoost, scikit-learn и отдельное окружение SecJev. Точные версии закреплены lock-файлами. Полный повтор вычислений требует исходного архива, входов, весов и отдельного каталога нового запуска.

```sh
python3 -m venv .venv-research
.venv-research/bin/pip install -e experiments/local_guards
.venv-research/bin/pip install pytest pytest-asyncio
PYTHONPATH=experiments/local_guards .venv-research/bin/python -m pytest experiments/local_guards/tests/test_v2_scoring_recovery.py experiments/local_guards/tests/test_v2_profile_compat.py experiments/local_guards/tests/test_v2_partial_profile_compat.py
```

Эта публикация позволяет проверять сохранённые результаты. Полная повторная сборка старого локального HTML требует дополнительных исходных файлов и прежней структуры каталогов; она не объявляется рабочей командой свежего checkout. Частичные экспорты не заменяются пустыми файлами ради успешного запуска.

Скрипты прежних исполнителей сохраняют старые абсолютные сроки и запреты перезаписи. Их нельзя автоматически перезапускать, сбросив срок. Новая вычислительная серия должна иметь собственные manifest, время и output. Новый живой запуск требует отдельно ограниченного расхода и актуальной проверки доступа.

## Ключевые файлы

| Материал | Расположение относительно `experiments/local_guards` |
|---|---|
| Все итоговые агрегаты | `results/guard-v2/comparison.csv.gz` |
| Основные независимые предсказания | `results/guard-v2/evaluation-v5/independent/predictions.jsonl.gz` |
| Архивные внешние предсказания | `results/guard-v2/evaluation-v5/archive-predictions.jsonl.gz` |
| Новый набор и метки | `results/guard-v2/hidden-test/` |
| Четыре этапа Jev | `results/guard-v2/jev-v5/08/scores.jsonl.gz` |
| Политики и разделение данных | `results/guard-v2/METHOD_FREEZE_05.json`, `SPLIT_PROTOCOL_FREEZE_05.json` |
| Источники задержки | `results/guard-v2/cost-provenance-05.json`, `jev-runtime-provenance-05.json`, `latency-summary-05.json` |
| Чувствительность к контракту | `results/guard-v2/audit/POLICY_UNDERSPEC_SENSITIVITY_SUMMARY_05.json` |
| Свежий контроль шести требований | `results/guard-v2/contract-rules-control/v5/` |
| Пересчёт Jev с LLM | `results/fallback-posthoc/diagnostic.json` |
| Пересчёт rules, Jev и LLM | `results/fallback-posthoc/rules-first.json` |
| Живой запуск Luna | `results/luna-showcase-night/summary.json` |
| Старый 4B | `results/night-4b/` |
| Счётчики разработки rules | `results/night-4b/rules-cost.json` |

Результаты качества и стоимости имеют разные знаменатели и условия замера. Архивные 93 безопасных P4, все 131 безопасное продолжение, 98 исходно честных задач и 120 допустимых действий нового контракта нельзя подменять друг другом.
