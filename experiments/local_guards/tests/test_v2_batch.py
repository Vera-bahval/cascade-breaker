import unittest
from types import SimpleNamespace
from collections import OrderedDict
try:
 import torch
except ImportError:
 torch=None
from cascade_guard.v2_runtime import CorrectedNLIAdapter
from cascade_guard.v2_inputs import canonical,record

class ToyTokenizer:
 pad_token_id=0
 def encode(self,text,add_special_tokens=False):return [ord(c)%100+1 for c in text]
 def num_special_tokens_to_add(self,pair=True):return 3
 def build_inputs_with_special_tokens(self,p,c):return [101]+p+[102]+c+[102]

@unittest.skipIf(torch is None,'torch runtime unavailable')
class BatchTests(unittest.TestCase):
 def adapter(self):
  adapter=CorrectedNLIAdapter.__new__(CorrectedNLIAdapter)
  adapter.device='cpu';adapter.labels={0:'contradiction',1:'entailment',2:'neutral'};adapter.block='N';adapter.batch_size=8
  adapter.tokenizer=ToyTokenizer();adapter.max_length=512;adapter.pair_cache=OrderedDict();adapter.calls=0
  class ToyModel:
   def __call__(self,input_ids,attention_mask):
    adapter.calls+=1
    # Padding must be excluded from both numerator and denominator.
    values=(input_ids*attention_mask).sum(dim=1).float()/attention_mask.sum(dim=1)
    return SimpleNamespace(logits=torch.stack((values/100,values/200,-values/100),dim=1))
  adapter.model=ToyModel()
  return adapter
 def test_padding_mask_matches_single_forward(self):
  adapter=self.adapter();sequences=[[5,7,9],[8],[1,2,3,4,5]]
  single=[adapter.infer_ids(sequence)[0] for sequence in sequences]
  batched=adapter.infer_batch(sequences)
  for a,b in zip(single,batched):
   for key in a:self.assertAlmostEqual(a[key],b[key],places=7)
 def test_exact_pair_cache_avoids_repeated_forward_and_preserves_scores(self):
  adapter=self.adapter();rec=record('opaque',canonical({'base_policy':'Pay correctly'},{}),{})
  first=adapter.score(rec);calls=adapter.calls;second=adapter.score(rec)
  self.assertGreater(calls,0);self.assertEqual(adapter.calls,calls)
  self.assertEqual(first['features'],second['features'])
  self.assertEqual(second['pair_cache']['unique_forward_pairs'],0)
  self.assertEqual(second['pair_cache']['hits'],second['window_count'])

if __name__=='__main__':unittest.main()
