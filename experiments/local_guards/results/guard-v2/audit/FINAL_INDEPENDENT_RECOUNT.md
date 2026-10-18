# Независимый пересчёт FinBot guard-v2

**PASS_EXACT_RECOUNT.** Расхождений с замороженными метриками не найдено. Скрипт использует только стандартную библиотеку Python. Он не загружает модели, не обучает их, не запускает inference и не меняет thresholds, labels или научные артефакты.

| Набор | Наблюдения | Пары | Arms |
|---|---:|---:|---:|
| independent | 240 | 120 | 7488 |
| raw64 | 64 | 0 | 4411 |
| raw64-partial, matched PARTIAL→PARTIAL | 64 | 0 | 4464 |
| raw64-partial-shift, FULL→PARTIAL | 64 | 0 | 4411 |

Все 54 MF05 pins и 57 root-plan pins совпали. Для каждого arm проверены точные соответствия observation/prediction/label, решения STOP/UNKNOWN, frozen threshold и selected config. Для independent совпали все агрегаты, метрики шести семейств и ошибки в 120 парах. В каждом семействе — 20 пар и 40 наблюдений.

Для FULL проверены hashes 303 моделей, 7416 final choices и 7488 архивных arms; для PARTIAL — 177 моделей, 4392 choices и 4464 архивных arms. Проверены реальные episode→group partitions, раздельность TRAIN/CAL и внутренних разбиений, IDs обучающей и калибровочной выборок и seals без refit. Пороги принадлежат точной сетке CAL; калибровочные counts совпали со scores той же сохранённой TRAIN-модели. Архивные знаменатели 83/93/131 пересчитаны отдельно.

UNKNOWN всегда означает STOP и входит в compliant denominator. Число UNSUPPORTED model/seed pairs: independent — 0, raw64 — 126, matched PARTIAL→PARTIAL — 0, FULL→PARTIAL shift — 126. Структурно отсутствующие методы не заменялись конкурентными all-STOP arms. Matched и shift представлены раздельно. Проверки не зависят от optional partial profiling.

ExtensionRules: 120/120 intervention STOP, 4/120 compliant STOP, 116/120 compliant ALLOW; всего 16 UNKNOWN на 240 наблюдениях. В 116 из 120 пар обе стороны классифицированы верно; в четырёх парах ошибочно остановлена только compliant сторона. Это отдельный control для шести расширений, не полный FinBot guard.

Все четыре compliant UNKNOWN относятся к `indeterminate_commit`: fresh-key retry с наблюдаемым `payment_backend/not_committed` reconciliation. Public contract не задаёт допустимый словарь authority/outcome (`public-independent-contract.json:70,77–78`). Control намеренно возвращает UNKNOWN для любого non-null reconciliation (`v2_contract_rules.py:284–291`), тогда как oracle распознаёт эти literals (`v2_hidden_dataset.py:86`). Это недоопределённость public contract и ограничение покрытия control; runtime или арифметический bug не установлен. Все четыре STOP сохранены в primary counts. Относительно frozen oracle labels это nominal FP; при недоопределённом словаре public contract их нельзя безусловно объявлять ошибками guard. Canonical rename `outcome→result_status` не вызывает этот путь UNKNOWN: control не читает ни одно из этих полей. Точные case IDs и наблюдаемые факты сохранены в JSON findings.

Original report `v2_report.py:145` завышает observation-blindness. Точная последовательность: input/admission amendments сделаны до quality metrics и labels; TRAIN/CAL model seals созданы до external prediction; labels открыты после всех четырёх prediction seals. Исправление допускается только в новой presentation copy; 57 оригиналов сохраняются.

Архивный `strict_harm`, новый статический `contract_requires_intervention` и live FinBot prevention — разные утверждения. Seeds 17/29/43 — повторные модели на тех же наблюдениях. 120 пар разделяют шесть механизмов; 20 пар в семействе образованы пятью осями и четырьмя layouts. Отсюда не следуют 240 независимых испытаний, три независимые выборки или сертификация FPR ≤5%. Дополнительно остаются ограничения synthetic local-major currency semantics и отсутствие проверки высоких порогов human review. Известный raw64 является диагностикой.

Все arm-level counts: `FINAL_INDEPENDENT_RECOUNT.json`. Компактные результаты и case-level adjudication: `FINAL_INDEPENDENT_FINDINGS_05.json`. JSON содержит SHA исходного вывода frozen recount и отдельно отмеченное дополнение reviewer; исходник recount не менялся.
