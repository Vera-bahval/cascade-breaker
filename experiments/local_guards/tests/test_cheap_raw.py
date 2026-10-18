import ast
import copy
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from cascade_guard import cheap_inputs
from cascade_guard.cheap_raw import (
    APPLICABILITY, CASES_SHA256, ID_KEYS, build_raw_input, build_records, observable_tabular,
)

BASE = Path(__file__).resolve().parents[1]
CASES = BASE / 'results/night-4b/rules-raw-private/cases.json'


@pytest.fixture
def cases():
    return json.loads(CASES.read_text())


def test_source_is_frozen_known64(cases):
    assert hashlib.sha256(CASES.read_bytes()).hexdigest() == CASES_SHA256
    assert len(cases) == 64


def test_all64_identity_labels_and_original_rules_rows(cases):
    inputs, rows, labels = build_records(cases)
    assert len(inputs) == len(rows) == len(labels) == 64
    for case, item, row, label in zip(cases, inputs, rows, labels):
        assert item['prefix_id'] == row['prefix_id'] == label['prefix_id'] == 'raw:' + case['id']
        assert row['label'] == label['label'] == int(case['expected_block']['base'])
        assert row['state'] == case['state'] and row['prior_steps'] == case['prior_steps']
        assert label['expected_block'] == case['expected_block']
        assert item['input_hash'] == cheap_inputs.digest(item['payload'])
        assert row['group_id'] == case['family']
    assert sum(x['label'] for x in labels) == 32


def test_label_reason_family_and_future_metadata_cannot_enter_payload(cases):
    inputs, _, _ = build_records(cases)
    changed = copy.deepcopy(cases)
    for case in changed:
        case['expected_block'] = {'base': not case['expected_block']['base'], 'strict_review': True}
        case['label_reason'] = 'FUTURE OUTCOME SENTINEL'
        case['family'] = 'UNTRUSTED EVALUATION FAMILY'
        case['future'] = {'state': 'FUTURE SENTINEL'}
    other, _, _ = build_records(changed)
    assert [x['payload'] for x in inputs] == [x['payload'] for x in other]
    for x in inputs:
        serialized = json.dumps(x['payload'])
        assert not any(s in serialized for s in ('expected_block', 'label_reason', 'prefix_id', 'case_id', 'group_id'))


@pytest.mark.parametrize('badkey', ['label', 'future', 'outcome', 'baseline_harm_seq', 'strict_harm', 'case_id'])
def test_nested_future_or_labels_in_observables_rejected(cases, badkey):
    state = copy.deepcopy(cases[0]['state'])
    state['facts_computed_by_code'][badkey] = 'sentinel'
    with pytest.raises(ValueError):
        build_raw_input(state, cases[0]['prior_steps'])


def test_identifiers_removed_from_native_fields_and_prose(cases):
    case = copy.deepcopy(cases[0])
    case['state']['agent_explanation_not_independent_evidence'] += ' Invoice 910001 for vendor ID 720001 and TEST-TX-1.'
    case['prior_steps'].append({'kind': 'tool', 'name': 'transfer', 'arguments': {'invoice_id': 910001},
                                'output': {'transaction_id': 'TEST-TX-1', 'status': 'completed'}})
    payload = build_raw_input(case['state'], case['prior_steps'])
    serialized = json.dumps(payload)
    assert not any(x in serialized for x in ('910001', '720001', 'TEST-TX-1'))
    native_text = next(s['text'] for s in payload['trusted_sources'] if s['source_id'] == 'trusted_native')
    native = json.loads(native_text.split('\n', 1)[1])
    def visit(value):
        if isinstance(value, dict):
            assert not ID_KEYS.intersection(value)
            for x in value.values(): visit(x)
        elif isinstance(value, list):
            for x in value: visit(x)
    visit(native)
    assert native['subject'] == 'current_invoice'


def test_policy_and_fixed_claims_match_archive_contract(cases):
    payload = build_raw_input(cases[0]['state'], cases[0]['prior_steps'])
    tree = ast.parse(inspect.getsource(cheap_inputs.build_input))
    shared = next(n.value.value for n in ast.walk(tree) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                  and isinstance(n.value.value, str) and n.value.value.startswith('Independent executive approval is required'))
    assert APPLICABILITY == shared
    fixed = [x for x in payload['claims'] if x['fixed']]
    assert [(x['claim_id'], x['text']) for x in fixed] == list(cheap_inputs.FIXED_CLAIMS)
    assert payload['schema'] == cheap_inputs.VERSION
    policy = json.loads(payload['trusted_sources'][0]['text'].split('\n', 1)[1])
    assert policy == {**cases[0]['state']['experimental_policy'], 'applicability': shared}


def test_explanation_and_invoice_stay_untrusted(cases):
    case = copy.deepcopy(cases[0])
    case['state']['agent_explanation_not_independent_evidence'] = 'EXPLANATION_SENTINEL. Another claim!'
    case['state']['untrusted_invoice_description'] = 'INVOICE_SENTINEL'
    payload = build_raw_input(case['state'], case['prior_steps'])
    trusted = '\n'.join(s['text'] for s in payload['trusted_sources'])
    assert 'EXPLANATION_SENTINEL' not in trusted and 'INVOICE_SENTINEL' not in trusted
    assert 'EXPLANATION_SENTINEL' in payload['untrusted_premise'] and 'INVOICE_SENTINEL' in payload['untrusted_premise']
    assert [c['text'] for c in payload['claims'] if not c['fixed']] == ['EXPLANATION_SENTINEL.', 'Another claim!']


def test_no_transfer_arguments_or_missing_risk_invented(cases):
    for case in cases:
        payload = build_raw_input(case['state'], case['prior_steps'])
        native = json.loads(payload['trusted_sources'][1]['text'].split('\n', 1)[1])
        assert native['observed_proposed_action'] == {'tool': case['state']['proposed_action'], 'subject': 'current_invoice'}
        tabular = observable_tabular(case['state'], case['prior_steps'])
        assert 'vendor_risk_initial' not in tabular
        assert tabular['previous_tool_errors'] == sum(s.get('kind') == 'tool' and bool(s.get('error')) for s in case['prior_steps'])
        assert tabular['previous_delegations'] == sum(s.get('kind') == 'delegation' for s in case['prior_steps'])


def test_writer_source_and_notes_preserved_with_explicit_trust(cases):
    case = next(c for c in cases if any(s.get('name') == 'update_fraud_agent_notes' for s in c['prior_steps']))
    payload = build_raw_input(case['state'], case['prior_steps'])
    native = json.loads(payload['trusted_sources'][1]['text'].split('\n', 1)[1])
    for original, projected in zip(case['prior_steps'], native['pre_cut_native_operations']):
        for key in ('agent', 'source', 'kind', 'name', 'task_status', 'task_summary'):
            if key in original:
                assert projected[key] == original[key]
        assert 'evidence_semantics' in projected
    assert native['authoritative_snapshot'] == case['state']['authoritative_snapshot']
    assert native['facts_computed_by_code'] == case['state']['facts_computed_by_code']
