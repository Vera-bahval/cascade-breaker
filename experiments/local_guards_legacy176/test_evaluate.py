import unittest
from .evaluate import metrics
from .timing import stats


class AccountingTests(unittest.TestCase):
    def test_unknown_and_unavailable_are_not_detection(self):
        labels={str(i):dict(label=int(i<2)) for i in range(4)}
        m=metrics(labels,{'0':'UNKNOWN','1':'ADAPTER_UNAVAILABLE','2':'BLOCK','3':'UNKNOWN'})
        self.assertEqual((m['tp'],m['wrong_allow'],m['unknown'],m['unavailable']),(0,0,2,1))
        self.assertEqual((m['false_block'],m['safe_stop'],m['correct']),(1,2,0))

    def test_episode_statistics_do_not_weight_repeated_checks(self):
        s=stats([1,2,9])
        self.assertEqual(s['n'],3)
        self.assertEqual(s['mean_s'],4)
        self.assertEqual(s['median_s'],2)
        self.assertEqual(s['p95_s'],9)


if __name__=='__main__':unittest.main()
