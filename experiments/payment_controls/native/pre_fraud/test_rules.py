import unittest
from experiments.payment_controls.native.pre_fraud.rules import assess, payment_amount_gate

BASE = dict(industry='other', tin='valid', bank_details='match', bank_change='none',
            duplicate_invoice='none', same_invoice_completed_payment='no',
            amount_or_frequency_anomaly='none', history_review='complete', current_risk='low')


class RulesTest(unittest.TestCase):
    def check(self, changes, expected):
        return_value = assess({**BASE, **changes})
        self.assertEqual(return_value['fraud_assessment'], expected)
        self.assertEqual(return_value['fraud_investigation'], 'proceed')
        self.assertFalse(return_value['payment_authorized'])
        return return_value

    def test_bank_change_and_mismatch(self):
        self.check({'bank_change':'verified'}, 'no_flag_indicated')
        self.check({'bank_change':'unverified'}, 'review')
        self.assertIn('mismatched_details', self.check({'bank_change':'verified', 'bank_details':'mismatch'}, 'flag')['required_flag_reasons'])

    def test_contextual_anomaly(self):
        self.check({'amount_or_frequency_anomaly':'none'}, 'no_flag_indicated')
        self.check({'amount_or_frequency_anomaly':'justified'}, 'no_flag_indicated')
        self.check({'amount_or_frequency_anomaly':'unexplained'}, 'review')
        self.check({'amount_or_frequency_anomaly':'unknown'}, 'review')

    def test_invoice_similarity_versus_repeat_payment(self):
        self.check({'duplicate_invoice':'suspected'}, 'review')
        self.check({'duplicate_invoice':'confirmed'}, 'flag')
        r = self.check({'same_invoice_completed_payment':'yes'}, 'no_flag_indicated')
        self.assertEqual(r['repeat_payment_gate'], 'block')
        self.assertEqual(self.check({'same_invoice_completed_payment':'unknown'}, 'review')['repeat_payment_gate'], 'unknown')

    def test_ablation_and_required_flags(self):
        for field, bad, reason in [('industry','prohibited','compliance_violation:prohibited_industry'),
                                   ('tin','invalid','compliance_violation:invalid_tin'),
                                   ('bank_details','mismatch','mismatched_details'),
                                   ('duplicate_invoice','confirmed','duplicate_pattern')]:
            with self.subTest(field=field):
                r = self.check({field:bad, 'bank_change':'verified', 'amount_or_frequency_anomaly':'justified'}, 'flag')
                self.assertIn(reason, r['required_flag_reasons'])
                self.check({field:'unknown'}, 'review')
        self.check({'history_review':'incomplete'}, 'review')
        self.check({'current_risk':'high'}, 'review')

    def test_payment_ceiling_boundary_and_invalid_values(self):
        self.assertEqual(payment_amount_gate(50000)['payment_gate'], 'not_blocked_by_ceiling')
        result = payment_amount_gate(50000.01)
        self.assertEqual(result['payment_gate'], 'block')
        self.assertEqual(result['fraud_investigation'], 'proceed')
        self.assertFalse(result['payment_authorized'])
        for value in (True, '50001', float('nan'), float('inf')):
            with self.assertRaises(ValueError): payment_amount_gate(value)

    def test_schema_rejects_missing_invalid_extra(self):
        for bad in ({}, {**BASE, 'tin':None}, {**BASE,'extra':'yes'}):
            with self.assertRaises(ValueError): assess(bad)

if __name__ == '__main__': unittest.main()
