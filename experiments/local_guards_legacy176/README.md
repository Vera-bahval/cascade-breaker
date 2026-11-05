# Проверка регрессии на 176 прежних эпизодах

**Результат:** исходные v1/v2 воспроизведены:78/83 и83/83 обнаруженных нарушений, без ошибочных BLOCK на93 прежних безопасных эпизодах. Новые v3/v4.3 дали68 правильных BLOCK и108 UNKNOWN, включая все93 безопасных. Бейзлайн не сохранился. [Сравнение](TABLES.md) · [Примеры](EXAMPLES.md) · [Полное время](TIMING.md).

Это проверка регрессии на известной серии, не новый закрытый тест. Выборка и метки закреплены публикацией ec93a1be, рабочая база7fb7902a. Из234 исходных эпизодов38 не достигли P4,20 имели неоднозначное целевое решение; [реестр исключений](exclusion-details.json).83 положительных означают нарушение прежней строгой платёжной проверки; это не83 независимо размеченные семантические атаки. Среди них39 также имеют вред по более узкой старой оценке исхода. Метки не переопределялись под новый контракт.

[Протокол](PROTOCOL.md), [допуск входов](INPUT_REVIEW.md) и [аудит таймеров](TIMING_SOURCE_REVIEW.md) предшествовали массовому запуску. Входы одобрены на коммите7a571bd83dbe81f7ca836448c29c7fc2b4b36f5d, input manifest9ca45be9fb83c8dd58e053ed98a9661c17ff05e7cf62fc52cf307447cbfc16c2. Новые предсказания заморожены до оценки; [receipt](prediction-freeze.json). Исходные методы и найденные факты после этого не менялись.

## Что сохранено

- `source-prefixes.jsonl.gz`: только начальное состояние, использованные до среза схемы инструментов и префикс событий. Итоговая БД и ответы защитников не попадают в подготовку.
- `prepared-inputs.jsonl.gz`:352 входа FULL/PARTIAL с происхождением фактов и входом каждого метода; [аудит передачи](audit_inputs.py). Снимок сервера не выдаётся за tool result.
- `predictions.jsonl.gz`:3872 неизменённых ответа правил/контролей; `saved-controls.jsonl.gz`:сохранённые SecJev, без inference. Все связи проверены по episode/cut/canonical/payload/inference hashes.
- `labels/scoring.jsonl.gz`:176 исходных меток, отдельно от подготовки. `quality.json`:качество и парные интервалы по45 базовым группам; `regressions.jsonl.gz`:все ухудшения локальных методов на FULL относительно v2; переходы сохранённых SecJev и PARTIAL находятся в quality.json.
- `timing-sources.jsonl.gz`:исходные таймеры отдельно от входов. `benchmark.jsonl.gz`:58 080 замеров,30 повторов каждого локального метода на176 входах. `full-time.json`:маршруты до P4 STOP или завершения и компоненты времени.
- `input-manifest.json`, `source-manifest.json`, `saved-controls-manifest.json`, `benchmark-receipt.json`, `result-audit.json`, `release-manifest.json`:хеши и проверки. Исходные v4/v4.2 оставлены в технических результатах.

FULL использует полные доступные архивные сведения. PARTIAL сохраняет прежнее сокращённое представление без привязки объектов и истории; это проверка чувствительности к сокращению входа, не основная оценка. У SecJev проверено совпадение прежнего canonical payload; новые правила дополнительно видят записанный server default валюты перевода. Он не подтверждает валюту счёта или разрешение платежа.

## Воспроизведение без моделей

Из корня репозитория, Python3 с зависимостями закреплённого стенда. В этой рабочей копии использован `experiments/local_guards/.venv-finbot/bin/python` из исходного workspace. Команды ниже выполняют только тесты, проверки и арифметику сохранённых результатов:

```sh
python -m unittest experiments.local_guards_legacy176.test_prepare experiments.local_guards_legacy176.test_timing experiments.local_guards_legacy176.test_benchmark experiments.local_guards_legacy176.test_evaluate -q
python -m experiments.local_guards_legacy176.audit_inputs
python -m experiments.local_guards_legacy176.saved_controls
python -m experiments.local_guards_legacy176.evaluate
python -m experiments.local_guards_legacy176.audit_results
python -m experiments.local_guards_legacy176.render
python -m experiments.local_guards_legacy176.manifest --check
```

Пути исходных больших архивов и модельных ответов находятся в source/saved manifests; они локальные и нужны для повторной сверки источников. Подготовленные входы, ответы и таблицы опубликованы, для пересчёта качества/времени исходные модели не нужны. Исходные контрольные суммы прежних результатов сохранены. `prepare --custody` и `prepare` заново строят входы, `run` выполняет только правила после допуска; `benchmark` измеряет только локальный replay. Для независимого воспроизведения запуска использовать отдельную копию: run/benchmark отказываются перезаписывать уже зафиксированные ответы. Подготовка должна снова получить независимый допуск, если код или входы изменены.

Нет новых LLM/API-вызовов, обучения и подбора порогов. SecJev0.8B OOF predictions получены раньше:основной seed17, остальные29/43 опубликованы без выбора победителя. Расходы API на эту проверку:$0; локальные вычисления не переведены в деньги. Время SecJev имеет явно неучтённые клиентские компоненты; тест воспроизводит сохранённый ход FinBot, не адаптацию LLM после вмешательства.

Точные сохранённые модели: SecJev-0.8B v1.0.0 (MPS FP32, AMEND05 renderer); SecJev-9B v1.3.0 (MPS BF16 backbone/FP32 LoRA-head); отдельный контроль `nativ-community/JEV-27B-VL-MLX-NVFP4`. Последний не переименовывается в SecJev. Ревизии, параметры, fingerprints и hashes источников приведены в saved-controls-manifest.json.
