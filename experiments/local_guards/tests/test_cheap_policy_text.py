"""Verify matched text reference isolation and saved policy artifacts."""
import json
from pathlib import Path
import unittest
from cascade_guard import cheap_eval as e
from cascade_guard import cheap_policy_text as text
from cascade_guard.ml import Fitted

BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'results/policy-comparison/text-reference'


class TextPolicyTests(unittest.TestCase):
    def test_formats_use_distinct_frozen_fields(self):
        rows=[{'text':'public rationale','text_facts_action':'facts only'}]
        self.assertEqual(Fitted('tfidf_logistic',17,'plus_rationale').x(rows),['public rationale'])
        self.assertEqual(Fitted('tfidf_logistic',17,'facts_action').x(rows),['facts only'])

    def test_vocabulary_is_fit_on_training_only(self):
        rows=[dict(text='common training text '+str(i),text_facts_action='common facts',label=i%2,group_id=str(i)) for i in range(4)]
        model=Fitted('tfidf_logistic',17).fit(rows)
        vocabulary=dict(model.model.named_steps['tfidf'].vocabulary_)
        model.predict([{'text':'zzzzzzzzzzz ONLY TEST UNIQUE'}])
        self.assertEqual(model.model.named_steps['tfidf'].vocabulary_,vocabulary)
        self.assertNotIn('zzz',vocabulary)

    @unittest.skipUnless((OUT/'metrics.json').exists(),'matched generation not run')
    def test_saved_groups_and_score_reproduction(self):
        rows,outcomes,alloc=text.inputs(BASE)
        lookup={r['prefix_id']:r for r in rows};amap={(a['seed'],a['outer_fold']):a for a in alloc}
        fits=e.read_jsonl(OUT/'cached-fits.jsonl')
        self.assertEqual(len(fits),18)
        for f in fits:
            a=amap[f['seed'],f['outer_fold']]
            self.assertFalse(set(a['train_groups'])&set(a['test_groups']))
            self.assertEqual({lookup[p['prefix_id']]['episode_id'] for p in f['outer']},set(a['test_episode_ids'])&{r['episode_id'] for r in rows})
            self.assertEqual({p['prefix_id'] for p in f['inner']},{r['prefix_id'] for r in rows if r['episode_id'] in a['train_episode_ids']})
        audit=json.loads((OUT/'historical-score-audit.json').read_text())
        self.assertEqual(audit['checked'],1056);self.assertEqual(audit['max_abs_score_delta'],0)

    @unittest.skipUnless((OUT/'metrics.json').exists(),'matched generation not run')
    def test_policy_scores_identical_and_selection_train_only(self):
        metrics=json.loads((OUT/'metrics.json').read_text())['aggregates']
        self.assertEqual(len(metrics),81);self.assertTrue(all(m['complete'] for m in metrics))
        preds=e.read_jsonl(OUT/'predictions.jsonl');scoremap={}
        for p in preds:
            if 'train_selected_format' in p['arm']:continue
            key=(p['seed'],p['prefix_id'],p['format'])
            scoremap.setdefault(key,p['probability']);self.assertEqual(scoremap[key],p['probability'])
        folds=json.loads((OUT/'folds.json').read_text())
        selected=[f for f in folds if 'selected_format' in f]
        self.assertEqual(len(selected),81)
        for f in selected:
            best=min(f['candidates'],key=lambda c:c['rank'])
            self.assertEqual(f['selected_format'],best['format'])
            self.assertEqual(f['calibration']['source'],'inner grouped OOF only')


class VerifiedTextGenerationTests(unittest.TestCase):
    def test_verified_cache_and_final_manifest(self):
        cache=BASE/'results/policy-comparison/text-reference-verified'
        final=BASE/'results/policy-comparison/text-reference-verified-final'
        for directory,filename in ((cache,'fit-input-freeze.json'),(final,'input-freeze.json')):
            e.verify_frozen(json.loads((directory/filename).read_text()))
        audit=json.loads((cache/'repeat-score-audit.json').read_text())
        self.assertEqual(audit['checked_inner_outer_probabilities'],3168)
        self.assertEqual(audit['max_abs_score_delta'],0)
        manifest=json.loads((final/'manifest.json').read_text())
        self.assertTrue(all(e.digest(item['path'])==item['sha256'] for item in manifest['output_files']))

    def test_final_selection_scopes_and_complete_coverage(self):
        final=BASE/'results/policy-comparison/text-reference-verified-final'
        metrics=json.loads((final/'metrics.json').read_text())['aggregates']
        self.assertEqual(len(metrics),90)
        self.assertTrue(all(m['complete'] and m['prefixes']==176 for m in metrics))
        pp=e.read_jsonl(final/'predictions.jsonl')
        self.assertEqual(len(pp),15840)
        self.assertEqual(len({(p['policy'],p['seed'],p['arm'],p['prefix_id']) for p in pp}),15840)
        legacy=[p for p in pp if 'Blegacy' in p['arm']]
        self.assertEqual(len(legacy),1584)
        self.assertTrue(all(p['selection_scope'].startswith('standalone only') for p in legacy))
        folds=json.loads((final/'folds.json').read_text())
        for f in folds:
            if 'selected_format' in f:
                self.assertEqual(f['selected_format'],min(f['candidates'],key=lambda c:c['rank'])['format'])


if __name__=='__main__':unittest.main()
