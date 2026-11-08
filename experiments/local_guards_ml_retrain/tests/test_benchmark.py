"""Benchmark accounting tests on own fixtures, never new test labels."""
import os
from pathlib import Path
import sys
import unittest
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))

class BenchmarkTests(unittest.TestCase):
    def module(self):
        self.assertTrue((HERE/'benchmark.py').exists(),'benchmark driver is not implemented')
        import benchmark
        return benchmark
    def test_stratified_sample_deterministic_and_eligible(self):
        bm=self.module()
        rows=[dict(prefix_id=str(i),observation=dict(checkpoint='P4' if i%2 else 'P0',proposal=dict(tool='finstripe__create_transfer'))) for i in range(20)]
        meta={r['prefix_id']:dict(family='f'+str(int(r['prefix_id'])%3)) for r in rows}
        a=bm.stratified_sample(rows,meta,'payment_v3',5)
        self.assertEqual([r['prefix_id'] for r in a],[r['prefix_id'] for r in bm.stratified_sample(rows,meta,'payment_v3',5)])
        self.assertEqual(len(a),5);self.assertTrue(all(r['observation']['checkpoint']=='P4' for r in a))
    def test_parent_linkage_never_fabricated(self):
        bm=self.module()
        class Agent:workflow_id='real-agent-workflow'
        link=(Agent(),'delegate_to_invoice',{},dict(context=dict(call_id='real-call')))
        self.assertEqual(bm.delegation_context('P2',link),dict(parent_workflow_id='real-agent-workflow',call_id='real-call'))
        self.assertEqual(bm.delegation_context('P2',None),{})
        self.assertEqual(bm.delegation_context('P1',link),{})
    def test_chain_summary_separates_stops_from_completion(self):
        bm=self.module()
        r=bm.native_summary([dict(method='m',status='completed',elapsed_ms=100,check_ms=[1]),dict(method='m',status='stopped',elapsed_ms=10,check_ms=[2])])['m']
        self.assertEqual(r['completed_chain']['n'],1);self.assertEqual(r['stopped_chain']['p50_ms'],10)
        self.assertNotIn('whole_chain',r)

if __name__=='__main__':unittest.main()
