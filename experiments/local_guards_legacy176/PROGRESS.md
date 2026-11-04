# Исполнение legacy176

- База7fb7902a, отдельный эксперимент, существующий изолированный worktree. Другие checkout только читаются.
- Подготовка и old baseline reproduction; новые guard predictions ещё не запускались.
- Независимый timing source audit выполняет legacy176_timing_audit(readonly).

- Input gate APPROVE7a571bd8/9ca45be9; new deterministic inference3872 rows sealed.
- First benchmark stopped on evidence-list ordering (no decision difference). Input hashes matched. Full multiset canonical comparison added with RED→GREEN control; incomplete timing attempt kept in/tmp, not evaluated.

Результаты зафиксированы:3872 deterministic predictions;58 080 локальных измерений (30 повторов), single/bulk parity. Исходныеv1/v2 воспроизвелись, новых моделей/API/обучения нет. Сохранённые SecJev сопоставлены по704 checkpoint input hashes; для cached входов использовано исходное reference-время. Новая оценка не меняет методы/входы/метки. Строгий старый target:83 положительных(39такжеlegacy-harm,44strict-only),93безопасных;45групп.58исключений разобраны:38неP4,20исходно неоднозначны.

Качество и полное время рассчитаны отдельно от inference; v3/v4.3 не сохранили v2 baseline. Успешное завершение отдельно от STOP, UNKNOWN не обнаружение, дополнительные бизнес-условия не меняют метки. К исходному48,052/47,675s wall не добавлялись новые guards поверх старых пауз: удалено2910,5895s суммарного ожидания, neutral31,515/31,226s. Консервативная граница и округление опубликованы отдельно. Ожидается независимый итоговый аудит точного коммита.
