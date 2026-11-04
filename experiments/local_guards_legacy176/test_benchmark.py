import unittest
from .benchmark import canonical_result

class BenchmarkTests(unittest.TestCase):
    def test_evidence_order_is_not_a_decision_difference(self):
        a={'decision':'BLOCK','evidence':[{'fact':'x','value':1},{'fact':'y','value':2}]}
        b={'decision':'BLOCK','evidence':list(reversed(a['evidence']))}
        self.assertEqual(canonical_result(a),canonical_result(b))
        b['evidence'][0]={'fact':'y','value':3}
        self.assertNotEqual(canonical_result(a),canonical_result(b))

if __name__=='__main__':unittest.main()
