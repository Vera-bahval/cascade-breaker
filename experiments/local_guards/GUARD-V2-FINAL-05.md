# Guard v2 AMEND05: завершённая исправленная серия

Все доступные методы оценены, предсказания заморожены до раскрытия независимых меток. Платные API и новые живые FinBot/Luna-запуски не использовались. Prompt Guard 2 22M/86M, NLI, MiniCheck завершили по 720 входов; SecJev 0.8B — 1968 контрольных точек. SecJev 4B не завершил CPU validation до исходного cutoff: результата качества нет. Это неполнота, а не установленный провал численной устойчивости.

## Протокол и границы

Научные исходники и входы сохранены в `results/guard-v2/METHOD_FREEZE_05.json` (SHA256 905199e01d99950fe905cb741d27bee56df5be745819d62d64820fb119747d44). `ROOT_AUTHORIZATION_PLAN_05.json` дополнительно закрепляет разрешённый исполнитель и контрольные предсказания. Модели/пороги не менялись после раскрытия меток. Три seed 17/29/43 не являются независимыми выборками. Порог выбран на CAL той же TRAIN-модели без последующего refit.

Архивная цель — наблюдаемый harm_if_continue; новая — contract_requires_intervention. Независимый генератор создал 120 причинных пар (240 случаев), шесть семейств и накопительные статические стадии. Это проверка переноса на расширенный контракт, включая законные частичные платежи, а не живое предотвращение в FinBot и не чистая проверка прежней политики. Raw64 — уже известный стресс-тест. Предел CAL FPR 5% не гарантирует внешний FPR.

## Проверенные исправления

До inference: типизированные денежные величины/идентификаторы; привязка ledger к invoice; bool HOLD; происхождение фактов и завершённость операций; одинаковый renderer и отдельный matched PARTIAL-контроль. После заморозки: отдельные адаптеры string→Path для scorer, `__main__.Model` для joblib-профайлера, отдельная копия partial-профайлера с точным дополнением имени входного файла. Научные frozen-файлы, модели, пороги, метки и предсказания не переписаны. Протоколы адаптеров и независимые source reviews сохранены рядом с результатами.

Основной пересчёт `audit/FINAL_INDEPENDENT_RECOUNT.json` прошёл. Его проверка включает соответствие предсказаний меткам, группы, CAL и хеши. Post-hoc sensitivity по 8 случаям недоопределённого reconciliation-контракта дана отдельно; исходные 240 меток и основной результат сохранены.

## Команды воспроизведения без inference

Из корня `${ORIGINAL_WORKSPACE}`:

```sh
python3 experiments/local_guards/scripts/replay_guard_v2_recount_05.py --output /private/tmp/guard-v2-recount-new.json
PYTHONPATH=experiments/local_guards experiments/local_guards/.venv-finbot/bin/python -m cascade_guard.v2_report_costs_05 --base experiments/local_guards
```

Первый путь результата должен быть новым: инструмент запрещает перезапись. Второй пересобирает только HTML, CSV агрегатов и report-manifest из готовых оценок. Первоначальный completion-HTML и manifest сохранены в `presentation-release-v5/original-completion/`.

Команды фактического inference и версии/checksum весов находятся в `scores-v5/runtime-run.json`, `jev-v5/runtime-run.json`, их stage/gate manifest и исходной заморозке. Команды обучения, fit/config/пороги и предсказания — в `evaluation-v5/`, `evaluation-partial-v5/` и `evaluation-runner-v5/`. Compatibility caller receipts сохраняют точные аргументы профилирования. `completion-v5/COMPLETE.json` и `MANUAL_RECOVERY_RECEIPT.json` фиксируют завершение четырёх внешних оценок.

Не перезапускайте старый one-shot или watchdog для нового inference: исходный cutoff не сбрасывается. Новая вычислительная серия требует отдельного manifest, времени и каталога, сохраняющего текущие результаты.

## Артефакты

- `reports/guard-v2-report.html`: итоговый отчёт со всеми методами и политиками.
- `results/guard-v2/comparison.csv`: все агрегаты; `findings.md`: интерпретация.
- `hidden-test/observations.jsonl`, `labels.jsonl`: независимые наблюдения и разметка; публичный контракт закреплён отдельно.
- `evaluation-v5/`, `evaluation-partial-v5/`: разбиения, замороженные модели, thresholds, внешние предсказания и метрики; `PREDICTIONS_FROZEN.json`/`METHODS_FROZEN.json` закрепляют соответствующие файлы.
- `scores-v5/`, `jev-v5/`, `feature-views-v5/`: сырые оценки, версии, хеши входов, окна, статусы и признаки.
- `cost-provenance-05.json`, `jev-runtime-provenance-05.json`, `latency-summary-05.json`: ресурсы с происхождением измерений.
- `audit/POLICY_UNDERSPEC_SENSITIVITY_05.json`: post-hoc чувствительность всех методов; основной результат не заменяет.
- `FINAL_RELEASE_05.json`: хеши итоговых артефактов, научных manifest и презентационного кода.

Изолированные head timings измерены на архивных входах: 303 full и 177 partial моделей. Стоимость извлечения на независимых случаях показана отдельно; суммирование старых четырёх Jev-вызовов — реконструкция мониторинга, не новый end-to-end замер. RSS и MPS driver memory не суммируются. Локальная денежная цена и точные токены разработки сабагентами недоступны; они не заменены оценочными числами или подписочными кредитами.
