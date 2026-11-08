"""Recover archive state with recorded inputs and source-bound setup only."""

from copy import deepcopy
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tarfile

from experiments.local_guards_archive_comparison.collector import (
    NATIVE_REVISION, decimal, evidence, file_hash, token,
)

RUNNERS = {
    'deepseek': ('deepseek_flash',
                 'a04a1720ce2ba528def5b79b0a7e7e79f278d68380ab0a1921c51c803b82b329',
                 '57b8bff7639d706e5b90418e30b9b7fe4e6bc4ee3d55fd78e8255685fa865331'),
    'luna': ('gpt_6_luna',
             '5c09fc6a63c75b84b15a93faea50988782621a25dc766170652c1a1e034c4999',
             '182e2264439176c9b9397a60d7fe49397800d80e934a7ec7dc3cdc19197d457f'),
}
SEED_HASH = '0af3fb44d69755ad7b552756218b118ecad906e048e9412898db1a447cc7a1e7'
DEMO = 'scripts/cascade_failure_demo.py'
REPOSITORIES = 'finbot/core/data/repositories.py'
MODELS = 'finbot/core/data/models.py'
NATIVE_SOURCES = {
    DEMO: 'e36359885c95bcf2c237f93b7f436cc90e1d9c7de24056bbaf6e382efda0727a',
    REPOSITORIES: '6ccad86525f69ba1bebcc4aa7d93b370a5d3acc3632b08e49603eb10f7cfdc3d',
    MODELS: 'f1c9f3c87a426cac699dfa050171c7777b026e412d59476290bd3ef3cae646e5',
}
JOB_FIELDS = ('episode', 'dataset', 'repeat', 'batch', 'index')
SCENARIO_FIELDS = ('id', 'amount', 'desc')
CAUSAL_SOURCES = (
    'finbot/agents/base.py', 'finbot/agents/cascade.py', 'finbot/agents/runner.py',
    'finbot/tools/data/fraud.py', 'finbot/tools/data/invoice.py',
    'finbot/tools/data/payment.py', 'finbot/tools/data/vendor.py',
    'finbot/mcp/servers/findrive/server.py', 'finbot/mcp/servers/finmail/server.py',
    'finbot/mcp/servers/finstripe/server.py', 'finbot/mcp/servers/taxcalc/server.py',
)
# Tools present in this evidence set with no writes to invoice, vendor or payment
# rows. Other tools (including SystemUtils) withhold fallback current-state facts.
SAFE_TOOLS = frozenset("""
    complete_task delegate_to_communication delegate_to_fraud delegate_to_invoice
    delegate_to_payments findrive__list_files findrive__search_files
    finmail__list_inbox finmail__search_emails finmail__send_email
    finstripe__get_transfer finstripe__list_transfers finstripe__get_account_balance
    get_invoice_details get_invoice_for_payment get_vendor_contact_info
    get_vendor_details get_vendor_invoices get_vendor_risk_profile
    taxcalc__calculate_tax taxcalc__get_tax_rates
""".split())
INVOICE_STATUS_WRITES = {'update_invoice_status', 'process_payment', 'flag_invoice_for_review'}
VENDOR_RISK_WRITES = {'update_vendor_risk'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def runner_digest(data):
    """Historical transport's JSON fingerprint serialization."""
    return sha(json.dumps(data, sort_keys=True, ensure_ascii=False).encode())


def job_subject(job):
    return tuple(job[k] for k in JOB_FIELDS) + tuple(job['scenario'][k] for k in SCENARIO_FIELDS)


class Archive:
    def __init__(self, root, cohort_manifest):
        root = Path(root).resolve()
        self.workspace = root.parents[1]
        self.artifacts = root.parent/'finbot-four-model-report/experiments/control-placement/four-model-comparison/artifacts'
        if isinstance(cohort_manifest, (str, Path)):
            cohort_manifest = json.loads(Path(cohort_manifest).read_text())
        self.p4_prefixes = {case['prefix_id'] for case in (cohort_manifest or {}).get('cases', [])
                            if 'prefix_id' in case}

    @lru_cache(maxsize=None)
    def _archive(self, name):
        published = json.loads((self.artifacts/'manifest.json').read_text())['archives'][name]
        path = self.artifacts/name
        if file_hash(path) != published['sha256']:
            raise ValueError('Published archive hash mismatch: ' + str(path))
        return path, published

    @lru_cache(maxsize=None)
    def _members(self, name):
        path, published = self._archive(name)
        payloads = {}
        with tarfile.open(path, 'r|gz') as archive:
            for member in archive:
                suffix = Path(member.name).name
                if not member.isfile() or suffix not in {
                    'job.json', 'hooks.jsonl', 'execution.json', 'manifest.json', 'worker.py', 'experiment.py',
                }:
                    continue
                if member.name in payloads:
                    raise ValueError('Duplicate archive member: ' + member.name)
                if suffix == 'hooks.jsonl':
                    # The verified outer archive covers the member. Decode only
                    # admission; no later hook content is needed here.
                    first_line = archive.extractfile(member).readline()
                    if first_line:
                        admission = json.loads(first_line)
                        payloads[member.name] = {key: admission.get(key) for key in
                                                 ('hook_kind', 'user_message', 'workflow_id')}
                    continue
                raw = archive.extractfile(member).read()
                receipt = published['members'][member.name]
                if sha(raw) != receipt['published_sha256']:
                    raise ValueError('Published member hash mismatch: ' + member.name)
                if suffix == 'job.json':
                    job = json.loads(raw)
                    payloads[member.name] = (
                        job_subject(job), job['phase'], job['execution_fingerprint'], runner_digest(job),
                    )
                else:
                    payloads[member.name] = raw
        return payloads

    @lru_cache(maxsize=None)
    def _runner(self, executor):
        directory, worker_sha, experiment_sha = RUNNERS[executor]
        name = f'{executor}-source-and-acceptance.tar.gz'
        path, _ = self._archive(name)
        members = self._members(name)
        manifest_name, = (m for m in members if m.endswith('/manifest.json'))
        manifest = json.loads(members[manifest_name])
        spec = manifest['execution_spec']
        revision = manifest.get('finbot_commit', spec.get('finbot_commit'))
        if revision != NATIVE_REVISION:
            raise ValueError('Unsupported FinBot source revision')
        fingerprint = runner_digest(spec)
        if manifest.get('execution_fingerprint', fingerprint) != fingerprint:
            raise ValueError('Runner manifest fingerprint mismatch')
        worker = f'experiments/control-placement/{directory}/worker.py'
        controller = f'experiments/control-placement/{directory}/experiment.py'
        sources = {}
        for member, expected in ((worker, worker_sha), (controller, experiment_sha)):
            rel = '/'.join(member.split('/')[-2:])
            if sha(members[member]) != expected or spec['source_hashes'][rel] != expected:
                raise ValueError('Unsupported runner source: ' + rel)
            sources[f'{path}::{member}'] = expected
        for rel, expected in NATIVE_SOURCES.items():
            native = self.workspace/'vendor/finbot'/rel
            if spec['finbot_hashes'][rel] != expected or file_hash(native) != expected:
                raise ValueError('Historical FinBot setup source mismatch: ' + rel)
            sources[str(native)] = expected
        sources[f'{path}::{manifest_name}'] = sha(members[manifest_name])
        if spec['pristine_sha256'] != SEED_HASH:
            raise ValueError('Unsupported initial database')
        native_runtime = self.workspace/'deepseek-flash-control-placement/experiments/control-placement/deepseek_flash/.runtime/finbot'
        causal_sources = {}
        for rel in CAUSAL_SOURCES:
            native = native_runtime/rel
            expected = spec['finbot_hashes'].get(rel)
            if not native.is_file() or file_hash(native) != expected:
                causal_sources = {}
                break
            causal_sources[str(native)] = expected
        return (fingerprint, {job_subject(j) for j in manifest['matrix']}, sources,
                f'{path}::{worker}', str(self.workspace/'vendor/finbot'/DEMO), revision,
                causal_sources)

    @lru_cache(maxsize=1)
    def _seed(self):
        path = (self.workspace/'deepseek-flash-control-placement/experiments/control-placement'
                /'deepseek_flash/results/paid/pristine_C.sqlite.gz')
        raw = gzip.decompress(path.read_bytes())
        if sha(raw) != SEED_HASH:
            raise ValueError('Historical SQLite seed hash mismatch')
        db = sqlite3.connect(':memory:')
        try:
            # The archived seed was checkpointed with TRUNCATE before use.
            # SQLite's in-memory deserialize reader cannot open WAL mode.
            # Switch only the in-memory copy's pager mode bytes after hashing.
            db.deserialize(raw[:18] + b'\x01\x01' + raw[20:])
            db.row_factory = sqlite3.Row
            vendor = dict(db.execute(
                '''SELECT id, namespace, status, trust_level, risk_level,
                          industry, bank_account_number
                   FROM vendors WHERE id=1'''
            ).fetchone())
            transactions = [dict(row) for row in db.execute('SELECT * FROM payment_transactions ORDER BY id')]
            max_invoice = db.execute('SELECT max(id) FROM invoices').fetchone()[0]
        finally:
            db.close()
        return path, vendor, transactions, max_invoice

    def _bound_initial(self, row, metadata):
        executor = metadata.get('executor')
        name = Path(metadata.get('source') or '').name
        match = re.fullmatch(r'(deepseek|luna)-(main-batch-[1-5]|additional-attempts)\.tar\.gz', name)
        if executor not in RUNNERS or match is None or match[1] != executor:
            return None, 'no_source_bound_initial_snapshot'
        path, published = self._archive(name)
        if metadata['source_sha256'] != published['sha256']:
            return None, 'episode_archive_hash_mismatch'
        hook = metadata['member']
        folder = hook.removesuffix('/hooks.jsonl').rstrip('/')
        member = folder+'/job.json'
        if metadata.get('fixture_ref', '').split('::')[-1] != member:
            return None, 'job_locator_mismatch'
        payloads = self._members(name)
        if member not in payloads:
            return None, 'no_archived_job'
        subject, phase, job_fingerprint, job_hash = payloads[member]
        fingerprint, matrix, sources, worker_ref, demo_ref, revision, causal_sources = self._runner(executor)
        if job_fingerprint != fingerprint:
            return None, 'job_fingerprint_not_bound_to_verified_runner'
        sources = dict(sources)
        if phase == 'main':
            if subject not in matrix:
                return None, 'job_not_in_frozen_main_matrix'
        else:
            phase_folder = folder.split('/episodes/', 1)[0]
            phase_ref = phase_folder+'/execution.json'
            if phase != 'pilot' or phase_ref not in payloads:
                return None, 'unverified_non_main_phase'
            phase_record = json.loads(payloads[phase_ref])
            if phase_record.get('fingerprint') != fingerprint or runner_digest(phase_record['spec']) != fingerprint:
                return None, 'unverified_non_main_execution_spec'
            sources[f'{path}::{phase_ref}'] = sha(payloads[phase_ref])
        if folder.split('/episodes/', 1)[-1] != subject[0]:
            return None, 'job_episode_path_mismatch'

        raw = row['raw_context']
        hook_member = hook if hook.endswith('.jsonl') else hook+'hooks.jsonl'
        first = payloads.get(hook_member, {})
        visible = next(iter(raw.get('events', [])), {})
        context = row['observation']['context']
        workflow = f'{executor}_{job_hash[:20]}'
        if (first.get('hook_kind') != 'before_model' or first.get('workflow_id') != workflow
                or context.get('workflow_id') not in (None, workflow)
                or (visible and (visible.get('hook_kind') != 'before_model'
                                 or visible.get('user_message') != first.get('user_message')))):
            return None, 'job_not_bound_to_admission'
        seed_path, vendor, transactions, max_invoice = self._seed()
        invoice_id = max_invoice + 1
        user = first.get('user_message') or ''
        if not (vendor['namespace'] == 'cascade-demo'
                and re.search(r'\binvoice_id:\s*'+str(invoice_id)+r'\b', user)
                and re.search(r'\bvendor_id:\s*1\b', user)
                and context.get('invoice_id') in (None, invoice_id)):
            return None, 'invoice_or_vendor_not_bound_to_admission'

        _, _, _, _, index, _, amount, description = subject
        invoice = {
            'id': invoice_id, 'vendor_id': 1, 'namespace': 'cascade-demo',
            'invoice_number': f'INV-2026-{1000+index:04d}', 'amount': float(amount),
            'description': description, 'status': 'submitted',
        }
        state = {'invoice': invoice, 'vendor': deepcopy(vendor), 'transactions': deepcopy(transactions)}
        job_ref = f'{path}::{member}'
        sources[job_ref] = published['members'][member]['published_sha256']
        sources[str(seed_path)+'#decompressed-sqlite'] = SEED_HASH
        hook_ref = f'{path}::{hook_member}'
        admission_ref = hook_ref+'#L1'
        sources[hook_ref] = published['members'][hook_member]['published_sha256']
        binding = dict(source_ref=worker_ref, session_source_ref=demo_ref, revision=revision,
                       root_attachment_file_ids=[],
                       namespace='cascade-demo', user_id='cascade_demo_user', origin_portal='vendor',
                       current_vendor_id=1, invoice_id=invoice_id, expires_in_s=7200)
        receipt = evidence(job_ref, 0, 'raw_context.initial_state', state,
                           {'invoice_id': invoice_id, 'vendor_id': 1},
                           status='derived', kind='deterministic_reconstruction',
                           derived_from=[*sources, admission_ref],
                           note='Verified initial simulated database and deterministic historical worker setup.')
        receipt.update(verified_inputs=sources, runner_binding=binding, causal_sources=causal_sources)
        return state, receipt

    def enrich(self, row, metadata):
        """Return a new row plus evidence receipts, without changing the cut or context."""
        if (self.p4_prefixes and row['checkpoint'] == 'P4'
                and row['prefix_id'] not in self.p4_prefixes):
            raise ValueError('P4 is outside the declared cohort: ' + row['prefix_id'])
        if row['episode_id'] != metadata.get('episode_id', row['episode_id']):
            raise ValueError('Archive metadata is from a different episode')
        output = deepcopy(row)
        raw = output['raw_context']
        initial = raw.get('initial_state') or {}
        original_state = raw.get('db_initial')
        if not initial and isinstance(original_state, dict):
            initial = raw['initial_state'] = deepcopy(original_state)
        if isinstance(initial.get('transactions'), list):
            locator = metadata.get('fixture_ref')
            if not locator or not locator.endswith('/db_initial'):
                return output, []
            return output, [dict(source_ref=locator, event_seq=0, field='raw_context.initial_state',
                                 status='observed', kind='historical', source_sha256=metadata.get('source_sha256'))]
        state, receipt = self._bound_initial(row, metadata)
        if state is None:
            return output, [dict(source_ref=metadata.get('fixture_ref') or metadata.get('source'),
                                 field='raw_context.initial_state', event_seq=0, status='unknown',
                                 kind='unknown', reason=receipt)]
        raw['initial_state'] = state
        return output, [receipt, *self._current_facts(output, state, receipt)]

    @staticmethod
    def _current_facts(row, state, initial_receipt):
        """Carry forward only values no earlier captured call could have changed."""
        obs = row['observation']
        context = obs['context']
        events = row['raw_context'].get('events', [])
        cut = row['event_seq']
        if (not initial_receipt['causal_sources'] or context.get('prefix_complete') is not True
                or [e['event_seq'] for e in events] != list(range(2, cut, 2))):
            return []
        tools = {e.get('tool_name') for e in events if e.get('hook_kind') in {'before_tool', 'after_tool'}}
        if tools - SAFE_TOOLS - INVOICE_STATUS_WRITES - VENDOR_RISK_WRITES - {'finstripe__create_transfer'}:
            return []
        invoice, vendor = state['invoice'], state['vendor']
        if context.get('invoice_id') != invoice['id'] or context.get('vendor_id') != vendor['id']:
            return []
        candidates = {
            'invoice_vendor_id': invoice['vendor_id'], 'invoice_amount': decimal(invoice['amount']),
            'invoice_number': invoice['invoice_number'], 'invoice_in_namespace': True,
            'vendor_in_namespace': True, 'vendor_status': vendor['status'],
            'vendor_industry': vendor['industry'], 'vendor_account_token': token(vendor['bank_account_number']),
            'vendor_bank_details_present': bool(vendor['bank_account_number']),
        }
        if not tools & INVOICE_STATUS_WRITES:
            candidates['invoice_status'] = invoice['status']
        if not tools & VENDOR_RISK_WRITES:
            candidates.update(vendor_trust_level=vendor['trust_level'], vendor_risk_level=vendor['risk_level'])
        if 'finstripe__create_transfer' not in tools and not state['transactions']:
            candidates.update(transfer_history=[], prior_completed_transfers_observed=0)
        result = []
        cut_ref = (row['raw_context'].get('proposed_action') or {}).get('source_ref')
        if not cut_ref:
            cut_ref = next(iter(context.get('source_refs') or []), initial_receipt['source_ref'])
        for field, value in candidates.items():
            # Incomplete, conflicting, or explicitly invalidated native evidence
            # takes precedence over a setup-derived fallback.
            prior = obs['provenance'].get(field, [])
            if (value is None or field not in obs['facts'] or obs['facts'][field] is not None
                    or any(p.get('note') and p.get('note') != 'Unavailable at cut; absence is not a false fact.'
                           for p in prior)):
                continue
            proof = evidence(cut_ref, cut, field, value, initial_receipt['subject'], status='derived',
                             kind='deterministic_reconstruction',
                             derived_from=[initial_receipt['source_ref'], cut_ref],
                             note='Bound setup value carried forward through a complete archived prefix.')
            obs['facts'][field] = value
            obs['provenance'][field] = [proof]
            row['evidence_status'][field] = 'derived'
            result.append(proof)
        return result
