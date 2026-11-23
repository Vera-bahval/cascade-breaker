# Навигатор по воспроизведению

[Выводы по всему плану](RESULTS.md) · [Иллюстрированная сводка](FINBOT_RESULTS.pdf) · [Независимая проверка ограничений](limitations.md)

| Исследовательский вопрос | Протокол и первичная опора | Где искать результат |
|---|---|---|
| Что действительно произошло в 542 эпизодах? | [Происхождение архива и пересечения](../expansion/lineage.md), [сопоставление предложения и квитанции](census.py) | [Каждый эпизод и признаки](census.csv), [действительные знаменатели](census.md) |
| Почему старые no-LLM и ML давали много запретов? | [Старое исследование](../../../NO_LLM_REPORT.md), [новая воспроизводимая сверка](../checkpoint/RESULTS.md) | [Пять моделей, проверка пересечений и ошибок](../checkpoint/ml_audit.md), [нативный TaxCalc](../checkpoint/tax_native.json) |
| Как выбирались случаи и ранний вход? | [542, 754 и 128](../expansion/lineage.json), [разбиение и требования](../mechanism_study/PROTOCOL.md), [аудит закрытой выборки](../confirmation/admission.md) | [Первые делегирования Fraud](../mechanism_study/ROUTE_CENSUS.md), [123 банковских сценария и 361 размеченный пакет](../validation/RESULTS.md) |
| Экономит ли предварительная проверка? | [Зафиксированные маршруты](../overnight/RESULTS.md), [фактические цены восьми новых задач](../expansion/live_natural_results.md) | [Сравнение по всей серии и по воздержанию кода](../mechanism_study/contrast.md), [условия фактически сэкономленного расследования](../confirmation/compatible_report.md) |
| Какой вход полезен Jev? | [Старый факторный эксперимент](../mechanism_study/PANEL_RESULTS.md), [границы сведений до Fraud](../mechanism_study/NOTES_PAIR.md), голоса о связи с квитанцией | [Новый эксперимент с формулировкой и перестановкой ответов](contrast_results.md), [аудит вероятностей](jev_probability.md), [метрики и число пропусков](jev_metrics.json) |
| Как влияют текст Fraud и формат передачи? | [Проверяемые поля структурированного отчёта](../mechanism_study/contrast_fraud_output.md), [36 удержаний и 8 других текстов](../validation/semantic_report.md) | [Прогноз и реальные записи ограничений](../validation/guard_report.md), [продолжение после отказа](../expansion/paired_results.md) |
| Как предотвращаются повтор и переплата? | [Два публичных источника и эксперименты](../expansion/RESULTS.md), [архивная переплата](money_archive.json), [фиксация ошибочного и допустимого префикса](money_freeze.json) | [Повторы с автономными агентами](../expansion/bridge_results.md), [контролируемая сумма и налог](money_report.md) |
| Где возникла ошибка в FinMail? | Парные исходные документы, [новый протокол](mail_protocol.md), [тип письма в журнале и базе](other_notice.md) | [Сумма, налог и попытка повторной отправки](mail_results.md), [изменение типа](other_notice_results.json), [отдельная ошибка связи ID из прошлого исследования](../mechanism_study/binding_results.md) |
| Меняет ли проверка исход по pending и при онбординге? | [Исторические выплаты и контроль](vendor_archive.json), до вызова и после доставки, [архив онбординга](process_archive.json) | [Статусы и платежи](vendor_results.md), [изменения профиля и письма](process.md) |
| Может ли чат восстановить пропущенный процесс? | [Исходные запросы](process_chat_inputs.json), [напоминание перед ответом](process.md), [ответы Jev на те же факты](selector_report.md) | [Штатная операция, проверка прав и результат рабочего процесса](selector_route_report.md) |
| Как разметили наблюдаемые отклонения? | [Рубрика](mast_rubric.md), первые 24, остальные 10 | [Разбор 34 попыток](mast_report.md), [машинное согласование](mast_reconciliation.json) |
| Время и деньги | [Сверка по журналам провайдеров](campaign.py), [отдельные часы для запроса и задачи](timings.py) | [Расходы](costs.json), [p50 и p95 с размером группы](timings.json) |

## Локальная проверка без обращения к моделям

Команды выполняются в корне исследовательского репозитория cascade-breaker-publication. Используется существующее окружение FinBot и сохранённые архивы. Первая группа команд повторяет расчёт показателей, вторая проверяет клиенты и новые маршруты без платежей, отправки реальных писем и запросов к провайдерам.

~~~sh
python3 -m experiments.payment_controls.native.completion.census
python3 -m experiments.payment_controls.native.completion.campaign
python3 -m experiments.payment_controls.native.completion.timings
PYTHONPATH=finbot:scenarios:. finbot/.venv/bin/python -m experiments.payment_controls.native.completion.contrast_verify
PYTHONPATH=finbot:scenarios:. finbot/.venv/bin/python -m experiments.payment_controls.native.completion.jev_audit
PYTHONPATH=finbot:scenarios:. finbot/.venv/bin/python -m pytest -q experiments/payment_controls/native/completion/test_jev_choice.py experiments/payment_controls/native/completion/selector_route_test.py experiments/payment_controls/native/overnight/test_route.py experiments/payment_controls/native/test_fraud_recheck.py experiments/payment_controls/native/test_verifier.py
~~~

Повтор запуска моделей — отдельный платный опыт. Время, текст следующего действия и сам факт достижения проверяемой границы могут измениться. Для проверки существующих результатов достаточно сохранённых данных. Числа расходов относятся к этому пользователю и этим квитанциям, а не к общей активности аккаунта Eliza.

## Размещение файлов

В этой папке и в архиве материалов находятся исходники проверок, протоколы, хеши, обезличенные оценки, отчёты и PDF. Отдельные каталоги предыдущих этапов расположены по ссылкам выше. Сырые ответы провайдеров, квитанции и базы симулятора остались в закрытой локальной области исследовательского checkout. Имена каталогов внутри .runtime/payment-controls-chp3:

- contrast-v1 — 144 исходных ответа Jev, оплаченные токены, исходное соответствие вариантов и слепая выдача.
- completion-mail-v1, money-completion-v1, completion-notice-v1 — обращения к DeepSeek, восстанавливаемые предложения, исправленные и доставленные письма, база и журналы попыток.
- vendor-eligibility-v1, completion-process-v1, completion-chat-v1 — исходный и конечный статус, архивные и новые признаки, данные по запуску процесса и доставке.
- completion-selector-v1, completion-selector-route-v1 — два подлинных ответа Jev, передача управления и привязанная к сессии квитанция рабочего процесса. Повторное чтение квитанций не означает нового обращения к Jev.

Базы симулятора и закрытые ключи соответствия остаются в рабочем пространстве. ZIP содержит материалы этого этапа для команды. Для сверки каждой исходной квитанции нужны локальные каталоги, а для повторения ранних исследований — соответствующие архивы исследований.
