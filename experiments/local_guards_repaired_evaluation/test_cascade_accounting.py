import unittest
from .cascade_accounting import route,metrics,one,quantile

class AccountingTests(unittest.TestCase):
    def test_routing_policies(self):
        self.assertEqual(route('UNKNOWN','ALLOW','local'),('UNKNOWN',False))
        self.assertEqual(route('ALLOW','BLOCK','block_then_llm'),('BLOCK',True))
        self.assertEqual(route('BLOCK','ALLOW','block_then_llm'),('BLOCK',False))
        self.assertEqual(route('ADAPTER_UNAVAILABLE','BLOCK','decisive_then_llm'),('BLOCK',True))
        self.assertEqual(route('ALLOW','BLOCK','decisive_then_llm'),('ALLOW',False))
    def test_unknown_stop_is_not_false_block(self):
        labels={'x':{'label':{'action_label':'ALLOW','author_category':'legit'}}}
        r=metrics(labels,{'x':'UNKNOWN'})
        self.assertEqual((r['false_block'],r['safe_stop'],r['legit_stop']),(0,1,1))
    def test_charges_and_time_only_when_called(self):
        labels={k:{'label':{'action_label':'BLOCK','author_category':'fraud'}} for k in ('x','y')}
        saved={k:dict(decision='ALLOW',query_id=k,charge_usd=cost,decision_ms=delay) for k,cost,delay in [('x',.3,100),('y',.7,200)]}
        r=one(labels,{'x':'BLOCK','y':'UNKNOWN'},saved,{'x':2,'y':3},'block_then_llm')
        self.assertEqual(r['historical_api_usd'],'0.7');self.assertEqual(r['llm_calls'],1)
        self.assertEqual(r['paired_elapsed_ms'],{'x':2,'y':203})
        self.assertEqual((r['p50_ms'],r['p95_ms']),(2,203))
    def test_quantile_not_sum_of_quantiles(self):
        self.assertEqual(quantile([1,3,2],.95),3)
        self.assertIsNone(quantile([],.5))

if __name__=='__main__':unittest.main()
