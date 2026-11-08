"""Build P0–P3 replay inputs and blind source-backed rating cases."""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import gzip
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
EXPERIMENTS = HERE.parent
ROOT = EXPERIMENTS.parent
STRICT = EXPERIMENTS / 'local_guards_v4_followup/data/strict'
ARCHIVE = EXPERIMENTS / 'local_guards_archive_comparison/data'
EARLY = ('P0', 'P1', 'P2', 'P3')
REACH = ('observed_attempt', 'no_observed_attempt')
TRANSFER = 'finstripe__create_transfer'
PRE_MUTATION = {'update_invoice_status', 'update_vendor_status', 'update_vendor_risk',
                'flag_invoice_for_review', 'process_payment'}
sys.path.insert(0, str(ARCHIVE.parent))
from collector import canonical, file_hash, parse_result  # noqa: E402


def require(check, message):
    if not check:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read_rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        yield from map(json.loads, stream)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                    encoding='utf-8')


@contextmanager
def writer(path):
    with path.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as stream:
        yield lambda row: stream.write((canonical(row) + '\n').encode())


def model_calls(value):
    if isinstance(value, str) and value.lstrip().startswith('{'):
        value = parse_result(value)
    return value.get('tool_calls') or [] if isinstance(value, dict) else []


def proposes_transfer(value):
    return any(isinstance(call, dict) and call.get('name') == TRANSFER
               for call in model_calls(value))


def native_reach(rows):
    pending = []
    model_open = False
    complete = bool(rows and rows[0]['hook_kind'] == 'before_model')
    terminal = False
    proposal = False
    for line, row in enumerate(rows, 1):
        kind, tool = row['hook_kind'], row.get('tool_name')
        if kind in {'before_tool', 'after_tool'} and tool == TRANSFER:
            return 'observed_attempt', {'source_event_index': line, 'kind': kind, 'event_seq': line * 2}
        if kind == 'after_model':
            proposal |= proposes_transfer(row.get('model_output'))
            complete &= model_open
            model_open = False
        if kind == 'before_model':
            complete &= not model_open
            model_open = True
        if kind == 'before_tool':
            complete &= not model_open
            if tool == 'complete_task':
                terminal = not pending and line == len(rows)
            else:
                pending.append((tool, row.get('tool_arguments') or {}))
        elif kind == 'after_tool' and tool != 'complete_task':
            match = bool(pending and pending[-1] == (tool, row.get('tool_arguments') or {}))
            complete &= match
            if match:
                pending.pop()
    if proposal:
        return 'unknown_proposal_only', None
    return (('no_observed_attempt', None) if complete and terminal
            else ('unknown_incomplete', None))


def legacy_reach(steps):
    proposal = False
    terminal = False
    complete = bool(steps and steps[0].get('point') == 'P0.input')
    for index, step in enumerate(steps):
        kind, seq = step['kind'], step['seq']
        complete &= index == seq
        if kind == 'tool':
            if step.get('name') == TRANSFER:
                return 'observed_attempt', {'source_event_index': seq, 'kind': 'tool', 'event_seq': 2 * seq}
            terminal |= step.get('agent') == 'orchestrator_agent' and step.get('name') == 'complete_task'
        elif kind == 'guard_context' and step.get('point') == 'P4.' + TRANSFER:
            require((step.get('payload') or {}).get('tool') == TRANSFER, 'legacy P4 tool mismatch')
            return 'observed_attempt', {'source_event_index': seq, 'kind': 'guard_context', 'event_seq': 2 * seq + 1}
        elif kind == 'llm' and not str(step.get('agent', '')).startswith('verifier'):
            proposal |= proposes_transfer(step.get('output'))
    if proposal:
        return 'unknown_proposal_only', None
    return ('no_observed_attempt', None) if complete and terminal else ('unknown_incomplete', None)


def raw_episodes(episodes, raw_root):
    manifest = {m['registry_source']: m for m in read_json(ARCHIVE / 'collector-manifest.json')['sources']}
    by_source = defaultdict(list)
    for ep in episodes:
        by_source[ep['source']].append(ep)
    for source, members in sorted(by_source.items()):
        receipt = manifest[source]
        locator = receipt['path']
        sha = receipt['sha256']
        require(all(ep['source_sha256'] == sha for ep in members), 'source binding mismatch: ' + source)
        if source.endswith('.tar.gz'):
            path = Path(locator)
            if not path.is_file():
                path = raw_root / 'experiments/control-placement' / (
                    'code/runs' if '/code/runs/' in source else 'four-model-comparison/artifacts'
                ) / path.name
            require(file_hash(path) == sha, 'source hash mismatch: ' + source)
            with tarfile.open(path, 'r:gz') as tar:
                for ep in sorted(members, key=lambda x: x['member']):
                    member = ep['member']
                    if not member.endswith('.jsonl'):
                        member += 'hooks.jsonl'
                    payload = tar.extractfile(member).read()
                    raw = [json.loads(line) for line in payload.splitlines() if line.strip()]
                    require(digest(raw) == ep['raw_hash'] and len(raw) == ep['raw_events'],
                            'hook member hash or count mismatch: ' + ep['episode_id'])
                    yield ep, raw, None, member
        else:
            if locator.startswith('git-blob:'):
                blob = locator.split(':', 2)[1]
                payload = subprocess.check_output(['git', 'cat-file', 'blob', blob], cwd=ROOT)
            else:
                path = Path(locator)
                if not path.is_file() and Path(source).name == 'shadow-main.jsonl.gz':
                    path = ROOT.parents[1] / 'experiments/local_guards/data/archive/shadow-main.jsonl.gz'
                payload = path.read_bytes()
            require(hashlib.sha256(payload).hexdigest() == sha, 'source hash mismatch: ' + source)
            require(source.endswith('.jsonl.gz'), 'unhandled source type: ' + source)
            ids = {ep['member']: ep for ep in members}
            found = set()
            for line, raw_run in enumerate(map(json.loads, gzip.decompress(payload).splitlines()), 1):
                run_id = raw_run['run_id']
                if run_id not in ids:
                    continue
                ep = ids[run_id]
                steps = sorted(raw_run['steps'], key=lambda x: x['seq'])
                require(digest(raw_run['steps']) == ep['raw_hash'], 'legacy journal hash mismatch: ' + run_id)
                found.add(run_id)
                initial = {k: raw_run.get(k) for k in ('db_initial', 'invoice', 'namespace', 'invoice_id', 'vendor_id')}
                yield ep, steps, initial, f'line:{line}'
            require(found == ids.keys(), 'legacy member missing: ' + source)


def observed_fields(obj, names):
    return {name: obj[name] for name in names if obj.get(name) is not None}


def native_events(raw):
    keep = ('hook_kind', 'tool_name', 'tool_source', 'tool_arguments', 'tool_result', 'user_message',
            'request_tools', 'request_tool_schemas', 'agent_name', 'session_id', 'workflow_id',
            'parent_workflow_id', 'call_id', 'tool_call_id', 'timestamp')
    events = []
    for line, row in enumerate(raw, 1):
        event = observed_fields(row, keep)
        event.update(event_seq=line * 2, source_event_index=line)
        events.append(event)
    return events


def legacy_events(raw):
    events = []
    for step in raw:
        seq, kind = step['seq'], step['kind']
        if kind == 'llm' and not str(step.get('agent', '')).startswith('verifier'):
            event = dict(hook_kind='before_model', event_seq=seq * 2,
                         user_message='\n\n'.join(m['content'] for m in step.get('messages', [])
                                                  if m.get('role') == 'user' and isinstance(m.get('content'), str)))
            if 'tools' in step:
                event['request_tools'] = step['tools']
        elif kind == 'tool':
            event = dict(hook_kind='after_tool', event_seq=seq * 2, tool_name=step['name'],
                         tool_arguments=step.get('arguments') or {}, tool_source=step.get('source'),
                         tool_result={'error': step['error']} if step.get('error') else step.get('output'))
        elif kind == 'guard_context' and step['point'].split('.')[0] in EARLY:
            payload = step.get('payload') or {}
            point = step['point'].split('.')[0]
            event = dict(hook_kind={'P0': 'admission', 'P2': 'after_delegation'}.get(point, 'before_tool'),
                         event_seq=seq * 2 + 1, point=point)
            if point in {'P0', 'P2'}:
                event['boundary_payload'] = payload
            else:
                event.update(tool_name=payload.get('tool'), tool_arguments=payload.get('arguments') or {})
        else:
            continue
        event.update(source_event_index=seq, source_event_kind=kind, agent_name=step.get('agent'))
        event.update(observed_fields(step, ('call_id', 'tool_call_id', 'session_id', 'workflow_id', 'parent_workflow_id')))
        events.append(event)
    return events


def index_anchors(episode_id, events, legacy):
    anchors = {}
    prior_returns = {}
    for event in events:
        kind = event['hook_kind']
        tool = event.get('tool_name')
        seq = event['event_seq']
        source_kind = event.get('source_event_kind', kind)
        if legacy:
            if kind == 'after_tool' and tool.startswith('delegate_to_'):
                prior_returns[tool] = event
            cp = event.get('point')
            if cp is None:
                continue
            if cp == 'P2':
                child = event['boundary_payload'].get('agent') or event.get('agent_name')
                tool = 'delegate_to_' + str(child).removesuffix('_agent')
                returned = prior_returns.get(tool)
                if returned is not None:
                    result = parse_result(returned.get('tool_result'))
                    if (returned['source_event_index'] + 1 != event['source_event_index']
                            or not isinstance(result, dict)
                            or any(event['boundary_payload'].get(k) != result.get(k)
                                   for k in ('task_status', 'task_summary'))):
                        returned = None
                anchor = dict(event=event, return_event=returned)
            else:
                anchor = dict(event=event)
            strict_base_seq = seq
            common = seq
        else:
            anchor = dict(event=event)
            if kind == 'before_model' and seq == 2:
                cp = 'P0'
                common = seq - 1
                strict_base_seq = 0
            elif kind == 'before_tool' and tool and tool != TRANSFER:
                cp = 'P3' if tool in PRE_MUTATION else 'P1'
                common = strict_base_seq = seq
            elif kind == 'after_tool' and tool and tool.startswith('delegate_to_'):
                cp = 'P2'
                anchor['return_event'] = event
                common = strict_base_seq = seq + 1
            else:
                continue
        pid = hashlib.sha256(f'{episode_id}/{strict_base_seq}/{tool}'.encode()).hexdigest()[:28]
        require(pid not in anchors, 'duplicate source anchor ' + pid)
        anchors[pid] = dict(anchor, checkpoint=cp, tool=tool, event_seq=common,
                            strict_event_seq=strict_base_seq + 2, kind=source_kind)
    return anchors


def select(rows, *, seed, cap):
    rng = random.Random(seed)
    pools = defaultdict(dict)
    for row in sorted(rows, key=lambda r: r['prefix_id']):
        cell = row['checkpoint'], row['reach_status']
        if cell[1] not in REACH:
            continue
        # Reservoir choice within each episode/cell, independent of policy evidence.
        pools[cell].setdefault(row['episode_id'], []).append(row)
    choices = {cell: {eid: (rng.random(), rng.choice(actions))
                      for eid, actions in sorted(by_episode.items())}
               for cell, by_episode in sorted(pools.items())}
    chosen, used = [], set()
    group_total = Counter()
    group_in_cell = defaultdict(Counter)
    for _ in range(cap):
        for cell in sorted(choices, key=lambda c: (len(choices[c]), c)):
            available = [pair for eid, pair in choices[cell].items() if eid not in used]
            if not available:
                continue

            def rank(pair):
                priority, row = pair
                group = row['base_group_id']
                return group_in_cell[cell][group], group_total[group], priority

            _, row = min(available, key=rank)
            chosen.append(row)
            used.add(row['episode_id'])
            group = row['base_group_id']
            group_in_cell[cell][group] += 1
            group_total[group] += 1
    rng.shuffle(chosen)
    return chosen


def pre_cut_events(row, events):
    return [e for e in events if e['event_seq'] < row['event_seq']]


def material(value, *, limit=1000):
    if isinstance(value, str):
        # Strip source locators and synthetic run identifiers, including fixture
        # suffixes embedded in invoice numbers. Keep ordinary invoice references.
        value = re.sub(r'(?:[/\w.-]+/)?[\w.-]+\.(?:hooks\.jsonl|jsonl\.gz|tar\.gz|jsonl)\b', '[archive locator omitted]', value)
        value = re.sub(r'\b(?:cle|att|cha|inj)-[\w.-]+-[a-f0-9]{6}\b', '[run identifier omitted]', value)
        return value if len(value) <= limit else value[:limit] + ' [continued in full case]'
    if isinstance(value, list):
        return [material(x, limit=limit) for x in value]
    if isinstance(value, dict):
        return {k: material(v, limit=limit) for k, v in value.items()
                if k not in ('source_ref', 'source_refs', 'filename', 'raw_hash', 'source_intent',
                             'source_requires_stop', 'expected_pay', 'truth')}
    return value


def blind_event(event, *, limit=1000):
    visible = observed_fields(event, ('event_seq', 'hook_kind', 'tool_name', 'tool_source', 'agent_name',
                                      'tool_arguments', 'tool_result', 'boundary_payload', 'user_message',
                                      'request_tools'))
    if isinstance(visible.get('tool_result'), str):
        parsed = parse_result(visible['tool_result'])
        if parsed is not None:
            visible['tool_result'] = parsed
    for key in ('session_id', 'workflow_id', 'parent_workflow_id', 'call_id', 'tool_call_id'):
        if event.get(key):
            visible[key] = digest(str(event[key]))[:12]
    return material(visible, limit=limit)


def blind_case(blind_id, row, raw, *, full=False):
    anchor = row['anchor']
    pre = pre_cut_events(row, raw['events'])
    o = row['observation']
    context = observed_fields(o['context'], ('origin_portal', 'technical_actor', 'delegated_actor',
                                             'delegation_succeeded', 'invoice_id', 'vendor_id',
                                             'current_vendor_id', 'attachment_file_ids', 'payment_reference'))
    sources = {}
    for name, proofs in o['provenance'].items():
        if o['facts'].get(name) is not None and proofs:
            sources[name] = [[p.get('source'), p.get('operation')] for p in proofs]
    calls = [e for e in pre if e['hook_kind'] == 'after_tool' and e != anchor.get('return_event')]
    prompts = list({e['user_message']: e for e in [*pre, anchor['event']]
                    if e.get('user_message')}.values())
    description = raw['initial_fixture']
    if full:
        timeline = [blind_event(e, limit=100_000) for e in pre]
    else:
        # Action-local native reads, state changes and delegated reports are
        # enough for the overview. The detailed packet includes the full
        # normalized source prefix, with verifier records omitted.
        relevant = {'get_invoice_details', 'get_invoice_for_payment', 'get_vendor_details',
                    'get_vendor_risk_profile', 'get_vendor_invoices', 'update_invoice_status',
                    'update_vendor_status', 'update_vendor_risk', 'flag_invoice_for_review',
                    'process_payment', TRANSFER, 'findrive__get_file', 'get_invoice_attachments'}
        timeline = []
        seen = set()
        for e in reversed(calls):
            tool = e.get('tool_name', '')
            if tool in seen or (tool not in relevant and not tool.startswith('delegate_to_')):
                continue
            item = blind_event(e, limit=170)
            if len(canonical(item)) > 450:
                if isinstance(item.get('tool_result'), dict):
                    keep = ('invoice_id', 'vendor_id', 'amount', 'status', 'task_status', 'task_summary',
                            'recommended_action', 'risk_level', 'trust_level', 'error',
                            'transfer_id', 'bank_account_number', 'vendor_status', 'updated')
                    item['tool_result'] = observed_fields(item['tool_result'], keep)
                else:
                    item['tool_result'] = str(item.get('tool_result', ''))[:170]
            args = item.get('tool_arguments', {})
            keep_args = ('invoice_id', 'vendor_id', 'status', 'amount', 'currency',
                         'payment_reference', 'recommended_action', 'attachment_file_ids')
            item['tool_arguments'] = observed_fields(args, keep_args)
            timeline.append(item)
            seen.add(tool)
            if len(timeline) == 3:
                break
        timeline.reverse()
        prompts = prompts[:1] + prompts[-1:] if len(prompts) > 1 else prompts
    if not full:
        sources = {name: list(dict.fromkeys(p[1] for p in proofs if p[1]))
                   for name, proofs in sources.items()}
        sources = {k: v for k, v in sources.items() if k in {
            'session_valid', 'invoice_status', 'vendor_status', 'binding_hold',
            'tool_scope_matches', 'delegation_subject_matches', 'payment_reference_matches_transfer',
        }}
    bound_return = anchor.get('return_event')
    if bound_return == anchor['event']:
        bound_return = None
    case = dict(case_id=blind_id, checkpoint=row['checkpoint'], subject_tool=anchor['tool'],
                action=blind_event(anchor['event'], limit=100_000 if full else 1100),
                bound_return=blind_event(bound_return, limit=100_000 if full else 650) if bound_return else None,
                initial_fixture=material(description, limit=100_000 if full else 500),
                reconstructed_context=context,
                reconstructed_facts={k: v for k, v in o['facts'].items() if full or v is not None},
                reconstruction_evidence=sources, prior_tool_evidence=timeline,
                task_texts=[material(e['user_message'], limit=100_000 if full else 330) for e in prompts],
                raw_session_id_recorded=bool(anchor['event'].get('session_id')),
                raw_workflow_id_recorded=bool(anchor['event'].get('workflow_id')),
                source_revision_attested=raw['source_revision_attested'])
    return material(case, limit=100_000)


def build(output, raw_root, *, seed=17, cap=16):
    output.mkdir(parents=True, exist_ok=False)
    manifest = read_json(STRICT / 'manifest.json')
    strict_names = ('episodes.jsonl.gz', 'observations.jsonl.gz', 'metadata.jsonl.gz')
    source_hashes = {str((STRICT / n).relative_to(ROOT)): manifest['output_hashes'][n] for n in strict_names}
    archive_hashes = read_json(ARCHIVE / 'artifact-hashes.json')
    for name in ('split-episodes.jsonl.gz', 'split-manifest.json', 'collector-manifest.json'):
        source_hashes[str((ARCHIVE / name).relative_to(ROOT))] = archive_hashes['data/' + name]
    for path, sha in source_hashes.items():
        require(file_hash(ROOT / path) == sha, 'input digest mismatch: ' + path)
    groups = set(read_json(ARCHIVE / 'split-manifest.json')['representative_groups'])
    episodes = [e for e in read_rows(ARCHIVE / 'split-episodes.jsonl.gz') if e['split'] == 'REPRESENTATIVE']
    strict_eps = {e['episode_id']: e for e in read_rows(STRICT / 'episodes.jsonl.gz')}
    cohort = {}
    for e in episodes:
        sid = e['episode_id']
        require(e['group_id'] in groups and sid not in cohort, 'invalid cohort membership ' + sid)
        require(all(e[k] == strict_eps[sid][k] for k in ('source', 'member', 'raw_hash')),
                'strict episode/source binding differs for ' + sid)
        cohort[sid] = e
    require(groups == {e['group_id'] for e in cohort.values()}, 'uncovered representative group')
    all_anchors, raw_by_episode, reach_counts = {}, {}, Counter()
    for ep, journal, initial, member in raw_episodes(episodes, raw_root):
        eid = ep['episode_id']
        legacy = initial is not None
        normalized = legacy_events(journal) if legacy else native_events(journal)
        reach_status, reach_evidence = legacy_reach(journal) if legacy else native_reach(journal)
        reach_counts[reach_status] += 1
        all_anchors.update(index_anchors(eid, normalized, legacy))
        # The split's scenario text is the recorded source submission in these
        # tar fixtures. For legacy use only the captured initial DB and invoice.
        scenario = initial['invoice'] if legacy else ep['scenario']
        fixture = observed_fields(scenario or {}, ('amount', 'desc', 'description', 'due_date_offset_days'))
        if legacy:
            db = initial['db_initial'] or {}
            fixture['invoice'] = observed_fields(db.get('invoice') or {}, ('id', 'vendor_id', 'amount', 'status', 'description'))
            fixture['vendor'] = observed_fields(db.get('vendor') or {}, ('id', 'status', 'trust_level', 'risk_level', 'industry'))
            fixture['initial_transaction_count'] = len(db['transactions']) if isinstance(db.get('transactions'), list) else None
        raw_by_episode[eid] = dict(episode_id=eid, base_group_id=ep['group_id'], events=normalized,
                                   initial_fixture=fixture, reach_status=reach_status,
                                   reach_evidence=reach_evidence, raw_member=member, source=ep['source'],
                                   raw_hash=ep['raw_hash'], source_sha256=ep['source_sha256'],
                                   source_revision_attested=bool(ep.get('verified_source_version')),
                                   source_revision=ep.get('verified_source_version'),
                                   raw_format='legacy_steps' if legacy else 'native_hooks')
    require(raw_by_episode.keys() == cohort.keys(), 'raw sources do not cover the representative cohort')
    meta = {m['prefix_id']: m for m in read_rows(STRICT / 'metadata.jsonl.gz')
            if m['episode_id'] in cohort and m['checkpoint'] in EARLY}
    prepared = []
    with writer(output / 'early-inputs.jsonl.gz') as emit:
        for wrapped in read_rows(STRICT / 'observations.jsonl.gz'):
            pid = wrapped['prefix_id']
            if pid not in meta:
                continue
            m = meta.pop(pid)
            eid = m['episode_id']
            raw = raw_by_episode[eid]
            o = wrapped['observation']
            require(not wrapped.get('assumptions'), 'strict row carries assumptions: ' + pid)
            anchor = all_anchors.get(pid)
            require(anchor is not None, 'strict prefix lacks verified source anchor: ' + str((pid, eid, o['checkpoint'], o['event_seq'], o['proposal'].get('tool'))))
            require((anchor['checkpoint'], anchor['strict_event_seq'], anchor['tool']) ==
                    (o['checkpoint'], o['event_seq'], o['proposal'].get('tool')), 'strict cut mismatch: ' + pid)
            require(all(p['event_seq'] < o['event_seq'] for entries in o['provenance'].values() for p in entries),
                    'strict proof crosses its cut: ' + pid)
            row = dict(wrapped, episode_id=eid, base_group_id=raw['base_group_id'],
                       checkpoint=anchor['checkpoint'], event_seq=anchor['event_seq'],
                       strict_event_seq=anchor['strict_event_seq'], reach_status=raw['reach_status'],
                       anchor=anchor, raw_format=raw['raw_format'])
            emit(row)
            prepared.append(row)
        require(not meta, 'unmatched strict metadata')
    chosen = select(prepared, seed=seed, cap=cap)
    blind_dir = output / 'blind'
    full_dir = blind_dir / 'cases'
    full_dir.mkdir(parents=True, exist_ok=True)
    sample = []
    for i, row in enumerate(chosen, 1):
        raw = raw_by_episode[row['episode_id']]
        bid = f'E{i:03d}'
        write_json(full_dir / (bid + '.json'), blind_case(bid, row, raw, full=True))
        sample.append(blind_case(bid, row, raw))
    for offset in range(0, len(sample), 16):
        target = blind_dir / f'batch-{offset // 16 + 1:02d}.jsonl'
        target.write_text(''.join(canonical(x) + '\n' for x in sample[offset:offset + 16]), encoding='utf-8')
    private = [dict(case_id=case['case_id'], **observed_fields(r, ('prefix_id', 'episode_id', 'base_group_id',
                      'event_seq', 'strict_event_seq', 'checkpoint', 'reach_status')))
               for case, r in zip(sample, chosen, strict=True)]
    write_json(output / 'id-map.private.json', private)
    write_json(blind_dir / 'index.json', [{'case_id': r['case_id'], 'checkpoint': r['checkpoint']} for r in sample])
    summary = dict(
        seed=seed, cap=cap, cohort_episodes=len(cohort), reach_episodes=reach_counts,
        input_rows=len(prepared), sample_rows=len(chosen), sample_groups=len({r['base_group_id'] for r in chosen}),
        sources=source_hashes, strata=[
            dict(checkpoint=p, reach_status=s,
                 candidate_rows=sum((r['checkpoint'], r['reach_status']) == (p, s) for r in prepared),
                 candidate_episodes=len({r['episode_id'] for r in prepared if (r['checkpoint'], r['reach_status']) == (p, s)}),
                 sample_rows=sum((r['checkpoint'], r['reach_status']) == (p, s) for r in chosen))
            for p in EARLY for s in (*REACH, 'unknown_proposal_only', 'unknown_incomplete')
        ])
    with writer(output / 'early-events.jsonl.gz') as emit:
        for eid in sorted(raw_by_episode):
            emit(raw_by_episode[eid])
    summary['output_hashes'] = {str(p.relative_to(output)): file_hash(p)
                                for p in sorted(output.rglob('*')) if p.is_file()}
    write_json(output / 'selection-manifest.private.json', summary)
    print(canonical({k: v for k, v in summary.items() if k != 'output_hashes'}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--raw-root', type=Path, default=ROOT.parent / 'finbot-four-model-report')
    args = parser.parse_args()
    build(args.out, args.raw_root)


if __name__ == '__main__':
    main()
