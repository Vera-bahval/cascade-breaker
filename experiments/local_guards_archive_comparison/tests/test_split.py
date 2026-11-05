import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from split import assign_groups, select_splits

class SplitTests(unittest.TestCase):
    def test_pair_variants_repeats_executors_and_same_text_united(self):
        rows=[dict(episode_id=str(i),executor=ex,scenario={'id':sid,'pair':pair,'desc':text},source_origin='test',source_version=None)
              for i,(ex,sid,pair,text) in enumerate([('mini','P4900-base-r1','P4900','base'),('nano','P4900-cfo-r2','P4900','changed'),('luna','OTHER',None,' BASE '),('mini','P4900-placebo-r9','P4900','different')])]
        grouped,receipts=assign_groups(rows)
        self.assertEqual(len(set(x['group_id'] for x in grouped)),1)
        self.assertTrue(receipts)

    def test_group_split_excludes_luna_and_selects_before_labels(self):
        rows=[dict(episode_id=f'{i}/{ex}',executor=ex,scenario={'id':str(i),'desc':f'input {i}'},source_origin='test',source_version=None) for i in range(30) for ex in ['mini','luna']]
        grouped,_=assign_groups(rows);result,manifest=select_splits(grouped)
        self.assertTrue(all(x['split'] not in ('TRAIN','CAL') for x in result if x['executor']=='luna'))
        self.assertEqual(len(manifest['representative_groups']),6)
        self.assertEqual(len(manifest['challenge_groups']),3)
        self.assertEqual(result,select_splits(grouped)[0])

if __name__=='__main__':unittest.main()
