"""Verify published archive bytes, request coverage and the account-data projection."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tarfile
import tempfile

from build_report import HERE, load, save, require_cohort, key as episode_key
from prepare_bundle import public_value


PATTERNS = {'api_key': re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}'),
            'github_token': re.compile(rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}'),
            'bearer_literal': re.compile(rb'Bearer [A-Za-z0-9_.~-]{24,}')}


def validate_public_json(data, name):
    content = gzip.decompress(data) if name.endswith('.gz') else data
    rows = ([json.loads(line) for line in content.decode().splitlines() if line.strip()]
            if name.endswith(('.jsonl', '.jsonl.gz')) else json.loads(content))
    if public_value(rows) != rows:
        raise ValueError('Account metadata survived publication projection: '+name)
    for label, pattern in PATTERNS.items():
        if pattern.search(content):
            raise ValueError('Potential credential pattern '+label+' in '+name)


def validate():
    manifest = json.loads((HERE/'artifacts/manifest.json').read_text())
    intents = {'deepseek': {}, 'luna': {}}
    outcomes = {'deepseek': {}, 'luna': {}}
    failures = {}; members_checked = 0; filtered = 0; contents_preserved = 0
    ledgers = {}; business_dbs = 0
    suspicious = []
    # Печатаются только имена файлов и классы совпадений, без значений секретов.
    patterns = PATTERNS
    for archive, info in manifest['archives'].items():
        path = HERE/'artifacts'/archive
        if hashlib.sha256(path.read_bytes()).hexdigest() != info['sha256']:
            raise ValueError('Archive hash mismatch: '+archive)
        model = archive.split('-', 1)[0]
        with tarfile.open(path) as tf:
            actual = {m.name:m for m in tf if m.isfile()}
            if set(actual) != set(info['members']):
                raise ValueError('Archive membership mismatch')
            for name, member in actual.items():
                if Path(name).is_absolute() or '..' in Path(name).parts:
                    raise ValueError('Unsafe archive path')
                data = tf.extractfile(member).read(); proof = info['members'][name]
                if hashlib.sha256(data).hexdigest() != proof['published_sha256']:
                    raise ValueError('Member hash mismatch: '+name)
                members_checked += 1
                content = gzip.decompress(data) if name.endswith('.jsonl.gz') else data
                if hashlib.sha256(content).hexdigest() != proof['published_content_sha256']:
                    raise ValueError('Decompressed content hash mismatch')
                filtered += proof['public_metadata_filtered']
                contents_preserved += proof['source_content_sha256'] == proof['published_content_sha256']
                if name.endswith(('.jsonl.gz','.jsonl')):
                    rows = [json.loads(line) for line in content.decode().splitlines() if line.strip()]
                    if public_value(rows) != rows:
                        raise ValueError('Account metadata survived publication projection: '+name)
                    for row in rows:
                        if row.get('event') in ('request','intent'):
                            identity = row['attempt_id']
                            if identity in intents[model]:
                                raise ValueError('Duplicate raw intent '+identity)
                            intents[model][identity] = name
                elif name.endswith('.json'):
                    row = json.loads(data)
                    if public_value(row) != row:
                        raise ValueError('Account metadata survived JSON projection: '+name)
                    if '/main/episodes/' in name and name.endswith('/episode.json'):
                        if row['episode'] in outcomes[model]:
                            raise ValueError('Duplicate canonical native outcome')
                        outcomes[model][row['episode']] = row
                    if name.endswith('/failed-episode.json'):
                        failures[row['episode']] = row
                if name.endswith(('/budget.sqlite.gz','/budget.snapshot.sqlite.gz')):
                    with tempfile.TemporaryDirectory() as td:
                        db_path = Path(td)/'ledger';db_path.write_bytes(gzip.decompress(data))
                        with sqlite3.connect(db_path) as db:
                            if db.execute('pragma integrity_check').fetchone()[0] != 'ok':
                                raise ValueError('Public ledger SQLite integrity')
                            db.row_factory = sqlite3.Row
                            table = 'requests' if model == 'deepseek' else 'intents'
                            ledgers[model] = {r['id']:dict(r) for r in db.execute('select * from '+table)}
                if '/main/episodes/' in name and name.endswith('/snapshot.sqlite.gz'):
                    snapshot_name = name.removesuffix('snapshot.sqlite.gz')+'database.json'
                    snapshot = json.load(tf.extractfile(actual[snapshot_name]))
                    with tempfile.TemporaryDirectory() as td:
                        db_path = Path(td)/'business';db_path.write_bytes(gzip.decompress(data))
                        with sqlite3.connect(db_path) as db:
                            if db.execute('pragma integrity_check').fetchone()[0] != 'ok':
                                raise ValueError('Public business SQLite integrity')
                            db.row_factory = sqlite3.Row
                            observed = {table:[dict(r) for r in db.execute('select * from "'+table+'"')] for table in snapshot}
                            if observed != snapshot:
                                raise ValueError('Public business SQLite/snapshot mismatch')
                    business_dbs += 1
                if name.endswith(('.json','.jsonl','.jsonl.gz','.txt')):
                    for label, pattern in patterns.items():
                        if pattern.search(content):
                            suspicious.append({'file':name,'class':label})
    if suspicious:
        raise ValueError('Review potential credentials by filename: '+json.dumps(suspicious))
    for model, expected_count in [('deepseek',8242),('luna',6847)]:
        requests = load(model+'-requests.json.gz')
        ids = [r['attempt_id'] for r in requests]
        if len(ids) != expected_count or len(ids) != len(set(ids)) or set(ids) != set(intents[model]):
            raise ValueError('Raw request/index coverage mismatch: '+model)
        if set(ids) != set(ledgers[model]):
            raise ValueError('Ledger/index identity mismatch')
        for row in requests:
            ledger = ledgers[model][row['attempt_id']]
            actual_cost = row['eliza_cost_usd'] if model == 'deepseek' else row['estimate_upper_usd']
            stored_cost = ledger['cost'] if model == 'deepseek' else ledger['upper']
            if actual_cost != stored_cost:
                raise ValueError('Ledger/index cost mismatch')
        episodes = [r for r in load(model+'-episodes.json') if r['phase']=='main']
        require_cohort(episodes, [episode_key(r) for r in outcomes[model].values()], 'published native '+model)
        if len(outcomes[model]) != 297 or {r['episode'] for r in episodes} != set(outcomes[model]):
            raise ValueError('Native canonical episode coverage')
        for row in episodes:
            original = outcomes[model][row['episode']]
            for key in ('scenario_id','repeat','dataset','invoice_status','amount','transfers','create_transfer_calls','payment_transactions'):
                if row[key] != original[key]:
                    raise ValueError('Published aggregate/native outcome mismatch: '+row['episode']+'/'+key)
        guards = load(model+'-defenders.json.gz')
        votes = {v['attempt_id'] for g in guards.values() for v in g['votes']}
        if len(guards) != 297 or len(votes) != 702:
            raise ValueError('Input guard vote coverage')
    luna = load('luna-requests.json.gz')
    unknown = [r for r in luna if r['accounting_state']=='unknown']
    if len(failures) != 4 or len(unknown) != 4 or any(r['native_usage'] is not None or r['estimate_upper_usd'] is not None for r in unknown):
        raise ValueError('Original four unknowns not preserved')
    if {r['episode'] for r in unknown} != set(failures):
        raise ValueError('Original failure identity mismatch')
    actual_inputs = {p.name for p in (HERE/'inputs').iterdir() if p.is_file()}
    if actual_inputs != set(manifest['inputs']):
        raise ValueError('Input inventory mismatch')
    for name, info in manifest['inputs'].items():
        data = (HERE/'inputs'/name).read_bytes()
        if hashlib.sha256(data).hexdigest() != info['published_sha256']:
            raise ValueError('Committed input hash mismatch: '+name)
        validate_public_json(data, name)
    result = {'archive_files':len(manifest['archives']),'members_checked':members_checked,
        'members_with_public_account_metadata_removed':filtered,'members_with_unchanged_logical_content':contents_preserved,
        'deepseek_raw_intents':len(intents['deepseek']),'luna_raw_intents':len(intents['luna']),
        'native_canonical_outcomes':{k:len(v) for k,v in outcomes.items()},'original_luna_unknowns':4,
        'native_business_sqlite_snapshots_checked':business_dbs,'ledger_indexes_reconciled':True,
        'unique_input_votes_per_native_model':702,'potential_credential_patterns':0,'new_model_requests':0,
        'public_input_files_checked':len(actual_inputs),
        'scope':'New public evidence and input indexes; historical archives separately checked by build_report.py',
        'validator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save(HERE/'PUBLICATION-CHECK.json',result)
    print(json.dumps(result))


if __name__ == '__main__':
    validate()
