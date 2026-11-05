"""Render saved annotation scores; no inference or label changes."""
import json
from pathlib import Path

E = Path(__file__).resolve().parent
PRIMARY = [
    ('v1|p4|historical_extension_control', 'Правила v1'),
    ('v2|p4|historical_extension_control', 'Правила v2'),
    ('v3|p4|historical_extension_control', 'Правила v3'),
    ('v42_payment_common|p4|historical_extension_control', 'v4.2: платёжная часть'),
    ('v42_fullA|p4|historical_extension_control', 'v4.2: основные проверки'),
    ('native_core|both|structural_diagnostic', 'Архивные правила: платёжные условия'),
    ('native|both|fixed', 'Архивные правила: условия и Fraud'),
    ('scenario_decision-lr-17:raw|p4|scenario_decision', 'LR: исход задачи'),
    ('scenario_decision-catboost-17:raw|p4|scenario_decision', 'CatBoost: исход задачи'),
    ('native_core-lr-17:raw|p4|native_core', 'LR: платёжные условия'),
    ('native_core-catboost-17:raw|p4|native_core', 'CatBoost: платёжные условия'),
    ('deepseek|both|none', 'DeepSeek'),
]


def behavioral(methods, selection, full=False):
    out = ['| Метод | Обычные задачи: разрешил / запретил (160) | Инъекция или фрод: разрешил / запретил (224) | UNKNOWN (542) | Неприменим вход (542) |',
           '| --- | ---: | ---: | ---: | ---: |']
    if full:
        out = [out[0]+' Проверки политики: разрешил / запретил (110) | Категория неизвестна: разрешил / запретил (48) |', out[1]+' ---: | ---: |']
    for key, name in selection:
        m = methods[key]; c = m['author_category']; a = m['action']
        ordinary = f"{c['legit']['ALLOW']} / {c['legit']['BLOCK']}"
        attacks = f"{c['injection']['ALLOW']+c['fraud']['ALLOW']} / {c['injection']['BLOCK']+c['fraud']['BLOCK']}"
        line = f"| {name} | {ordinary} | {attacks} | {a['unknown']} | {a['adapter_unavailable']} |"
        if full:
            line += f" {c['policy']['ALLOW']} / {c['policy']['BLOCK']} | {c['unknown']['ALLOW']} / {c['unknown']['BLOCK']} |"
        out.append(line)
    return '\n'.join(out)


def correctness(methods, selection):
    out = ['| Метод | Правильно разрешил | Правильно запретил | Разрешил установленное нарушение | Запретил допустимое действие | Разрешил / запретил при недостатке сведений | Подтверждённо решено из 542 |',
           '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for key, name in selection:
        a = methods[key]['action']; correct = a['correct_allow']+a['correct_block']
        out.append(f"| {name} | {a['correct_allow']} | {a['correct_block']} | {a['wrong_allow_known_block']} | {a['wrong_block_gold_allow']} | {a['unsupported_allow_gold_insufficient']} / {a['block_gold_insufficient']} | {correct} ({correct/542:.1%}) |")
    return '\n'.join(out)


def main():
    results = json.loads((E/'results/scores.json').read_text())
    freeze = json.loads((E/'consensus-freeze.json').read_text())
    methods = results['methods']
    sections = [
        '# Сравнение сохранённых решений на 542 реальных состояниях',
        'Единица наблюдения: состояние непосредственно перед переводом. Все методы оценены на одном наборе. '
        'В основной таблице ML показан с исходным порогом, seed 17; варианты с калибровкой, проверкой доказательств и seeds 29/43 приведены ниже. '
        'Выбор строк задан до чтения новой оценки качества.',
        '## Поведение по исходной категории сценария',
        'Категории восстановлены из авторских данных: 160 обычных задач, 216 сценариев с инъекцией, 8 с фродом, 110 проверок политики; '
        'для 48 категория не восстановлена. Инъекция может не привести к запрещённому действию, а обычная задача может дойти до нарушения. '
        'Поэтому эти числа описывают поведение, а не правильность каждого решения. '
        'UNKNOWN и неприменимый вход не входят в пару «разрешил / запретил».',
        behavioral(methods, PRIMARY),
        '## Правильность действия по независимой разметке',
        'Две независимые оценки Terra для каждого состояния, разбор расхождений и контрольная выборка согласий. '
        'Это модельная исследовательская разметка, не человеческий эталон. '
        f"Итоговое распределение: `{json.dumps(freeze['action_counts'], ensure_ascii=False, sort_keys=True)}`; статусы: `{json.dumps(freeze['status_counts'], sort_keys=True)}`. "
        'Решённым считается только подтверждённо правильный ALLOW или BLOCK. '
        'Недостаток сведений не доказывает опасность или безопасность действия; решения по таким случаям показаны отдельно.',
        correctness(methods, PRIMARY),
        '## Все сохранённые варианты',
        'Имена ниже соответствуют файлам предсказаний. `raw` использует исходный порог; `calibrated` — ранее выбранные пороги; '
        '`gated` дополнительно проверяет наличие доказательств. `scenario_decision` обучался на исходной цели задачи, '
        '`native_core` — на платёжных условиях. Эти цели отличаются от полной новой оценки действия. '
        'Константы разрешают всё, запрещают всё или всегда отвечают UNKNOWN.',
        behavioral(methods, [(k,'`'+k.replace('|',r'\|')+'`') for k in sorted(methods)], True),
        correctness(methods, [(k,'`'+k.replace('|',r'\|')+'`') for k in sorted(methods)]),
        '## Совместимость остальных результатов',
        'Для исходного v4.1, старых ML-контролей v3 и отдельно переобученных моделей не найден готовый вектор на той же проекции этих 542 входов. '
        'Их собственные результаты остаются в отчётах соответствующих этапов. Отсутствующий сопоставимый ответ не заменён UNKNOWN. '
        'У v1/v2 недоступный конструктор входа выделен отдельно от вердикта исходных правил.',
        '## Воспроизведение',
        'См. `SCORING_USAGE.md`, `consensus-freeze.json` и `results/scores.json`. Последний содержит все числа, '
        'интервалы с повторной выборкой целых базовых задач и хеши источников. '
        'Новые ответы защитника, обучение и предсказания локальных методов не выполнялись.',
    ]
    (E/'TABLES.md').write_text('\n\n'.join(sections)+'\n')


if __name__ == '__main__':
    main()
