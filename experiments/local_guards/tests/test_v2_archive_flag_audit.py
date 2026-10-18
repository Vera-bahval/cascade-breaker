import unittest
from cascade_guard.v2_archive_flag_audit import flag_commit, flags


class ArchiveFlagTests(unittest.TestCase):
    def test_observed_true_false_unknown_are_distinct(self):
        self.assertIs(flag_commit({'output': {'flagged': True}})[0], True)
        self.assertIs(flag_commit({'output': {'flagged': False}})[0], False)
        self.assertIsNone(flag_commit({'output': {}})[0])
        self.assertIsNone(flag_commit({'error': 'transport failure'})[0])
        self.assertIsNone(flag_commit({'output': {'flagged': True, 'error': 'contradiction'}})[0])

    def test_unknown_bounds_do_not_invent_confirmation(self):
        items = [{'kind': 'tool', 'name': 'flag_invoice_for_review', 'output': output}
                 for output in ({'flagged': True}, {'flagged': False}, {})]
        self.assertEqual(flags(items, unknown_stops=False), items[:1])
        self.assertEqual(flags(items, unknown_stops=True), [items[0], items[2]])


if __name__ == '__main__': unittest.main()
