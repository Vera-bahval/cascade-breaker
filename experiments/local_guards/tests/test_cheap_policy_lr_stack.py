"""Matched semantic LR policy reference: provenance, fold isolation and stable scores."""
import json
from pathlib import Path
import unittest
from cascade_guard import cheap_eval as e
from cascade_guard import cheap_policy_lr_stack as stack
from cascade_guard.ml import semantic_vector
from cascade_guard.offline import load_semantics
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'results/policy-comparison/lr-stack-reference'

class SemanticStackPolicyTests(unittest.TestCase):
    def test_input_hash_validation_and_complete_vectors(self):
        rows,_,_=stack.inputs(BASE)
        scores=load_semantics(BASE/'results/secjev-mps-scores.jsonl',e.read_jsonl(BASE/'data/prefixes.jsonl'))
        self.assertTrue(all(semantic_vector(r,scores,fmt) is not None for r in rows for fmt in stack.FORMATS))
        with self.assertRaisesRegex(ValueError,'input/model hash'):
            bad=dict(rows[0],state=dict(rows[0]['state'],changed=True))
            load_semantics(BASE/'results/secjev-mps-scores.jsonl',[bad]+[r for r in e.read_jsonl(BASE/'data/prefixes.jsonl') if r['prefix_id']!=bad['prefix_id']])

    @unittest.skipUnless((OUT/'metrics.json').exists(),'reference not run')
    def test_full_folds_metrics_and_identity(self):
        rows,_,alloc=stack.inputs(BASE);lookup={r['prefix_id']:r for r in rows};amap={(a['seed'],a['outer_fold']):a for a in alloc}
        fits=e.read_jsonl(OUT/'cached-fits.jsonl');self.assertEqual(len(fits),18)
        for f in fits:
            a=amap[f['seed'],f['outer_fold']]
            self.assertEqual({lookup[p['prefix_id']]['episode_id'] for p in f['outer']},set(a['test_episode_ids'])&{r['episode_id'] for r in rows})
            self.assertEqual({p['prefix_id'] for p in f['inner']},{r['prefix_id'] for r in rows if r['episode_id'] in a['train_episode_ids']})
        pp=e.read_jsonl(OUT/'predictions.jsonl');self.assertEqual(len(pp),15840)
        self.assertEqual(len({(p['policy'],p['seed'],p['arm'],p['prefix_id']) for p in pp}),len(pp))
        metrics=json.loads((OUT/'metrics.json').read_text())['aggregates'];self.assertEqual(len(metrics),90)
        self.assertTrue(all(m['complete'] for m in metrics))
        for f in json.loads((OUT/'folds.json').read_text()):
            if 'selected_format' in f:
                self.assertEqual(f['selected_format'],min(f['candidates'],key=lambda c:c['rank'])['format'])
        scoremap={}
        for p in pp:
            if 'selected' in p['arm']:continue
            key=p['seed'],p['prefix_id'],p['format'];scoremap.setdefault(key,p['probability'])
            self.assertEqual(scoremap[key],p['probability'])
            self.assertGreater(p['inference_cost_ms'],0)
        manifest=json.loads((OUT/'manifest.json').read_text());e.verify_frozen(manifest)
        self.assertTrue(all(e.digest(p['path'])==p['sha256'] for p in manifest['output_files']))

if __name__=='__main__':unittest.main()
