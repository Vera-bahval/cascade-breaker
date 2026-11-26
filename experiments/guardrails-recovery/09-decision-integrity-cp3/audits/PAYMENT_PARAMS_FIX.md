# CP3 — исправление платёжных параметров после независимого аудита (25.11.2026)

**Статус девяти ячеек (TH606 / TA527 / TH668 × A / B / C): READY.** Нужно только отдельное согласование на платный запуск.

## Что исправлено (FAIL-1, FAIL-2 из `CP3_INDEPENDENT_CODE_REVIEW.md`)

| файл | изменение |
|---|---|
| `finbot/core/data/transfer_flags.py` | константы `INVOICE_CURRENCY = "usd"` (у счёта нет своей валюты, используется валюта платформы) и `ALLOWED_PAYMENT_METHODS = {bank_transfer, wire, ach}` (как у PaymentsAgent) |
| `finbot/mcp/servers/finstripe/server.py` · `create_transfer` | отказ `code="currency"`, если валюта ≠ `usd` (или конфиг FinStripe не `usd`); отказ `code="payment_method"` вне списка. Проверки стоят после привязки к счёту и **до** флагового барьера, вне транзакции записи |
| `finbot/tools/data/payment.py` · `process_payment` | квитанция не подходит для `paid`, если её валюта ≠ `usd` или способ не из списка |
| `scripts/cp3_live.py` | новые коды добавлены в `known_refusals`: такой отказ FinStripe записывается как отказ, а не как технический сбой. `PREFLIGHT` → `preflight-ledger-v4-paramfix`; прежний `preflight-ledger-v4` сохранён без изменений |
| `scripts/cp3_offline_test.py` | `test_payment_parameters_checked_in_every_arm[A/B/C]`: EUR, «USD» в верхнем регистре, crypto → отказ без записи перевода. USD + wire → перевод. EUR-квитанция и способ crypto не дают `paid`; правильная квитанция даёт |

Diff: `patches/CP3_PAYMENT_PARAMS_FIX.patch`; копии до правки — `patches/*.before-currency-fix`.

Не менялись: Safe M2, запись Fraud-флагов, алгоритм барьера (флаги, статус, сумма, получатель, повтор, атомарность),
матрица A/B/C, исходный FinBot, стенд Димы.

## Проверки (без платных вызовов)

- офлайн-набор — **46/46 PASS**: 43 прежних + 3 новых;
- воспроизведение из аудита: EUR → `currency`, crypto → `payment_method` (раньше оба давали `completed`);
- `verify` — PASS: архивы FD55-A/B/C и снимки совпадают;
- mock-preflight v4 — **COMPLETE 9/9**, стартовый остаток $0,23105060848, резервов в полёте нет;
- `auth-check` — `READY_METADATA_ONLY`;
- новый хеш одобрения: `c43aeb7abec164b56ad50e10ff68e0f194c282f670388774e18bb0140da97459`. Прежний `e09c…` недействителен.

## Что такое ветки A / B / C — фиксируется для отчёта о результатах

- **A — Decision Integrity без активной блокировки Fraud-флагов, а не исходный FinBot.** В A активны: привязка к
  доверенному `invoice_id`, проверка состояния, получателя, статуса, суммы, валюты, способа оплаты, повторного перевода
  и квитанции. В тень переведена **только** проверка флагов: M3a пишет BLOCK/ALLOW, но не останавливает. Safe M2 в
  задании нет.
- **B** — A + Safe M2 в задании Payments. Флаговый барьер в тени.
- **C** — B + активный флаговый барьер FinStripe.

Сравнение A/B измеряет эффект Safe M2, B/C — эффект барьера. Сравнения «до/после внедрения DI в FinBot» в этой панели
нет.

## Команда (не выполнялась)

Из `CascadeLab/iv_lab/finbot-cp3`:

```bash
LLM_PROVIDER=mock PYTHONPATH=. ../../../finbot-pr477/.venv/bin/python -B scripts/cp3_live.py live --approval c43aeb7abec164b56ad50e10ff68e0f194c282f670388774e18bb0140da97459
```
