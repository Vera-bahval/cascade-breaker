import unittest
from copy import deepcopy
from .prepare import server_snapshot,strip_run,prepare_one,HERE
from experiments.local_guards_adapter_repair.inventory import rows
from experiments.local_guards_adapter_repair.prepare import preparation_fence

class PrepareTests(unittest.TestCase):
    def test_forbidden_labels_are_not_readable_by_preparer(self):
        with preparation_fence(),self.assertRaises(PermissionError):
            (HERE/'labels/scoring.jsonl.gz').read_bytes()
    def test_real_full_partial_and_method_only(self):
        c=next(rows(HERE/'source-prefixes.jsonl.gz'))
        full=prepare_one(c);partial=prepare_one(c,'partial')
        self.assertTrue(all(r['event_seq']<full['bundle']['event_seq'] for r in full['bundle']['records']))
        self.assertFalse(partial['adapters']['v1']['applicable'])
        self.assertEqual(partial['adapters']['v1']['payload']['state'],None)
        for name in ('v1','v2','v3','v4.3','native'):
            self.assertEqual(prepare_one(c,only=name,verify_legacy=False)['payload'],full['adapters'][name]['payload'])
    def test_strip_excludes_future_and_outcomes(self):
        r={'run_id':'x','db_initial':{},'db_final':{'secret':1},'label':1,'steps':[{'seq':1,'kind':'tool'},{'seq':2,'kind':'guard','decision':'BLOCK'},{'seq':3,'kind':'guard_context'},{'seq':4,'kind':'tool'}]}
        p=strip_run(r,3)
        self.assertNotIn('db_final',p);self.assertNotIn('label',p)
        self.assertEqual([s['seq'] for s in p['steps']],[1,3])
    def test_snapshot_is_not_tool_or_clearance(self):
        b={'event_seq':9,'context':{'invoice_id':1,'vendor_id':2},'current':{},'records':[],'rejected':[],'coordinates':[]}
        server_snapshot(b,{'invoice':{'id':1,'vendor_id':2,'amount':50,'status':'approved'},'vendor':{'id':2,'status':'active','bank_account_number':'acct'},'transactions':[]},8,'raw/step/4')
        record=b['current']['invoice_status']
        self.assertEqual(record['source'],'server_context');self.assertEqual(record['evidence_kind'],'server_snapshot')
        self.assertNotIn('source_call_id',record);self.assertNotIn('binding_hold',b['current'])
        self.assertEqual(b['current']['prior_completed_transfers']['value'],0)
    def test_missing_ledger_not_empty(self):
        b={'event_seq':9,'context':{'invoice_id':1,'vendor_id':2},'current':{},'records':[],'rejected':[],'coordinates':[]}
        server_snapshot(b,{'invoice':{'id':1},'vendor':{'id':2}},8,'s')
        self.assertNotIn('prior_completed_transfers',b['current'])
    def test_foreign_snapshot_rejected(self):
        b={'event_seq':9,'context':{'invoice_id':1,'vendor_id':2},'current':{},'records':[],'rejected':[],'coordinates':[]}
        server_snapshot(b,{'invoice':{'id':3,'amount':2},'vendor':{'id':2}},8,'s')
        self.assertNotIn('invoice_amount',b['current']);self.assertTrue(b['rejected'])
    def test_new_snapshot_replaces_stale_or_conflicting(self):
        old={'value':'approved','current':True,'source':'native_tool'}
        b={'event_seq':9,'context':{'invoice_id':1,'vendor_id':2},'current':{'invoice_status':old},'records':[],'rejected':[],'coordinates':[]}
        server_snapshot(b,{'invoice':{'id':1,'status':'rejected'},'vendor':{'id':2}},8,'s')
        self.assertEqual(b['current']['invoice_status']['value'],'rejected')
        self.assertEqual(b['current']['invoice_status']['source'],'server_context')
    def test_snapshot_does_not_invent_currency_or_human_approval(self):
        b={'event_seq':9,'context':{'invoice_id':1,'vendor_id':2},'current':{},'records':[],'rejected':[],'coordinates':[]}
        server_snapshot(b,{'invoice':{'id':1,'amount':500},'vendor':{'id':2}},8,'s')
        self.assertNotIn('invoice_currency',b['current']);self.assertNotIn('human_approved',b['current'])
    def test_known_hold_survives_snapshot(self):
        hold={'value':True,'current':True}
        b={'event_seq':9,'context':{'invoice_id':1,'vendor_id':2},'current':{'binding_hold':hold},'records':[],'rejected':[],'coordinates':[]}
        server_snapshot(b,{'invoice':{'id':1,'status':'approved','agent_notes':'no hold'},'vendor':{'id':2}},8,'s')
        self.assertEqual(b['current']['binding_hold'],hold)

if __name__=='__main__':unittest.main()
