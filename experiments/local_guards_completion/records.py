"""Prepare common records using factual pre-cut policy/tool supplements."""
import gzip
import hashlib
import json
from pathlib import Path
from .rules import prepare
from .source_links import restore_links, source_manifest as links_manifest

HERE = Path(__file__).resolve().parent
EXP = HERE.parent


def rows(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt') as f:
        yield from map(json.loads, f)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def policy_path():
    return HERE/'captured-policies.json.gz'


def tool_names(value):
    if isinstance(value, dict):
        if isinstance(value.get('name'), str):
            yield value['name']
        for v in value.values():
            yield from tool_names(v)
    elif isinstance(value, list):
        for v in value:
            yield from tool_names(v)


def supplements():
    annotation = EXP/'local_guards_archive_annotation'
    manifest = json.loads((annotation/'custodian_manifest.json').read_text())['cases']
    with gzip.open(policy_path(), 'rt') as stream:
        source = json.load(stream)
    availability = {}
    for folder in ('supplementary_evidence', 'supplementary_evidence_v2'):
        root = annotation/folder
        for item in json.loads((root/'availability.json').read_text())['cases']:
            path = root/'blind_inputs'/(item['annotation_id']+'.json')
            assert sha(path) == item['blind_sha256']
            value = json.loads(path.read_text())
            if value.get('availability') == 'captured_payments_tool_request':
                tools = value['payments_precut_llm_tool_requests'][-1]
            elif value.get('status') == 'payments_request_tools_captured':
                assert value['latest_request_within_model_interval']
                tools = value['payments_requests_before_p4'][-1]['tools']
            else:
                continue
            availability[item['annotation_id']] = ('taxcalc__calculate_tax' in set(tool_names(tools)), str(path))
    result = {}
    for case in manifest:
        pid = case['prefix_id']; evidence = {}
        if case['annotation_id'] in availability:
            available, ref = availability[case['annotation_id']]
            evidence['tax_available'] = dict(value=available, event_seq=0, source_ref=ref,
                coordinate_kind='source_bound_pre_cut_configuration_not_a_native_event')
        policy = source['cases'].get(pid, {}).get('payments')
        if policy:
            text = source['policies'][policy['policy_sha256']]['text']
            evidence['tax_clause_required'] = dict(value='If tax calculation tools are available' in text,
                event_seq=0, source_ref='captured-policy/'+policy['policy_sha256'],
                coordinate_kind='first_system_policy_applies_at_session_start_not_a_native_event')
        result[pid] = evidence
    assert len(result) == 542 and len(availability) == 87
    return result


def attach(row, supplement):
    row = restore_links(row)
    row['completion_evidence'] = supplement.get(row['prefix_id'], {})
    return row


def run():
    from .ml import canonical
    identities = {r['prefix_id']:r for r in json.loads((EXP/'local_guards_archive_annotation/custodian_manifest.json').read_text())['cases']}
    path = HERE/'records.jsonl.gz'
    if path.exists():
        raise FileExistsError(path)
    supplement = supplements(); count = 0; observed_availability = 0
    sources = EXP/'local_guards_adapter_repair/inputs/p4-inputs.jsonl.gz'
    meta = {r['prefix_id']:r for r in rows(EXP/'local_guards_archive_comparison/data/split-metadata.jsonl.gz') if r['prefix_id'] in identities}
    with gzip.open(path, 'wt') as out:
        for row in rows(sources):
            if row['mode'] != 'common':
                continue
            pid = row['prefix_id']; native = row['adapters']['native']['payload']
            record = dict(prefix_id=pid, episode_id=meta[pid]['episode_id'], group_id=meta[pid]['group_id'],
                native=native, observation=prepare(attach(row, supplement)),
                input_sha256=row.get('input_sha256'), source_input=identities[pid]['annotation_id'])
            observed_availability += any(e['field']=='tax_available' and e['origin']!='assumed' for e in record['observation']['evidence'])
            out.write(canonical(record)+'\n'); count += 1
    assert count == 542
    manifest = dict(n=count, records_sha256=sha(path), source_sha256=sha(sources),
        policy_sha256=sha(policy_path()), captured_tool_lists=87, observed_availability=observed_availability,
        configuration_coordinate_note='event_seq=0 marks source-bound pre-cut/static configuration, not an execution event',
        restored_links=links_manifest(),
        code_sha256={name:sha(HERE/name) for name in ('records.py','prepare.py','rules.py')})
    (HERE/'records-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('PREPARED_RECORDS',count)


if __name__ == '__main__':
    run()
