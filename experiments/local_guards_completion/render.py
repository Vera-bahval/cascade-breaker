"""Render sealed completion scores, without inference, fitting or API calls."""
import argparse
from decimal import Decimal
import gzip
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
AXES = {'substantive_label': 'Содержательная допустимость',
        'process_label': 'Обязательные процедуры', 'action_label': 'Полное действие'}
CELLS = ('correct_allow', 'correct_block', 'wrong_allow', 'wrong_block',
         'insufficient_allow', 'insufficient_block', 'unknown', 'unavailable')
NAMES = {'completion/current': 'Новая текущая проверка',
         'completion/baseline': 'Новая базовая проверка', 'deepseek': 'Сохранённый DeepSeek',
         'constant_ALLOW': 'Всегда ALLOW', 'constant_BLOCK': 'Всегда BLOCK',
         'archive_profile/v3': 'Прежний архивный профиль v3',
         'archive_profile/v4.3': 'Прежний архивный профиль v4.3',
         'archive_profile/v3_archive': 'Прежний архивный профиль v3',
         'archive_profile/v4.3_archive': 'Прежний архивный профиль v4.3',
         'saved/native_core|rule|A': 'Прежние платёжные условия без Fraud',
         'saved/native|rule|A': 'Прежние платёжные условия с Fraud'}
ROUTES = {'local': 'локально', 'llm': 'DeepSeek',
          'block_then_llm': 'BLOCK локально, остальные DeepSeek',
          'decisive_then_llm': 'ALLOW/BLOCK локально, остальные DeepSeek',
          'allow_then_llm': 'ALLOW локально, остальные DeepSeek'}


def read(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt') as stream:
        return json.load(stream)


def fmt(value, digits=2):
    return 'нет данных' if value is None else f'{value:.{digits}f}'.replace('.', ',')


def pct(value, total):
    return 'нет данных' if value is None or not total else fmt(100 * value / total) + '%'


def name(key):
    if key in NAMES:
        return NAMES[key]
    if key.startswith('completion/'):
        return 'Текущая проверка; N14 исключён при неизвестной доступности' + ('; расширенные сведения' if '/expanded' in key else '')
    if key.startswith('oof/'):
        parts = key.split('/')
        model = {'lr': 'LR', 'catboost': 'CatBoost'}[parts[1]]
        variant = 'argmax, диагностика' if 'argmax' in parts[2] else 'порог по CAL'
        return f'Новая OOF {model}, {variant}' + ('; проверка процедур' if key.endswith('_process_gated') else '')
    original = key.removeprefix('saved/')
    if original.endswith('|rule|A'):
        return 'Прежние правила ' + original.split('|')[0]
    if original.startswith('v3_ml/'):
        model = original.split('/')[1]
        return 'Прежний ML v3, ' + {'structured_logistic': 'LR', 'structured_catboost': 'CatBoost',
            'text_diagnostic': 'TF-IDF, диагностика'}.get(model, model)
    if original.startswith('archive_ml/'):
        model = 'CatBoost' if 'catboost' in original else 'LR'
        target = 'исходное решение сценария' if 'scenario_decision' in original else 'базовые платёжные условия'
        return f'Прежняя архивная {model}, {target}'
    if original.startswith('frozen_revision2/'):
        model = 'CatBoost' if 'catboost' in original else 'LR'
        features = 'новые' if '__new__' in original else 'старые'
        sample = 'смесь' if '__mixed__' in original else 'архив'
        return f'Прежняя переобученная {model}, {features} признаки, {sample}'
    return key.removeprefix('saved/')


def table(headers, rows):
    escape = lambda v: str(v).replace('|', r'\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
        '|' + '|'.join('---' for _ in headers) + '|',
        *['| ' + ' | '.join(map(escape, row)) + ' |' for row in rows]])


def quality_table(items, n, identifiers=False, compact=False):
    data = []
    for key, m in items:
        if sum(m[field] for field in CELLS) != n:
            raise ValueError('quality cells do not partition cohort: ' + key)
        if (m['correct'] != m['correct_allow'] + m['correct_block'] or
                m['unavailable'] != m['model_unavailable'] + m['adapter_unavailable']):
            raise ValueError('inconsistent quality totals: ' + key)
        data.append([key if identifiers else name(key), f"{m['correct_allow']} / {m['correct_block']}",
            f"{m['wrong_allow']} / {m['wrong_block']}", m['unknown'],
            f"{m['model_unavailable']} / {m['adapter_unavailable']}",
            f"{m['insufficient_allow']} / {m['insufficient_block']}",
            f"{m['correct']} / {n} ({pct(m['correct'], n)})"])
    headers = ['Метод', 'Верно ALLOW / BLOCK', 'Ошибка ALLOW / BLOCK', 'UNKNOWN',
        'Нет модели / входа', 'При INSUFFICIENT ALLOW / BLOCK', 'Правильных ответов / n']
    if compact:
        if any(row[4] != '0 / 0' for row in data):
            raise ValueError('cannot hide nonzero unavailability')
        headers.pop(4)
        for row in data:
            row.pop(4)
    return table(headers, data)


def interval_table(items):
    def bounds(value):
        return 'нет данных' if value is None else ' / '.join(fmt(100 * x) + '%' for x in value)

    return table(['Вектор', 'Допустимые / недопустимые', 'Определённые метки',
        '95%: правильное покрытие', '95%: FPR', '95%: разница покрытия с DeepSeek'],
        [[key, f"{m['safe_n']} / {m['bad_n']}", m['resolved_n'],
          bounds(m['intervals']['correct_coverage_ci95']),
          bounds(m['intervals']['false_block_rate_ci95']),
          bounds(m['intervals']['difference_vs_saved_deepseek_ci95'])] for key, m in items])


def primary(s):
    return [key for key in s['p4']['primary_methods'] if not s['p4']['methods'][key]['diagnostic']]


def compact(s):
    keys = ['completion/current', 'deepseek', 'oof/lr/calibrated',
        'oof/catboost/calibrated', 'constant_ALLOW', 'constant_BLOCK']
    return [key for key in keys if key in s['p4']['methods']]


def interruptions(s):
    data = []
    for key in compact(s):
        m = s['p4']['methods'][key]['axes']['substantive_label']
        data.append([name(key), f"{m['wrong_block']} / {m['safe_n']}",
            f"{m['safe_deferral']} / {m['safe_n']}",
            f"{m['author_legit_not_allowed']} / {m['author_legit_n']}",
            f"{m['review_benign_not_allowed']} / {m['review_benign_n']}"])
    return table(['Метод', 'BLOCK допустимых действий', 'Их отсрочки / нет ответа',
        'Без ALLOW, авторские legit', 'Без ALLOW, benign по пересмотру'], data)


def cascade_table(items, identifiers=False):
    data = []
    for key, mode, row in items:
        sub, full = (row['axes'][axis] for axis in ('substantive_label', 'action_label'))
        data.append([(key if identifiers else name(key)) + '; ' + ROUTES[mode],
            f"{sub['wrong_allow']} / {sub['wrong_block']}",
            f"{full['wrong_allow']} / {full['wrong_block']}", row['final_deferrals'],
            row['local_decisions'], row['llm_calls'], '$' + fmt(Decimal(row['historical_api_usd']), 9),
            row['latency_n'], fmt(row['p50_ms']) + ' / ' + fmt(row['p95_ms'])])
    return table(['Метод и маршрут', 'Содержание: ошибка ALLOW / BLOCK',
        'Полное: ошибка ALLOW / BLOCK', 'Нет решения', 'Локальные решения',
        'Вызовы LLM', 'Архивная цена API', 'n времени', 'p50 / p95, мс'], data)


def selected_cascades(s):
    for key, modes in [('completion/current', ('local', 'block_then_llm', 'decisive_then_llm')),
                       ('deepseek', ('llm',)), ('oof/lr/calibrated', ('local', 'block_then_llm')),
                       ('oof/catboost/calibrated', ('local', 'block_then_llm'))]:
        for mode in modes:
            yield key, mode, s['p4']['cascades'][key][mode]


def legacy_table(legacy):
    return table(['Метод, прежний контракт', 'Верно ALLOW', 'Верно BLOCK', 'Ошибка ALLOW',
        'Ошибка BLOCK', 'UNKNOWN', 'Нет входа', 'Без ALLOW допустимых', 'Верно'],
        [[('Контрфактическое исключение N14 по метке конвертера' if 'unknown_unavailable' in key else name(key)),
          m['allow'] - m['wrong_allow'], m['tp'], m['wrong_allow'], m['false_block'],
          m['unknown'], m['unavailable'], f"{m['safe_stop']} / {m['safe']}",
          f"{m['correct']} / {m['n']}"] for key, m in legacy['methods'].items()])


def time_table(legacy, full=False):
    methods = [('completion/', legacy['full_time'])]
    if full:
        methods = [('saved/', legacy['previous_full_time']),
            ('archive_profile/', legacy['archive_profile_full_time']), *methods]
    data = []
    baseline = legacy['baseline']['clean']
    data.append(['Архивное выполнение без прежних ожиданий', f"не разделено / {baseline['n']}",
        fmt(baseline['mean_s']) + ' / ' + fmt(baseline['median_s']), 'см. прежний источник', 'нет', 'нет'])
    for prefix, records in methods:
        for key, row in records.items():
            end, completed = row['terminal'], row['completed']
            stop = row.get('stopped', row.get('blocked'))
            if stop is None:
                raise ValueError('missing task STOP timing: ' + key)
            added = row['paired_completed_overhead']
            data.append([name(prefix + key), f"{completed['n']} / {end['n']}",
                fmt(end['mean_s']) + ' / ' + fmt(end['median_s']),
                fmt(completed['mean_s']) + ' / ' + fmt(completed['median_s']),
                f"{stop['n']}: {fmt(stop['mean_s'])} / {fmt(stop['median_s'])}",
                fmt(added['mean_s']) + ' / ' + fmt(added['median_s'])])
    return table(['Метод', 'Завершено / n', 'До завершения или STOP, среднее / медиана, с',
        'Завершённые, среднее / медиана, с', 'STOP: n, среднее / медиана, с',
        'Добавка на тех же завершённых, с'], data)


def curve_points(curves):
    result = {}
    for method, records in curves['methods'].items():
        points = []
        for row in records:
            m = row['metrics']
            if not m['n'] or m['safe_n'] < 0 or m['correct'] > m['n']:
                raise ValueError('invalid OOF curve denominator')
            point = (100 * m['correct'] / m['n'], m['wrong_allow'],
                100 * m['safe_stop'] / m['safe_n'] if m['safe_n'] else None)
            if not all(math.isfinite(v) for v in point if v is not None):
                raise ValueError('nonfinite OOF curve point')
            points.append(point)
        result[method] = points
    return result


def plot_curves(curves, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams['svg.hashsalt'] = 'finbot-completion-oof'
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), constrained_layout=True)
    for model, values in curve_points(curves).items():
        label = {'lr': 'LR', 'catboost': 'CatBoost'}.get(model, model)
        axes[0].scatter([p[0] for p in values], [p[1] for p in values], s=15, alpha=.35, label=label)
        known = [p for p in values if p[2] is not None]
        axes[1].scatter([p[0] for p in known], [p[2] for p in known], s=15, alpha=.35, label=label)
    for ax in axes:
        ax.set_xlabel('Правильные локальные решения, % всех состояний')
        ax.set_xlim(-1, 101)
        ax.grid(alpha=.2)
        ax.legend()
    axes[0].set_ylabel('Ошибочные ALLOW, число')
    axes[1].set_ylabel('Допустимые действия без ALLOW, %')
    fig.suptitle('OOF: все заданные пары порогов, полная цель действия')
    for suffix in ('png', 'svg'):
        path = Path(output) / ('OOF_CURVES.' + suffix)
        fig.savefig(path, dpi=180,
                    metadata={'Date': None} if suffix == 'svg' else None)
        if suffix == 'svg':
            path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()) + '\n')
    plt.close(fig)


def build_report(s, cost, policy_n):
    n, a, p4, ml = s['p4']['n'], s['annotation'], s['p4'], s['ml']
    sensitivity, agreement = p4['sensitivity'], a['agreement']
    target_table = table(['Цель разметки', 'ALLOW', 'BLOCK', 'INSUFFICIENT'],
        [[title, *(a['counts'][axis].get(k, 0) for k in ('ALLOW', 'BLOCK', 'INSUFFICIENT'))]
         for axis, title in AXES.items()] +
        [['Без неизвестного N14: ' + title, *(sensitivity['target_counts'][axis].get(k, 0) for k in ('ALLOW', 'BLOCK', 'INSUFFICIENT'))]
         for axis, title in AXES.items() if axis != 'substantive_label'])
    main_keys = ['completion/current', 'deepseek',
        'saved/native_core|rule|A', 'saved/native|rule|A', 'archive_profile/v4.3_archive',
        'saved/archive_ml/scenario_decision-lr-17|raw|A',
        'oof/lr/calibrated', 'oof/catboost/calibrated', 'constant_ALLOW', 'constant_BLOCK']
    quality = quality_table([(key, p4['methods'][key]['axes']['substantive_label']) for key in main_keys], n, compact=True)
    legacy_keys = ['archive_profile/v4.3_archive', 'saved/v1', 'saved/v2',
        'saved/Jev27B_MLX_NVFP4_cached_fixed05', 'saved/SecJev9B_MPS_mixed_fixed05']
    main_legacy = dict(s['legacy176'], methods={k: s['legacy176']['methods'][k]
        for k in legacy_keys if k in s['legacy176']['methods']})
    third_n = agreement['disagreements'] + len(agreement['audited_agreement_ids']) + a['additional_agreement_review_n']
    charged, selected = cost['charged_run'], cost['selected542']
    current = p4['methods']['completion/current']['axes']['substantive_label']
    old_current = s['legacy176']['methods']['completion/current']
    sensitivity_table = quality_table(
        [(k, r['axes']['action_label']) for k, r in sensitivity['methods'].items() if '/expanded' not in k] +
        [(k, axes['action_label']) for k, axes in sensitivity['baselines_scored_on_sensitivity_gold'].items()], n, compact=True)
    source = p4['source_expectation']
    source_table = quality_table([(key, source['methods'][key]['metrics']) for key in compact(s)], n, compact=True)
    early = table(['Режим', 'Условие остановки', 'Эпизоды', 'Первый BLOCK', 'Первый UNKNOWN',
        'Без местной остановки', 'Достигнутые точки'],
        [[mode, policy, row['episodes'], seq.get('blocked_episodes', 0), seq.get('deferred_episodes', 0),
          seq.get('no_local_stop', 0), seq['reached_points']]
         for mode, row in s['early']['modes'].items() for policy, seq in row['sequential'].items()])
    report = f'''# Локальные проверки FinBot без дополнительной LLM

Цель исследования: установить, какую часть решений дополнительного LLM-защитника можно правильно принимать правилами или локальным ML, сколько обращений к LLM это экономит и какой ценой для обычных задач. Штатные агенты FinBot остаются в процессе.

## Практический результат

В таблицах ALLOW означает разрешение действия, BLOCK запрет, UNKNOWN передачу на дальнейший разбор. INSUFFICIENT означает, что для действия не определён правильный ответ.

Проверка слишком часто останавливает допустимые по содержанию платежи: из {current['safe_n']} разрешает {current['correct_allow']}, запрещает {current['wrong_block']} и оставляет {current['safe_deferral']} без решения.
Из {current['bad_n']} недопустимых запрещает {current['correct_block']} и ошибочно разрешает {current['wrong_allow']}.

Для одних и тех же {n} состояний перед переводом, точка P4, размечены три цели.
Содержательная цель оценивает обоснованность платежа; процедурная включает обязательные проверки; полная объединяет их.

{target_table}

Налоговая проверка N14 входит в процедурную и полную цели.
Правильный BLOCK по полной цели может означать пропущенную налоговую процедуру и сам по себе не доказывает обнаружение мошенничества, успешную инъекцию или предотвращённый ущерб.
Основная таблица использует содержательную цель; другие цели приведены в приложении.

При полном эталоне правила дают 536 правильных решений из 542, LR 539, CatBoost 537, а постоянный BLOCK 536. Эти близкие результаты нужно читать вместе с преобладанием запретов в эталоне.
Подробные таблицы полной и процедурной целей сохранены в приложении.

На прежней серии текущая проверка выдаёт {old_current['block']} BLOCK и {old_current['allow']} ALLOW из {s['legacy176']['n']}; среди {old_current['safe']} прежде допустимых действий без ALLOW остаются {old_current['safe_stop']}.
При основном процедурном контракте самостоятельное продолжение обычных задач здесь отсутствует. Общий запрет не считается улучшением антифрода.

{interruptions(s)}

«Без ALLOW» объединяет запрет, UNKNOWN и недоступный ответ. Это прерванные или отложенные действия, а не FPR.
В этом архиве исходно обычные запросы также приводят к недопустимым платёжным действиям; категория запроса не определяет допустимость действия.
Категории legit и benign описывают происхождение запроса. Полная метка учитывает обязательные процедуры, содержательная отдельно оценивает обоснованность платежа и отрицательной рекомендации.
FPR, доля ошибочных запретов, считается среди допустимых действий соответствующей цели. Переданный сохранённой LLM UNKNOWN полезен как отсрочка, но правильным локальным ответом не считается.

## Данные и разметка

Основная серия состоит из {n} состояний и {p4['groups']} групп сценариев.
Использованы раскрытый архив, сохранённые ответы и исходные журналы до предлагаемого действия.
Новых запусков исполнителя и изучаемых LLM нет. Ретроспективная проверка не измеряет живой адаптивный каскад или обобщение на новый закрытый набор.

Для {policy_n} состояний извлечены системные инструкции соответствующего вызова.
Остальные используют явно объявленные исторические правила FinBot, включая послабление новым поставщикам до 1000 долларов.
Доступность налогового инструмента наблюдается в {sensitivity['observed_availability']} состояниях, в {sensitivity['assumed_availability']} принята по допущению.
Отдельный анализ исключает N14 только при фактически неизвестной доступности, сохраняя известные ошибки и успешные вычисления.

{sensitivity_table}

Этот анализ меняет условие применимости налоговой проверки, а не объявляет инструмент недоступным. Соблюдение действительной обязательной процедуры остаётся самостоятельной задачей контроля. Частота пропусков TaxCalc сама по себе не доказывает ошибку постановки или причину поведения модели.

Здесь все строки оценены по полной цели без неизвестного N14. У текущей проверки и DeepSeek сохранены исходные ответы; отдельная строка текущей проверки меняет и само допущение N14.
Так отделяется влияние допущения на решения от изменения оценочной цели.

Два независимых чтения исходников дали {agreement['disagreements']} расхождений.
Третий разбор охватил их, выборку из {len(agreement['audited_agreement_ids'])} первоначально совпавших записей и ещё {a['additional_agreement_review_n']} после расширения проверки согласий: всего {third_n}.
Разметка выполнена с помощью моделей, не является человеческим эталоном и не имеет технической изоляции рецензентов.
Критерии закреплены до новых предсказаний; N01–N08 унаследованы с четырьмя исправлениями N07 по исторической сигнатуре инструмента.

Исходные ожидания сценариев сохранены отдельно.
Для 310 действий генератор не задаёт абсолютное expected-pay/stop; это not_defined, а не незавершённая реконструкция.
Категория injection не превращается автоматически в BLOCK для каждого последующего действия.
В условии D обычный текст счёта сопровождается BEC-контекстом: непроверенной сменой счёта по письму и несовпадением владельца с компанией.
В E смену подтвердили обратным звонком и банковским письмом. Этот контекст сохраняется независимо от оценки текста счёта как benign.

Успешный hold, reject или escalate для того же счёта действует до успешной проверки, начавшейся после удержания.
Заметка, approved и завершение прежней проверки удержание не снимают. Обоснованность рекомендации оценивается отдельно.
Выше 10 000 долларов политика допускает деловое исключение ниже жёсткого максимума без нового реестра ручных разрешений.
Отклонение суммы требует оценки контекста и не создаёт неизменяемый запрет; оплаченная история исключает текущий счёт.

[Исходные ожидания](local_guards_completion/SOURCE_TARGETS.md), [исправления N07](local_guards_completion/CORE_REVIEW.md), [протокол](local_guards_completion/PROTOCOL.md) и [заморозка разметки](local_guards_completion/labels-freeze.json) сохраняют основания и хеши.

## Исходная цель авторского теста

Исходная цель сценария оценивается отдельно от трёх целей платёжной допустимости.
Исходная цель определена для {source['defined_n']} действий: {source['original_expected_counts']['ALLOW']} ALLOW и {source['original_expected_counts']['BLOCK']} BLOCK. Ещё {source['not_defined_n']} имеют not_defined.
В покрытии учитывается вся серия из {source['n']} состояний; ошибки используют только определённые ожидания.
Столбец INSUFFICIENT здесь означает отсутствие исходного ожидания, а не новую метку содержательной допустимости. Injection не преобразован в BLOCK.

{source_table}

Эта таблица отвечает на вопрос о воспроизведении авторской цели. Она не заменяет проверку действующей политики и не доказывает финансовый вред.

## Сравнение по содержательной допустимости

В покрытии учитывается вся серия из {n} состояний. Ошибки считаются только по определённым меткам.
Решения при INSUFFICIENT показаны отдельно; недоступная модель не объединена с UNKNOWN или отсутствующим входом.
Интервалы в приложении получены повторной выборкой групп архива и описывают только эту выборочную неопределённость. Неопределённость разметки и допущений в них не входит.
В полной цели всего {a['counts']['action_label'].get('ALLOW', 0)} допустимых действий; этого недостаточно для точной оценки FPR или выводов об обобщении.

{quality}

Сохранённые LR/CatBoost v3 возвращают UNKNOWN на всех 542 состояниях. Такой же результат у шести вариантов прежнего переобучения; ещё два в основном запрещают действия или воздерживаются. Их построчные результаты находятся в приложении вместе с диагностикой и всеми порогами. Массовое воздержание показывает ограничение этих сохранённых систем при данном контракте, но не доказывает неспособность самих классификаторов решать задачу.

Прежние проверки исходных платёжных условий с Fraud и без него, сохранённые модели, DeepSeek и константы сохранены как контрольные системы.
Прежний архивный профиль показан как историческая версия той же проверки, а не новая независимая архитектура.
Новые базовая и текущая проверки используют один восстановленный вход и общую логику. Базовая сравнивает сумму и получателя с исходными значениями, текущая с актуальными. Совпадение их результатов ожидаемо при общей логике и не даёт независимого подтверждения.

Новые LR и CatBoost обучены на полной цели действия, в которой часто решает налоговая процедура.
Их качество по содержательной цели диагностическое: цель обучения и оцениваемая содержательная цель различаются.
Эта таблица не определяет победителя архитектур антифрода с одинаковой целью обучения.
Вариант «проверка процедур» добавляет общий процедурный контроль к классификатору; его вклад выделен в приложении.

## Обучение и пороги новых моделей

Использованы пять внешних разбиений по {p4['groups']} группам, seed 17, и первое из четырёх внутренних разбиений для CAL.
OOF означает, что каждое состояние оценивает модель, не обучавшаяся на его группе. FIT используется для обучения, CAL для подбора порогов; предобработка обучается только на FIT.
LR использует C 1; CatBoost 200 деревьев, глубину 3, скорость 0,03 и L2 5.
Предусмотрено {ml['expected_model_slots']} обучений, фактически выполнено {ml['actual_fits']}; перебор конфигураций не проводился.
В приложении {len(p4['methods'])} векторов решений, включая сохранённые конфигурации, диагностику и варианты процедурного контроля. Каждый такой вектор не означает отдельное новое обучение.
При недостатке классов модель недоступна. При недопустимом CAL-пороге доступная модель сохраняет вероятности и возвращает UNKNOWN.

Порог CAL максимизирует правильные определённые ответы при отсутствии ошибочных ALLOW и не более пяти процентов допустимых действий без ALLOW на CAL.
Внешняя тестовая часть пороги не выбирает. Равенство вероятностей даёт UNKNOWN.
На графике показаны все заданные заранее пары порогов OOF, включая полное воздержание. Это описательные точки, а не выбор лучшего тестового порога.

![OOF: покрытие и ошибки на полной цели](local_guards_completion/OOF_CURVES.png)

[SVG для экспорта](local_guards_completion/OOF_CURVES.svg). Все части CAL и совпадения признаков находятся в приложении.
Разделение по группам не гарантирует уникальности признаков: одинаковые наборы структурных признаков могут повторяться в FIT и тестовой части.
[Прежнее переобучение](local_guards_ml_retrain/REPORT.md) сохранено отдельно; его результаты здесь не объявлены новыми.

## Маршруты с сохранённой LLM

Локальный режим принимает ALLOW и BLOCK, оставляя UNKNOWN нерешённым.
В режиме «BLOCK локально» остальные состояния передаются сохранённому DeepSeek.
Приложение также показывает маршруты, принимающие оба определённых ответа или только локальный ALLOW.
Вызов LLM после UNKNOWN не добавляет правильный локальный ответ; итог каскада оценивается отдельно.

{cascade_table(selected_cascades(s))}

Два столбца ошибок относятся к содержательной и полной целям на тех же {n} действиях.
Время вычислено парно на измеренной части {len(p4['latency_sample'])} заранее выбранных состояний; фактическое число указано в столбце n времени. Затем вычислены p50 и p95; отдельные квантили не складываются.
p50 обозначает медиану, p95 время, в которое укладываются 95 процентов измерений.
Новые локальные компоненты измерены по 30 повторов. Для старых систем сохранена прежняя область измерения; доли миллисекунды не доказывают превосходства реализации.
Неизмеренное время остаётся «нет данных». Локальное вычисление не оценено в долларах.

## Прежняя серия из {s['legacy176']['n']} эпизодов

Прежние метки, предсказания и контрольные системы не менялись.
Их более строгие критерии и ошибки после неуспешного Fraud отличаются от новой разметки; объединять эту серию с {n} состояниями нельзя.
Новые проверки добавлены к неизменённым входам для регрессии.
Для всех 176 эпизодов исходные списки инструментов Payments подтверждают доступность TaxCalc. Конвертер помечает доступность как assumed из-за потери полей связи, но исходные списки подтверждают наличие инструмента.
В приложении исключение N14 по метке конвертера сохранено как контрфактическая проверка чувствительности. Она не отменяет подтверждённую исходниками доступность инструмента.

{legacy_table(main_legacy)}

Новые базовая и текущая проверки здесь совпадают с постоянным BLOCK: все 176 действий остановлены, включая 93 допустимых по прежним меткам. Старые v4 и v4.2 возвращают UNKNOWN во всех 176 случаях; v3 и v4.3 запрещают 68 и передают на разбор 108. Полная таблица, остальные SecJev и контрфактическое исключение N14 находятся в приложении.

Среднее время до STOP у новой текущей проверки составляет {fmt(s['legacy176']['full_time']['current']['terminal']['mean_s'])} с, медиана {fmt(s['legacy176']['full_time']['current']['terminal']['median_s'])} с. Завершённых задач нет. Архивная база без прежних ожиданий занимает в среднем {fmt(s['legacy176']['baseline']['clean']['mean_s'])} с; по этой разнице нельзя судить об ускорении успешного выполнения.

Среднее и медиана до завершения или STOP включают ранние остановки и не означают ускорения успешно выполненной задачи.
В приложении раздельно указаны времена завершённых задач, остановок и добавка проверяющего на тех же эпизодах для прежних методов.
UNKNOWN не считается завершением или доказанным провалом всего задания: это неразрешённая точка проверки.
Время использует архивное продолжение с исключёнными прежними ожиданиями защитника и добавленной локальной работой; нового исполнения агента нет.

## Ранние действия P0–P3

Прежние 128 ранних меток оцениваются отдельно от новой платёжной разметки.
Первый BLOCK и первый ответ, отличный от ALLOW, задают разные условные траектории.
При учёте только первого BLOCK неразрешённые UNKNOWN пропускаются; расчёт не доказывает достижимость следующего действия при реальном исполнении.

{early}

Сохранённый ответ DeepSeek для P4 не переносится на ранние точки. Новых ранних вызовов LLM нет.
Условная остановка не доказывает предотвращение адаптирующейся атаки; ошибки и достигнутые точки приведены в приложении.

## Недоработки FinBot и ограничения постановки эксперимента

FinBot оставляет часть платёжных условий на усмотрение модели, а учебные инструменты упрощают исполнение. Это осложнило выбор однозначного правильного ответа: успешный вызов, соблюдение инструкции и обоснованный платёж пришлось оценивать отдельно. Ниже приведён код версии, сохранённой в этом репозитории. Для исторических исполнений приоритет имеют извлечённые инструкции и исходные журналы; наличие кода в checkout не доказывает, что все эпизоды исполнялись именно на нём.

### Налоговая проверка описана отдельно от основного маршрута

В [Payments](https://github.com/Vera-bahval/cascade-breaker/blob/31d0351d7fee2fb1f7edb3f3b12d3ccb9bd43e86/finbot/finbot/agents/specialized/payments.py#L118) основной маршрут состоит из получения счёта, проверки поставщика, перевода и отметки оплаты. TaxCalc в этих шагах отсутствует. Ниже [отдельная строка инструкции](https://github.com/Vera-bahval/cascade-breaker/blob/31d0351d7fee2fb1f7edb3f3b12d3ccb9bd43e86/finbot/finbot/agents/specialized/payments.py#L169) требует проверить применимый налог, если инструмент доступен. [Подключение TaxCalc](https://github.com/Vera-bahval/cascade-breaker/blob/31d0351d7fee2fb1f7edb3f3b12d3ccb9bd43e86/finbot/finbot/agents/specialized/payments.py#L76) делает его доступным агенту, но не запускает расчёт автоматически.

Сам [калькулятор](https://github.com/Vera-bahval/cascade-breaker/blob/31d0351d7fee2fb1f7edb3f3b12d3ccb9bd43e86/finbot/finbot/mcp/servers/taxcalc/server.py#L41) считает налог кодом по сумме, юрисдикции и категории; для услуг предусмотрено освобождение от налога. Параметры вызова выбирает агент. Поэтому факт успешного расчёта не подтверждает, что категория подходит счёту. В эксперименте успешный связанный вызов принят как свидетельство выполнения N14. Этот способ проверки и допущение о доступности инструмента существенно влияют на эталон. Массовый пропуск шага требует отдельного анализа соблюдения процесса; причина пропусков и их связь с атаками не установлены.

### HOLD не превращён в самостоятельный запрет платёжного инструмента

[flag_invoice_for_review](https://github.com/Vera-bahval/cascade-breaker/blob/31d0351d7fee2fb1f7edb3f3b12d3ccb9bd43e86/finbot/finbot/tools/data/fraud.py#L168) записывает рекомендацию в agent_notes. Для hold и escalate статус сохраняется; reject меняет его только из submitted или processing. Между тем [process_payment](https://github.com/Vera-bahval/cascade-breaker/blob/31d0351d7fee2fb1f7edb3f3b12d3ccb9bd43e86/finbot/finbot/tools/data/payment.py#L82) проверяет approved, но не применяет рекомендации Fraud как запрет. Таким образом, approved не доказывает отсутствия действующего удержания.

Для оценки понадобилась история успешных рекомендаций и последующих проверок. Простая проверка текущего статуса теряет этот запрет; требование нового независимого реестра снятия HOLD, напротив, добавило бы условие, которого данный код не реализует. Принятый порядок снятия удержания описан в протоколе. Обоснованность самой рекомендации проверяется отдельно.

### Завершённый перевод и статус paid не удостоверяют друг друга

В [FinStripe.create_transfer](https://github.com/Vera-bahval/cascade-breaker/blob/31d0351d7fee2fb1f7edb3f3b12d3ccb9bd43e86/finbot/finbot/mcp/servers/finstripe/server.py#L47) явная проверка суммы ограничена положительностью. Функция создаёт запись со статусом completed, не сверяя в своём теле сумму и получателя со счётом, статус approved, HOLD или результат TaxCalc. Это учебное моделирование перевода.

Отдельный [process_payment](https://github.com/Vera-bahval/cascade-breaker/blob/31d0351d7fee2fb1f7edb3f3b12d3ccb9bd43e86/finbot/finbot/tools/data/payment.py#L47) принимает payment_reference как строку и переводит approved в paid; наличие соответствующего перевода в этой функции не проверяется. Поэтому успешный результат инструмента или paid недостаточны как эталон корректной оплаты. В исследовании отдельно проверяются предложенный перевод и подтверждение для записи оплаты. Вывод о предотвращении реального финансового ущерба по этому симулятору сделать нельзя.

### Порядок работы и передача доверия описаны текстом

[Рецепт оркестратора](https://github.com/Vera-bahval/cascade-breaker/blob/31d0351d7fee2fb1f7edb3f3b12d3ccb9bd43e86/finbot/finbot/agents/orchestrator.py#L126) требует сначала Invoice, затем Fraud и Payments. Явное условие шага Payments ссылается на одобрение Invoice; результат Fraud приходится учитывать из переданного контекста. Там же [предписана дословная передача task_summary](https://github.com/Vera-bahval/cascade-breaker/blob/31d0351d7fee2fb1f7edb3f3b12d3ccb9bd43e86/finbot/finbot/agents/orchestrator.py#L168), без фильтрации, вместе с compliance directives и operational context.

Для эксперимента это означает, что успешное делегирование не удостоверяет правильность оценки Fraud, а инструкция внутри переданного отчёта не становится автоматически доверенным разрешением. Пришлось сохранять происхождение сообщений, порядок вызовов и различать завершение проверки, её рекомендацию и последующее действие. Само наличие такого пути передачи контекста ещё не доказывает успех инъекции в конкретном эпизоде.

### Бизнес-исключения не дают готового бинарного эталона

[Invoice](https://github.com/Vera-bahval/cascade-breaker/blob/31d0351d7fee2fb1f7edb3f3b12d3ccb9bd43e86/finbot/finbot/agents/specialized/invoice.py#L125) допускает исключения по бизнес-потребностям выше порога ручного рассмотрения. [Fraud](https://github.com/Vera-bahval/cascade-breaker/blob/31d0351d7fee2fb1f7edb3f3b12d3ccb9bd43e86/finbot/finbot/agents/specialized/fraud.py#L128) требует оценивать отклонение от типичных счетов и изменения банковских данных, но эти строки не определяют единый алгоритм установления обоснованной цены или бизнес-исключения.

Это ограничение формализации политики, а не основание запрещать каждое исключение. Безусловный запрет выше 10 000 долларов или сравнение только со средним значением истории изменили бы исходные правила. Поэтому дополнительная разметка учитывает контекст и сохраняет INSUFFICIENT там, где обоснованность платежа установить не удалось.

### Что относится к архиву и нашему исследованию

Отсутствие абсолютного pay/stop-эталона у 310 сценариев относится к [генераторам и анализу исходного бенчмарка](local_guards_completion/SOURCE_TARGETS.md), а не к платёжному коду FinBot. Различия исторических версий и неполные сведения о доступности инструментов потребовали извлечения инструкций и анализа чувствительности. Потерянные связи сессий и ролей, ошибки обработки начала и завершения проверок относились к нашим адаптерам; их исправления описаны в [проверке кода](local_guards_completion/CODE_REVIEW.md) и [аудите источников](local_guards_completion/SOURCE_ADMISSION.md).

Эти обстоятельства не делают весь пересчёт некорректным. Они объясняют, почему нельзя было взять статус paid, успешный ответ агента или категорию injection как единый правильный ответ. Корректное сравнение потребовало явных условий, отдельных целей оценки и дополнительной разметки. Полученные результаты относятся к этим зафиксированным условиям.

## Ответы на вопросы исследования

### Самостоятельные решения

Локально удаётся принимать правильные решения, но долю полезной замены LLM нельзя выражать одним процентом. При полном контракте текущая проверка даёт 536 правильных ответов из 542, из них только два разрешения. По содержательной цели у неё 319 правильных ответов, столько же у постоянного BLOCK. Для исходных авторских ожиданий она правильно решает 89 случаев из всей серии, DeepSeek 159; ещё 310 не имеют абсолютного авторского эталона. Поэтому большая доля локальных решений сама по себе не подтверждает выполнение исходной цели.

### Правила перед дополнительной LLM

Как предварительный этап правила заметно сокращают обращения к защитнику. Маршрут с локальным BLOCK оставляет 8 вызовов DeepSeek вместо 542 и $0,034691784 исторической цены вместо $2,321758440. Он сохраняет 185 запретов содержательно допустимых действий. Если принимать и локальный ALLOW, LLM остаётся для четырёх UNKNOWN, но два ошибочных разрешения проходят локально. Передача неопределённого случая LLM полезна; надёжность такого каскада зависит также от правильности локальных запретов и разрешений.

### Цена для обычных задач

Цена для обычных задач пока слишком велика для самостоятельного применения текущей проверки. Она запрещает 185 из 191 содержательно допустимого действия и оставляет четыре без решения; DeepSeek запрещает 26. Даже при исключении N14 для неизвестной доступности инструмента остаются шесть ошибочных разрешений, а 221 случай требует дальнейшего разбора. Этот вариант показывает возможность более широкого делегирования LLM, но отдельно меняет контракт налоговой проверки.

### Правила и модели

Преимущество правил над ML или ML над LLM исследование не установило. Новые LR и CatBoost обучены на полной цели с шестью допустимыми действиями. Их 539 и 537 правильных ответов близки к 536 у постоянного BLOCK; по содержательной цели они дают по 322 правильных ответа, DeepSeek 329. Разные цели обучения и раскрытый архив ограничивают сравнение архитектур. Прежняя архивная LR по содержательной оценке даёт 373 правильных ответа, но допускает 76 ошибочных ALLOW и 61 ошибочный BLOCK; её большее покрытие также не означает безопасную замену защитника.

### Время решения и всей задачи

Локальная проверка существенно быстрее дополнительного запроса LLM: на парной выборке из 30 состояний медиана текущей проверки около 1,36 мс, сохранённого DeepSeek около 2051 мс. Это задержка решения. На старых 176 задачах новая проверка останавливает всё, поэтому ускорение успешно завершённой задачи этим результатом не подтверждено.

Итог исследования: структурные правила подходят для проверки конкретных обязательных условий и для передачи нерешённых случаев защитнику. Проверенные конфигурации пока не обеспечивают широкую самостоятельную замену дополнительной LLM с приемлемой ценой для обычных задач. Сокращение числа запросов подтверждено ретроспективным расчётом; качество живого адаптивного каскада остаётся непроверенным. Причина редких вызовов TaxCalc и необходимость конкретного способа налоговой проверки для каждого счёта отдельно не установлены.

## Стоимость и воспроизводимость

Полный сохранённый запуск защитника содержит {charged['unique_query_ids']} оплаченных запросов на ${charged['charges']['rounded_9dp_usd']}.
Выбранные {selected['unique_query_ids']} ответа входят в тот же запуск и стоят ${selected['charges']['rounded_9dp_usd']}; это другая область учёта, а не дополнительное списание.
Сверены сохранённые ответы, запросы и read-only ledger по идентификаторам и фактической цене без сегодняшнего пересчёта тарифов.
Новых изучаемых вызовов API в этой работе {s['new_api_calls']}. Локальные вычисления и обучение ML не оценены в долларах.
Аудит не заменяет выписку провайдера и не восстанавливает все расходы первоначального исполнителя FinBot.

[Аудит стоимости](local_guards_completion/COST_AUDIT.md) содержит источники и ограничения учёта.
[Полное приложение](local_guards_completion/TABLES.md) содержит все векторы, цели, проверки процедур, интервалы и режимы допущений.
[Итоговый JSON](local_guards_completion/results-summary.json) хранит точные значения и хеши входов.
[Независимая проверка](local_guards_completion/FINAL_AUDIT.md) фиксирует проверенные источники и границы выводов; [порядок воспроизведения](local_guards_completion/README.md) содержит точные команды.
Отчёт строится командой `python3 -m experiments.local_guards_completion.render`; прежний update_report перенаправляет сюда.
'''
    return '\n\n'.join(block if block.startswith(('#', '|', '![')) else ' '.join(block.splitlines())
        for block in report.split('\n\n'))


def build_tables(s, curves, feature_audit):
    n = s['p4']['n']
    parts = ['# Полные результаты завершения', '',
        'Знаменатель указан для каждой цели. UNKNOWN и недоступность не являются правильным локальным ответом.', '']
    for axis, title in AXES.items():
        parts += ['## ' + title, '', quality_table([(k, r['axes'][axis]) for k, r in s['p4']['methods'].items()], n, identifiers=True), '']
        parts += [interval_table([(k, r['axes'][axis]) for k, r in s['p4']['methods'].items()]), '']
    parts += ['## Исходные ожидания сценариев, все векторы', '',
        quality_table([(k, r['metrics']) for k, r in s['p4']['source_expectation']['methods'].items()], n, identifiers=True), '',
        interval_table([(k, r['metrics']) for k, r in s['p4']['source_expectation']['methods'].items()]), '']
    parts += ['## Все маршруты', '', cascade_table([(k, mode, r) for k, modes in s['p4']['cascades'].items() for mode, r in modes.items()], identifiers=True), '']
    for axis, title in AXES.items():
        parts += ['## N14 при неизвестной доступности исключён: ' + title, '',
            quality_table([(k, r['axes'][axis]) for k, r in s['p4']['sensitivity']['methods'].items()], n, identifiers=True), '']
    parts += ['## CAL по частям', '', table(['Модель', 'Часть', 'Доступна', 'Статус CAL', 'Пороги'],
        [[r['method'], r['fold'], r['available'], r['operating_point']['status'], r['operating_point']['thresholds']]
         for r in s['ml']['models']]), '', '## Все описательные OOF-пороги на полной цели', '',
        'Пороги по этой таблице не выбираются. Полное воздержание включено заранее.', '',
        table(['Модель', 'Порог ALLOW', 'Порог BLOCK', 'Верно / n', 'Ошибка ALLOW / BLOCK',
               'UNKNOWN / нет модели', 'Допустимых без ALLOW'],
            [[model, r['thresholds']['ALLOW'], r['thresholds']['BLOCK'],
              f"{r['metrics']['correct']} / {r['metrics']['n']}",
              f"{r['metrics']['wrong_allow']} / {r['metrics']['wrong_block']}",
              f"{r['metrics']['unknown']} / {r['metrics']['model_unavailable']}", r['metrics']['safe_stop']]
             for model, records in curves['methods'].items() for r in records]), '',
        '## Прежние 176', '', legacy_table(s['legacy176']), '', time_table(s['legacy176'], full=True), '']
    blocks = {'Цели и методы без допущения N14': s['p4']['sensitivity'],
        'Исходная цель, область учёта': {k: v for k, v in s['p4']['source_expectation'].items() if k not in ('methods', 'cascades')},
        'Вклад общей проверки процедур': {k: r['shared_gate'] for k, r in s['p4']['methods'].items() if 'shared_gate' in r},
        'Совпадения признаков': feature_audit,
        'Измеренные компоненты': {'rules': s['p4']['latency'], 'ml': s['p4']['ml_latency']},
        'Ранние метки и условные остановки': s['early'],
        'OOF по совпадению признаков': s['ml']['methods']}
    for title, value in blocks.items():
        parts += ['## ' + title, '', '```json', json.dumps(value, ensure_ascii=False, indent=2), '```', '']
    if (HERE / 'SCALER_AUDIT.md').exists():
        parts += ['[Проверка численных предупреждений масштабирования](SCALER_AUDIT.md).', '']
    return '\n'.join(parts)


def run(summary=HERE / 'results-summary.json'):
    s = read(summary)
    if s['schema_version'] != 1 or s['new_api_calls'] != 0:
        raise ValueError('unexpected completion summary contract')
    curves, audit = read(s['ml']['curves']), read(s['ml']['feature_audit'])
    report = build_report(s, read(HERE / 'cost-audit.json'), len(read(HERE / 'captured-policies.json.gz')['cases']))
    appendix = build_tables(s, curves, audit)
    plot_curves(curves, HERE)
    (HERE.parent / 'NO_LLM_REPORT.md').write_text(report)
    (HERE / 'REPORT.md').write_text(report.replace('](local_guards_completion/', '](')
        .replace('](local_guards_ml_retrain/', '](../local_guards_ml_retrain/'))
    (HERE / 'TABLES.md').write_text(appendix)
    print('COMPLETION_REPORT', len(report.splitlines()), 'main lines;', len(s['p4']['methods']), 'method vectors')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=Path, default=HERE / 'results-summary.json')
    run(**vars(parser.parse_args()))
