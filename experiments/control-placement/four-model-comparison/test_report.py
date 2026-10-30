import json
import gzip
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import build_report
from prepare_bundle import public_value, publication_bytes, source_revision
from build_report import (aligned_common, measured_sum, request_accounting, require_cohort,
                          any_known, observed_rate, guard_sample, guard_input_fpr,
                          legacy_guards, cost_reconciliation, luna_accounting)
from validate_bundle import validate_public_json


class ReportTests(unittest.TestCase):
    # Общая выборка требует одинаковых идентификаторов и не принимает дубликаты.
    def test_alignment_rejects_duplicate(self):
        row = dict(dataset='fpr', scenario_id='A', repeat=1)
        with self.assertRaises(ValueError):
            aligned_common({'mini': [row, row], 'luna': [row]})

    # Отсутствующие токены не превращаются в измеренный ноль.
    def test_missing_counter(self):
        self.assertIsNone(measured_sum([None, None]))
        self.assertEqual(measured_sum([0, 4, None]), 4)

    # Несовпадающие наборы нельзя незаметно свести пересечением.
    def test_alignment_rejects_missing_episode(self):
        a = dict(dataset='fpr', scenario_id='A', repeat=1)
        b = dict(dataset='fpr', scenario_id='B', repeat=1)
        with self.assertRaises(ValueError):
            aligned_common({'mini':[a,b], 'luna':[a]})

    # Известная часть стоимости не выдаётся за полную при неизвестной попытке.
    def test_unknown_cost_keeps_total_null(self):
        value = request_accounting([{'cost':1.2}, {'cost':None}], 'cost')
        self.assertEqual(value['known_cost_usd'], 1.2)
        self.assertEqual(value['cost_unknown_requests'], 1)
        self.assertIsNone(value['total_cost_usd'])

    # Публичная копия сохраняет стоимость и удаляет служебные сведения аккаунта.
    def test_public_envelope(self):
        source = {'response': {'usage': {'input_tokens': 4}}, 'cost': .1, 'key': 'private-id',
                  'stats': {'user': 'private-user', 'quota': {'x': 10}, 'usage': {'x': 2},
                            'provider': 'backend', 'model_family': 'deepseek'}}
        result = public_value(source)
        self.assertEqual(result['cost'], .1)
        self.assertEqual(result['response']['usage']['input_tokens'], 4)
        self.assertNotIn('key', result)
        self.assertEqual(result['stats'], {'provider': 'backend', 'model_family': 'deepseek'})
        self.assertIn('user', source['stats'])

    # Строковое HTTP-тело очищается тем же правилом, а бизнес-данные остаются.
    def test_raw_body_and_business_key(self):
        source = {'event': 'http_response', 'raw_body': json.dumps({'response': {}, 'cost': 0,
                  'key': 'private-id', 'stats': {'user': 'private-user'}})}
        result = public_value(source)
        self.assertNotIn('key', json.loads(result['raw_body']))
        self.assertEqual(public_value({'key': 'invoice-field', 'value': 1})['key'], 'invoice-field')

    # Дубль повтора Веры не может заменить другой повтор при прежнем числе строк.
    def test_repeat_identity_coverage(self):
        a = dict(dataset='vera7', scenario_id='V1', repeat=1)
        b = dict(a, repeat=2)
        with self.assertRaises(ValueError):
            require_cohort([a, a], [('vera7','V1',1), ('vera7','V1',2)], 'fixture')
        with self.assertRaises(ValueError):
            require_cohort([a, b], [('vera7','V1',1), ('vera7','V2',1)], 'fixture')

    # Загрузка native-эпизодов отвергает дубли Веры ещё до агрегации метрик.
    def test_native_duplicate_vera(self):
        original_load = build_report.load
        def duplicate(name):
            value = original_load(name)
            if name == 'luna-episodes.json':
                positions = [i for i,r in enumerate(value) if r['phase']=='main' and r['dataset']=='vera7']
                value[positions[-1]] = value[positions[0]]
            return value
        with patch.object(build_report, 'load', side_effect=duplicate):
            with self.assertRaisesRegex(ValueError, 'Duplicate episode: native luna'):
                build_report.native_models()

    # Пропущенная проверка отличается от измеренного отрицательного ответа.
    def test_missing_guard_is_not_false(self):
        self.assertIsNone(any_known(False, None))
        self.assertTrue(any_known(True, None))
        value = observed_rate([False, None])
        self.assertIsNone(value['rate'])
        self.assertIsNone(value['k'])
        self.assertEqual(value['missing'], 1)

    # Исчезнувшее поле старого защитника не превращает результат в ноль.
    def test_legacy_guard_missing_view(self):
        real_loads = json.loads
        def remove_view(data):
            value = real_loads(data)
            for row in value.get('items', []):
                if row.get('kind') == 'harm':
                    row.pop('orch', None)
            return value
        with patch.object(build_report.json, 'loads', side_effect=remove_view):
            variants, _ = legacy_guards()
        self.assertIsNone(variants['v2:orchestrator']['harm_detected']['rate'])

    # Отсутствие двух boundary-представлений не создаёт бесплатную проверку.
    def test_missing_guard_economics(self):
        sample, _ = guard_sample({'views':{}}, 'facts', 'boundary')
        self.assertIsNone(sample['cost_usd'])
        self.assertIsNone(sample['query_duration_sum_s'])
        partial = {'views':{'facts:b_invoice':{'cost_usd':.1,'latency_s':2}}}
        self.assertIsNone(guard_sample(partial, 'facts', 'boundary')[0]['cost_usd'])
        self.assertEqual(guard_sample({}, 'v2', 'rules')[0]['cost_usd'], 0)

    # Сумма длительностей голосов и оценка параллельного запуска различаются.
    def test_vote_durations(self):
        guard = {'votes':[{'cost_usd':.1,'latency_s':v} for v in (1,2,3)]}
        sample, _ = guard_sample(guard, 'v2', 'input')
        self.assertEqual(sample['query_duration_sum_s'], 6)
        self.assertEqual(sample['input_votes_parallel_duration_s'], 3)
        self.assertAlmostEqual(sample['cost_usd'], .3)

    # Знаменатель FPR читается из summary даже для другой по размеру серии.
    def test_guard_denominator_from_summary(self):
        summary = {'phases':{'main':{'input_guard_fpr':{'numerator':1,'denominator':8}}}}
        with patch.object(build_report, 'load', return_value=summary):
            self.assertEqual(guard_input_fpr('fixture')['rate'], .125)

    # Все фазы сверяются с billing proof; изменённая сумма останавливает сборку.
    def test_billing_reconciliation(self):
        ds = [{'phase':'main','eliza_cost_usd':4}, {'phase':'pilot','eliza_cost_usd':.5}]
        proof = dict(accepted=True, cost_usd=4.5, unknown_requests=0, successful_paid_requests=2)
        with patch.object(build_report, 'load', return_value=proof):
            value = cost_reconciliation(ds, [])['deepseek']
            self.assertEqual(value['phases']['main']['total_cost_usd'], 4)
            self.assertEqual(value['all_phases']['total_cost_usd'], 4.5)
        with patch.object(build_report, 'load', return_value=dict(proof, cost_usd=4.6)):
            with self.assertRaises(ValueError):
                cost_reconciliation(ds, [])

    # Неизвестный расход и несовпавшие границы оценки Luna остаются явными.
    def test_luna_estimate_interval(self):
        value = luna_accounting([{'estimate_lower_usd':1,'estimate_upper_usd':2},
                                 {'estimate_lower_usd':None,'estimate_upper_usd':None}])
        self.assertEqual(value['known_lower_usd'], 1)
        self.assertEqual(value['known_upper_usd'], 2)
        self.assertIsNone(value['known_cost_usd'])
        self.assertIsNone(value['total_cost_usd'])

    # Статистика меняет и таблицы, и вводный текст отчёта.
    def test_render_uses_data(self):
        data = json.loads((build_report.HERE/'comparison.json').read_text())
        data['common_metrics']['luna']['honest_transfer_attempt']['k'] = 42
        data['main_costs']['deepseek_main_reconciled_usd'] = 4.123
        with tempfile.TemporaryDirectory() as td, patch.object(build_report, 'HERE', Path(td)):
            build_report.render(data)
            text = (Path(td)/'REPORT.md').read_text()
        self.assertIn('GPT-6 Luna High: 42/150 честных', text)
        self.assertIn('| Списание Eliza, main, USD | 4.123000000 |', text)

    # Все сжатые индексы и карты защитников проходят одинаковую очистку и проверку.
    def test_compressed_public_inputs(self):
        value = {'eliza_stats':{'user':'private-user'}, 'nested':{'response':{},'cost':0,'key':'private'}}
        for name in ('luna-requests.json.gz','deepseek-defenders.json.gz','luna-defenders.json.gz'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as td:
                path = Path(td)/name
                path.write_bytes(gzip.compress(json.dumps(value).encode()))
                with self.assertRaises(ValueError):
                    validate_public_json(path.read_bytes(), name)
                clean = publication_bytes(path)
                validate_public_json(clean, name)
                self.assertEqual(json.loads(gzip.decompress(clean)), public_value(value))

    # Ревизии берутся из указанного репозитория, независимо от каталога процесса.
    def test_source_revision_from_other_directory(self):
        with tempfile.TemporaryDirectory() as td:
            roots = [Path(td)/name for name in ('source','caller')]
            for root in roots:
                subprocess.run(['git','init','-q',str(root)], check=True)
                subprocess.run(['git','-C',str(root),'-c','user.name=Test','-c','user.email=test@example.invalid',
                                'commit','-q','--allow-empty','-m',root.name], check=True)
                for ref in ('refs/remotes/origin/main', 'refs/remotes/origin/research/control-placement'):
                    subprocess.run(['git','-C',str(root),'update-ref',ref,'HEAD'], check=True)
            expected = subprocess.check_output(['git','-C',str(roots[0]),'rev-parse','HEAD'], text=True).strip()
            previous = Path.cwd()
            try:
                os.chdir(roots[1])
                for ref in ('HEAD','origin/main','origin/research/control-placement'):
                    self.assertEqual(source_revision(roots[0], ref), expected)
            finally:
                os.chdir(previous)


if __name__ == '__main__':
    unittest.main()
