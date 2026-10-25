import json
import unittest

from prepare_bundle import public_value
from build_report import aligned_common, measured_sum, request_accounting


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


if __name__ == '__main__':
    unittest.main()
