# Как проверить цифры отчёта

- [Сводка для команды](FINBOT_TEAM.html) содержит данные и сценарий визуализации внутри одного HTML. Скачайте HTML через Download raw file и откройте его в браузере.
- [Технический отчёт](TECHNICAL_REPORT.md) и [протокол](PROTOCOL.md) описывают знаменатели, области видимости, метки и критерии вывода.
- [Сверка архивных результатов](OFFLINE_CORRECTIONS.md) документирует N14, сырые категории и фактическую маршрутизацию, парные контрасты, пересечения семейств, достижимость Jev до Fraud и чувствительность MAST. [Воспроизведение переписи пакетов](offline_route_census.py)
- [Протокол исправлений](correction/PROTOCOL.md), [реестр](correction_registry.json) и [проверка дизайна](correction/design/RESULTS.md) фиксируют изменения относительно первого отчёта, версию заморозки, баланс порядка запусков и ограничения разметки.
- [Действующая платёжная политика](correction/policy/results.json), [построчные метки](correction/policy/adjudication.jsonl), [сопоставление со старыми исходами](correction/policy/assignment-overlay.jsonl) и [сверка квитанций с SQLite](correction/policy/mechanical-census.jsonl) позволяют различить старую рубрику и переоценку по текущему контракту.
- [Протокол парного сравнения защитников](correction/guards/PROTOCOL.md), [заморозка](correction/guards/freeze.json) и [сверка исторических 542 P4](correction/guards/archive_542_readback.json) дают отдельные основания для выводов из исходных сохранённых ответов и нового сравнения. [516 основных пар](correction/guards/primary-results.json) · [Пороги и калибровка](correction/guards/thresholds.json) · [Все варианты запроса](correction/guards/RESULTS.md) · [Сверка объяснений](correction/guards/REASONS.md) · [Две точки вместе](correction/guards/joint_replay.json).
- [Архив P4](p4/README.md) и [построчная таблица](p4/recovery_table.jsonl) связывают каждую из 1 261 исходных неопределённых меток с дополнительным свидетельством или конкретным пробелом.
- [Исследование входа модели](panel/RESULTS.md), [метод](panel/METHOD.md) и [точная стоимость панелей](panel/panel_costs_final.json) включают сравнение одних и тех же предложений по дозе, представлению, вопросу, вероятностям, контрольной маске и решениям кода.
- [Подтверждение достаточности фактов до Fraud](pre_fraud_truth/RESULTS.md) включает независимую разметку первых делегаций и коррекции после просмотра первоисточника.
- [Первые попытки и повторы](review/RESULTS.md), [цифры по ветвям и парам](review/results.json), [построчные оценки](review/assignment_outcomes.json) и [рубрика](review/RUBRIC.md) описывают финансовый исход, процедуру, сообщение и выполнение исходной задачи.
- [Разбор реальных случаев](examples/README.md) и [реестр свидетельств](examples/evidence.json) дают координаты в журнале и проверки БД.
- [Две дополнительные развилки из состояния удержания](examples/CONTINUATION.md) описывают проверку возможности восстановить SQLite-состояние и поручение до наблюдавшейся остановки. Статус и дополнительные расходы указаны в техническом отчёте.
- [Восстановление контрольного снимка](correction/continuations/restore.py), [проверка результатов](correction/continuations/readback.py) и [учёт резервов](correction/continuations/runtime-cost.json) связывают продолжения из общего состояния с исходной трассой и независимыми итогами. [Все 12 продолжений](correction/continuations/RESULTS.md) · [Повторы 4 счетов](correction/design/repeats.md).
- Исходные счета, глобальная заморозка назначений, квитанции провайдеров, частные полные трассы, состояния БД и материалы двух независимых чтений хранятся в checkout исследования. Для живой серии рабочая директория — `.runtime/payment-controls-chp3/final-study-payment-finale/`. При повторной сборке из источников требуется тот же исследовательский checkout. Публичные сводки и построчные индексы доступны в репозитории без подключения к сервисам.

Сборка обеих форм отчёта из одних и тех же уже проверенных результатов не вызывает модели:

```sh
python3 experiments/payment_controls/native/final_study/finale/technical.py
python3 experiments/payment_controls/native/final_study/finale/publish.py
```

В обзоре всей работы использованы [сравнение Jev и DeepSeek на 125 совместных поручениях](../paired_guard/RESULTS.md), [проверка низких порогов перед Fraud](panel/LOW_PROBABILITY.md), [сверка 40 спорных переводов по прежней рубрике](review/NATIVE_A_AUDIT.md) и [ответы на исходные вопросы команды](../BOARD_ANSWERS.md). Расчёт по низким порогам использует сохранённые векторы Jev; для штатной ветви сверены фактические платежи с SQLite и FinStripe.
