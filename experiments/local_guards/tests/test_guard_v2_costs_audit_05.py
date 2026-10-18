"""Independent metadata-boundary fixtures; no experiment data is opened."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'cost_audit', Path(__file__).parents[1] / 'scripts/audit_guard_v2_costs_05.py')
addon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(addon)


class CostBoundaryAudit(unittest.TestCase):
    def test_unrequested_nested_container_strings_are_skipped(self):
        raw = ('{"features":{"quoted":"escaped \\\" } ] : ","nested":[UNREAD]},'
               '"probability":UNREAD,"timing_ms":{"total":12.5}}')
        projected, end = addon.project(raw, addon.ROW_FIELDS)
        self.assertEqual(projected, {'timing_ms': {'total': 12.5}})
        self.assertEqual(end, len(raw))

    def test_container_in_scalar_slot_fails_before_decoder(self):
        raw = '{"timing_ms":{"total":{"labels":UNREAD}}}'
        with self.assertRaises(ValueError) as raised:
            addon.project(raw, addon.ROW_FIELDS)
        self.assertNotEqual(type(raised.exception).__name__, 'JSONDecodeError')

    def test_fractional_stage_wall_uses_exact_observed_interval(self):
        stage = {'started_at': '2026-10-15T12:00:00.125+00:00',
                 'finished_at': '2026-10-15T12:00:01.875+00:00'}
        self.assertEqual(addon.interval(stage), 1750.0)
        self.assertIsNone(addon.interval({'started_at': 'UNKNOWN'}))


if __name__ == '__main__':
    unittest.main()
