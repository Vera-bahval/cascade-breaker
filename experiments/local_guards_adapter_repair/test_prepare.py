import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .test_evidence import example, held
from .prepare import packet_from_request, preparation_fence, prepared
from experiments.local_guards_archive_comparison import views


class PreparationTests(unittest.TestCase):
    def test_request_identity_covers_prompt_parameters_and_action(self):
        row=example(held());row['mode']='historical';row['evidence_status']={}
        packet=views.predictor_view(row)
        request={'model':'saved-model','temperature':0,
                 'messages':[{'role':'system','content':'fixed policy'},
                             {'role':'user','content':json.dumps(views.pack_view(packet))}]}
        identity=hashlib.sha256(json.dumps(request,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        saved={'query_id':identity,'request':request}
        # Use the same actual action boundary kind required for all 542 P4.
        packet['raw_context']['proposed_action']['source_event_kind']='before_tool_hook'
        request['messages'][1]['content']=json.dumps(views.pack_view(packet))
        saved['query_id']=hashlib.sha256(json.dumps(request,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(packet_from_request(saved,packet),packet)
        changed=copy.deepcopy(saved);changed['request']['messages'][0]['content']='other policy'
        with self.assertRaises(ValueError):
            packet_from_request(changed,packet)
        changed=copy.deepcopy(packet);changed['event_seq']+=2
        with self.assertRaises(ValueError):
            packet_from_request(saved,changed)

    def test_forbidden_files_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ('responses.jsonl.gz','consensus.json','snapshot.sqlite.gz','database.json','gold-private.json'):
                path=Path(root)/name;path.write_text('not evidence')
                with preparation_fence(),self.assertRaises(PermissionError):
                    path.read_bytes()

    def test_preparation_never_invokes_a_checker(self):
        from experiments.local_guards_v4 import guard as v4
        from experiments.local_guards_v4_followup import guard as v42
        from experiments.local_guards_final_replay import p4
        from . import guard43
        with patch.object(v4,'guard',side_effect=AssertionError('guard called')), \
             patch.object(v42,'guard',side_effect=AssertionError('guard called')), \
             patch.object(p4,'predict',side_effect=AssertionError('predict called')), \
             patch.object(guard43,'guard',side_effect=AssertionError('v43 called')),preparation_fence():
            result=prepared({'prefix_id':'control'},example(held()),{},('v3','v4','v4.2','v4.3'))
        self.assertTrue(result['adapters']['v4']['payload']['facts']['binding_hold'])
        self.assertNotIn('decision',result)

    def test_prepared_common_evidence_is_not_enriched(self):
        row=example(held())
        result=prepared({'mode':'common'},row,{},('v4.3',))
        self.assertNotIn('session_valid',result['adapters']['v4.3']['payload']['facts'])
        self.assertNotIn('human_approved',result['adapters']['v4.3']['payload']['facts'])
        self.assertNotIn('invoice_currency',result['adapters']['v4.3']['payload']['facts'])
        self.assertNotIn('technical_actor',result['bundle']['context'])

    def test_ml_feature_transformation_is_frozen_and_deterministic(self):
        from experiments.local_guards_ml_retrain.features_revision2 import features
        from .adapters import adapt
        from .evidence import build_evidence
        row=adapt(build_evidence(example(held())),'retrain_ml')['payload']
        first=features(row,'new')
        self.assertEqual(first,features(copy.deepcopy(row),'new'))
        self.assertTrue(all(isinstance(k,str) for k in first))
        self.assertTrue(all(isinstance(v,(str,float,int)) for v in first.values()))

class ExecutionGateTests(unittest.TestCase):
    def test_future_runner_requires_independent_approval_before_loading_methods(self):
        from .execute_reviewed import approval
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'approval.json'
            path.write_text('{"status":"PREPARED"}')
            with self.assertRaises(ValueError):
                approval(Path(root),path)

class EarlyBoundaryTests(unittest.TestCase):
    def test_normalization_preserves_actual_tool_and_subject_at_p1(self):
        row=example()
        row['checkpoint']='P1'
        row['raw_context'].pop('proposed_action')
        row['anchor']={'event':{'event_seq':100,'hook_kind':'before_tool','tool_name':'get_invoice_details',
                                'tool_arguments':{'invoice_id':99}}}
        output=prepared({'prefix_id':'control'},row,{},('v4.3',))
        self.assertEqual(output['bundle']['proposal']['tool'],'get_invoice_details')
        self.assertEqual(output['bundle']['context']['invoice_id'],99)
        self.assertEqual(output['action_boundary']['tool_arguments']['invoice_id'],99)

class ReferenceEncodingTests(unittest.TestCase):
    def test_short_receipt_ids_keep_equality_with_payment_reference(self):
        from .test_evidence import call
        args={'invoice_id':1,'vendor_id':1,'amount':'100','vendor_account':'acct'}
        row=example(call('finstripe__create_transfer',args,{'invoice_id':1,'vendor_id':1,'status':'completed','transfer_id':'tx'},40))
        row['checkpoint']='P3'
        row['raw_context']['proposed_action'].update(tool_name='process_payment',tool_arguments={'invoice_id':1,'payment_reference':'tx'})
        output=prepared({'prefix_id':'control'},row,{},('v4.3',))
        self.assertTrue(output['adapters']['v4.3']['payload']['facts']['payment_reference_matches_transfer'])
