import importlib.util
import unittest

from cascade_guard.mps_diagnostics import aa_summary, unit_lower_inverse


class DiagnosticsTests(unittest.TestCase):
    def test_aa_detects_missing_and_changing_distributions(self):
        def result(p):
            return {"status":"OK", "probabilities":{"q":{"true":p,"false":1-p}}, "timing_ms":{"compute":1}}
        self.assertTrue(aa_summary([result(.2),result(.2),result(.2)])["identical"])
        self.assertFalse(aa_summary([result(.2),result(.8),result(.2)])["stable_decisions"])
        self.assertFalse(aa_summary([result(.2),{"status":"UNKNOWN","error":"NaN"}])["identical"])

    @unittest.skipUnless(importlib.util.find_spec("torch"), "Run numerical solver checks in the separate SecJev/MPS environment")
    def test_block_inverse_matches_five_dimensional_unit_lower_solve(self):
        import torch
        torch.manual_seed(17)
        a = torch.randn(2,3,4,64,64)*.015
        b = torch.randn(2,3,4,64,128)
        # Deliberately non-unit diagonal/upper values must be ignored.
        reference = torch.linalg.solve_triangular(a,b,upper=False,unitriangular=True)
        candidate = unit_lower_inverse(torch,a) @ b
        self.assertLess(float((reference-candidate).abs().max()),1e-5)
        with self.assertRaises(ValueError):
            unit_lower_inverse(torch,torch.ones(3,3))


if __name__ == "__main__":
    unittest.main()
