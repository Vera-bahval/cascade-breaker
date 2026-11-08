"""Open-data latency supplement, integrity assertions and human-readable tables."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import random
from time import perf_counter

from .latency_followup import HERE, ROOT, Candidate, configs, offline, stats
from . import evaluate as ev


def load(path):
    with (gzip.open(path,'rt') if path.suffix=='.gz' else path.open()) as h:return json.load(h)


def text_supplement(output):
    rows=[]
    path=HERE/'data/observations.jsonl.gz'
    with gzip.open(path,'rt') as h:
        for line in h:
            r=json.loads(line)
            if (r['observation']['checkpoint']=='P4' and
                r['observation']['proposal'].get('tool')=='finstripe__create_transfer' and
                ev.text_compatible(ev.baseline_observation(r))):
                rows.append(r)
                if len(rows)==64:break
    assert len(rows)==64,'need 64 actually present invoice+agent text inputs'
    candidates={c['name']:Candidate(c) for c in configs()}
    rng=random.Random(43);raw=[]
    for repeat in range(5):
        names=list(candidates);rng.shuffle(names)
        for name in names:
            indices=list(range(len(rows)));rng.shuffle(indices)
            for i in indices:
                start=perf_counter();r=candidates[name](rows[i]);ms=(perf_counter()-start)*1000
                raw.append({'method':name,'repeat':repeat,'prefix_id':rows[i]['prefix_id'],
                            'checked':r['checked'],'decision':r['decision'],'elapsed_ms':ms})
    result={'created_at':datetime.now(timezone.utc).isoformat(),'selection':'first 64 archive P4 rows with both actual invoice+agent text; no labels used',
            'script_sha256':ev.digest(Path(__file__)),'candidate_script_sha256':ev.digest(HERE/'latency_followup.py'),
            'archive_sha256':ev.digest(path),'raw':raw,'new_inference_api_calls':0,
            'summary':{n:stats([r['elapsed_ms'] for r in raw if r['method']==n and r['checked']]) for n in candidates}}
    ev.write_json(output,result)


def verify(x):
    assert x['source_sha256']==ev.digest(HERE/'latency_followup.py')
    ev.verify_manifest(HERE/'results/methods-final.json')
    for f,d in x['inputs'].items():assert ev.digest(ROOT/f)==d,f
    methods=[c['name'] for c in configs()]
    pure=x['pure']['raw'];assert len(pure)==23*400*5
    assert not x['pure']['frozen_prediction_mismatches']
    assert all(v==2000 for v in Counter(r['method'] for r in pure).values())
    expected={(r['method'],r['prefix_id']):r for r in ev.read_rows(HERE/'results/closed-predictions.jsonl.gz')}
    for r in pure:
        e=expected[r['method'],r['prefix_id']]
        assert (r['decision'],r['checked'])==(e['decision'],e['checked'])
    raw=x['native']['raw'];assert len(raw)==24*15
    for r in raw:
        assert (r['payments'],r['invoice_status'])==((1,'paid') if r['status']=='completed' else (0,'approved') if r['method'].startswith('saved_P4_') else (0,'submitted'))
        if r['status']=='completed':assert r['model_stub_calls']==11
        if r['method']=='constant_STOP':assert r['model_stub_calls']==0
    assert all(n==15 for n in Counter(r['method'] for r in raw).values())
    assert len(x['contention']['raw'])==90
    for r in x['contention']['raw']:
        admitted=sum(a['outcome']=='admitted' for a in r['attempts'])
        expected_count=(r['workers'] if not r['B02_enabled'] or r['scope']=='different_invoices'
                        else 1 if r['scope']=='same_invoice' else 0)
        assert admitted==expected_count,(r,admitted,expected_count)
        assert len(r['attempts'])==r['workers']
        for a in r['attempts']:
            assert a['admission_ms']>=0
            if a['outcome']=='rejected':assert a['request_ms']==a['admission_ms']
    for r in x['contention']['recovery']:
        assert r['until_readmission_ms']>=r['assigned_reconciliation_delay_ms']
    assert x['new_inference_api_calls']==0
    return {'single_decisions':len(pure),'native_chains':len(raw),'contention_batches':90,
            'recovery_cases':len(x['contention']['recovery']),'methods':len(methods),
            'frozen_prediction_mismatches':0,'successful':True}


def label(name):
    return {'control_p4_v3':'v3, только P4','early_A':'v4, только P0–P3',
        'A_with_P4':'v4, основные P0–P4','A_plus_B01':'v4, основные и актуальность одобрения',
        'A_plus_B02':'v4, основные и запрет дублей','A_plus_B03':'v4, основные и запрет SystemUtils',
        'A_plus_allB':'v4, все ограничения','A_P01_with_P4':'v4, вход/инструменты и P4',
        'A_P2_with_P4':'v4, результат дочернего агента и P4','A_P3_with_P4':'v4, изменение состояния и P4',
        'legacy_v1':'Старые rules v1','legacy_v2':'Старые rules v2',
        'constant_ALLOW':'Всегда разрешать','constant_STOP':'Всегда останавливать'}.get(name,
            name.replace('saved_P4_structured_logistic_','LR, seed ').replace('saved_P4_structured_catboost_','CatBoost, seed ').replace('saved_P4_text_diagnostic_','TF-IDF и LR, seed '))


def pair(s,digits=3):
    if not s['n']:return 'не применяется'
    return f"{s['p50_ms']:.{digits}f} / {s['p95_ms']:.{digits}f}"


def tables(x,t,output):
    lines=['# Полные результаты дополнительных измерений времени','',
        'Открытый инженерный эксперимент после раскрытия теста. Методы и оценка качества заморожены.',
        'Все времена в таблицах - миллисекунды. В каждой паре сначала медиана (p50), затем p95.',
        'Каждая строка одиночных решений измерена отдельно; состав применимых точек различается.',
        'Таблица показывает задержку полного одиночного вызова с маршрутизацией, проекцией и признаками, без чтения native-БД.', '',
        '| Метод | Решение на искусственных состояниях, p50 / p95 | Решение на архивных P4 с текстом, p50 / p95 | Применимых вызовов в первом замере | Холодный процесс, мс; RSS, МиБ |',
        '| --- | ---: | ---: | ---: | ---: |']
    cold={r['method']:r for r in x['cold']}
    for c in configs():
        n=c['name'];s=x['pure']['summary'][n]['applied'];q=cold[n]
        lines.append(f"| {label(n)} | {pair(s)} | {pair(t['summary'][n])} | {s['n']} | {q['parent_wall_seconds']*1000:.1f}; {q['peak_rss_bytes']/1048576:.1f} |")
    lines += ['', '400 состояний, пять проходов; каждый метод получает все состояния, но таблица исключает неприменимые вызовы. Их время отдельно сохранено в JSON.',
        'Текстовый вход отсутствует во всех 184 искусственных P4. Здесь TF-IDF возвращает UNKNOWN без вычисления текстового score. Для его реальной работы использованы первые 64 архивных P4 с доступными текстами счёта и агента, пять проходов. Это отдельная выборка, не тот же состав состояний.',
        'ML получает по одному наблюдению: предобработка и score включены, batch-amortization не используется. Холодный процесс измерен один раз на метод: запуск Python, общие импорты адаптера, загрузка данных/весов и первый ответ. RSS включает зависимости, а не только веса.', '',
        '## Одна и та же сценарная цепочка через FinBot','',
        '15 повторов каждого метода, порядок перемешан. Длительность начинается перед запуском оркестратора; подготовка тестовых БД и загрузка моделей вынесены за границу. Подмена модели отвечает без сетевого ожидания. Общее число обращений к настоящей LLM - ноль.',
        'Все методы подключены через общий экспериментальный адаптер, который собирает native-состояние и пишет доказательства даже для старых контролей и неприменимых точек. Это стоимость такой интеграции; оптимальный отдельный P4-перехват здесь не измерен. Методы, возвращающие no-check, не объявляются разрешившими действие.', '',
        '| Метод | Завершились / остановились из 15 | Вся цепочка или время до STOP, p50 / p95 | Разница с выключенным профилем для завершённых, p50 / p95 | Полная Runtime.check, p50 / p95 | Обращений к подмене модели |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for n,s in x['native']['summary'].items():
        lines.append(f"| {label(n) if n!='profile_off' else 'Профиль выключен'} | {s['completed']} / {s['stopped']} | {pair(s['whole_chain'],2)} | {pair(s['successful_paired_overhead'],2)} | {pair(s['full_check'],2)} | {','.join(map(str,s['model_stub_calls']))} |")
    lines += ['', 'Разница рассчитана для каждого успешного повтора и выключенного профиля того же раунда, затем взяты квантили разниц. Она не равна разнице отдельно посчитанных квантилей. На 15 повторах p95 равен наибольшему наблюдению; это нестабильная оценка хвоста, не SLA. Малые различия между вариантами не доказывают превосходства.',
        'Всегда разрешающий контроль показывает цену сбора состояния и журнала без содержательных правил. Сравнение только времени до STOP с успешной цепочкой некорректно: CatBoost блокирует разрешённый тестовый платёж, TF-IDF останавливает его из-за отсутствия текста. Ни один из них не завершает эту задачу.', '',
        '## Изолированная конкуренция за активную задачу','',
        'Реальный EvidenceStore/SQLite, 1, 4 или 8 потоков, пять серий каждого режима. Перед попыткой общего старта установлен барьер. Второй барьер не даёт освободить ни одну запись до завершения всех попыток допуска; затем каждая допущенная задача удерживает запись ещё 50 мс. Приём и удержание разделены намеренно, чтобы исключить поздний повторный допуск после уже завершившейся работы.',
        'Эта синхронизация увеличивает длительность партии. Ни длительность, ни завершения/сек не являются оценкой производственной пропускной способности. Завершение означает только окончание имитируемой работы с записью, не платёж. Выключенный B02 не выполняет операций claims.', '',
        '| Потоков | Объекты | B02 | Допущено / попыток | Допуск, p50 / p95 | Ответ на запрос, p50 / p95 | Партия, p50 / p95 | Завершений/с всей серии |',
        '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for workers in (1,4,8):
        for scope in ('different_invoices','same_invoice','vendor_wide_overlap'):
            for enabled in (False,True):
                rows=[r for r in x['contention']['raw'] if (r['workers'],r['scope'],r['B02_enabled'])==(workers,scope,enabled)]
                a=[a for r in rows for a in r['attempts']];count=sum(q['outcome']=='admitted' for q in a)
                scope_name={'different_invoices':'разные счета одного вендора','same_invoice':'один счёт','vendor_wide_overlap':'вендор уже занят целиком'}[scope]
                lines.append(f"| {workers} | {scope_name} | {'вкл.' if enabled else 'выкл.'} | {count}/{len(a)} | {pair(stats([q['admission_ms'] for q in a]),2)} | {pair(stats([q['request_ms'] for q in a]),2)} | {pair(stats([r['batch_ms'] for r in rows]),2)} | {count/(sum(r['batch_ms'] for r in rows)/1000):.1f} |")
    lines += ['', 'Отказы отвечают сразу после acquire; второй барьер учитывается только в длительности партии, а не в времени ответа отказа. При vendor-wide конфликте существующая задача не входит в число заявок. При одном счёте без B02 все имитируемые работы допускаются: это не доказательство безопасности такого исполнения.', '',
        '## Неопределённый исход и повтор','',
        'Сначала запись переводится в uncertain. Новый запуск обязан получить отказ. Затем тест задаёт задержку сверки, явно освобождает запись как проверенную и повторяет admission. Пять повторов каждой заданной задержки.', '',
        '| Заданное ожидание сверки, мс | Отказ до сверки, p50 / p95 | До повторного допуска с ожиданием, p50 / p95 |',
        '| ---: | ---: | ---: |']
    for delay in (0,50,200):
        rows=[r for r in x['contention']['recovery'] if r['assigned_reconciliation_delay_ms']==delay]
        lines.append(f"| {delay} | {pair(stats([r['rejected_attempt_ms'] for r in rows]),2)} | {pair(stats([r['until_readmission_ms'] for r in rows]),2)} |")
    lines += ['', 'Задержки 0/50/200 мс заданы экспериментатором. Они показывают зависимость времени восстановления от сверки, но не оценивают реальную длительность сверки. Без неё запись не освобождается по таймеру. Автоматический retry/очередь не реализованы.', '',
        'Исходные данные: [основной JSON](results/latency-followup/raw.json.gz), [текстовый замер](results/latency-followup/text.json.gz), [проверка результатов](results/latency-followup/verification.json).',
        'Код: [основной замер](latency_followup.py), [анализ](latency_analysis.py), [план и границы](LATENCY_PLAN.md). Денежная стоимость и время реального каскада с моделью остаются неизвестными.']
    output.write_text('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--text-output',type=Path)
    p.add_argument('--raw',type=Path);p.add_argument('--text',type=Path);p.add_argument('--report',type=Path)
    p.add_argument('--verification',type=Path)
    args=p.parse_args()
    with offline():
        if args.text_output:text_supplement(args.text_output);return
        x,t=load(args.raw),load(args.text)
        v=verify(x);assert len(t['raw'])==23*64*5
        assert all(s['n']==320 for n,s in t['summary'].items() if n!='early_A')
        v['archive_text_decisions']=len(t['raw'])
        if args.report:tables(x,t,args.report)
        if args.verification:ev.write_json(args.verification,v)
        print(json.dumps(v,indent=2))


if __name__=='__main__':main()
