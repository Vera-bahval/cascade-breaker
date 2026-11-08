import unittest
from .timing import union_ms,clock,stats

class TimingTests(unittest.TestCase):
    def test_union_not_sum(self):
        self.assertEqual(union_ms([(10,20),(15,25),(30,40)]),25)
    def test_remove_current_shadow_pause_before_stop(self):
        r={'cut_seq':3,'wall_s':5,'steps':[{'seq':0,'kind':'llm','t_ms':1000},
            {'seq':1,'kind':'guard_context','t_ms':1600,'pause_ms':500},
            {'seq':2,'kind':'tool','t_start_ms':1600,'t_ms':2000},
            {'seq':3,'kind':'guard_context','t_ms':2800,'pause_ms':700},
            {'seq':4,'kind':'guard','t_ms':2800},
            {'seq':5,'kind':'tool','t_start_ms':2800,'t_ms':3000},
            {'seq':6,'kind':'guard_context','t_ms':4200,'pause_ms':1000},
            {'seq':7,'kind':'tool','t_start_ms':4200,'t_ms':4999}]}
        c=clock(r)
        self.assertAlmostEqual(c['complete_s'],2.8)
        self.assertAlmostEqual(c['stop_s'],1.6)
        self.assertEqual(c['pause_ms'],2200)
    def test_nested_delegate_duration_not_subtracted_twice(self):
        r={'cut_seq':1,'wall_s':5,'steps':[{'seq':0,'kind':'llm','t_ms':1000},
            {'seq':1,'kind':'guard_context','t_ms':2000,'pause_ms':500},
            {'seq':2,'kind':'tool','t_start_ms':2000,'t_ms':3000},
            {'seq':3,'kind':'tool','name':'delegate_to_payments','t_start_ms':0,'t_ms':4900,'duration_ms':4900}]}
        self.assertEqual(clock(r)['complete_s'],4.5)
    def test_stats_mean_median_and_empty(self):
        self.assertEqual(stats([1,2,9])['mean_s'],4)
        self.assertEqual(stats([1,2,9])['median_s'],2)
        self.assertEqual(stats([1,2])['median_s'],1.5)
        self.assertIsNone(stats([])['mean_s'])

if __name__=='__main__':unittest.main()
