import copy
import json
from pathlib import Path
import tempfile
import unittest

from cascade_guard.v2_jev import QUESTIONS, payload_from_common, prepare, choose_probe, batch, feature_records
from cascade_guard.secjev import canonical_hash
from cascade_guard.secjev_batch import inference_input_hash


class CanonicalJevTest(unittest.TestCase):
 def item(self, index=0):
  return {'prefix_id':str(index),'input_hash':str(index),'provenance':{'stage':index},
          'payload':{'trusted_sources':[{'source_id':'trusted_combined','text':'Trusted facts '+str(index)}],
                     'untrusted_premise':'Untrusted assertions '+('x'*index),
                     'canonical':{'secret_future_label':1}}}

 def test_only_common_premise_and_explicit_untrusted_source(self):
  item=self.item();before=copy.deepcopy(item);p=payload_from_common(item)
  self.assertNotIn('secret_future_label',json.dumps(p));self.assertEqual(item,before)
  self.assertEqual(p['state'],'Trusted facts 0\n\nUntrusted assertions ')
  self.assertEqual(list(p['questions']),list(QUESTIONS))
  self.assertTrue(all(set(q['criteria'])=={'false','true'} for q in QUESTIONS.values()))

 def test_prepare_immutable_and_source_bound(self):
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)/'in';dest=Path(temp)/'out'
   source.write_text(json.dumps(self.item())+'\n');a=prepare(source,dest);b=prepare(source,dest)
   self.assertEqual(a,b)
   changed=self.item();changed['payload']['untrusted_premise']='changed'
   source.write_text(json.dumps(changed)+'\n')
   with self.assertRaises(ValueError):prepare(source,dest)

 def test_probe_selection_deterministic_no_labels(self):
  rows=[{'prefix_id':str(i),'payload_hash':str(i),'payload':{'state':'x'*i}} for i in range(10)]
  self.assertEqual([x['prefix_id'] for x in choose_probe(rows)],['0','1','2','7','8','9'])
  self.assertEqual(choose_probe(rows),choose_probe(list(reversed(rows))))

 def test_mps_requires_gate_before_any_call(self):
  class Engine:
   device='mps'
  with tempfile.TemporaryDirectory() as temp:
   with self.assertRaises(ValueError):batch([],Engine(),Path(temp)/'out')

 def sequence(self):
  inputs=[];scores=[];metadata={'model':'SecJev-0.8B','model_load_ms':2.}
  fingerprint=canonical_hash({'model':'SecJev-0.8B'})
  for i in range(4):
   row={'prefix_id':str(i),'payload':{'state':str(i),'questions':QUESTIONS},
        'common_input_hash':str(i),'provenance':{'episode_id':'episode','stage_index':i,'cut_seq':i*10}}
   inputs.append(row)
   scores.append({'prefix_id':str(i),'model_metadata':metadata,'input_hash':inference_input_hash(row['payload'],fingerprint),
                  'common_input_hash':str(i),'unknown':False,'probabilities':{q:(i+1)/10 for q in QUESTIONS},
                  'latency_ms':i+1,'cache_hit':False})
  return inputs,scores

 def test_sequence_exact_order_cost_and_dynamic_values(self):
  inputs,scores=self.sequence();rows=feature_records(list(reversed(inputs)),list(reversed(scores)),'0.8B')
  byblock={r['block']:r for r in rows}
  self.assertEqual(len(byblock['J_seq']['features']),16)
  self.assertEqual(byblock['J_seq']['inference_cost_ms'],10)
  self.assertEqual(byblock['J_prior']['inference_cost_ms'],6)
  self.assertAlmostEqual(byblock['J_dynamic']['features']['delta.invoice_agent_to_create_transfer.untrusted_instruction'],.3)

 def test_missing_stage_unknown_does_not_poison_current(self):
  inputs,scores=self.sequence();rows=feature_records(inputs[:1]+inputs[2:],scores[:1]+scores[2:],'0.8B')
  statuses={r['block']:r['status'] for r in rows}
  self.assertEqual(statuses['J_cur'],'OK');self.assertEqual(statuses['J_seq'],'UNKNOWN')

 def test_sequence_rejects_input_and_chronology_mismatch(self):
  inputs,scores=self.sequence();scores[0]['common_input_hash']='bad'
  with self.assertRaises(ValueError):feature_records(inputs,scores,'0.8B')
  inputs,scores=self.sequence();inputs[0]['provenance']['cut_seq']=100
  with self.assertRaises(ValueError):feature_records(inputs,scores,'0.8B')

if __name__=='__main__':unittest.main()
