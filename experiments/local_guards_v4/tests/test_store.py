import concurrent.futures
import importlib.util
import pathlib
import tempfile
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / 'store.py'
if PATH.exists():
    spec=importlib.util.spec_from_file_location('v4_store',PATH)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    EvidenceStore=module.EvidenceStore; ClaimConflict=module.ClaimConflict
else:
    EvidenceStore=None; ClaimConflict=Exception


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(EvidenceStore,'EvidenceStore implementation missing')
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=pathlib.Path(self.tmp.name)/'evidence.sqlite'
        self.store=EvidenceStore(self.path)

    def context(self):
        ctx=dict(namespace='ns',invoice_id=3,vendor_id=2,account_ref='acct')
        ctx.update(self.store.material_state('ns',3,2,'12.00','USD','acct',1))
        return ctx

    def test_material_revisions_and_aba_survive_restart(self):
        ctx=self.context(); original=(ctx['invoice_version'],ctx['vendor_version'])
        self.assertEqual(dict(zip(('invoice_version','vendor_version'),original)),
                         self.store.material_state('ns',3,2,'12','usd','acct',2))
        changed=self.store.material_state('ns',3,2,'13','USD','other',3)
        restored=self.store.material_state('ns',3,2,'12','USD','acct',4)
        self.assertNotEqual(original,(restored['invoice_version'],restored['vendor_version']))
        self.assertNotEqual(changed,restored)
        self.assertEqual(restored,EvidenceStore(self.path).material_state('ns',3,2,'12','USD','acct',5))

    def test_fresh_binding_never_resurrects_after_observed_change(self):
        ctx=self.context(); binding=self.store.bind_approval(ctx,'12','USD',2)
        self.assertEqual(binding,EvidenceStore(self.path).approval(ctx))
        self.store.material_state('ns',3,2,'12','USD','other',3)
        self.store.material_state('ns',3,2,'12','USD','acct',4)
        self.assertIsNone(self.store.approval(ctx))
        with self.assertRaises(ValueError): self.store.bind_approval(ctx,'12','USD',5)

    def test_claim_conflicts_and_distinct_invoices(self):
        claim=self.store.acquire_claim('ns',2,3,'one',1)
        self.assertEqual(claim,self.store.acquire_claim('ns',2,3,'one',2))
        self.store.acquire_claim('ns',2,4,'two',3)
        for invoice,owner in [(3,'three'),(None,'wide')]:
            with self.assertRaises(ClaimConflict): self.store.acquire_claim('ns',2,invoice,owner,4)
        with self.assertRaises(ClaimConflict): self.store.acquire_claim('ns',2,4,'one',4)

    def test_same_invoice_conflicts_even_if_vendor_argument_changed(self):
        self.store.acquire_claim('ns',2,3,'one',1)
        with self.assertRaises(ClaimConflict): self.store.acquire_claim('ns',9,3,'two',2)

    def test_vendor_wide_claim_conflicts_other_invoice(self):
        self.store.acquire_claim('ns',2,None,'wide',1)
        with self.assertRaises(ClaimConflict): self.store.acquire_claim('ns',2,3,'one',2)
        self.store.acquire_claim('other',2,3,'other',2)

    def test_concurrency_one_owner_and_restart(self):
        def acquire(i):
            try: return EvidenceStore(self.path).acquire_claim('ns',2,3,str(i),1)
            except ClaimConflict: return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            winners=[x for x in pool.map(acquire,range(12)) if x]
        self.assertEqual(1,len(winners))
        winner=winners[0]
        self.assertEqual(winner,EvidenceStore(self.path).claim(winner['owner_workflow_id']))

    def test_uncertain_retained_known_release_generation_increases(self):
        first=self.store.acquire_claim('ns',2,3,'one',1)
        self.store.release_claim('one',known_outcome=False)
        self.assertEqual('uncertain',EvidenceStore(self.path).claim('one')['state'])
        with self.assertRaises(ClaimConflict): self.store.acquire_claim('ns',2,3,'two',2)
        self.store.release_claim('one',known_outcome=True)
        second=self.store.acquire_claim('ns',2,3,'two',3)
        self.assertGreater(second['generation'],first['generation'])
        self.assertNotEqual(second['record_id'],first['record_id'])

    def test_stop_and_events_durable_sql_safe(self):
        owner="owner'); DROP TABLE events; --"
        self.store.mark_stop(owner,'UNKNOWN',['missing'])
        self.store.record_event(owner,'cut',{'checkpoint':'P1'},2)
        reopened=EvidenceStore(self.path)
        self.assertEqual('UNKNOWN',reopened.stopped(owner)['decision'])
        self.assertEqual({'checkpoint':'P1'},reopened.events(owner)[0]['payload'])
        self.assertIsNone(reopened.stopped('another'))

    def test_bad_inputs_and_stale_observations(self):
        self.context()
        for amount,seq in [('NaN',2),('12',True),('12',0)]:
            with self.assertRaises(ValueError):
                self.store.material_state('ns',3,2,amount,'USD','acct',seq)
        with self.assertRaises(ValueError): self.store.acquire_claim('ns',True,3,'one',1)

if __name__=='__main__': unittest.main()
