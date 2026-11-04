# Проверка регрессии legacy176

Подготовка новой оценки на exact176 старой серии с SecJev. База7fb7902a, старые опубликованные методыec93a1be. Статус: **входы подготовлены, ожидают независимого допуска; новые правила ещё не запускались**.

[Протокол](PROTOCOL.md) фиксирует неизменные методы и метки. В source-prefixes сохранены только initial и prefix+current snapshot; labels и будущие таймеры находятся отдельно. Старый чистый builder сохранён побайтно в frozen_dataset.py; его исходные функции оценки исходов не вызываются. Конструктор воспроизводит исходные state176/176 и качество v1=78/83,0/93,v2=83/83,0/93.

FULL передаёт найденные native результаты, начальную БД и текущий серверный снимок. Server snapshot не превращается в tool result: source=server_context,evidence_kind=server_snapshot,snapshot_id без source_call_id. Согласованный новый снимок не отменяет ещё актуальное native доказательство; противоречивый/новый после устаревания заменяет его и не позволяет выбрать удобный старый факт. HOLD хранится отдельно и снимком approved не снимается.

PARTIAL сохраняет исходные сокращённые canonical поля, но без объектов/ledger/action arguments. Непривязанные скаляры сохраняются с отсутствующей связью субъекта; они не становятся разрешением. Для v1/v2 такой конструктор недоступен. Сокращённый вариант — проверка доступности данных, не основной результат.

Точные источники и hashes: source-manifest.json,input-manifest.json. Канонические записи старого SecJev не выдаются за новые прогоны. Предстоящий timing пересчёт отделит старые shadow pauses и наблюдаемое wall время; первичная новая точка только перед finstripe transfer, не перед последующим process_payment.

```sh
python -m unittest experiments.local_guards_legacy176.test_prepare -q
python -m experiments.local_guards_legacy176.audit_inputs
```

Подготовка источников: `python -m experiments.local_guards_legacy176.prepare --custody`; затем `python -m experiments.local_guards_legacy176.prepare`. Команды не запускают новые правила или модели, но проверяют прежний v1/v2 baseline. Для будущего вывода потребуется независимый approval с точным commit/input hash.
