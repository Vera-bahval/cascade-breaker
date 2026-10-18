# Три политики порога: исследовательский пересчёт

Эта серия начата после просмотра предыдущих результатов. Все новые сравнения
являются **post-hoc**, даже при выборе порогов и конфигураций исключительно
внутри групповой обучающей части. Исходные разметка, HOLD-политика, группы,
разбиения и научные результаты `cheap-guards` и `night-4b` сохранены.

Основная популяция: 176 P4-префиксов / 214 эпизодов, 83 опасных продолжения,
131 безопасный эпизод, из которых 93 достигли P4. Seeds 17/29/43 повторно
используют эти эпизоды; это не три независимые выборки.

## Определения

Решение: `UNKNOWN OR rules OR score >= threshold`. Порог `+infinity`
отключает только конечный score, но не rules и UNKNOWN. Кандидаты нового
поколения — точные уникальные наблюдённые оценки и `+infinity`.

- **A:** при inner episode FPR ≤5% максимизировать обнаружение, затем
  минимизировать FP, затем выбрать максимальный порог.
- **B:** выбрать порог компонента без rules по тому же критерию, затем
  объединить с rules. Ограничение компонента не гарантирует FPR всей системы.
- **C:** минимальный допустимый кандидат конечной сетки при совместном
  inner FPR ≤5%. Это не минимум по всем вещественным порогам.

Для B отдельно показаны **Blegacy** (выбор конфигурации без rules, затем OR)
и **B2** (самостоятельно калиброванный порог, выбор конфигурации по итоговым
wrapped inner метрикам). Для всех политик внешний набор не участвует в выборе.
Недопустимый даже при infinity бюджет сохраняется как `infeasible`.

## Артефакты и воспроизведение

Из корня workspace:

```sh
export PYTHONPATH=experiments/local_guards
experiments/local_guards/.venv/bin/python -m cascade_guard.cheap_policy_comparison \
  --base experiments/local_guards --output /tmp/cascade-policy-main-reproduction
experiments/local_guards/.venv/bin/python -m cascade_guard.cheap_policy_report \
  --base experiments/local_guards
```

Для первого вызова нужен новый каталог назначения. Подробные команды:

- `results/policy-comparison/matched-reference/REPRODUCE.txt`: 4B, включая
  восстановление отсутствовавших inner оценок небольших CatBoost из кеша.
- `results/policy-comparison/text-reference-verified-final/REPRODUCE.txt`:
  TF-IDF + Logistic Regression, оба прежних текстовых представления.
- `cascade_guard.cheap_policy_lr_stack --output <новый-каталог>`: прежняя
  Logistic Regression на табличных признаках и четырёх оценках SecJev 0.8B,
  оба прежних формата; входы и новые небольшие fits заморожены отдельно.
- `POLICY-RAW64.md`: применение архивной калибровки к уже известному raw64.

Повторить финальную текстовую калибровку из проверенного кеша, сохранив старую:

```sh
experiments/local_guards/.venv/bin/python -c \
  'from pathlib import Path; from cascade_guard.cheap_policy_text_final import run; run(Path("experiments/local_guards").resolve(), Path("/tmp/cascade-text-policy-reproduction"))'
```

Переменная `PYTHONPATH` должна быть установлена, как в первом блоке. Повторную
запись в каталог с финальными метриками запрещает сам evaluator. Для отдельного
повторного обучения TF-IDF используйте `cheap_policy_text --output <новый-каталог>`;
финальная команда выше намеренно использует проверенный опубликованный кеш.
Серию следует переносить вместе с полными manifest и общими зависимостями,
а не экспортировать один каталог отдельного классификатора.

Нового transformer inference, платных API и живого FinBot в серии нет.
Основные cheap-методы используют сохранённые inner curves и outer scores.
Повторное обучение downstream-моделей помечено отдельно; это не новый
inference SecJev. Исторические промежуточные попытки сохранены, включая
устранённый разрыв provenance первого текстового прогона. Для публикации
используется только поколение `text-reference-verified-final` с повторно
проверенными входами и побитным совпадением inner/outer оценок.

`results/policy-comparison/review/independent-method-review.md` содержит
независимое ревью определений до новых результатов. `final-audit.json`
проверяет уже полученные результаты. Предложенные там новые семейства ошибок —
план будущей независимой проверки, а не выполненный эксперимент. Raw64 уже
известен и такого подтверждения не даёт.

HTML: `reports/cheap-policy-report.html`. Полные таблицы, внешние предсказания,
пороговые решения, source/input/output manifest и проверки лежат в
`results/policy-comparison/`. Старый HTML сохранён в `previous-report/`;
добавление ссылки на новую серию — изменение представления, не результатов.
