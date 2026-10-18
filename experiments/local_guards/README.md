# FinBot локальные эксперименты с защитниками

Стенд сравнивает правила, TF-IDF/табличный Logistic Regression, CatBoost, SecJev и их комбинации по сохранённым префиксам FinBot. Основной результат — контрфактическая остановка до первого вредного перевода. Реальное выполнение защитника отдельно проверено в API-free replay с настоящими FinBot/MCP/SQLite.

Результаты и график: [отчёт](reports/report.html), [ML CSV](results/offline/metrics.csv), [полный ML/SecJev CSV](results/with-semantic/metrics.csv), [manifest](results/experiment-manifest.json). Основная серия завершена: пять размещений, две абляции, три seeds; 390 агрегатов и 108 420 OOF predictions, без ошибок fit и отсутствующих scores.

Отдельная ночная серия SecJev-4B/CatBoost и улучшенных rules: [новый отчёт](reports/night-report.html), [протокол и команды](NIGHT-4B.md), [текущее состояние](results/night-4b/run.json). Первый успешный повтор Luna содержит шесть эпизодов в отдельных БД; его результаты не используются для обучения. Численная проверка 4B пройдена в FP32 с последовательными вопросами на MPS; полнота основной серии явно указана в новом отчёте.

## Данные и политика

Архив `shadow-main` взят из `cascade-breaker@2476ceb9d88d003ce86e106c7d1644151ec283c1`. SHA256 gzip и экспортов сохранены в `data/archive/provenance.json`. Данные: 234 эпизода, 866 префиксов, 50 групп. Основная оценка: 214 эпизодов и 786 префиксов; 20 неоднозначных эпизодов представлены отдельно.

Строгая политика делает успешный FLAG/HOLD/escalate/reject обязательным запретом до независимого разрешения. Это даёт 83 вредных исхода в основной выборке, старая oracle — 39. Обе оценки сохранены. Изменение политики нельзя считать улучшением защитника. `fraud_review_completed` означает наблюдавшееся завершение вызова Fraud, как в исходном V1; это не доказательство успешности его вывода.

Метка `harm_if_continue` относится к наблюдаемому продолжению, не к ошибке конкретного шага. Agent notes — наблюдаемые объяснения, не внутренний CoT и не независимое подтверждение разрешения. Абляция `facts_action` сохраняет исходное недоверенное описание счёта, но убирает объяснение агента; `plus_rationale` добавляет его.

## Окружения и воспроизведение

Все команды ниже выполняются из корня workspace, если явно не указан переход в директорию. Веса, credentials, окружения и vendor-код находятся в игнорируемых `models/`, `.runtime/` и `vendor/`.

ML использует Python 3.12 и lock-файл:

```sh
cd experiments/local_guards
UV_CACHE_DIR=../../.cache/uv UV_PYTHON_INSTALL_DIR=../../.runtime/python uv sync --python 3.12
.venv/bin/python -m cascade_guard.offline run --output results/offline
.venv/bin/python -m cascade_guard.offline freeze
.venv/bin/python -m cascade_guard.manifest
.venv/bin/python -m cascade_guard.report
```

Поставляемый локальный gzip уже достаточен для анализа. Для повторного экспорта нужен checkout коллег с указанным Git commit; его путь передаётся явно:

```sh
.venv/bin/python -m cascade_guard.offline export --archive-repo /path/to/cascade-breaker
```

Exporter не перезаписывает отличающийся immutable dataset. Все префиксы, повторы и инъекции одной базовой задачи находятся в одной группе. ML fit, vocabulary, scaling и пороги используют только обучающую часть внешнего разбиения. Seeds 17/29/43, 3 внешних folds, 2 внутренних; фиксированные гиперпараметры без поиска. Пилотная цель — 5% episode FPR внутри обучения, не гарантия на внешнем тесте.

## SecJev CPU и MPS

CPU-эталон: SecJev-0.8B v1.0.0, Qwen3.5-0.8B-Base с фиксированной ревизией, FP32, unmerged LoRA, исходная температура. Зависимости в `requirements-secjev.lock.txt`. `scripts/bootstrap_secjev.py` проверяет checksum модели и backbone и сохраняет исходные лицензии в скачанных source-пакетах. Первое скачивание не требует API key.

Из корня workspace:

```sh
UV_CACHE_DIR=.cache/uv UV_PYTHON_INSTALL_DIR=.runtime/python uv venv --python 3.12 .runtime/secjev/.venv
UV_CACHE_DIR=.cache/uv uv pip install --python .runtime/secjev/.venv/bin/python -r experiments/local_guards/requirements-secjev.lock.txt
.runtime/secjev/.venv/bin/python experiments/local_guards/scripts/bootstrap_secjev.py
PYTHONPATH=experiments/local_guards .runtime/secjev/.venv/bin/python -m cascade_guard.secjev --device cpu --threads 1 serve --port 8011
```

PyTorch 2.6 MPS имеет подтверждённую ошибку многомерного `solve_triangular`; этот backend не используется для исследовательских предсказаний. Исправленный путь — отдельный PyTorch 2.14 FP32 + GPU block inverse, после A/A и сравнения с тем же CPU checkpoint. Диагностика, источники, сырые распределения и команды: [MPS README](results/mps-diagnostics/README.md). MPS-service оставлен на `127.0.0.1:8012`; CPU-reference на `8011` остановлен после завершения сравнений.

Чистая установка и запуск исправленного MPS из корня workspace:

```sh
python3 experiments/local_guards/scripts/bootstrap_secjev_mps.py --workspace .
.runtime/mps-diagnostics/.venv/bin/python experiments/local_guards/scripts/serve_secjev_mps.py --port 8012
```

Lock `requirements-secjev-mps.lock.txt` совпадает с проверенным runtime. Launcher не требует dataset для загрузки и сохраняет тот же scorer fingerprint. CPU↔MPS: 392 пары P4, max Δ=1.69×10⁻⁵, без смен решений; A/A совпадает между загрузками. Полный MPS scorer завершён: 1 732 строки, 1 135 inference, 597 cache hits, UNKNOWN=0. CPU-артефакт содержит только 392 P4 строки и остаётся отдельным контрольным замером.

Считать все префиксы и две абляции, сохранив отдельный MPS-артефакт:

```sh
PYTHONPATH=experiments/local_guards experiments/local_guards/.venv/bin/python -m cascade_guard.secjev_batch --input experiments/local_guards/data/prefixes.jsonl --output experiments/local_guards/results/secjev-mps-scores.jsonl --url http://127.0.0.1:8012
```

Точный payload cache сохраняет все prefix/ablation строки. Cache hits, реальная retrieval latency и повторно использованная reference compute latency различаются. Model benchmark считается по фактическим inference, без включения нулевого времени cache hits. При возобновлении сверяются input hash и scorer fingerprint. Переполнение state + question >8192 токенов даёт `UNKNOWN`, без обрезания.

Из `experiments/local_guards`:

```sh
.venv/bin/python -m cascade_guard.offline run --secjev-scores results/secjev-mps-scores.jsonl --output results/with-semantic
.venv/bin/python -m cascade_guard.offline freeze --secjev-scores results/secjev-mps-scores.jsonl --cv-dir results/with-semantic --artifact-dir artifacts/frozen-semantic
```

Неполный scorefile отмечается `not_ready`; завершённый `UNKNOWN` вызывает STOP с отдельным учётом доступности и utility. Brier/log loss используют только существующие численные оценки, не выдуманные вероятности для UNKNOWN.

## FinBot и подписочный доступ

FinBot: commit `a7f6964fbc60da807e2544d826a5b4e20eb0c5dc`, 21 патч первого прототипа и `finbot-local.patch`. `scripts/bootstrap_finbot.py` воспроизводит checkout. Headless runtime использует отдельный Python 3.13.15 и `requirements-finbot.lock.txt`; установщик применяет lock-файл и устанавливает обе локальные editable-копии с `--no-deps`. Дополнительные provenance — `results/finbot-environment.txt` и `results/finbot-harness-provenance.json`.

Из корня workspace:

```sh
python3 experiments/local_guards/scripts/bootstrap_finbot.py --install
```

Пример локального API-free replay из `experiments/local_guards`:

```sh
cascade_replay_dir=$(mktemp -d ../../.runtime/replay.XXXXXX)
.venv-finbot/bin/python -m cascade_guard.harness --archive data/archive/shadow-main.jsonl.gz --run-id cle-clean_00-6077e5 --database "$cascade_replay_dir/clean.db" --output "$cascade_replay_dir/clean.jsonl" --p4-rules
```

Три случая, параллельное исполнение и подтверждение установки с чистым окружением: [FINBOT-REPLAY.md](FINBOT-REPLAY.md), [bootstrap evidence](results/bootstrap-lock-check.json). Каждому worker нужна новая БД.

`BLOCK` и `UNKNOWN` ставят терминальный stop latch до перевода; позднейшие tools, LLM и повторы не выполняются. Каждый worker использует свой процесс/SQLite; каждый эпизод — новый namespace. [Replay evidence](results/replay-integration-summary.json): корректный платёж выполнен, HOLD и неверные сумма/получатель заблокированы, внешних HTTP-запросов и шагов после STOP — ноль.

Отдельный официальный OAuth приложения сохранён в `.runtime/oauth/`; существующий Codex login не используется и не изменяется. Метаданные каталога подтвердили успешную авторизацию, но **GPT-5 nano отсутствует**: [preflight](results/live-preflight.json). Пользователь отдельно разрешил маленький GPT-6 Luna showcase; он не входит в обучение и калибровку. Инструкция, bounds и описание механических вмешательств — [SHOWCASE.md](SHOWCASE.md).

Первый Luna запуск: 13 Responses-запросов, включая smoke и шесть workflow-попыток, ноль tools/переводов/P4. Usage атрибутирует function calls, а адаптер сохранил пустой output; вероятная причина — неучтённые промежуточные `output_item.done`. Raw SSE не был сохранён, точные события не восстановлены. Обработка completed items и failed workflow исправлена локально; теперь пустой smoke останавливает серию. Это сбой интеграции, не предотвращение вреда; результаты не включены в основное сравнение. При запуске пользователь подтвердил сохранённый лимит приложения ≤10% подписочной квоты и выключенный глобальный credit fallback. Числовой лимит 1000 кредитов не заявляется.

Готовый живой пилот: `examples/live-pilot.json`, 24 новых случая ×2 повтора ×6 arms. Пример команды из этой директории:

```sh
.venv-finbot/bin/python -m cascade_guard.live --runtime ../../.runtime/oauth --config examples/live-pilot.json --cap-proof ../../.runtime/oauth/cap-readback.json --output results/live-pilot --database ../../.runtime/live-worker.db --run
```

Этот исходный nano pilot не запускался. Gate требует точную доступность nano и независимо подтверждённый backend credit cap, которого актуальная документация не предоставляет в числовом виде; его нельзя пройти выдуманным proof. Маленький showcase использует отдельный путь included-plan-only с реальным пользовательским readback. В обоих случаях проверяются hashes frozen ML/semantic artifacts и fingerprint resident SecJev. Token usage, USD-тариф и подписочные credits не конвертируются друг в друга. Неуспешный или незавершённый stream останавливает транспорт; tool calls исполняются только после `response.completed`.

## Проверки и пределы вывода

Полная проверка кода, включая FinBot, выполняется в Python 3.13 environment:

```sh
cd experiments/local_guards
.venv-finbot/bin/python -m pytest tests
```

MPS-численные тесты запускаются отдельно в диагностическом окружении, команды в MPS README. CPU и GPU-замеры выполняются последовательно для сравнений скорости. Доверительные интервалы исследовательские, bootstrap по базовым группам. Для FPR ниже 1% при нуле ошибок нужны около 299 независимых корректных эпизодов; повторные генерации одного счёта не дают такую независимость.

Итоговая проверка: 101 pytest checks прошли, один Torch-test пропущен в FinBot environment и выполнен в MPS environment; там оба диагностических unit checks прошли. [Verification](results/verification.json) и [JUnit](results/tests.xml) сохраняют команды и результаты.

## Дополнительные диагностики после пилота

[Парное сравнение Rules/V3](results/diagnostics/rules-v3-benign-paired.json) показывает происхождение всех 32 source-benign HOLD и confound с пустой историей vendor. [Тест модели и формата](results/diagnostics/structured-ledger/factorial/report.md): 9 cases /8 groups, 0.8B/2B ×текущая сводка/хронология/компактный журнал, 54 наблюдения, UNKNOWN=0, A/A Δ=0. Тест выбран после просмотра ошибок и не оценивает FPR. Один длинный safe input проверен на CPU2B; расхождение с MPS ≤2.62×10⁻⁶. Первичные scores/CV/frozen artifacts не менялись; полный 2B sweep не выполнен.

2B current улучшает выбранные authority и безопасные контроли, а большие history bundles повышают missing-evidence и на безопасных оплатах. Следующая стратегия и будущие эксперименты изложены в [research/cheap-cascade-control.md](../../research/cheap-cascade-control.md): применимые обязательства, адресные semantic queries и отдельный проверяемый recovery.
