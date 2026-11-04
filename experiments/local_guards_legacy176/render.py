"""Render tables from saved arithmetic; never calls a guard or a model."""
from collections import defaultdict
import json
from .prepare import HERE

NAMES={
 'v1':'Правила v1','v2':'Правила v2','v3':'Правила v3','v4':'Правила v4','v4.2':'Правила v4.2','v4.3':'Правила v4.3',
 'v4.3_payment':'v4.3, только платёжная проверка','native':'Платёжные условия с Fraud','native_core':'Платёжные условия без Fraud',
 'constant_ALLOW':'Всегда ALLOW','constant_BLOCK':'Всегда STOP',
 'SecJev08_canonical_fixed05':'SecJev 0.8B, текущая точка, фиксированный порог 0,5',
 'SecJev9B_MPS_mixed_fixed05':'SecJev 9B, MPS, порог 0,5 (смешанный режим)',
 'Jev27B_MLX_NVFP4_cached_fixed05':'JEV-27B-VL, MLX NVFP4, порог 0,5',
}
for seed in (17,29,43):
    for arm,description in [('catboost_J_cur_none','CatBoost, текущая точка'),('catboost_J_seq_none','CatBoost, четыре точки'),('scalar_J_cur_none','линейная свёртка, текущая точка')]:
        NAMES[f'SecJev08_CV_{arm}_seed{seed}']=f'SecJev 0.8B + {description}, seed {seed}'

MAIN=['v1','v2','v3','v4.3','native_core','native','SecJev08_CV_catboost_J_cur_none_seed17',
      'SecJev08_CV_catboost_J_seq_none_seed17','SecJev9B_MPS_mixed_fixed05','Jev27B_MLX_NVFP4_cached_fixed05','constant_ALLOW','constant_BLOCK']


def table(headers,records):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join('---' for _ in headers)+'|']+
        ['| '+' | '.join(map(str,r))+' |' for r in records])+'\n'


def run():
    q=json.loads((HERE/'quality.json').read_text())['methods'];t=json.loads((HERE/'full-time.json').read_text())
    quality=[];intervals=[]
    for name,modes in q.items():
        for mode,r in modes.items():
            quality.append([NAMES[name],mode,r['allow'],r['block'],r['unknown'],r['unavailable'],r['tp'],r['wrong_allow'],r['false_block'],f"{100*r['false_block']/93:.2f}",r['safe_stop'],r['correct']])
            ci=r['intervals'];fmt=lambda pair:' / '.join(f'{v*100:.2f}' for v in pair)
            intervals.append([NAMES[name],mode,fmt(ci['correct_ci95']),fmt(ci['fpr_block_ci95']),fmt(ci['safe_stop_ci95']),fmt(ci['paired_correct_difference_vs_v2_ci95']),fmt(r['paired_v1_ci95'])])
    content='# Все решения на legacy176\n\nFULL: полные исторические свидетельства. PARTIAL: исходное сокращённое представление без привязки объектов и полной истории. SAVED: неизменённые модельные ответы, входы сопоставлены по хешам.\n\n'
    content+=table(['Метод','Вход','ALLOW','BLOCK','UNKNOWN','Вход недоступен','Верный BLOCK /83','Ошибочный ALLOW /83','Ошибочный BLOCK /93','FPR BLOCK, %','Все STOP /93','Верные /176'],quality)
    content+='\n## Интервалы и парные различия\n\nПроцентные пункты; 95% percentile bootstrap, 2000 выборок 45 исходных базовых групп, seed 17. Нулевой наблюдаемый FPR даёт нулевой bootstrap-интервал, что не доказывает нулевой риск вне архива. Разность покрытия считается на парных решениях каждой группы.\n\n'
    content+=table(['Метод','Вход','Верное покрытие, 95%','FPR BLOCK, 95%','STOP safe, 95%','Разность с v2, 95%','Разность с v1, 95%'],intervals)
    content+='\nВсе ухудшения локальных методов на FULL относительно v2: [regressions.jsonl.gz](regressions.jsonl.gz). Матрицы всех переходов относительно v1/v2, включая улучшения, сохранённые SecJev и PARTIAL, находятся в [quality.json](quality.json). Метки сохранены; UNKNOWN и недоступный вход не являются обнаружением.\n'
    (HERE/'TABLES.md').write_text(content)
    fmt=lambda v:'нет' if v is None else f'{v:.3f}'
    time_rows=[];paired=[]
    for name in MAIN:
        r=t['methods'][name];a=r['terminal'];c=r['completed'];s=r['stopped'];p=r['paired_completed_overhead'];base=r['paired_completed_baseline']
        time_rows.append([NAMES[name]+(' *' if name.startswith(('SecJev','Jev')) else ''),a['n'],fmt(a['mean_s']),fmt(a['median_s']),fmt(a['p95_s']),c['n'],fmt(c['mean_s']),fmt(c['median_s']),fmt(c['p95_s']),s['n'],fmt(s['mean_s']),fmt(s['median_s']),fmt(s['p95_s'])])
        paired.append([NAMES[name],c['n'],fmt(base['mean_s']),fmt(base['median_s']),fmt(p['mean_s']),fmt(p['median_s']),fmt(p['p95_s'])])
    content='# Время всей задачи\n\n'
    content+='Все значения в секундах, единица наблюдения: эпизод. Локальное время одного эпизода усредняется по 30 измерениям, затем считаются статистики 176 эпизодов. ALLOW сохраняет весь последующий архивный ход; BLOCK/UNKNOWN обрывает его перед первым переводом. Последующие инструменты и проверки после STOP не учитываются. «Завершение» означает успешное окончание исходного исполнения, не доказанную безопасность оплаты.\n\n'
    content+='Исходный wall_s включает старые теневые проверки: среднее 48,052 с, медиана 47,675 с, p95 55,030 с (n=176). После удаления объединения 2343 интервалов ожидания: 31,515 / 31,226 / 38,280 с. Суммарно удалено 2910,5895 с. Вложенные вызовы делегирования не складываются; время кеша не подменяет вычисление модели.\n\n'
    content+=table(['Метод','Всего n','До конца/STOP среднее','Медиана','p95','Завершено n','Среднее','Медиана','p95','STOP n','Среднее','Медиана','p95'],time_rows)
    content+='\n* Для SecJev включены исходные вычисления модели. Время рендеринга/клиента и индивидуальной OOF-свёртки не сохранено: числа являются нижней оценкой этих накладных расходов, не полным новым измерением. 9B объединяет сохранённые режимы MPS reference и cache-assisted; 27B использует экспериментальный MLX NVFP4. Их нельзя трактовать как чистое сравнение архитектур.\n\n'
    content+='## Цена проверки на тех же завершённых эпизодах\n\nУ каждой строки собственное завершившееся подмножество, сравнение парное. Разность средних между разными подмножествами из предыдущей таблицы не является ускорением.\n\n'
    content+=table(['Метод','n','База среднее','База медиана','Добавлено среднее','Добавлено медиана','Добавлено p95'],paired)
    content+='\n## Источники и точность\n\n[Независимый аудит таймеров](TIMING_SOURCE_REVIEW.md) устанавливает порядок записи контекста после ожидания. Архив указывает ревизию 631100dc; полного исходного объекта локально нет. Проверена сохранённая реализация runtime 08b7b900 с тем же порядком таймеров и согласованность всех trace-интервалов. Номинальный расчёт вычитает pause_ms; дополнительная консервативная граница вычитает весь промежуток между соседними событиями. Очищенная база по этой границе: среднее 31,462, медиана 31,180 с. Разница с номинальной около 53 мс на эпизод, максимальная погрешность округления около 5,7 мс. Все нижние границы сохранены в full-time.json, это не претензия на новый live-замер.\n\n'
    content+='Локальный benchmark: изолированная SQLite хранит архивный префикс; чтение и JSON-разбор, построение доказательств, адаптация и решение измерены отдельно. Это измерение выбранной replay-интеграции, а не производственной интеграции FinBot. Вывод артефактов и диагностическое хеширование исключены из рабочего времени; payload и вердикты совпали во всех 58 080 измерениях. Для v1/v2 учитывается только их исходный конструктор; константы не оплачивают ненужный сбор. Средняя добавка на завершившихся задачах: v1 1,64 мс, v2 1,83 мс, платёжные условия с Fraud 12,10 мс.\n\n'
    content+='SecJev 0.8B: одна точка содержит четыре атомарных ответа; четыре точки содержат 16. J_cur использует текущую точку, J_seq вычисляет признаки четырёх точек и принимает итоговое решение на P4; это не каскад с ранней остановкой. Для кешированных одинаковых входов берётся исходное reference-время. Последние 9B/27B scores имеют те же canonical payload hashes, но различный runtime. Накладные расходы отсутствуют явно, а не заменяются стоимостью чтения кеша.\n\n[Все временные компоненты и маршруты](full-time.json) · [Исходные таймеры](timing-sources.jsonl.gz) · [30 повторов](benchmark.jsonl.gz).\n'
    (HERE/'TIMING.md').write_text(content)


if __name__=='__main__':run()
