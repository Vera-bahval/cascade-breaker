# CP3-LIVE v6 — готовность полной матрицы (25.11.2026)

**READY.** Платных вызовов при подготовке не было. Запуск — только по отдельному согласованию.

## Состав

- **11 ячеек** в замороженном порядке: FD55-B, FD55-C, TH606-B/C/A, TA527-C/A/B, TH668-A/C/B.
- **FD55-A** не повторяется и остаётся частичным живым наблюдением (`live/FD55-A`).
- **FD55-B/C и TH606-B/C возвращены.** В v2–v5 они ни разу не отправили действующий ключ (`one_arm` затирал `key`),
  решения модели нет. Каждая ячейка стартует с чистой копии `frozen.db`; sha сверяется с `relocated_manifest()`.
- Архивы v2–v5 проверяются по контрольной сумме и состоянию (`prior_attempt`, `v3_attempt`, `v4_attempt`,
  `v5_attempt`) и не возобновляются. Их технические остановки вынесены в `comparison.json →
  archived_technical_stops` и не заполняют строки результатов v6.
- Новые каталоги: `preflight-ledger-v6`, `continuation-v6`. Второй пока не существует.

## Бюджет

| | $ |
|---|---|
| лимит панели | 0,24 |
| подтверждено (FD55-A) | 0,00086889152 |
| удержанные резервы, **не освобождены** до сверки с OpenRouter | FD55-B 0,004040250 · FD55-C 0,004040250 · TH606-B 0,003939250 · TH606-C 0,003939250 = 0,01595900 |
| **программный остаток на v6** | **0,22317210848** |
| максимум v6 (11 × $0,02) | 0,22 — укладывается |

## Проверки

- Офлайн-набор — **49/49 PASS**.
- Регрессия ключа:
  - `test_one_arm_passes_the_api_key_unchanged_to_execute`;
  - **сквозной** `test_one_arm_execute_sends_the_original_key_over_http[TH606-C, FD55-B]`: настоящий
    `one_arm → execute → openrouter_sdk`, подставной HTTP-транспорт видит ровно `Authorization: Bearer <переданный
    ключ>`.
  - На копии раннера с возвращённой ошибкой все 3 теста **падают**, на исправленном — проходят.
- `verify` — PASS.
- Mock-preflight v6 — **COMPLETE 11/11**:
  - FD55-C и TA527-C — без перевода (активный барьер);
  - остальные — оплачены;
  - квитанции совпадают с SQLite.
- `auth-check` — `READY_METADATA_ONLY`.
- **Условия не менялись:**
  - файлы Decision Integrity в стенде (`finstripe/server.py`, `payment.py`, `transfer_flags.py`, `fraud.py`,
    `payments.py`), `m2safety.py` и `manifest.json` (тексты A/B/C) — без изменений с последних проверенных правок;
  - в `cp3_live.py` изменены только набор ячеек, каталоги, проверка архива v5 и учёт резервов;
  - тень барьера для A/B (`patch(stripe.active_flags)` при `arm != "C"`) — как прежде.

## Ветки

- **A** — Decision Integrity без активного Fraud-барьера: не исходный FinBot.
- **B** — A + Safe M2.
- **C** — B + активный Fraud-барьер.

## Хеш одобрения и команда (не выполнялась)

`767d3dfe2b25f34fa084cc67cf50517661a96564eae1f7ad7914f3254ecf486b`

Из `CascadeLab/iv_lab/finbot-cp3`:

```bash
LLM_PROVIDER=mock PYTHONPATH=. ../../../finbot-pr477/.venv/bin/python -B scripts/cp3_live.py live --approval 767d3dfe2b25f34fa084cc67cf50517661a96564eae1f7ad7914f3254ecf486b
```
