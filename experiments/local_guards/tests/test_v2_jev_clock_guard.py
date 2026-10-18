import importlib.util
from pathlib import Path
import unittest

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('jev_clock_guard',BASE/'scripts/run_guard_v2_jev_serial_v5_guarded.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
METHOD=BASE/'results/guard-v2/METHOD_FREEZE_05.json'
DEADLINE='2026-10-15T22:59:58.072112+00:00'
CUTOFF='2026-10-15T21:39:58.072112+00:00'


class ClockGuardTest(unittest.TestCase):
 def test_exact_frozen_clocks_accepted(self):
  self.assertEqual(guard.validate_clock(METHOD,DEADLINE,CUTOFF)['inference_cutoff_utc'],CUTOFF)

 def test_absolute_deadline_cannot_extend_one_microsecond(self):
  with self.assertRaisesRegex(ValueError,'absolute deadline'):
   guard.validate_clock(METHOD,'2026-10-15T22:59:58.072113+00:00',CUTOFF)

 def test_model_cutoff_cannot_move_one_microsecond(self):
  with self.assertRaisesRegex(ValueError,'prospective cutoff'):
   guard.validate_clock(METHOD,DEADLINE,'2026-10-15T21:39:58.072113+00:00')


if __name__=='__main__':unittest.main()
