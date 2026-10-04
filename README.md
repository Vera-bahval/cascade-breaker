# cascade-breaker

Исследование: где и как ставить проверку согласованности, чтобы обрывать каскадные ошибки в мультиагентной
LLM-системе при приемлемых задержке и FPR. Стенд — FinBot (OWASP FinBot CTF).

**Сейчас это исследовательский код, а не продукт.** Ветка `research/first-prototype` содержит первый прототип:
пилот на FinBot, его данные и отчёт.

## FinBot — временный сабмодуль

`finbot/` — сабмодуль на форк [Vera-bahval/finbot-ctf](https://github.com/Vera-bahval/finbot-ctf), коммит `a7f6964`
(Cascade Lab, PR #477). Он добавлен **временно**, только для этого исследования. Наши изменения FinBot лежат
патчами в `finbot-patches/` и накладываются скриптом:

```bash
git submodule update --init finbot
./finbot-patches/apply.sh
```

Сабмодуль есть только на этой ветке. На ветках без него ничего скачивать не нужно; и здесь `git clone` без
`--recurse-submodules` его не скачивает. Для чтения отчёта и пересчёта цифр сабмодуль не нужен.

## Литература

Методика и словарь взяты из двух статей, которые используются в проекте как источники (числа из них не переносим):

- **MAST** — Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* (NeurIPS 2025, Datasets & Benchmarks):
  таксономия 14 режимов отказа и LLM-аннотатор трасс.
- **Sherlock** — Ro et al., arXiv 2511.00330 (препринт): где ставить проверку в агентном графе, контрфактические
  инъекции, правило размещения.

Кратко — `docs/literature.md`.

## Что где

| Путь | Что |
| --- | --- |
| `docs/literature.md` | две статьи: что берём и что не переносим |
| `docs/experiment.md` | текущий эксперимент: вопрос, точки контроля, проверяющие, дизайн, как воспроизвести |
| `docs/finbot-probe-report.pdf` | короткий отчёт с графиками |
| `docs/finbot-probe-report.md` | полный отчёт пилота |
| `finbot-patches/` | код пилота для FinBot (21 патч) и скрипт применения |
| `experiments/finbot-probe/` | трассы (`runs/*.jsonl.gz`), оракул, анализ, таблицы, графики |

Пересчитать все цифры и графики из трасс, без API:

```bash
cd experiments/finbot-probe
uv run --no-project --with numpy --with matplotlib python analysis.py
```
