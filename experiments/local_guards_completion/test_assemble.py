import unittest
from .assemble import aggregate, targets, CHANGED


class AssemblyTests(unittest.TestCase):
    def test_known_violation_dominates_unknown_without_losing_substance_axis(self):
        revised = {k: dict(status='satisfied') for k in CHANGED}
        revised['N14']['status'] = 'violated'
        revised['N11']['status'] = 'unknown'
        result = targets({'N01':dict(status='satisfied')}, revised)
        self.assertEqual(result['process_label'], 'BLOCK')
        self.assertEqual(result['substantive_label'], 'INSUFFICIENT')
        self.assertEqual(result['action_label'], 'BLOCK')
        self.assertEqual(result['without_tax_label'], 'INSUFFICIENT')

    def test_missing_status_not_silently_approved(self):
        with self.assertRaises(ValueError):
            aggregate([])


if __name__ == '__main__':
    unittest.main()
