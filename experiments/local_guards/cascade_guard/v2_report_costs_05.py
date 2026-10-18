"""Presentation only: corrected development and sealed independent evaluations.

The generator never opens scenario observations or labels. Independent metrics
are read only after the evaluator writes its irreversible UNBLINDED marker.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import html
import json
from pathlib import Path

from .cheap_policy_report import export_csv
from .night_report import render_text

SEEDS=(17,29,43)
COUNTS=(('harm_prevented_counterfactual','Опасные STOP'),
        ('p4_reached_safe93_interruption','Безопасные P4 STOP'),
        ('raw_episode_fpr','Все безопасные STOP'),
        ('unknown_stop','UNKNOWN STOP'))
POLICY_NOTE='A_joint — первичная заранее выбранная политика. B2, Blegacy и C — заранее зафиксированные вторичные сравнения; победитель по новому тесту не выбирается.'


def read(path,default=None):
 return json.loads(path.read_text()) if path.exists() else default


def text(value):
 return html.escape(str(value))


def display(value):
 if value is None:return '—'
 if isinstance(value,dict):
  if 'k' in value and 'n' in value:return f"{value['k']}/{value['n']}"
  return json.dumps(value,ensure_ascii=False,sort_keys=True)
 if isinstance(value,float):return f'{value:.4f}'
 return str(value)


def seeds(rows,key):
 by={r['seed']:r for r in rows}
 if not set(by)&set(SEEDS) and len(by)==1:return display(next(iter(by.values())).get(key))
 return ' / '.join(display(by[s].get(key)) if s in by and by[s].get('complete',True) else '—' for s in SEEDS)


def selected(row):
 return row['arm'] in ('NoDefense','R1','R2') or 'train_selected' in row['arm'] or 'contract' in row['arm'].lower()


def table(rows):
 groups=defaultdict(list)
 for row in rows:groups[row['policy'],row['arm']].append(row)
 intervention=any('contract_intervention_recall' in r for r in rows)
 counts=(('contract_intervention_recall','Требующие вмешательства STOP'),('compliant_stop_fpr','Допустимые STOP'),('compliant_allow_rate','Допустимые ALLOW'),('unknown_stop','UNKNOWN STOP')) if intervention else COUNTS
 risk_keys=() if intervention else ('pr_auc','brier','log_loss','calibration_probability_count')
 headings=['Политика','Метод']+[v for _,v in counts]+([] if intervention else ['PR-AUC','Brier','Log loss','Известные оценки риска'])
 result=['<div class="scroll"><table><thead><tr>'+''.join('<th>'+text(h)+'</th>' for h in headings)+'</tr></thead><tbody>']
 for (policy,arm),rr in sorted(groups.items()):
  cells=[policy,arm]+[seeds(rr,k) for k,_ in counts]+[seeds(rr,k) for k in risk_keys]
  result.append('<tr>'+''.join('<td>'+text(c)+'</td>' for c in cells)+'</tr>')
 return ''.join(result)+'</tbody></table></div>'


def details_json(path,label):
 if path.exists() and path.stat().st_size>100_000:
  relative=path.resolve().relative_to(Path(__file__).resolve().parents[1])
  return '<p>'+text(label)+': <a href="../'+text(relative.as_posix())+'">полный JSON</a> ('+text(path.stat().st_size)+' bytes). Большие диагностические массивы доступны отдельным файлом.</p>'
 value=read(path)
 if value is None:return '<p>'+text(label)+': пока отсутствует.</p>'
 return '<details><summary>'+text(label)+'</summary><pre>'+text(json.dumps(value,ensure_ascii=False,indent=2))+'</pre></details>'



def representative(row):
 arm=row['arm']
 return selected(row) or (arm.count('+')<=1 and arm.startswith(('scalar:', 'logistic:', 'tfidf:', 'catboost:')))


def quality_latency(rows,profiles,choices):
 lookup={(r['seed'],r['config']):r for r in profiles.get('profiles',[])}
 final={(r['policy'],r['denominator'],r['seed'],r['arm']):r for r in choices}
 groups=defaultdict(list)
 for r in rows:
  if r.get('denominator')=='reached' and representative(r):groups[r['policy'],r['arm']].append(r)
 out=['<div class="scroll"><table><tr><th>Политика / метод</th><th>Требующие STOP / цель</th><th>Допустимые STOP</th><th>Архивный singleton head p50/p95, мс; seeds17/29/43</th><th>Архивный cached source p50/p95, мс</th><th>Архивная реконструкция source+head p50/p95, мс</th></tr>']
 for (policy,arm),rr in sorted(groups.items()):
  costs=[[],[],[]]
  for seed in SEEDS:
   c=final.get((policy,'reached',seed,arm),{}).get('config',arm.rsplit(':',1)[0] if ':' in arm else None)
   profile=lookup.get((seed,c),{})
   for dst,key in zip(costs,('warm_single_row_prediction','cached_source_extraction','reconstructed_eager_path_excluding_rules')):
    item=profile.get(key,{})
    dst.append(f"{item['p50_ms']:.3f}/{item['p95_ms']:.3f} (n={item['n']})" if isinstance(item.get('p50_ms'),(int,float)) and isinstance(item.get('p95_ms'),(int,float)) else 'UNKNOWN')
  intervention=any('contract_intervention_recall' in r for r in rr)
  target='contract_intervention_recall' if intervention else 'harm_prevented_counterfactual'
  fp='compliant_stop_fpr' if intervention else 'p4_reached_safe93_interruption'
  cells=[policy+' / '+arm,seeds(rr,target),seeds(rr,fp)]+['; '.join(c) for c in costs]
  out.append('<tr>'+''.join('<td>'+text(c)+'</td>' for c in cells)+'</tr>')
 return ''.join(out)+'</table></div><p>Во всех таблицах, включая внешние когорты, затраты этой колонки относятся к архивной выборке и не являются замером на новых случаях. Стоимость извлечения на независимых случаях дана отдельно в выводах. Head измерен на фиксированной hash-выборке до 16 известных архивных P4 на seed/model, warm singleton с собственным preprocessing. Source взят из фактического кеша; сумма — реконструкция eager serial path без rules и без нового end-to-end замера. Для архивного nested CV это стоимость финальной TRAIN-модели, а не всех fold-моделей. UNKNOWN означает отсутствие измерения, а не нулевую стоимость.</p>'


def semantic_matrix():
 rows=[('R1 / R2','Наблюдаемые факты через замороженный legacy bridge','Прежняя узкая платёжная политика','Ручные правила; UNKNOWN при нехватке фактов'),
 ('ExtensionRules','Общий canonical контракт','Только шесть новых расширений','Отдельный фиксированный prospective control; не полный защитник'),
 ('SecJev 0.8B / 4B','Canonical факты, политика, история и публичное объяснение','Четыре замороженных атомарных вопроса','Ответы не являются вероятностью вреда'),
 ('SecJev sequence','Четыре реальные архивные либо synthetic native стадии','Порядок / агрегаты / динамика атомарных оценок','Синтетические стадии не LLM-траектории; raw64 недоступен'),
 ('Prompt Guard 2 22M / 86M','Недоверенное описание и публичные утверждения агентов','Признаки prompt injection','Не проверяет весь платёжный контракт'),
 ('NLI / MiniCheck','Общий renderer: локальные, полные и facts-only свидетельства','Поддержка фиксированных требований / объяснений','Support не равен разрешению; projections стоят как полный extraction'),
 ('TF-IDF / табличные LR / CatBoost','Текст либо типизированные наблюдаемые признаки','Архивная harm-target supervised модель','Новые target и семейства не использованы для обучения'),
 ('CatBoost комбинации / LR stack','Замороженные блоки вероятностей и optionally tabular','Архивный harm-risk','Все arms отдельно; train_selected выбирается только TRAIN, порог CAL')]
 return '<div class="scroll"><table><tr><th>Метод</th><th>Вход</th><th>Что оценивает</th><th>Ограничение</th></tr>'+''.join('<tr>'+''.join('<td>'+text(c)+'</td>' for c in r)+'</tr>' for r in rows)+'</table></div>'


def resource_table(summary):
 stages=summary.get('stages',[]) if isinstance(summary,dict) else summary
 if not isinstance(stages,list) or not stages:return '<p>Сводка фактических ресурсов пока отсутствует. Память на отдельную модель не выводится из общего process envelope.</p>'
 fields=('block','collection','records','p50_ms','p95_ms','row_sum_ms','cold_setup_ms','cold_setup_status','max_rss_bytes','max_mps_driver_bytes')
 out=['<div class="scroll"><table><tr>'+''.join('<th>'+text(k)+'</th>' for k in fields)+'</tr>']
 for r in stages:
  r=dict(r)
  if not isinstance(r.get('cold_setup_ms'),(int,float)) or r['cold_setup_ms']<=0:
   r['cold_setup_ms']=None;r.setdefault('cold_setup_status','NOT_MEASURED_IN_THIS_COLLECTION')
  out.append('<tr>'+''.join('<td>'+text(display(r.get(k)))+'</td>' for k in fields)+'</tr>')
 return ''.join(out)+'</table></div><p>Cold setup может включать semantic sanity: загрузка весов и sanity должны читаться раздельно по runtime metadata. RSS и Metal driver — наблюдаемые process/device envelope, не память каждого head; их нельзя складывать. Aborted04 учитывается отдельно.</p>'

def refresh(base:Path):
 root=base/'results/guard-v2';evaluation=root/'evaluation-v5';report=base/'reports/guard-v2-report.html'
 report.parent.mkdir(parents=True,exist_ok=True);root.mkdir(parents=True,exist_ok=True)
 sections=[];all_rows=[];statuses=[]
 for name,label,path in (
  ('archive','Исправленный архив: разработка и nested CV',evaluation/'archive-metrics.json'),
  ('archive-partial','Архив с частичными сведениями: отдельная разработка',(root/'evaluation-partial-v5/archive-metrics.json')),
  ('raw64-matched','raw64: сопоставимый PARTIAL→PARTIAL контроль',root/'evaluation-partial-v5/raw64-partial/metrics.json'),
  ('raw64','raw64: вторичная диагностика FULL→RAWFULL',evaluation/'raw64/metrics.json'),
  ('raw64-partial-shift','raw64: дополнительный сдвиг FULL→PARTIAL',evaluation/'raw64-partial-shift/metrics.json'),
  ('independent','Независимый синтетический тест: шесть новых семейств',evaluation/'independent/metrics.json')):
  if name=='independent' and not (path.parent/'UNBLINDED.json').exists():
   sections.append('<h2>'+label+'</h2><p>Тест запечатан либо оценка ещё не завершена. Метрики не прочитаны.</p>')
   statuses.append(name+': SEALED/PENDING');continue
  obj=read(path)
  if obj is None:
   sections.append('<h2>'+label+'</h2><p>Результаты пока отсутствуют; оценка не объявляется завершённой.</p>');statuses.append(name+': PENDING');continue
  rows=[dict(r,evidence_set=name) for r in obj.get('aggregates',[])];all_rows+=rows
  primary=[r for r in rows if r.get('denominator')=='reached']
  legacy=[r for r in rows if r.get('denominator')!='reached']
  statuses.append(f'{name}: {len(rows)} агрегированных строк')
  sections.append('<h2>'+label+'</h2>')
  if name in ('archive','archive-partial'):sections.append('<p>POST-HOC DEVELOPMENT: архив уже известен исследователям. 176 достигших P4: 83 опасных и 93 безопасных; 131 — вторичный знаменатель всех безопасных эпизодов. Изменены renderer, признаки, формулировки требований и основной знаменатель калибровки: сравнение со старыми таблицами не изолирует влияние одного исправления.</p>')
  elif name.startswith('raw64'):sections.append('<p>Это ранее раскрытая диагностика, не независимое подтверждение. Отдельно сопоставляются общий формат и доступность фактов. Прежнее all-STOP нельзя причинно приписать одному фактору без абляций. Пороги по raw64 не настраиваются.</p>')
  else:sections.append('<p>240 сценариев: 120 причинных пар, по 20 пар в каждом семействе; 120 допустимых и 120 предложений, требующих вмешательства. Все достигли P4. Для каждого seed модель обучена на TRAIN; конфигурация выбрана по внутреннему OOF только TRAIN; порог выбран на отдельной групповой CAL для той же модели. После калибровки модель не переобучалась. Исправления подготовки входов сделаны до просмотра качества и разметки; ML-модели и пороги зафиксированы до внешнего предсказания, метки раскрыты после всех prediction freezes. Строгая независимость разработки от просмотра тестовых наблюдений не заявляется. Цель — contract_requires_intervention для статического предложения, а не harm_if_continue: backend может самостоятельно отклонить действие. Показатели предотвращения реального вредного перевода и Brier по прежнему harm-target здесь не вычисляются. Это не живой FinBot.</p>')
  profile_path=(path.parent/'profile.json') if name!='archive' else (evaluation/'profile.json')
  if name.startswith('raw64-matched') or name=='archive-partial':profile_path=root/'evaluation-partial-v5/profile.json'
  profiles=read(profile_path,{})
  if not profiles and not name.startswith(('raw64-matched','archive-partial')):profiles=read(evaluation/'profile.json',{})
  methods_dir=root/'evaluation-partial-v5' if name in ('archive-partial','raw64-matched') else evaluation
  choices=read(methods_dir/'final-choices.json',[])
  sections.append('<h3>Качество на указанной когорте — архивная задержка того же финального head</h3>'+quality_latency(rows,profiles,choices))
  sections.append('<h3>Основная калибровка: достигшие P4 безопасные случаи</h3>'+table([r for r in primary if selected(r)]))
  sections.append('<details><summary>Все фиксированные методы и комбинации</summary>'+table(primary)+'</details>')
  sections.append('<details><summary>Вторичная калибровка по прежнему знаменателю</summary>'+table(legacy)+'</details>')
  if obj.get('by_family'):
   for family,rr in sorted(obj['by_family'].items()):
    sections.append('<details><summary>Семейство: '+text(family)+'</summary>'+table([r for r in rr if r.get('denominator')=='reached' and selected(r)])+'</details>')
  if name not in ('archive','archive-partial'):
   for filename,title in (('unsupported.json','Структурно недоступные методы'),('pair-metrics.json','Парные ошибки'),('coverage.json','Покрытие контракта и наблюдаемость'),('timings.json','Измеренное время предсказания'),('UNBLINDED.json','Граница раскрытия теста'),('external-diagnostics.json','Отдельная ranking/backend диагностика и ExtensionRules')):
    sections.append(details_json(path.parent/filename,title))
 export_csv(root/'comparison.csv',all_rows)
 audit=root/'audit/design-review.md'
 review=render_text(audit.read_text()) if audit.exists() else '<p>Ревью пока отсутствует.</p>'
 findings=root/'findings.md'
 findings_html=render_text(findings.read_text()) if findings.exists() else '<p>Выводы ещё не подготовлены; численные результаты не подставляются заранее.</p>'
 status='<ul>'+''.join('<li>'+text(s)+'</li>' for s in statuses)+'</ul>'
 intro='''<h1>Guard v2: общий вход и независимые семейства</h1>
<p class="note">Новая серия сохраняет все прежние артефакты. Сам факт изменения формата не доказывает причину прежнего all-STOP. Архивная разработка, известный raw64 и независимый новый тест показаны раздельно.</p>
<p>Числа через « / »: seeds 17, 29, 43. Это повторные модели над теми же эпизодами, не три независимые выборки. В каждой дроби указан собственный знаменатель. 120 пар нового теста также не являются 240 независимыми испытаниями для доверительных границ.</p>
<p>UNKNOWN от ошибки модели означает STOP и входит в безопасный знаменатель. Структурно недоступная последовательность — отдельное отсутствие метода, а не конкурентоспособный all-STOP. Оценки атомарных NLI/SecJev/Prompt Guard не называются вероятностью вреда; Brier/log loss применимы к обученным оценкам риска с указанным покрытием.</p>'''
 limitation='''<h2>Границы сравнения и стоимость</h2>
<p>Политики и различия требований нельзя смешивать с ошибками реализации. R1/R2 заморожены под прежнюю политику полной суммы и отсутствия предыдущего перевода; новый контракт допускает законные частичные расчёты. Ошибки старых правил не исправляются изменением тестовых меток. Новые контрактные правила — отдельный метод.</p>
<p>Полный renderer одинаков; назначение моделей различается: Prompt Guard читает недоверенные тексты, NLI проверяет поддержку утверждений, CatBoost учится на архивных исходах. Отсутствие наблюдаемого факта не превращается в ложь. Независимый тест использует ту же TRAIN-модель на CAL и тесте без final-refit; прежний сдвиг OOF→full-fit исключён из этой первичной цепочки. Отдельные nested-CV результаты архива остаются разработкой.</p>
<p>Синтетическая политика использует пороги в major units валюты исходного invoice без USD/FX-конвертации; исходный FinBot задаёт USD-пороги. Применяются исходная нормализованная сумма invoice, а не FX-перевод или остаток. Суммы генератора 120–367 не покрывают границы 5 000 / 10 000 / 50 000 и high-value human review. Поэтому эта серия не подтверждает эти ветви политики. Четыре синтетические стадии — накопительные заранее созданные native снимки, не реальные LLM-траектории.</p>
<p>Дополнительный ExtensionRules — отдельный проспективный контроль шести расширений публичного контракта. Он не входит в основной селектор и не является полным защитником исходной политики. Его код и предсказания запечатаны до меток; результаты нельзя выдавать за добавленную пользу основному методу без отдельного сравнения.</p>
<p>Прерванный AMEND04 сохраняется как отдельный aborted compute; его частичные 146 NLI входов не являются результатом качества и не смешиваются с актуальной ревизией. Resume manifest с written=0 не измеряет стоимость исходного inference: сохраняются фактические stages/gates и исходные row timings. Представления NLI/MiniCheck local/full/facts получают стоимость полного исходного извлечения, а не выдуманную меньшую задержку. CPU/MPS validation, холодная загрузка, warm p50/p95, память, обучение и кеш показываются по сохранённым измерениям. Реконструкция стоимости нескольких этапов не является новым замером end-to-end. Общие источники нельзя дважды учитывать; runtime UNKNOWN и структурная недоступность не имеют выдуманной нулевой стоимости. Локальная денежная стоимость неизвестна; платные inference API в серию не входят.</p>'''
 reproduc='''<h2>Воспроизведение и артефакты</h2><p>См. <a href="../GUARD-V2-FINAL-05.md">завершённая серия: протокол и воспроизведение</a>, <a href="../results/guard-v2/comparison.csv">все агрегаты CSV</a>, <a href="../results/guard-v2/evaluation-v5/METHODS_FROZEN.json">замороженные методы</a>, <a href="../results/guard-v2/evaluation-v5/training-input-freeze.json">входы обучения</a>. Исходный <a href="cheap-policy-report.html">post-hoc отчёт</a> сохранён отдельно.</p>'''
 css='body{font:15px system-ui,sans-serif;max-width:1500px;margin:32px auto;padding:0 20px;color:#20252b;background:#fafbfc}p{max-width:1050px;line-height:1.55}.note{padding:16px;background:#fff1d2;border-left:5px solid #b77b0b}table{border-collapse:collapse;font-size:12px;background:white}th,td{padding:8px;border:1px solid #dce1e6;text-align:left;vertical-align:top}th{background:#edf2f7;position:sticky;top:0}.scroll{overflow:auto;max-height:650px;margin:14px 0}details{margin:14px 0}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;max-height:550px;overflow:auto;font-size:12px}a{color:#155d96}'
 report.write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Guard v2 — исправленный эксперимент</title><style>'+css+'</style><body>'+intro+'<p>'+text(POLICY_NOTE)+'</p>'+status+'<h2>Методы, свидетельства и границы целей</h2>'+semantic_matrix()+'<h2>Выводы</h2>'+findings_html+''.join(sections)+limitation+'<details><summary>Независимый аудит постановки</summary>'+review+'</details>'+details_json(evaluation/'timings.json','Затраты обучения и решений')+'<h2>Фактические ресурсы извлечения</h2>'+resource_table(read(root/'cost-provenance-05.json',read(root/'runtime-summary.json',{})))+details_json(root/'runtime-summary.json','Полные runtime metadata')+details_json(root/'cost-provenance-05.json','Provenance стоимости: actual owner stages, row sums, gates, duplicate overhead и abort04')+details_json(root/'scores-amend04-aborted-summary/runtime-run.json','Отдельная стоимость прерванного AMEND04')+details_json(root/'jev-runtime-provenance-05.json','SecJev: AA, CPU/MPS, холодная загрузка и память')+details_json(root/'latency-summary-05.json','Задержка: когорты и реконструкция мониторинга')+details_json(root/'audit/POLICY_UNDERSPEC_SENSITIVITY_SUMMARY_05.json','Post-hoc: неполнота публичного контракта')+details_json(root/'audit/FINAL_INDEPENDENT_RECOUNT.json','Независимый пересчёт')+reproduc+'</body></html>')
 inputs=[p for p in (root/'comparison.csv',root/'findings.md',audit,root/'runtime-summary.json',root/'cost-provenance-05.json',evaluation/'archive-metrics.json',evaluation/'training-input-freeze.json',evaluation/'METHODS_FROZEN.json',root/'profile.json',evaluation/'profile.json',root/'evaluation-partial-v5/profile.json') if p.is_file()]
 # No traversal of hidden observations, predictions, labels or scorer caches.
 for folder in (evaluation/'independent',evaluation/'raw64',root/'evaluation-partial-v5/raw64-partial',evaluation/'raw64-partial-shift'):
  if folder.name=='independent' and not (folder/'UNBLINDED.json').exists():continue
  inputs.extend(p for p in (folder/'metrics.json',folder/'UNBLINDED.json',folder/'pair-metrics.json',folder/'unsupported.json',folder/'coverage.json',folder/'external-diagnostics.json') if p.exists())
 inputs.extend(p for p in (root/'audit/FINAL_INDEPENDENT_RECOUNT.json',root/'audit/RESULTS_INTERPRETATION_05.json',root/'completion-v5/COMPLETE.json',root/'completion-v5/MANUAL_RECOVERY_RECEIPT.json',root/'SCORING_RECOVERY_PROTOCOL_05.json',root/'PROFILE_COMPAT_PROTOCOL_05.json') if p.exists())
 inputs.extend(p for p in (base/'GUARD-V2-FINAL-05.md',root/'jev-runtime-provenance-05.json',root/'latency-summary-05.json',root/'audit/POLICY_UNDERSPEC_SENSITIVITY_SUMMARY_05.json',root/'audit/POLICY_UNDERSPEC_CASES_05.json',root/'audit/POLICY_UNDERSPEC_SENSITIVITY_SOURCE_FREEZE_05.json',root/'PARTIAL_PROFILE_COMPAT_PROTOCOL_05.json') if p.exists())
 files=[report,Path(__file__).resolve()]+inputs
 manifest={'metric_rows':len(all_rows),'sha256':{str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
 (root/'report-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 return report


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--base',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args();print(refresh(args.base))

if __name__=='__main__':main()
