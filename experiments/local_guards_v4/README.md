# Local guards v4

Исследовательский профиль FinBot, включаемый явно; по умолчанию выключен.
Основной русский отчёт: [REPORT.md](REPORT.md). Контракт: [POLICY.md](POLICY.md),
реестр: [policy.json](policy.json), вход: [schema.json](schema.json).

## Что сохранено

- `guard.py`, `store.py`, `runtime.py`: детерминированные проверки, отдельная SQLite-БД доказательств/активных задач, адаптер настоящих путей FinBot.
- `finbot/finbot/probe/v4.py` и небольшие изменения чата, runner, callable/MCP и model hooks: перехват и распространение STOP. Публичные HTTP API и UX сохранены.
- `data/`: найденные архивы, сгруппированные эпизоды, наблюдения до действия, независимая разметка, TRAIN/CAL и контрольные суммы.
- `results/methods-final.json`, `frozen-methods.json`, `calibration.json`: заморозка до нового теста; конфигурация A на CAL не выбрана.
- `results/*predictions.jsonl.gz` и receipts: исходные решения всех 23 конфигураций до чтения соответствующего gold.
- `closed/`: новая синтетическая проверка контракта. Её автору доступны только контракт и схема; данные не являются новыми реальными атаками на LLM.
- `results/*evaluation/`: эпизодные результаты, общие и достигшие точки знаменатели, групповые интервалы; P5 без зачёта предотвращения.
- `results/native-untraced.json`: 32 сценарных native-теста, 148 полных проверок, их наблюдения/результаты и локальные задержки без tracemalloc.
- `results/reconciled-retry.json`: дополнительный настоящий запуск после явно подтверждённого отсутствия эффекта и освобождения claim.
- `results/api-mast-coverage.json`: открытый каталог всех 48 сценариев, без заявления об исполнении атак.
- Отчёты авторов/ревью и журналы чтений: процедурная изоляция и её известное нарушение раскрыты в `developer-report.md`.

Архивные результаты имеют смысл «остановил бы». Финальные БД дают только исход,
не признаки для ранней проверки. `UNKNOWN` останавливает исполнение. Уверенность
модели и пересказ агента не заменяют обязательное доказательство.

## Воспроизведение

Команды выполняются из корня этого checkout. Нужны сохранённые Git blobs и
исходный внешний shadow-архив из `data/source-inventory.json`; перемещение
checkout требует сопоставления абсолютных локальных путей в receipts. Указанные
существующие окружения уже содержат зависимости; их версии записаны в манифесте.
Новые каталоги вывода не должны существовать. Опубликованные файлы не перезаписываются.

```sh
PY=/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv/bin/python
NATIVE=/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python
V4=experiments/local_guards_v4

# Только проверка замороженных файлов, не новые предсказания.
$PY -m experiments.local_guards_v4.verify_artifacts

# Архивный extractor в отдельном каталоге, с побайтовым сравнением payload.
python3 -m experiments.local_guards_v4.reproduce_data --output /tmp/finbot-v4-data-repro

# Повторить детерминированные предсказания; timing_ms закономерно отличается.
$PY $V4/evaluate.py predict --observations $V4/data/observations.jsonl.gz \
  --metadata $V4/data/metadata.jsonl.gz --manifest $V4/results/methods-final.json \
  --output /tmp/finbot-v4-archive-predictions.jsonl.gz
$PY $V4/evaluate.py score --predictions /tmp/finbot-v4-archive-predictions.jsonl.gz \
  --data $V4/data --output /tmp/finbot-v4-archive-score --repeats 1000

# Генератор пишет рядом со своим файлом; запускаем только в новой копии.
# Новый тест уже раскрыт: повтор не является ещё одной закрытой оценкой.
CLOSED_REPRO=$(mktemp -d /tmp/finbot-v4-closed.XXXXXX)
cp $V4/POLICY.md $V4/policy.json $V4/schema.json $V4/make_closed_test.py "$CLOSED_REPRO/"
$NATIVE "$CLOSED_REPRO/make_closed_test.py"
$PY $V4/evaluate.py predict --observations $V4/closed/observations.jsonl.gz \
  --metadata $V4/closed/metadata.jsonl.gz --manifest $V4/results/methods-final.json \
  --output /tmp/finbot-v4-closed-predictions.jsonl.gz
$PY $V4/evaluate.py score --predictions /tmp/finbot-v4-closed-predictions.jsonl.gz \
  --data $V4/closed --output /tmp/finbot-v4-closed-score --repeats 1000

# Настоящие пути FinBot; сценарный исполнитель, внешние сокеты запрещены.
$NATIVE -m experiments.local_guards_v4.integration_replay --output /tmp/finbot-v4-native.json
$NATIVE -m experiments.local_guards_v4.benchmark_native --output /tmp/finbot-v4-native-untraced.json
$NATIVE -m experiments.local_guards_v4.execution_supplement --output /tmp/finbot-v4-retry.json
$PY -m experiments.local_guards_v4.robustness --native $V4/results/native-untraced.json \
  --output /tmp/finbot-v4-invariance.json

# Точные файлы, без broad discover и лишних импортов.
$PY -m unittest experiments.local_guards_v4.tests.test_guard \
  experiments.local_guards_v4.tests.test_store \
  experiments.local_guards_v4.tests.test_data \
  experiments.local_guards_v4.tests.test_evaluate
```

Профиль включается `FINBOT_V4_PROFILE=A` или `B` вместе с
`FINBOT_V4_STORE=/absolute/path/research.sqlite`. Для эксперимента нужны
изолированные source DB и sidecar. Native Invoice не содержит валюту:
реальный адаптер без независимого источника возвращает UNKNOWN; USD в политике
сам по себе такого источника не создаёт. Объявленный USD fixture используется
только в явно синтетическом стенде.

Source DB и sidecar не образуют общей транзакции. Защита активного workflow не
доказывает атомарность платежа и не заменяет reconciliation неопределённого исхода.
Без новых запусков LLM качество адаптировавшегося агента и экономия каскада не измерены.
