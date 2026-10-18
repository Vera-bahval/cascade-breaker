"""Presentation gates and denominator integrity for corrected experiments."""
import hashlib
import json
from cascade_guard.v2_report import refresh,seeds


def test_independent_metrics_are_not_opened_before_unblind(tmp_path):
 independent=tmp_path/'results/guard-v2/evaluation-v5/independent'
 independent.mkdir(parents=True)
 # Parsing this before the gate would raise, so the test verifies access ordering.
 (independent/'metrics.json').write_text('sealed, deliberately invalid json')
 report=refresh(tmp_path).read_text()
 assert 'SEALED/PENDING' in report and 'Метрики не прочитаны' in report
 assert '240 сценариев' not in report


def test_unblinded_metrics_keep_seeds_and_actual_denominators(tmp_path):
 root=tmp_path/'results/guard-v2';independent=root/'evaluation-v5/independent';independent.mkdir(parents=True)
 (independent/'UNBLINDED.json').write_text('{}')
 rows=[]
 for seed,fp in ((17,3),(43,7)):
  rows.append(dict(policy='A_joint',denominator='reached',seed=seed,arm='train_selected:<unsafe>',
   harm_prevented_counterfactual=dict(k=19,n=20,rate=.95),
   p4_reached_safe93_interruption=dict(k=fp,n=20,rate=fp/20),
   raw_episode_fpr=dict(k=fp,n=20,rate=fp/20),unknown_stop=dict(k=0,n=40,rate=0)))
 (independent/'metrics.json').write_text(json.dumps(dict(aggregates=rows,by_family={'new family':rows})))
 report=refresh(tmp_path)
 content=report.read_text()
 assert '19/20 / — / 19/20' in content
 assert '3/20 / — / 7/20' in content
 assert '&lt;unsafe&gt;' in content and '<unsafe>' not in content
 assert 'Семейство: new family' in content
 assert 'не три независимые выборки' in content
 manifest=json.loads((root/'report-manifest.json').read_text())
 assert manifest['metric_rows']==2
 assert manifest['sha256']['reports/guard-v2-report.html']==hashlib.sha256(report.read_bytes()).hexdigest()
 assert 'p4_reached_safe93_interruption_n' in (root/'comparison.csv').read_text()


def test_missing_status_does_not_become_perfect_result(tmp_path):
 content=refresh(tmp_path).read_text()
 assert 'archive: PENDING' in content and 'raw64: PENDING' in content
 assert 'оценка не объявляется завершённой' in content
 assert 'runtime: 0' not in content


def test_seed_display_keeps_incomplete_seed_missing():
 assert seeds([dict(seed=17,complete=False,metric={'k':0,'n':20})],'metric')=='— / — / —'


def test_intervention_target_does_not_claim_money_harm_or_brier():
 from cascade_guard.v2_report import table
 r=dict(seed=17,policy='A_joint',arm='R1',contract_intervention_recall={'k':3,'n':20},compliant_stop_fpr={'k':2,'n':20},compliant_allow_rate={'k':18,'n':20},unknown_stop=0,brier=.01)
 content=table([r])
 assert 'Требующие вмешательства STOP' in content
 assert '3/20 / — / —' in content
 assert 'Brier' not in content and 'Опасные STOP' not in content


def test_quality_latency_reports_actual_profile_count_and_missing_as_unknown():
 from cascade_guard.v2_report import quality_latency
 rows=[dict(seed=17,policy='A_joint',denominator='reached',arm='catboost:N:none',contract_intervention_recall={'k':1,'n':2},compliant_stop_fpr={'k':0,'n':2})]
 profile=dict(seed=17,config='catboost:N',warm_single_row_prediction=dict(n=16,p50_ms=1.,p95_ms=2.),cached_source_extraction=dict(n=16,p50_ms=10.,p95_ms=20.),reconstructed_eager_path_excluding_rules=dict(n=16,p50_ms=11.,p95_ms=22.))
 content=quality_latency(rows,{'profiles':[profile]},[])
 assert '1.000/2.000 (n=16)' in content and '10.000/20.000 (n=16)' in content
 assert 'UNKNOWN' in content and 'реконструкция eager serial path' in content
