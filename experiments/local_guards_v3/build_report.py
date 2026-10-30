"""Rebuild the concise report and figures from immutable, already scored artifacts."""
import json
import os
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent


def load(relative):
    return json.loads((HERE / relative).read_text())


def select(rows, method, strategy='P4', seed=None, field='all', value=None):
    return next(r for r in rows if r['method'] == method and r['strategy'] == strategy
                and r['seed'] == seed and r['slice'] == field and r['value'] == value)


def fraction(row, first, second):
    return f"{row[first]}/{row[second]}"


def main():
    archived = load('results/archive-evaluation/metrics.json')['aggregates']
    closed = load('results/closed-evaluation/metrics.json')['aggregates']
    latency = load('results/latency.json')
    freeze = load('results/frozen/freeze-manifest.json')
    audit = load('closed-test/review.json')
    labels = {'rules': 'Новые правила', 'legacy_v1': 'Прежние rules v1', 'legacy_v2': 'Прежние rules v2',
              'structured_logistic': 'LR', 'structured_catboost': 'CatBoost',
              'rules+structured_logistic': 'Правила + LR', 'rules+structured_catboost': 'Правила + CatBoost',
              'text_diagnostic': 'TF-IDF + LR'}
    closed_table = []
    for name in ('rules', 'legacy_v1', 'legacy_v2', 'structured_logistic', 'structured_catboost',
                 'rules+structured_logistic', 'rules+structured_catboost', 'text_diagnostic'):
        r = select(closed, name, seed=None if name in {'rules','legacy_v1','legacy_v2'} else 17)
        closed_table.append(f"| {labels[name]} | {fraction(r,'safe_stops','safe_episodes')} | "
            f"{fraction(r,'intervention_stops','intervention_episodes')} | {r['intervention_auto_allows']} |")
    archive_table = []
    for name in ('rules', 'legacy_v2', 'rules+structured_logistic', 'rules+structured_catboost', 'text_diagnostic'):
        r = select(archived, name, seed=None if name in {'rules','legacy_v2'} else 17)
        archive_table.append(f"| {labels[name]} | {fraction(r,'harm_prevented','harmful_episodes')} | "
            f"{fraction(r,'safe_stops','safe_episodes')} | {fraction(r,'source_benign_interruptions','source_benign_episodes')} |")
    r, staged = select(archived, 'rules'), select(archived, 'rules', strategy='staged')
    components = {r['method']: r for r in latency['measurements']}
    speed = ', '.join(f"{labels.get(n,n)} {components[n]['p95_ms']:.3f}" for n in
                      ('rules','legacy_v2','structured_logistic','structured_catboost','text_diagnostic'))
    text = f'''# FinBot: обобщаемые проверки без LLM

31 октября 2026. **Практический результат: проверка платёжных обязательств по доверенным данным переносится лучше обученных здесь классификаторов. Самостоятельный антифрод она не заменяет.** Новых inference API-запросов: **0**.

## Закрытая проверка

Модели, признаки, политика и пороги зафиксированы до создания теста. Автор получил только политику и схему; другой агент проверил все случаи и пересечения с TRAIN/CAL. Предсказания сохранены и захешированы до раскрытия меток. Правила и пороги после теста не менялись.

320 синтетических P4-эпизодов: 160 допустимых, 95 доказанных нарушений, 65 случаев недостаточных доказательств. Восемь семейств, 160 пар, **233 уникальных представления**; повторы и пары не являются независимыми новыми атаками.

| Метод, seed 17 для ML | Ложные остановки допустимых | Остановлены доказанные нарушения | Ошибочно разрешены нарушения |
|---|---:|---:|---:|
{chr(10).join(closed_table)}

Новые правила выдали правильный трёхзначный вердикт во всех 320 случаях: 160 ALLOW, 95 BLOCK, 65 UNKNOWN. Самостоятельно решены 255/320, **79,7%**; UNKNOWN не считается одобрением. Недостающую независимую авторизацию LLM также не может заменить своим утверждением.

Прежние правила не использовали положительное ручное разрешение для суммы выше 10 000: этим объясняются 76 ложных остановок, одинаковых у v1 и v2. Это сравнение с неизменёнными прежними реализациями. В архиве нет независимого реестра ручных разрешений; положительный путь проверен синтетически.

LR и CatBoost не перенесли новые сочетания состояний, включая корректное независимое разрешение, которого не было в обучающих трассах. Их калибровочные 5% FPR не сохранились на тесте. Добавление правил возвращает остановку нарушений, но не устраняет ложные остановки классификатора. Seed 29/43 сохранены отдельно, лучший seed по тесту не выбирался.

## Что происходит на записанных траекториях

Ниже **описательный пересчёт всего архива**, включая TRAIN/CAL: 1 352 эпизода, 277 групп. Вред определён исходной разметкой сценария и подтверждённым переводом; проверка формальных обязательств размечена отдельно. Для 78 эпизодов исходный вред не установлен; их не считали безопасными. Суммы разных исходных оракулов не являются оценкой одной однородной популяции.

| Метод | Вред остановлен бы | Остановлены формально безопасные P4 | Прерваны задачи с исходной меткой legit |
|---|---:|---:|---:|
{chr(10).join(archive_table)}

**0/593 формальных ложных остановок не означает нулевой FPR на честных задачах:** новые правила прерывают 90/846 таких задач, 10,6%. В части этих цепочек сам Fraud уже создал обязательный HOLD. По строгому контракту остановились бы 168/168 вредных переводов; по исходной разметке осталось бы 55/112 вредных продолжений. В частности, для DeepSeek остановлено 0/6, для mini — 15/43: корректные платёжные реквизиты и завершённая Fraud-проверка не доказывают отсутствие фрода.

На CAL заранее выбраны правила: 38/38 вмешательств при 0/126 ложных остановок; ML не улучшил этот критерий. Luna полностью исключена из TRAIN/CAL: на её знакомых сценариях правила дали 3/3 остановки исходного вреда и 0/53 остановки формально безопасных P4. Три вредных случая не подтверждают широкий перенос. Подтверждённых новых семейств реальных архивных атак не найдено; синтетический тест не выдаётся за такой архив.

## Размещение и цена

Для новых правил P4 и P2b → P3 → P4 остановили бы одинаковые **57/112** исходных вредных продолжений. Ранние проверки увеличили прерывания legit-задач с **90/846 до 325/846**, а число эпизодов с проверками — с 789 до 1 349. Для этих трасс **P4 — основной рекомендуемый гейт**. Более ранняя остановка полезна как отдельная политика, но улучшения конечного предотвращения здесь нет.

![Качество, ложные остановки и время](results/comparison.png)

Измеренный p95 одной проверки, миллисекунды, включая JSON-декодирование и вычисление признаков: **{speed}**. Холодный импорт библиотек — {latency['imports_ms']/1000:.2f} с; загрузки сохранённых моделей измерены отдельно. Пиковая память процесса со всеми компонентами — {latency['process_peak_rss_mib']:.0f} МиБ. Онлайн-задержка агентной системы не измерялась; локальная цена вычислений и разработки в USD неизвестна.

## Предварительный этап перед LLM

В отдельной архивной диагностике маршрутизатор достигает 214 запросов: **73** имеют точно совпавший сохранённый P2-контекст, **141** остаются UNKNOWN. Независимо от LLM, 28 случаев отсутствия обязательного доказательства не получают разрешения. Полноценное качество и стоимость каскада по этим неполным данным не установлены.

Все **227** сохранённых `final`-контекстов используют `process_payment.agent_notes`, появившиеся после перевода. Они исключены как свидетельства проверки до платежа. Проверены 227 совместимых контекстов границы Fraud; их наличие зависит от состоявшейся оплаты, поэтому условную точность нельзя переносить на всю выборку. Подробности — [saved-fallback-report.md](saved-fallback-report.md).

## Проверяемость и пределы

Новые правила читают типизированные факты и их происхождение, а не должности, фразы атак или объяснения агента. Нет обращения к будущей БД. Отсутствие событий считается доказанным только при проверенном создании нового счёта и полном журнале. На 320 перестановках несущественного текста/идентификаторов решения правил и оценки структурных моделей не изменились.

157 тестов эксперимента и 42 исходных probe-теста прошли. Пять отдельных SQLite-баз с настоящим FinBot runtime и in-process FinStripe MCP подтвердили: корректный платёж, остановку HOLD/UNKNOWN, актуальное чтение изменённой суммы, запрет другого получателя, повторного перевода и вызовов после STOP. Это последовательная интеграционная проверка; конкурентное исполнение и причинный эффект в живой LLM-цепочке не измерены.

Групповые интервалы и парные сравнения находятся в JSON. Нулевая выборочная ошибка и восемь синтетических семейств не гарантируют FPR ниже 1%. Старые raw64/240 случаев с расширенными FX/budget/partial-settlement требованиями оставлены историческими данными другого контракта, а не новым внешним тестом этой политики.

[Команды воспроизведения](README.md) · [метрики архива](results/archive-evaluation/metrics.csv) · [метрики закрытого теста](results/closed-evaluation/metrics.csv) · [заморозка](results/pre-test-freeze.json) · [независимый аудит](prefreeze-audit.md) · [проверка теста](closed-test/review.md)
'''
    (HERE / 'REPORT.md').write_text(text)

    cache = Path(tempfile.gettempdir()) / 'finbot-v3-matplotlib'
    cache.mkdir(exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR', str(cache))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for name in ('rules','legacy_v2','rules+structured_logistic','rules+structured_catboost','text_diagnostic'):
        item = select(archived, name, seed=None if name in {'rules','legacy_v2'} else 17)
        axes[0].scatter(100*item['safe_stop_fpr'], 100*item['harm_prevention_rate'], s=65)
        axes[0].annotate(labels[name], (100*item['safe_stop_fpr'],100*item['harm_prevention_rate']),
                         xytext=(4,6 if name != 'legacy_v2' else -14), textcoords='offset points', fontsize=8)
    axes[0].set(xlabel='Остановки безопасных P4, %',ylabel='Исходный вред остановлен бы, %',
                title='Архив: описательный пересчёт',xlim=(-.3,7),ylim=(40,68))
    names=('rules','legacy_v2','structured_logistic','structured_catboost','text_diagnostic')
    axes[1].barh([labels[n] for n in names],[components[n]['p95_ms'] for n in names],color='#537fa3')
    axes[1].invert_yaxis()
    axes[1].set(xlabel='p95 одной проверки, мс',title='Один процесс, без кеша')
    for axis in axes:
        axis.spines[['top','right']].set_visible(False)
        axis.grid(alpha=.2)
    figure.tight_layout()
    figure.savefig(HERE/'results/comparison.png',dpi=180)
    figure.savefig(HERE/'results/comparison.svg')
    plt.close(figure)
    print('REPORT.md and comparison figure rebuilt from frozen results')


if __name__ == '__main__':
    main()
