# Прогоны на FinBot (ветка PR #477) — вспомогательные скрипты

Скопированы из временной папки сессии 2026-10-04, чтобы результаты в `code/runs/finbot477_*` можно было повторить.
Код FinBot не меняется: всё работает через обёртки и настройки.

**Подготовка (один раз):**
- `finbot-pr477/` — ветка `pr-477`, выгруженная из `finbot-upstream` через `git archive` (без `.git`);
  окружение `uv sync` (Python 3.13). `.env` FinBot: SQLite, `LLM_DEFAULT_MODEL=openai/gpt-4o-mini`, `HOST=127.0.0.1`, `DEBUG=true`.
- `fb.sh` — запускает команду в `finbot-pr477` с ключом OpenRouter из `.env в корне исследования` (`OPENAI_API_KEY`,
  `OPENAI_BASE_URL=https://openrouter.ai/api/v1`); ключ никуда не копируется и не печатается.
- Базы: `scripts/db.py setup` → `seed_trusted.py` / `seed_profile.py A|B|C|D <port>` (поставщик + история + конфиг хуков)
  → `sqlite3 <db> "pragma wal_checkpoint(TRUNCATE)"` → копия «чистой» базы (перед каждым счётом база восстанавливается).

**Скрипты:**

| Файл | Что делает |
|---|---|
| `hook_receiver.py <out.jsonl> [port]` | локальный приёмник guardrail-хуков: пишет каждый вызов, всегда отвечает `allow` |
| `enable_hooks.py` | включает все 4 хука для демо-пользователя |
| `seed_trusted.py` | поставщик Northlight: active / high / low + 5 оплаченных счетов + хуки |
| `seed_profile.py A\|B\|C\|D <port>` | 4 профиля поставщика (A pending/low; B active/low; C надёжный; D смена реквизитов) |
| `run_one_scenario.py <idx> [cap]` | один сценарий Веры (Cascade Lab) с подсчётом токенов и пределом |
| `run_ours_one.py <scenarios.json> <idx>` | один наш счёт на поставщике id=1 |
| `run_record_one.py <scenarios.json> <idx> <calls.jsonl>` | то же + полная запись каждого вызова модели; для gpt-5* — пересказ рассуждений |
| `run_all.sh`, `run_ours_all.sh`, `run_set.sh`, `run_set_rec.sh`, `exp1.sh`, `exp2.sh` | пакетные прогоны (чистая база, приёмник, исход из базы, бюджет) |
| `our_scenarios.json` | 77 счетов: v5 без подложенных ошибок + H1–H5 |
| `exp1_scenarios.json` | 20 счетов для эксперимента с профилями (TH501–510, TA501–510) |
| `or_responses_test.py`, `test_reasoning.py` | проверка OpenRouter: Responses API с инструментом; пересказ рассуждений gpt-5-nano |

Пути в скриптах — относительно этой папки (`SP=${0:A:h}`, FinBot — `../../finbot-pr477`, ключ — `../../.env`). Скрипты
первых прогонов (`run_all.sh`, `run_ours_all.sh`, `run_set.sh`, `exp1.sh`, `exp2.sh`, `run_set_rec.sh`) оставлены как запись
того, как шли прогоны 04.10; для новых прогонов — `run_set_rec2.sh` (полная запись, температура параметром).

**Прогоны 05.10 (температура 0):**

| Файл | Что делает |
|---|---|
| `run_set_rec2.sh <scenarios> <pristine.db> <port> <outdir> <dbfile> <budget> <model> <temperature>` | пакетный прогон с полной записью вызовов |
| `build_pristine.sh <A–F> <port>` | собирает чистую базу профиля в `pristine/` (в гит не класть) |
| `seed_profile.py` | профили A–F (E — подтверждённая смена реквизитов, F — высокий риск) |
| `v6_honest_scenarios.json`, `run227_*.json` | 150 обычных честных (Llama) и набор 227 счетов |
| `make_matrix_scenarios.py`, `matrix_scenarios.json` | набор матрицы «24 сценария × 6 профилей» |

**Анализ (в `code/`):** `make_finbot_lenta.py`, `guard_on_texts.py`, `policy_costs.py`, `levels_finbot477.py`
(`--views v1|v2`), `data_rules_exp1.py`, `make_think_lenta.py`, `make_think_log.py`. Результаты и выводы — `experiments.md` (рядом с папкой `code/`).

**Свои эксперименты (07.10):** `run_experiment.sh -p <профиль> -a <суммы> -b <бюджет> [-v варианты] [-r повторы] [-n имя]`
— одна команда: порт и чистая база по профилю, сценарии (`make_custom_scenarios.py`), план и цена, вопрос «запускать?»,
прогон через `run_pairs.sh`, сводка `code/summarize_run.py`. Подробно — раздел «Как воспроизвести» в `docs/01-setup-and-method.md`.
