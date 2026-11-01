import tempfile
import unittest
from pathlib import Path
from experiments.local_guards_archive_comparison.eliza import Ledger, parse_answer, query_identity, remaining


class ElizaBoundaryTests(unittest.TestCase):
    def test_unknown_charge_blocks_restart_and_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'ledger.sqlite'
            ledger = Ledger(p, 1)
            ledger.reserve('a', .2)
            with self.assertRaises(RuntimeError):
                Ledger(p, 1).reserve('a', .2)
            with self.assertRaises(RuntimeError):
                Ledger(p, 1).reserve('b', .2)
            ledger.complete('a', .1)
            ledger.reserve('b', .9)
            with self.assertRaises(RuntimeError):
                ledger.reserve('c', .1)

    def test_cost_and_output_must_be_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Ledger(Path(d)/'ledger.sqlite', 1)
            ledger.reserve('a', .2)
            for cost in [None, -1, float('nan'), True]:
                with self.assertRaises(ValueError):
                    ledger.complete('a', cost)
        for text in ['{}', '{"decision":"maybe"}', '{"decision":true}']:
            self.assertEqual(parse_answer(text)['decision'], 'UNKNOWN')
        self.assertEqual(parse_answer('{"decision":"BLOCK","reason":"native amount"}')['decision'], 'BLOCK')

    def test_context_identity_and_quota(self):
        a={'model':'deepseek-flash','messages':[{'role':'user','content':'x'}]}
        self.assertNotEqual(query_identity(a), query_identity(dict(a, temperature=0)))
        self.assertNotEqual(query_identity(a), query_identity(dict(a, model='other')))
        meta={'quotas':{'quotas':{'external':{'limits':[
            {'name':'all','limits':[{'type':'daily','usage':{'cost':15}}]},
            {'name':'chain:top_opensource','limits':[{'type':'monthly','usage':{'cost':50}}]}]}}},
            'usage':{'usage':{'chain:top_opensource':{'stats':{'monthly':{'cost':3},'daily':{'cost':1}}}}}}
        self.assertEqual(remaining(meta), {'monthly_usd':47., 'daily_usd':14.})


if __name__=='__main__': unittest.main()
