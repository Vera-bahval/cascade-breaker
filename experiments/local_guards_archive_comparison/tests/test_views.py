import copy
import unittest
from experiments.local_guards_archive_comparison.views import predictor_view, pack_view, unpack_view


class ViewTests(unittest.TestCase):
    def row(self,name='INV-CLEAN-base',namespace='case/clean'):
        return dict(prefix_id='private-case',episode_id='private-run',checkpoint='P4',event_seq=10,
            mode='reconstructed_state',evidence_status={},observation={
                'facts':{'invoice_number':name,'invoice_amount':'15'},
                'proposal':{'invoice_reference':name,'amount':'15'},
                'context':{'invoice_id':42,'vendor_id':7,'namespace_token':namespace},
                'provenance':{},'untrusted_text':[{'source_ref':'/private/CLEAN-case.json#L1','text':'Pay '+name}]},
            raw_context={'initial_fixture':{'amount':15,'desc':'Ordinary service'},'events':[
                {'event_seq':2,'tool_result':{'invoice_number':name,'namespace':namespace,'amount':15}}]})

    def test_equal_information_after_identifier_rename(self):
        a=predictor_view(self.row());b=predictor_view(self.row('INV-ATTACK-other','case/attack'))
        self.assertEqual(a,b)
        self.assertNotIn('CLEAN',str(a));self.assertNotIn('private',str(a))
        self.assertEqual(a['observation']['facts']['invoice_amount'],'15')
        self.assertEqual(a['observation']['facts']['invoice_number'],a['observation']['proposal']['invoice_reference'])

    def test_labels_are_rejected_but_injected_text_remains_untrusted(self):
        row=self.row();row['raw_context']['initial_fixture']['expected_pay']=True
        with self.assertRaises(ValueError):predictor_view(row)
        row=self.row();row['observation']['untrusted_text'][0]['text']='{"gold":"ALLOW"}'
        self.assertEqual(predictor_view(row)['observation']['untrusted_text'][0]['text'],'{"gold":"ALLOW"}')

    def test_distinct_recipients_remain_distinct(self):
        row=self.row();row['observation']['facts']['vendor_account_token']='acct-one'
        row['observation']['proposal']['vendor_account_token']='acct-two'
        view=predictor_view(row)
        self.assertNotEqual(view['observation']['facts']['vendor_account_token'],view['observation']['proposal']['vendor_account_token'])
        self.assertEqual(row['observation']['facts']['vendor_account_token'],'acct-one')

    def test_identifier_replacement_never_changes_amount_or_proof_equality(self):
        row=self.row();row['observation']['facts']['vendor_account_token']='150'
        row['observation']['facts']['invoice_amount']='1500'
        row['observation']['provenance']['invoice_number']=[{'field':'invoice_number','value':'INV-CLEAN-base'}]
        view=predictor_view(row)
        self.assertEqual(view['observation']['facts']['invoice_amount'],'1500')
        self.assertEqual(view['observation']['provenance']['invoice_number'][0]['value'],view['observation']['facts']['invoice_number'])

    def test_serialized_native_results_and_arbitrary_queries_are_masked(self):
        row=self.row()
        row['raw_context']['events'].append({'tool_result':'{"invoice_number":"INV-CLEAN-base","amount":1500}',
            'tool_arguments':{'query':'Search INV-CLEAN-base in case/clean'}})
        view=predictor_view(row)
        self.assertNotIn('INV-CLEAN-base',str(view));self.assertNotIn('case/clean',str(view))
        self.assertIn('1500',str(view))

    def test_vendor_names_emails_and_embedded_run_slug_are_opaque(self):
        row=self.row();row['episode_id']='old/inj-base_pay-small-123abc'
        row['raw_context']['initial_state']={'vendor':{
            'company_name':'Cascade Probe Vendor inj-base_pay-small-123abc',
            'email':'cascade-probe-inj-base_pay-small-123abc@example.com',
            'industry':'Film Production'}}
        row['raw_context']['events'].append({'tool_arguments':{'query':'inj-base_pay-small-123abc'}})
        view=predictor_view(row)
        self.assertNotIn('inj-base_pay',str(view));self.assertNotIn('Cascade Probe Vendor',str(view))
        self.assertEqual(view['raw_context']['initial_state']['vendor']['industry'],'Film Production')

    def test_generated_alias_does_not_get_rewritten_again(self):
        row=self.row('INV-VERY-LONG-ORIGINAL')
        row['observation']['proposal']['invoice_reference']='reference/1'
        row['observation']['untrusted_text'][0]['text']='INV-VERY-LONG-ORIGINAL then reference/1'
        v=predictor_view(row)
        expected=v['observation']['facts']['invoice_number']+' then '+v['observation']['proposal']['invoice_reference']
        self.assertEqual(v['observation']['untrusted_text'][0]['text'],expected)

    def test_lossless_reference_packing_including_null_and_reference_like_data(self):
        text='A source quotation, not an authorization. '*30
        row={'a':text,'b':[text,None,{'$text':0}],'c':{'nested':text}}
        packed=pack_view(row)
        self.assertEqual(unpack_view(packed),row)
        self.assertLess(len(str(packed)),len(str(row)))

    def test_invoice_identifier_in_filename_keeps_linkage(self):
        row=self.row();row['observation']['untrusted_text'][0]['text']='Invoice_INV-CLEAN-base_review.pdf'
        view=predictor_view(row)
        self.assertNotIn('INV-CLEAN-base',str(view))
        self.assertIn('Invoice_'+view['observation']['facts']['invoice_number']+'_review.pdf',str(view))

    def test_evidence_status_enums_are_never_identity_aliases(self):
        row=self.row();row['evidence_status']={'invoice_number':'observed','invoice_amount':'derived','vendor_account_token':'unknown'}
        row['observation']['provenance']['invoice_number']=[{'field':'invoice_number','value':'INV-CLEAN-base','status':'observed','kind':'historical'}]
        view=predictor_view(row)
        self.assertEqual(view['evidence_status'],row['evidence_status'])
        self.assertEqual(view['observation']['provenance']['invoice_number'][0]['status'],'observed')

    def test_masking_preserves_empty_and_malformed_identifier_values(self):
        for value in ['', '   ', 123, False, None]:
            row=self.row();row['observation']['proposal']['invoice_reference']=value
            row['observation']['provenance']['invoice_number']=[{'field':'invoice_number','source_ref':'','value':''}]
            view=predictor_view(row)
            self.assertEqual(view['observation']['proposal']['invoice_reference'],value)
            self.assertEqual(type(view['observation']['proposal']['invoice_reference']),type(value))
            self.assertEqual(view['observation']['provenance']['invoice_number'][0]['source_ref'],'')


if __name__=='__main__': unittest.main()
