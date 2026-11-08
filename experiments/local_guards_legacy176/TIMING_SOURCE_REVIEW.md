# Независимая проверка таймеров до эксперимента

Ревьюер legacy176_timing_audit, readonly, без новых моделей/API. Exact176 IDs старой серииec93a1be проверены по исходному shadow-main архиву. У всех176 wall_s и временные метки; ошибок/stopped_by нет.

2343 guard_context интервала [t_ms-pause_ms,t_ms], без отрицательных начал и пересечений. Сумма/union пауз2910.5895s; raw wall sum8457.19s; очищенное wall sum5546.6005s, median31.2258s. Внешние delegate durations включают759 проверок: повторно вычитать их нельзя. Текущая transfer-P4 pause также включена в cut timestamp и удаляется до STOP. Последующий process_payment-P4 уже после перевода; новой точкой он не становится.

Сохранённая реализация runtime подтверждает порядок await gather → pause_ms → recorder.add(context). Её git-источник08b7b900cf48c3344dfbc039223a4b1e258e193f:finbot/finbot/probe/guards/runtime.py, SHA256df376da90125afdd461f67bf7dac9ad0a780bdf43d87d4e7a884b5e3124ef22e. Полное тождество отсутствующему631100dc не утверждается. Harness считает wall до финального snapshot и posthoc P7; started_at не начало trace-clock. Округление wall10ms, trace/pause0.1ms; максимальная погрешность очищенного wall около5.7ms.

Консервативные envelopes: предыдущий trace-event t_ms (либо0) до следующего non-guard события t_start_ms или t_ms. Они включают немного соседнего обычного кода. Дополнительная вычитаемая ширина33.5–69.1ms/эпизод, медиана52.7ms; для STOP20.9–51.6ms. Это диапазон оценки, не точный новый live замер.

Canonical AMEND05 SecJev проверен отдельно от ранних1.83/6.52s scores:704common→payload→inference hashes совпали,176P4 IDs exact. Source latency четырёх atomic questions уже входит в один checkpoint total. 701noncache+3cache; cache использует reused_reference_latency_ms, подтверждённый noncache reference. J_cur median18261.4427ms,p9526031.1357ms; J_seq median53945.2255ms,p9572401.4959ms. Source sum3497549.6395/10041481.9305ms. J_seq — четыре checkpoint totals, не дополнительное умножение на4.

OOF head singleton timings не сохранены: timings.json содержит batch measurements; profile.json —16sample/config/seed final heads. Они не подменяют176 индивидуальных OOF head times. Для таких heads полное время имеет неучтённый компонент; для фиксированного scalar threshold модели-head нет.
