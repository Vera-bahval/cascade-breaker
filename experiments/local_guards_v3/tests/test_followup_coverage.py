"""Check that the open coverage probe does not invent trusted chat authorizations."""
import copy
import json
import sys
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from followup_coverage import conditional_observation
from rules_v3 import guard


class CoverageProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = {r["scenario"]["id"]: r["scenario"] for r in json.loads(
            (HERE / "results/followup-coverage/catalog-source.json").read_text())["records"]}

    def test_chat_hold_remains_text_only(self):
        obs, _ = conditional_observation(self.catalog["S06_n"])
        self.assertFalse(obs["facts"]["binding_hold"])
        self.assertEqual(guard(obs)["decision"], "ALLOW")
        obs["facts"]["binding_hold"] = True
        self.assertEqual(guard(obs)["decision"], "BLOCK")

    def test_quote_positive_does_not_fabricate_manual_approval(self):
        obs, _ = conditional_observation(self.catalog["S20_p"])
        self.assertIsNone(obs["facts"]["human_approved"])
        self.assertEqual(guard(obs)["decision"], "UNKNOWN")

    def test_catalog_negative_is_not_automatically_action_block(self):
        obs, _ = conditional_observation(self.catalog["S01_n"])
        self.assertEqual(guard(obs)["decision"], "ALLOW")
        renamed = copy.deepcopy(self.catalog["S01_n"])
        renamed["id"], renamed["title"] = "unrelated", "unrelated"
        self.assertEqual(conditional_observation(renamed)[0], obs)


if __name__ == "__main__":
    unittest.main()
