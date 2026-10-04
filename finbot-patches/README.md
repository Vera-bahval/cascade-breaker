# Изменения FinBot для пилота

21 коммит поверх `a7f6964` (PR #477, ветка `cascading_failures` форка `Vera-bahval/finbot-ctf`).
Сабмодуль `finbot/` закреплён на `a7f6964`; эти коммиты лежат здесь патчами, потому что в форк мы не пушим.

```bash
./finbot-patches/apply.sh   # инициализирует сабмодуль и создаёт в нём локальную ветку cascade-control-probe
```

Проверено: дерево после `git am` совпадает с исходной веткой (`88e30027`).

Что внутри (подробнее — `docs/finbot-probe-report.md`, раздел 2):

| Патчи | Что |
| --- | --- |
| 0001–0003 | OpenRouter: `OPENAI_BASE_URL`, закрепление провайдера, `seed`; usage и стоимость в ответе |
| 0004–0005 | журнал расходов со стоп-условиями; конфиг «роль → модель» |
| 0006–0007 | тестовые запросы этапа 0, пробный прогон этапа 1 |
| 0008 | `agent_name` в конверте guardrail-хуков |
| 0009–0010 | полная трасса, точки P0–P5, режимы `off` / `shadow` / `enforce`, инъекции отказов |
| 0011–0012 | проверяющие V1–V5 |
| 0013–0021 | чистые счета, раннер, перепроверка V3, replay, HTML-просмотрщик, замер webhook, служебное |

Без включённых флагов FinBot ведёт себя как на `a7f6964`; тесты с `LLM_PROVIDER=mock` — те же 3 падения, что
на `a7f6964`.

Запуск (из `finbot/` после `apply.sh`; нужен `.env` с ключом OpenRouter, см. `docs/experiment.md`):

```bash
uv sync
uv run python scripts/db.py setup
uv run python scripts/probe/run_batch.py --label <имя> --sets attacks clean --mode shadow
```
