"""Durable sidecar evidence for covered protected-runtime writers, not source-DB atomicity.

Every operation opens its own SQLite connection. Claim acquisition and material/
approval updates use BEGIN IMMEDIATE. No expiry or inferred reconciliation exists.
The adapter must call material_state on every covered material write (including
restorations), and re-read native state before effects. External-write races remain.
"""
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4


class ClaimConflict(RuntimeError):
    """An active/uncertain overlapping claim already owns the subject."""


def _text(value,name):
    if not isinstance(value,str) or not value.strip(): raise ValueError(name)
    return value


def _int(value,name,minimum=0):
    if type(value) is not int or value<minimum: raise ValueError(name)
    return value


def _money(value):
    if not isinstance(value,str) or not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',value): raise ValueError('amount')
    try: amount=Decimal(value)
    except InvalidOperation: raise ValueError('amount') from None
    if not amount.is_finite(): raise ValueError('amount')
    # Decimal equality, without context-dependent rounding from normalize().
    return amount


def _currency(value):
    value=_text(value,'currency').upper()
    if not re.fullmatch('[A-Z]{3}',value): raise ValueError('currency')
    return value


def _json(value): return json.dumps(value,separators=(',',':'),sort_keys=True,allow_nan=False)


class EvidenceStore:
    def __init__(self,path):
        if str(path)==':memory:': raise ValueError('durable filesystem path required')
        self.path=str(Path(path))
        with self._connection(write=True) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS invoice_material (namespace TEXT, invoice_id INTEGER, vendor_id INTEGER, amount TEXT, currency TEXT, revision INTEGER, seq INTEGER, PRIMARY KEY(namespace,invoice_id))')
            conn.execute('CREATE TABLE IF NOT EXISTS vendor_material (namespace TEXT, vendor_id INTEGER, account_ref TEXT, revision INTEGER, seq INTEGER, PRIMARY KEY(namespace,vendor_id))')
            conn.execute('CREATE TABLE IF NOT EXISTS approvals (namespace TEXT, invoice_id INTEGER, record TEXT NOT NULL, PRIMARY KEY(namespace,invoice_id))')
            conn.execute('CREATE TABLE IF NOT EXISTS claims (owner TEXT PRIMARY KEY, namespace TEXT NOT NULL, vendor_id INTEGER NOT NULL, invoice_id INTEGER, record TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS generations (generation INTEGER PRIMARY KEY AUTOINCREMENT)')
            conn.execute('CREATE TABLE IF NOT EXISTS stops (owner TEXT PRIMARY KEY, record TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, seq INTEGER NOT NULL)')

    @contextmanager
    def _connection(self,write=False):
        conn=sqlite3.connect(self.path,timeout=30,isolation_level=None)
        conn.row_factory=sqlite3.Row
        try:
            if write: conn.execute('BEGIN IMMEDIATE')
            yield conn
            if write: conn.commit()
        except BaseException:
            if write: conn.rollback()
            raise
        finally: conn.close()

    @staticmethod
    def _versions(invoice,vendor):
        return {'invoice_version':'invoice:'+str(invoice['revision']),
                'vendor_version':'vendor:'+str(vendor['revision'])}

    def material_state(self,namespace,invoice_id,vendor_id,amount,currency,account_ref,seq):
        """Observe covered material fields; return immutable monotonic revision tokens.

        Notes are intentionally absent. Same material content does not increment a
        revision. A changed-and-restored content sequence increments on both calls.
        """
        _text(namespace,'namespace'); _int(invoice_id,'invoice_id',1); _int(vendor_id,'vendor_id',1)
        value=_money(amount); currency=_currency(currency); _text(account_ref,'account_ref'); _int(seq,'seq')
        with self._connection(write=True) as conn:
            invoice=conn.execute('SELECT * FROM invoice_material WHERE namespace=? AND invoice_id=?',(namespace,invoice_id)).fetchone()
            vendor=conn.execute('SELECT * FROM vendor_material WHERE namespace=? AND vendor_id=?',(namespace,vendor_id)).fetchone()
            invoice_changed=invoice is None or (invoice['vendor_id']!=vendor_id or _money(invoice['amount'])!=value or invoice['currency']!=currency)
            vendor_changed=vendor is None or vendor['account_ref']!=account_ref
            for previous,changed in ((invoice,invoice_changed),(vendor,vendor_changed)):
                if previous and (seq<previous['seq'] or seq==previous['seq'] and changed): raise ValueError('stale material observation')
            ir=1 if invoice is None else invoice['revision']+int(invoice_changed)
            vr=1 if vendor is None else vendor['revision']+int(vendor_changed)
            conn.execute('INSERT OR REPLACE INTO invoice_material VALUES (?,?,?,?,?,?,?)',(namespace,invoice_id,vendor_id,str(value),currency,ir,seq))
            conn.execute('INSERT OR REPLACE INTO vendor_material VALUES (?,?,?,?,?)',(namespace,vendor_id,account_ref,vr,seq))
            if invoice_changed: conn.execute('DELETE FROM approvals WHERE namespace=? AND invoice_id=?',(namespace,invoice_id))
            if vendor_changed:
                conn.execute('DELETE FROM approvals WHERE namespace=? AND invoice_id IN (SELECT invoice_id FROM invoice_material WHERE namespace=? AND vendor_id=?)',(namespace,namespace,vendor_id))
            return {'invoice_version':'invoice:'+str(ir),'vendor_version':'vendor:'+str(vr)}

    def _current(self,conn,context):
        if not isinstance(context,dict): raise ValueError('context')
        ns=_text(context.get('namespace'),'namespace')
        iid=_int(context.get('invoice_id'),'invoice_id',1); vid=_int(context.get('vendor_id'),'vendor_id',1)
        invoice=conn.execute('SELECT * FROM invoice_material WHERE namespace=? AND invoice_id=?',(ns,iid)).fetchone()
        vendor=conn.execute('SELECT * FROM vendor_material WHERE namespace=? AND vendor_id=?',(ns,vid)).fetchone()
        if not invoice or not vendor or invoice['vendor_id']!=vid: return None
        versions=self._versions(invoice,vendor)
        if any(context.get(k)!=v for k,v in versions.items()) or context.get('account_ref')!=vendor['account_ref']: return None
        return invoice,vendor

    def bind_approval(self,context,amount,currency,seq):
        """Bind current material revisions; ordinary approval is not human approval.

        context needs namespace,invoice_id,vendor_id,account_ref,invoice_version,
        vendor_version. The adapter couples native approved mutation with this
        protected sidecar transaction; this method alone cannot change a source DB.
        """
        value=_money(amount); currency=_currency(currency); _int(seq,'seq')
        with self._connection(write=True) as conn:
            current=self._current(conn,context)
            if not current: raise ValueError('stale or missing material context')
            invoice,vendor=current
            if seq<max(invoice['seq'],vendor['seq']) or value!=_money(invoice['amount']) or currency!=invoice['currency']: raise ValueError('approval material mismatch')
            record={k:context[k] for k in ('invoice_id','vendor_id','account_ref','invoice_version','vendor_version')}
            record.update(record_id=uuid4().hex,amount=str(value),currency=currency,approved_seq=seq)
            conn.execute('INSERT OR REPLACE INTO approvals VALUES (?,?,?)',(context['namespace'],context['invoice_id'],_json(record)))
            return record

    def approval(self,context):
        """Return current unrevoked binding or None; stale snapshots never revive it."""
        with self._connection() as conn:
            current=self._current(conn,context)
            if not current: return None
            row=conn.execute('SELECT record FROM approvals WHERE namespace=? AND invoice_id=?',(context['namespace'],context['invoice_id'])).fetchone()
            if not row: return None
            record=json.loads(row['record'])
            if any(record[k]!=context[k] for k in ('invoice_id','vendor_id','account_ref','invoice_version','vendor_version')): return None
            return record

    def acquire_claim(self,namespace,vendor_id,invoice_id,owner_workflow_id,seq):
        """Atomically acquire; only exact internal same-owner continuation inherits.

        invoice_id=None is vendor-wide. A caller must create a fresh owner for each
        start_workflow; inheritance is reserved for internal delegation by adapter.
        """
        _text(namespace,'namespace'); _int(vendor_id,'vendor_id',1)
        if invoice_id is not None: _int(invoice_id,'invoice_id',1)
        _text(owner_workflow_id,'owner_workflow_id'); _int(seq,'seq')
        key=[namespace,'invoice',invoice_id,vendor_id] if invoice_id is not None else [namespace,'vendor',vendor_id]
        with self._connection(write=True) as conn:
            old=conn.execute('SELECT * FROM claims WHERE owner=?',(owner_workflow_id,)).fetchone()
            if old:
                record=json.loads(old['record'])
                if record['state'] in {'active','uncertain'}:
                    if record['state']=='active' and json.loads(record['key'])==key and seq>=record['acquired_seq']: return record
                    raise ClaimConflict('owner already bound to another or uncertain subject')
            rows=conn.execute('SELECT * FROM claims WHERE namespace=? AND (vendor_id=? OR invoice_id=?)',(namespace,vendor_id,invoice_id)).fetchall()
            for row in rows:
                record=json.loads(row['record'])
                if record['state'] in {'active','uncertain'} and ((row['vendor_id']==vendor_id and (invoice_id is None or row['invoice_id'] is None)) or (invoice_id is not None and row['invoice_id']==invoice_id)):
                    raise ClaimConflict('overlapping active or uncertain claim')
            generation=conn.execute('INSERT INTO generations DEFAULT VALUES').lastrowid
            record=dict(record_id=uuid4().hex,key=_json(key),owner_workflow_id=owner_workflow_id,
                        generation=generation,state='active',acquired_seq=seq)
            conn.execute('INSERT OR REPLACE INTO claims VALUES (?,?,?,?,?)',(owner_workflow_id,namespace,vendor_id,invoice_id,_json(record)))
            return record

    def claim(self,owner):
        _text(owner,'owner')
        with self._connection() as conn:
            row=conn.execute('SELECT record FROM claims WHERE owner=?',(owner,)).fetchone()
            return json.loads(row['record']) if row else None

    def release_claim(self,owner,known_outcome=True):
        _text(owner,'owner')
        if type(known_outcome) is not bool: raise ValueError('known_outcome')
        with self._connection(write=True) as conn:
            row=conn.execute('SELECT record FROM claims WHERE owner=?',(owner,)).fetchone()
            if row:
                record=json.loads(row['record'])
                if record['state']=='released': return
                record['state']='released' if known_outcome else 'uncertain'
                conn.execute('UPDATE claims SET record=? WHERE owner=?',(_json(record),owner))

    def mark_stop(self,owner,decision,reasons):
        _text(owner,'owner')
        if decision not in {'BLOCK','UNKNOWN'} or not isinstance(reasons,list) or any(not isinstance(x,str) for x in reasons): raise ValueError('stop')
        record={'decision':decision,'reasons':list(reasons)}
        with self._connection(write=True) as conn:
            # First STOP is irreversible for this admitted owner, including retries.
            conn.execute('INSERT OR IGNORE INTO stops VALUES (?,?)',(owner,_json(record)))

    def stopped(self,owner):
        _text(owner,'owner')
        with self._connection() as conn:
            row=conn.execute('SELECT record FROM stops WHERE owner=?',(owner,)).fetchone()
            return json.loads(row['record']) if row else None

    def record_event(self,owner,kind,payload,seq):
        _text(owner,'owner'); _text(kind,'kind'); _int(seq,'seq')
        if not isinstance(payload,dict): raise ValueError('payload')
        with self._connection(write=True) as conn:
            conn.execute('INSERT INTO events(owner,kind,payload,seq) VALUES (?,?,?,?)',(owner,kind,_json(payload),seq))

    def events(self,owner):
        _text(owner,'owner')
        with self._connection() as conn:
            return [{'kind':row['kind'],'payload':json.loads(row['payload']),'seq':row['seq']}
                    for row in conn.execute('SELECT * FROM events WHERE owner=? ORDER BY id',(owner,))]
