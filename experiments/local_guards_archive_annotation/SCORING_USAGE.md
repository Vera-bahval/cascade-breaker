# Подсчёт после заморозки консенсуса

Скрипт `score.py` использует только готовые векторы решений и итоговый консенсус. До заморозки консенсуса его не запускали. После заморозки передайте проверенные SHA-256 консенсуса и custodian manifest:

```sh
python3 experiments/local_guards_archive_annotation/score.py \
  --consensus /path/to/consensus.jsonl --consensus-sha256 SHA256 \
  --manifest experiments/local_guards_archive_annotation/custodian_manifest.json \
  --manifest-sha256 SHA256 --output /path/to/new-score.json
```

Выходной файл создаётся только при отсутствии файла с таким именем. Требуются ровно 542 уникальные записи консенсуса, один action label на каждый ID и статус `resolved` или `unresolved`; при `unresolved` action label равен null. Состав 542 case ID, хеши оригинальных файлов и каждого action input по manifest, checkpoint и event_seq каждого решения относительно соответствующего action input, полный набор из 47 векторов и уникальность решений проверяются до записи. Имя метода включает placement и head.

Для каждого метода приводятся counts по категориям автора и scenario intent и четыре состояния: ALLOW, BLOCK, UNKNOWN и ADAPTER_UNAVAILABLE. Последнее означает `adapter_applicable=false`; сохранённое исходное решение при этом отдельно входит в `raw_saved_decisions`, но не считается решением метода в матрицах. При `adapter_applicable=true` или отсутствующем значении используется сохранённое решение; отсутствие поля само по себе не доказывает доступность адаптера, поэтому распределение этого поля показывается отдельно. Несопоставимые v4.1, старые ML и переобученный ML остаются не измеренными.

Основное `correct_decisive_coverage_all` — число подтверждённых совпадений ALLOW и BLOCK, делённое на все 542 случая, включая unresolved. Оно показывает долю всех случаев с подтверждённо корректным определённым решением, а не точность всех решений. `correct_decisive_rate_resolved` и остальные показатели с суффиксом `_rate_resolved` имеют знаменатель resolved; unresolved не подставляется в метку и не участвует в оценке правильности. UNKNOWN на INSUFFICIENT не считается правильным определённым решением. Counts UNKNOWN и ADAPTER_UNAVAILABLE включают unresolved и поэтому пересекаются с его count; `total_cases`, `resolved_gold` и `unresolved_gold` выводятся отдельно.

Кластерный bootstrap выбирает группы `group_id` с возвращением (1000 повторений, seed 17); в каждой выборке соответствующий знаменатель пересчитывается. В процентили входят только выборки с определённым знаменателем, их количество показано. Intent — описание происхождения, не эталон действия. Исходные контракты правил и цели ML различаются с новой референсной задачей; сравнение не доказывает ошибку метода по его собственному контракту.

Проверка логики: `cd experiments/local_guards_archive_annotation && python3 -m unittest test_score.py`. Тесты используют только искусственные записи и временный файл вектора.
