"""API-free replay checks: effects/STOP, registry readback, and timing accounting."""
from pathlib import Path
import sys
import unittest
import gc
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from experiments.local_guards_archive_comparison import replay


class ReplayTests(unittest.TestCase):
    def test_scripted_chat_chain_reaches_native_payment_and_records_delegations(self):
        self.assertTrue(callable(getattr(replay, 'native_trial', None)), 'native replay runner is missing')
        result = replay.native_trial('extension', 'safe', diagnosis=False)
        self.assertEqual((result['status'], result['payments'], result['invoice_status']),
                         ('completed', 1, 'paid'))
        self.assertEqual(result['registry']['technical_delegations'], 4)
        self.assertGreater(result['registry']['completed_transfer_events'], 0)
        self.assertGreater(len(result['timings']['decision_ready_ms']), 0)
        self.assertEqual(result['external_socket_attempts'], 0)

    def test_native_amount_mismatch_stops_with_no_transfer_or_later_model(self):
        off = replay.native_trial('extension', 'amount_mismatch', diagnosis=False)
        on = replay.native_trial('extension', 'amount_mismatch', diagnosis=True)
        for result in (off, on):
            self.assertEqual((result['status'], result['payments']), ('stopped', 0))
            self.assertTrue(result['stop_persisted'])
            self.assertTrue(result['later_model_blocked'])
            self.assertTrue(result['later_native_effect_blocked'])
        self.assertEqual(replay.effect_signature(off), replay.effect_signature(on))
        self.assertEqual(off['timings']['diagnosis_ms'], [])
        self.assertGreater(len(on['timings']['diagnosis_ms']), 0)

    def test_material_change_is_separate_extension_and_reads_real_binding(self):
        result = replay.native_trial('extension', 'material_change', diagnosis=False)
        self.assertEqual((result['status'], result['payments']), ('stopped', 0))
        self.assertEqual(result['material_binding']['before']['invoice_version'], 'invoice:1')
        self.assertIsNone(result['material_binding']['after'])
        self.assertIn('B01:unknown', result['stop']['reasons'])

    def test_new_native_profile_uses_real_p4_arguments_and_state(self):
        self.assertTrue(callable(getattr(replay, 'native_profile_trial', None)), 'native profile hook adapter is missing')
        # Native guard is unchanged; the old timed driver also pinned an unused
        # pre-compatibility ML file. Inject only the independently verified guard.
        from unittest.mock import patch
        from experiments.local_guards_archive_comparison.methods import guard
        expected = '8e7aa49c198a23f8313fdc9ee2873ad099c1112aae2d4a7d85990888be73a81b'
        self.assertEqual(replay.digest(replay.HERE/'methods.py'), expected)
        with patch.object(replay, 'load_native_guard', return_value=(guard, expected)):
            good = replay.native_profile_trial('safe', diagnosis=False)
            bad = replay.native_profile_trial('amount_mismatch', diagnosis=True)
        self.assertEqual((good['status'], good['payments']), ('completed', 1))
        self.assertEqual((bad['status'], bad['payments']), ('stopped', 0))
        self.assertEqual(good['p4_verdicts'], ['ALLOW'])
        self.assertEqual(bad['p4_verdicts'], ['BLOCK'])
        self.assertTrue(bad['later_model_blocked'])
        self.assertTrue(bad['later_native_effect_blocked'])
        self.assertNotIn('invoice_currency', good['common_row_facts'])
        self.assertEqual(good['profile'], 'native')
        self.assertTrue(good['temporary_cleanup']['sidecar_directory_removed'])

    def test_sqlite_wait_is_not_a_business_duplicate_denial(self):
        gc.collect()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', ResourceWarning)
            result = replay.contention_trial('same_invoice', workers=2)
            gc.collect()
        self.assertEqual([str(item.message) for item in caught if 'unclosed database' in str(item.message)], [])
        self.assertEqual(sorted(r['outcome'] for r in result['attempts']),
                         ['admitted', 'business_duplicate_denied'])
        self.assertEqual(result['sqlite_lock_errors'], 0)
        self.assertEqual(result['remaining_active_claims'], 0)
        other = replay.contention_trial('different_vendor_keys', workers=2)
        self.assertEqual([r['outcome'] for r in other['attempts']], ['admitted', 'admitted'])
        self.assertEqual(other['remaining_active_claims'], 0)


if __name__ == '__main__':
    unittest.main()
