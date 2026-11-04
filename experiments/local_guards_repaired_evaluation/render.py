"""Render every frozen configuration and selected primary comparisons."""
import argparse
import json
from pathlib import Path

from .run import HERE
from experiments.local_guards_adapter_repair.inventory import write_json,sha

RETRAIN='frozen_revision2/payment_v3__'
RETRAIN_UNKNOWN=[RETRAIN+s+'__17|gated|A' for s in (
    'old__archive__logistic','old__archive__catboost','new__archive__logistic',
    'new__archive__catboost','old__mixed__logistic','new__mixed__catboost')]
PRIMARY=[
 ('Правила v1',['v1|rule|A']),('Правила v2',['v2|rule|A']),
 ('Правила v3',['v3|rule|A']),('Правила v4',['v4|rule|A']),
 ('Правила v4.2',['v4.2|rule|A']),('Правила v4.3',['v4.3|rule|A']),
 ('Платёжные условия без Fraud',['native_core|rule|A']),
 ('Платёжные условия с Fraud',['native|rule|A']),
 ('ML этапа v3: LR, CatBoost, TF-IDF; каждый',
  [f'v3_ml/{model}/17/P4|frozen|A' for model in ('structured_logistic','structured_catboost','text_diagnostic')]),
 ('LR по ожидаемому решению сценария',['archive_ml/scenario_decision-lr-17|raw|A']),
 ('CatBoost по ожидаемому решению сценария',['archive_ml/scenario_decision-catboost-17|raw|A']),
 ('LR по базовым платёжным условиям',['archive_ml/native_core-lr-17|raw|A']),
 ('CatBoost по базовым платёжным условиям',['archive_ml/native_core-catboost-17|raw|A']),
 ('Переобученная LR: новые признаки, смесь',[RETRAIN+'new__mixed__logistic__17|gated|A']),
 ('Переобученный CatBoost: старые признаки, смесь',[RETRAIN+'old__mixed__catboost__17|gated|A']),
 ('Остальные шесть платёжных сочетаний переобучения; каждое',RETRAIN_UNKNOWN),
 ('DeepSeek',['deepseek']),('Всегда BLOCK, контроль',['constant_BLOCK|rule|A'])]
FIELDS=('correct_allow','correct_block','wrong_allow','wrong_block','insufficient_allow','insufficient_block','unknown','unavailable','correct')


def escape(value):return str(value).replace('|',r'\|')


def quality_table(items):
    lines=['| Метод | Верно ALLOW / BLOCK | Ошибка ALLOW / BLOCK | При неполной разметке ALLOW / BLOCK | UNKNOWN | Нет полного входа | Верно из 542 |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for name,s in items:
        values=[f"{s['correct_allow']} / {s['correct_block']}",f"{s['wrong_allow']} / {s['wrong_block']}",
                f"{s['insufficient_allow']} / {s['insufficient_block']}",str(s['unknown']),str(s['unavailable']),
                f"{s['correct']} ({100*s['correct']/542:.1f}%)"]
        lines.append('| '+escape(name)+' | '+' | '.join(values)+' |')
    return '\n'.join(lines)


def aggregate(s,categories):
    return {key:sum(s['by_category'].get(c,{}).get(key,0) for c in categories) for key in
            ('decision_ALLOW','decision_BLOCK','unknown','unavailable')}


def task_table(items):
    lines=['| Метод | Обычные задачи: ALLOW / BLOCK / UNKNOWN / нет входа (160) | Инъекция или фрод: ALLOW / BLOCK / UNKNOWN / нет входа (224) |',
           '|---|---:|---:|']
    for name,s in items:
        values=[]
        for categories in (('legit',),('injection','fraud')):
            v=aggregate(s,categories);values.append(' / '.join(str(v[k]) for k in ('decision_ALLOW','decision_BLOCK','unknown','unavailable')))
        lines.append('| '+escape(name)+' | '+' | '.join(values)+' |')
    return '\n'.join(lines)


def grouped(result):
    selected=[]
    for name,keys in PRIMARY:
        values=[result['saved_deepseek'] if k=='deepseek' else result['methods'][k]['common'] for k in keys]
        signature=lambda s:[s.get(k,0) for k in FIELDS]
        assert all(signature(s)==signature(values[0]) for s in values),name
        # Task counts must also agree before compressing several rows into one.
        assert all(s['by_category']==values[0]['by_category'] for s in values),name
        selected.append((name,values[0]))
    return selected


def run():
    result=json.loads((HERE/'results/p4-summary.json').read_text())
    selected=grouped(result)
    (HERE/'PRIMARY.md').write_text(quality_table(selected)+'\n')
    (HERE/'TASKS.md').write_text(task_table(selected)+'\n')
    lines=['# Полное сравнение платёжных решений','',
        'Все 569 локальных конфигураций, включая диагностику и константы; по 542 состояния в каждом режиме. '
        'raw/calibrated/gated/frozen обозначают исходные, уже закреплённые варианты порогов и проверок. '
        'argmax_diagnostic не предлагается для исполнения. ALLOW/BLOCK относится к действию, категория сценария считается отдельно.','']
    for mode,title in (('common','Сведения из запроса DeepSeek'),('expanded','Дополнительные архивные сведения'),('conditional','Условный технический контекст')):
        items=[(key,v[mode]) for key,v in result['methods'].items()]
        if mode=='common':items.append(('saved DeepSeek',result['saved_deepseek']))
        lines+=['## '+title,'',quality_table(items),'']
    (HERE/'TABLES.md').write_text('\n'.join(lines))
    lines=['# Цена для категорий задач','',
        'Категория задана автором сценария и не заменяет разметку самого действия. '
        'Вне двух показанных групп ещё 110 policy-сценариев и 48 неизвестной категории; они остаются в основной таблице из 542.','',task_table(selected),'']
    (HERE/'TASKS.md').write_text('\n'.join(lines))
    # Compact early appendix, including the separately declared profiles.
    early=json.loads((HERE/'results/early-summary.json').read_text())
    lines=['# Ранние действия','',
        '128 действий:107 ALLOW,3 BLOCK,18 INSUFFICIENT. Историческая политика определяет допустимость действия; новые B-требования отдельно меняют контракт.','',
        '| Конфигурация | Режим | Верно ALLOW / BLOCK | Ошибка ALLOW / BLOCK | UNKNOWN | Неполная разметка ALLOW / BLOCK |',
        '|---|---|---:|---:|---:|---:|']
    for key,values in early['methods'].items():
        for mode,value in values.items():
            s=value['sample']['ALL'];lines.append(f"| {escape(key)} | {mode} | {s['correct_allow']} / {s['correct_block']} | {s['wrong_allow']} / {s['wrong_block']} | {s['unknown']} | {s['insufficient_allow']} / {s['insufficient_block']} |")
    lines+=['','## Первая остановка','',
        '| Конфигурация | Режим | Политика STOP | Первая BLOCK | Первая UNKNOWN | Без наблюдаемых точек | Достигнуто / пропущено точек |',
        '|---|---|---|---:|---:|---:|---:|']
    for key,values in early['methods'].items():
        for mode,value in values.items():
            for stop,record in value['sequential'].items():
                c=record['counts'];blocks=sum(n for k,n in c.items() if k.endswith(':BLOCK'));unknown=sum(n for k,n in c.items() if k.endswith(':UNKNOWN'))
                lines.append(f"| {escape(key)} | {mode} | {stop} | {blocks} | {unknown} | {c['no_points']} | {c['reached_points']} / {c['skipped_points']} |")
    (HERE/'EARLY.md').write_text('\n'.join(lines)+'\n')
    latency=json.loads((HERE/'benchmark/latency.json').read_text())
    lines=['# Задержка одиночного вызова','',
        'Готовое наблюдение, включая исходные ML-преобразователи и gate. До 30 заранее выбранных состояний на метод и режим. '
        'Чтение файла и экспериментальная диагностика исключены. load_ms и first_call_ms в JSON относятся к общему процессу, не к изолированному холодному старту.','',
        '| Конфигурация | Режим | n | p50, мс | p95, мс |','|---|---|---:|---:|---:|']
    for key,value in latency['methods'].items():
        for mode,s in value['modes'].items():
            fmt=lambda v:'—' if v is None else f'{v:.4f}'
            lines.append(f"| {escape(key)} | {mode} | {s['n']} | {fmt(s['p50_ms'])} | {fmt(s['p95_ms'])} |")
    (HERE/'LATENCY.md').write_text('\n'.join(lines)+'\n')
    write_json(HERE/'render-receipt.json',dict(renderer_sha256=sha(Path(__file__)),
        summaries={p:sha(HERE/p) for p in ('results/p4-summary.json','results/early-summary.json','benchmark/latency.json')},
        primary=PRIMARY,outputs={p:sha(HERE/p) for p in ('PRIMARY.md','TASKS.md','TABLES.md','EARLY.md','LATENCY.md')}))


if __name__=='__main__':run()
