import tempfile
import unittest
import argparse
import hashlib
import json
from jsonschema import ValidationError
from pathlib import Path
from experiments.local_guards_archive_comparison.eliza import Ledger, parse_answer, query_identity, remaining, sanitize_metadata, validate_inputs


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

    def test_nonfinite_caps_and_excess_charge_stop(self):
        with tempfile.TemporaryDirectory() as d:
            for cap in [float('nan'),float('inf'),-1,0,True]:
                with self.assertRaises(ValueError):Ledger(Path(d)/'bad.sqlite',cap)
            ledger=Ledger(Path(d)/'ledger.sqlite',1)
            ledger.reserve('a',.1)
            with self.assertRaises(RuntimeError):ledger.complete('a',.2)
            self.assertEqual(ledger.summary()['cost_usd'],.2)

    def test_metadata_does_not_persist_unknown_identity_fields(self):
        meta={'quotas':{'quotas':{'external':{'limits':[]},'secret_key':'s'}},
              'usage':{'usage':{},'email':'private'},
              'model':{'data':[{'id':'deepseek-flash','key':'private','prices':{'input_tokens':'0.3'}}]}}
        safe=sanitize_metadata(meta)
        self.assertNotIn('private',str(safe));self.assertNotIn('secret_key',str(safe))

    def test_freeze_binds_inputs_prompt_config_and_output_directory(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);code='experiments/local_guards_archive_comparison/eliza.py'
            prompt=d/'prompt.txt';prompt.write_text('fixed policy')
            config=d/'config.json';config.write_text(json.dumps(dict(prompt_path=str(prompt),model='deepseek-flash',
                endpoint='/deepseek/chat/completions',input_price_cap=.0000003,output_price_cap=.0000012,max_tokens=768)))
            methods=d/'methods.json';methods.write_text(json.dumps({'sources':{code:hashlib.sha256(Path(code).read_bytes()).hexdigest()}}))
            schema=d/'schema.json';schema.write_text(json.dumps({'type':'object','properties':{'text':{'type':'string'}},'additionalProperties':False}))
            inputs=d/'inputs.jsonl';inputs.write_text(json.dumps({'case_id':'a','split':'REPRESENTATIVE','input':{'text':'invoice'}})+'\n')
            freeze=d/'freeze.json'
            def receipt():
                paths=[code,str(config),str(prompt),str(methods),str(schema),str(inputs)]
                freeze.write_text(json.dumps(dict(sources={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths},
                    method_manifest=str(methods),input_schema_path=str(schema),run_output=str(d/'run'),selected_case_ids=['a'])))
            receipt();args=argparse.Namespace(cap=1,config=str(config),inputs=str(inputs),freeze=str(freeze),output=str(d/'run'))
            self.assertEqual(len(validate_inputs(args)[1]),1)
            inputs.write_text(json.dumps({'case_id':'a','split':'REPRESENTATIVE','input':{'text':'invoice','gold':'BLOCK'}})+'\n')
            with self.assertRaises(RuntimeError):validate_inputs(args)
            receipt()
            with self.assertRaises(ValidationError):validate_inputs(args)
            inputs.write_text(json.dumps({'case_id':'a','split':'REPRESENTATIVE','input':{'text':'invoice'}})+'\n');receipt()
            args.output=str(d/'other')
            with self.assertRaises(RuntimeError):validate_inputs(args)


if __name__=='__main__': unittest.main()
