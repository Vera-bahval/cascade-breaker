import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime

from experiments.payment_controls.native.overnight.preflight import available


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.now=datetime(2026,11,16,22,55,tzinfo=UTC)
        self.meta={'remaining':{'monthly_usd':2.09,'daily_usd':-1},
          'quotas':{'quotas':{'external':{'limits':[{'name':'all','limits':[{'type':'daily','usage':{'cost':-1}}]}]}}},
          'usage':{'usage':{'chain:top_opensource':{'stats':{'monthly':{'requests':8223,'cost':47.90668693695899}}}}}}
        db=sqlite3.connect(self.folder/'ledger.sqlite'); db.execute('create table requests (id text,cost real,status text)')
        cost=.005617488/16
        for i in range(16):
            key=f'{i:064x}'; db.execute('insert into requests values (?,?,?)',(key,cost,'complete'))
            row={'owner':f'seed-panel/{i}','provider':'eliza','model':'deepseek-flash','valid':True,
                 'usd':cost,'hash':key,'response_sha256':'a'*64}
            p=self.folder/(str(i)+'.json'); p.write_text(json.dumps(row)); t=self.now.timestamp(); os.utime(p,(t,t))
        db.commit(); db.close()

    def test_unknown_daily_with_matched_seed_and_monthly_reserve(self):
        self.assertAlmostEqual(available(self.meta,self.folder,now=self.now),1.59)

    def test_numeric_daily_and_monthly_reserve_remain_mandatory(self):
        self.meta['remaining']['daily_usd']=.4
        with self.assertRaises(ValueError): available(self.meta,self.folder,now=self.now)
        self.meta['remaining']['daily_usd']=.8
        self.assertAlmostEqual(available(self.meta,self.folder,now=self.now),.3)
        self.meta['remaining']['monthly_usd']=.49
        with self.assertRaises(ValueError): available(self.meta,self.folder,now=self.now)

    def test_expired_unknown_and_unreconciled_receipts_stop(self):
        with self.assertRaises(ValueError): available(self.meta,self.folder,now=datetime(2026,11,17,0,1,tzinfo=UTC))
        self.meta['quotas']['quotas']['external']['limits'][0]['limits'][0]['usage']['cost']=-2
        with self.assertRaises(ValueError): available(self.meta,self.folder,now=self.now)
        self.meta['quotas']['quotas']['external']['limits'][0]['limits'][0]['usage']['cost']=-1
        db=sqlite3.connect(self.folder/'ledger.sqlite'); db.execute("update requests set status='unknown'"); db.commit(); db.close()
        with self.assertRaises(ValueError): available(self.meta,self.folder,now=self.now)

    def test_fewer_than_two_valid_receipts_stop(self):
        for i in range(15):
            p=self.folder/(str(i)+'.json'); row=json.loads(p.read_text()); row['valid']=False; p.write_text(json.dumps(row)); t=self.now.timestamp(); os.utime(p,(t,t))
        with self.assertRaises(ValueError): available(self.meta,self.folder,now=self.now)
