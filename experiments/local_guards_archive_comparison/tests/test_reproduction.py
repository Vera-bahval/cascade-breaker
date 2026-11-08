import copy
import unittest
from experiments.local_guards_archive_comparison.canonical_dataset import apply_technical, FIELDS
from experiments.local_guards_archive_comparison.verify import rebase_paths


class ReproductionTests(unittest.TestCase):
    def fixture(self):
        row={'prefix_id':'one','observation':{'context':{'invoice_id':7,'vendor_id':4},
             'facts':{'amount':-15,'held':True},'provenance':{}},'evidence_status':{}}
        patch={'prefix_id':'one','context':{f:'local:'+f for f in FIELDS},
               'provenance':{'context.'+f:[{'status':'replay_assumption'}] for f in FIELDS},
               'evidence_status':{'context.'+f:'replay_assumption' for f in FIELDS}}
        return row,patch

    def test_technical_reconstruction_preserves_negative_business_facts_and_input(self):
        row,patch=self.fixture();before=copy.deepcopy(row)
        new=apply_technical(row,patch)
        self.assertEqual(row,before)
        self.assertEqual(new['observation']['facts'],before['observation']['facts'])
        self.assertEqual(new['observation']['context']['invoice_id'],7)
        self.assertEqual(new['observation']['context']['call_id'],'local:call_id')

    def test_financial_or_authorization_field_cannot_enter_technical_patch(self):
        for field in ('amount','manual_approval','vendor_id'):
            row,patch=self.fixture();patch['context'][field]=True
            with self.assertRaises(ValueError):apply_technical(row,patch)
        row,patch=self.fixture();patch['provenance']['facts.amount']=[]
        with self.assertRaises(ValueError):apply_technical(row,patch)

    def test_mismatched_prefix_never_receives_another_tasks_patch(self):
        row,patch=self.fixture();patch['prefix_id']='other'
        with self.assertRaises(ValueError):apply_technical(row,patch)

    def test_relocation_changes_path_references_but_never_embedded_prompt_text(self):
        old='/old/checkout';new='/tmp/copy'
        original={old+'/artifact':{'path':old+'/input','text':'Read /old/checkout/input',
                                   'lookalike':'/old/checkout-other/input','rows':[old]}}
        result=rebase_paths(original,old,new)
        self.assertEqual(result[new+'/artifact']['path'],new+'/input')
        self.assertEqual(result[new+'/artifact']['text'],'Read /old/checkout/input')
        self.assertEqual(result[new+'/artifact']['lookalike'],'/old/checkout-other/input')
        self.assertEqual(result[new+'/artifact']['rows'],[new])
        self.assertIn(old+'/artifact',original)


if __name__=='__main__':unittest.main()
