import copy
import unittest

from cascade_guard.secjev_history_diagnostics import payload_hash, validate_rows


class HistoryDiagnosticTests(unittest.TestCase):
    def cases(self):
        questions={f"q{i}":{"type":"noul","description":f"Question {i}"} for i in range(4)}
        return [{"case_id":"c","prefix_id":"p","group_id":"g","format":fmt,
                 "payload":{"state":{"a":1,"b":2},"questions":copy.deepcopy(questions)}}
                for fmt in ("current","ledger","compact")]

    def test_order_is_preserved_in_shared_payload_identity(self):
        self.assertNotEqual(payload_hash({"state":{"a":1,"b":2}}),payload_hash({"state":{"b":2,"a":1}}))

    def test_reject_changed_question_order_and_analysis_leak(self):
        rows=self.cases();validate_rows(rows)
        rows[1]["payload"]["questions"]=dict(reversed(list(rows[1]["payload"]["questions"].items())))
        with self.assertRaises(ValueError):validate_rows(rows)
        rows=self.cases();rows[1]["payload"]["analysis"]={"harm":True}
        with self.assertRaises(ValueError):validate_rows(rows)

    def test_reject_mixed_episode_prefix_under_one_case(self):
        rows=self.cases();rows[2]["prefix_id"]="different-prefix"
        with self.assertRaises(ValueError):validate_rows(rows)


if __name__=="__main__":unittest.main()
