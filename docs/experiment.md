# Текущий эксперимент: где обрывать каскад на FinBot

**Вопрос.** Где и как ставить проверку согласованности, чтобы обрывать каскадные ошибки в мультиагентной системе при
приемлемых задержке и FPR. **Гипотеза:** есть уровень системы, где отношение «предотвращённые каскады / накладные
расходы» лучше остальных; альтернатива — все уровни дают одинаковый эффект.

Это пилот (разведка): проверить, реализуем ли план на FinBot, и получить первые цифры. Результаты —
`docs/finbot-probe-report.md`, коротко с графиками — `docs/finbot-probe-report.pdf`.

## Стенд

FinBot (OWASP FinBot CTF) с Cascade Lab из PR #477: сабмодуль `finbot/` на `a7f6964`, наши изменения —
`finbot-patches/`. Оркестратор делегирует invoice → fraud → payments → communication. Каскад может идти двумя
каналами: текстом (отчёты агентов дописываются к задаче следующего) и через БД (статус счёта). Деньги переводит
MCP-инструмент `finstripe__create_transfer`.

## Точки контроля и проверяющие

| Точка | Где |
| --- | --- |
| P0 | вход: счёт до запуска агентов |
| P1 | оркестратор перед делегированием |
| P2a / P2b / P2c | граница агентов: отчёт invoice / fraud / payments до передачи дальше |
| P3 | инструменты, меняющие статус счёта или риск вендора |
| P4 | перед переводом денег (необратимое действие) |
| P5, P6, P7 | после перевода: финальный ответ, асинхронный монитор, пост-хок по трассе (только обнаружение) |

Проверяющие: V1 — инварианты по БД, V2 — регулярки по тексту (цикличны относительно атак), V3 — LLM-проверка
согласованности, V4 — V3 с голосованием из трёх, V5 — аннотатор MAST.

## Дизайн

- **Теневой режим.** Все проверяющие работают во всех точках, но только записывают вердикты. При политике «стоп и
  эскалация» прогон с защитой совпадает с прогоном без защиты до первого `block`, поэтому исход любой из
  78 125 конфигураций «тип проверки в каждой точке» считается офлайн по записям.
- **Живая проверка.** 3 конфигурации прогнаны с настоящей блокировкой (`enforce`) и сравнены с офлайн-предсказанием.
- **Оракул** — только по БД и аргументам перевода, не по текстам агентов; политика — `experiments/finbot-probe/policy.json`.
- **Отложенная выборка:** отбор на половине A, цифры на половине B.

| Набор | Прогонов |
| --- | ---: |
| 7 сценариев PR #477 × 10 повторов | 70 |
| 40 чистых счетов × 2 (12 трудных: «urgent», «approved by», «deadline») | 80 |
| 3 базовых счёта × 4 без инъекций | 12 |
| Инъекции: 4 узла × 3 типа отказа × 3 базы × 2 | 72 |
| Проверка канала: 3 инъекции × 3 | 9 |
| Контроль: режим `off` | 5 |
| Живая проверка: 3 конфигурации × 36 | 108 |

Модель — `openai/gpt-4o-mini-2024-07-18` через OpenRouter, провайдер закреплён на OpenAI, T = 0 (`seed` через
Responses API OpenRouter не передаётся). Потрачено $4,83.

## Как воспроизвести

Цифры и графики — из записанных трасс, без API:

```bash
cd experiments/finbot-probe
uv run --no-project --with numpy --with matplotlib python analysis.py     # results/, figures/
uv run --no-project --with numpy --with matplotlib python report_pdf.py   # docs/finbot-probe-report.pdf
```

Новые прогоны — после `./finbot-patches/apply.sh`, из `finbot/`, с `.env`, где задан ключ OpenRouter
(`OPENAI_API_KEY`, `OPENAI_BASE_URL=https://openrouter.ai/api/v1`, `LLM_PROVIDER_PIN=openai`,
`LLM_DEFAULT_MODEL=openai/gpt-4o-mini-2024-07-18`, `LLM_DEFAULT_TEMPERATURE=0`):

```bash
uv sync && uv run python scripts/db.py setup
uv run python scripts/probe/run_batch.py --label shadow-main --sets attacks clean bases injections --mode shadow
uv run python scripts/probe/run_batch.py --label enforce-p2a-v3 --sets attacks clean --mode enforce --enforce P2.invoice_agent=V3
uv run python scripts/probe/replay.py runs/shadow-main.jsonl --all --limit 5    # воспроизведение без API
uv run python scripts/probe/render_traces.py runs/shadow-main.jsonl            # HTML-просмотрщик трасс
```

Раннеры пишут в `experiments/finbot-probe/` относительно корня исследовательского репозитория; при запуске отсюда
поправьте `EXPERIMENT_DIR` в `finbot/scripts/probe/common.py`.

## Дальше

Более разнообразные и трудные каскады (сейчас их два вида, и у лучших конфигураций предотвращение упирается в 100%),
≥385 каскадных и ≥189 чистых прогонов на группу, решения руководителя по политике (сценарии с заявлениями CEO,
пометка fraud, счета выше $10 000).
