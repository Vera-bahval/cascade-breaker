"""Narrow overnight-only quota evidence gate; -1 is unknown, never unlimited."""
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent


def available(meta, receipt_folder, *, now=None):
    """Return spend available after a $0.50 reserve; no inference that -1 is unlimited."""
    evidence = json.loads((HERE/'quota_evidence.json').read_text())
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError('timezone required')
    remaining = meta['remaining']
    monthly, daily = remaining['monthly_usd'], remaining['daily_usd']
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in (monthly,daily)):
        raise ValueError('invalid quota remaining')
    if monthly < .5:
        raise ValueError('monthly reserve unavailable')
    if daily >= 0:
        if daily < .5:
            raise ValueError('daily reserve unavailable')
        return min(monthly,daily) - .5
    limits = meta['quotas']['quotas']['external']['limits']
    daily_limit = next(r['usage']['cost'] for x in limits if x['name']=='all'
                       for r in x['limits'] if r['type']=='daily')
    if daily_limit != -1:
        raise ValueError('unsupported negative daily quota')
    if (now.astimezone(UTC).date().isoformat()!=evidence['utc_day'] or
        now.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()!=evidence['moscow_day']):
        raise ValueError('seed evidence is not from this UTC and Moscow day')
    usage = meta['usage']['usage']['chain:top_opensource']['stats']['monthly']
    if (usage['requests'] < evidence['after_monthly_requests'] or
        usage['cost'] + 1e-9 < evidence['after_monthly_cost']):
        raise ValueError('current usage does not include reconciled seed activity')
    if (evidence['after_monthly_requests']-evidence['before_monthly_requests'] != evidence['seed_requests'] or
        not math.isclose(evidence['after_monthly_cost']-evidence['before_monthly_cost'], evidence['seed_cost'], abs_tol=1e-9)):
        raise ValueError('seed aggregate mismatch')
    folder=Path(receipt_folder)
    with sqlite3.connect((folder/'ledger.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
        ledger={row[0]:row for row in db.execute('select id,cost,status from requests')}
    seed=[]
    for p in folder.glob('*.json'):
        row=json.loads(p.read_text())
        if not str(row.get('owner','')).startswith('seed-panel/'):
            continue
        at=datetime.fromtimestamp(p.stat().st_mtime,UTC)
        if (at.date().isoformat()!=evidence['utc_day'] or
            at.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()!=evidence['moscow_day']):
            continue
        if row.get('valid') is not True:
            continue
        cost=row.get('usd'); entry=ledger.get(row.get('hash'))
        if (row.get('provider')!='eliza' or row.get('model')!=evidence['model'] or row.get('valid') is not True or
            type(cost) not in (int,float) or not math.isfinite(cost) or cost<=0 or
            not isinstance(row.get('response_sha256'),str) or len(row['response_sha256'])!=64 or
            entry is None or entry[2]!='complete' or not math.isclose(entry[1],cost,abs_tol=1e-12)):
            raise ValueError('invalid or unreconciled paid seed receipt')
        seed.append(cost)
    if len(seed)<2 or len(ledger)!=evidence['seed_requests'] or any(
        row[2]!='complete' or type(row[1]) not in (int,float) or row[1]<=0 for row in ledger.values()
    ) or not math.isclose(sum(row[1] for row in ledger.values()),evidence['seed_cost'],abs_tol=1e-9):
        raise ValueError('paid same-day seed evidence incomplete')
    return monthly - .5
