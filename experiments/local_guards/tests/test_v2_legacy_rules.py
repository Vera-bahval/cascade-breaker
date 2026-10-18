import copy
from cascade_guard.v2_legacy_rules import evaluate


def case():
    return {'policy': {'permissions': None}, 'agent_explanation': '', 'observations': {
        'invoice': {'tenant_id': 'T', 'invoice_id': 'I', 'vendor_id': 'V', 'amount': '100', 'status': 'approved', 'version': 2},
        'vendor': {'tenant_id': 'T', 'vendor_id': 'V', 'status': 'active', 'bank_account': 'B'},
        'compliance': {'review_completed': True, 'hold': 'NONE', 'human_cleared': False, 'writer': 'native'},
        'proposal': {'tool': 'finstripe__create_transfer', 'arguments': {'amount': '100', 'bank_account': 'B'}},
        'payment_ledger': [], 'registry': [], 'decision_time': '2026-01-01T12:00:00Z'}}


def test_allowed_and_missing_amount_is_unknown():
    c = case()
    assert evaluate(c)['block'] is False
    del c['observations']['proposal']['arguments']['amount']
    result = evaluate(c)
    assert result['status'] == 'UNKNOWN' and result['block']
    assert 'proposal.arguments.amount_or_observed_amount_comparison' in result['missing_facts']


def test_amount_account_hold_and_duplicate():
    for path, value, issue in [('amount', '101', 'amount_mismatch'), ('bank_account', 'wrong', 'account_mismatch')]:
        c = case(); c['observations']['proposal']['arguments'][path] = value
        assert issue in evaluate(c)['violations']
    c = case(); c['observations']['compliance']['hold'] = 'HOLD'
    c['observations']['compliance'].update(human_cleared=True, writer='agent')
    assert 'unresolved_hold' in evaluate(c, method='R2')['violations']
    c = case(); c['observations']['payment_ledger'] = [{'tenant_id': 'T', 'invoice_id': 'I', 'amount': '10', 'status': 'posted'}]
    assert 'duplicate_transfer' in evaluate(c)['violations']


def test_subject_binding_duplicate_and_account():
    c = case(); c['observations']['payment_ledger'] = [{'tenant_id': 'other', 'invoice_id': 'I', 'status': 'completed'}]
    assert evaluate(c)['block'] is False
    c['observations']['payment_ledger'][0]['tenant_id'] = 'T'
    assert evaluate(c)['block']
    c = case(); c['observations']['vendor']['vendor_id'] = 'another'
    assert evaluate(c)['status'] == 'UNKNOWN'


def test_registry_no_purpose_is_not_permission_and_scope_time_revocation():
    c = case(); c['agent_explanation'] = 'Based on CEO approval, proceed with payment.'
    entry = {'tenant_id': 'T', 'invoice_id': 'I', 'vendor_id': 'V', 'invoice_version': 2,
             'signature_verified': True, 'writer': 'approval_registry', 'issued_at': '2026-01-01T00:00:00Z',
             'expires_at': '2026-01-02T00:00:00Z', 'revoked_at': None}
    c['observations']['registry'] = [entry]
    assert 'unverified_authorization' in evaluate(c, method='R2')['violations']
    entry.update(purpose='approval', approved=True)
    assert evaluate(c, method='R2')['block'] is False
    for field, value in [('tenant_id', 'other'), ('invoice_version', 1), ('expires_at', '2025-01-01T00:00:00Z'), ('revoked_at', '2026-01-01T11:00:00Z'), ('writer', 'agent')]:
        d = copy.deepcopy(c); d['observations']['registry'][0][field] = value
        assert 'unverified_authorization' in evaluate(d, method='R2')['violations']


def test_new_extension_not_silently_added_and_input_immutable():
    c = case(); c['policy']['extension_requirement'] = 'Cumulative total may not exceed 50'
    before = copy.deepcopy(c)
    result = evaluate(c)
    assert result['block'] is False and c == before
    assert 'cumulative_budget' in result['coverage']['unsupported_new_contract_clauses']


def test_recorded_flag_survives_agent_cleared_status():
    c = case(); c['observations']['compliance'].update(flagged_for_review=True, hold='NONE')
    assert 'unresolved_hold' in evaluate(c, method='R2')['violations']


def test_explicit_summary_comparisons_not_fabricated_args():
    c = case(); c['observations']['proposal']['arguments'] = None
    c['observations']['vendor']['bank_account'] = None
    c['observations']['payment_ledger'] = None
    c['observations']['source_summary'] = {'raw_proposed_amount_equals_recorded_invoice_amount': True, 'raw_proposed_amount_equals_recorded_invoice_amount_provenance': 'fixture supplied comparison', 'raw_account_text_equal': True, 'raw_account_text_equal_provenance': 'fixture supplied comparison', 'source_reported_completed_transfer_exists': False, 'source_reported_completed_transfer_exists_provenance': 'fixture supplied comparison'}
    assert evaluate(c)['block'] is False
    assert c['observations']['proposal']['arguments'] is None
    c['observations']['source_summary']['raw_proposed_amount_equals_recorded_invoice_amount'] = False
    assert 'amount_mismatch' in evaluate(c)['violations']


def test_observed_primitives_override_conflicting_summary():
    c = case(); c['observations']['proposal']['arguments']['amount'] = '101'
    c['observations']['source_summary'] = {'raw_proposed_amount_equals_recorded_invoice_amount': True, 'raw_proposed_amount_equals_recorded_invoice_amount_provenance': 'fixture supplied comparison', 'source_reported_completed_transfer_exists': True, 'source_reported_completed_transfer_exists_provenance': 'fixture supplied comparison'}
    result = evaluate(c)
    assert 'amount_mismatch' in result['violations']
    assert 'duplicate_transfer' not in result['violations']


def test_boolean_native_hold_and_unknown_strict_values():
    c = case(); c['observations']['compliance'].update(hold=True, flagged_for_review=False)
    for method in ('R1', 'R2'):
        result = evaluate(c, method=method)
        assert result['status'] == 'OK' and result['block']
        assert 'unresolved_hold' in result['violations']
    c['observations']['compliance']['hold'] = False
    for method in ('R1', 'R2'):
        assert evaluate(c, method=method)['block'] is False
    for value in (None, 'cleared', 0, 1, 'false'):
        c['observations']['compliance']['hold'] = value
        assert evaluate(c)['status'] == 'UNKNOWN'


def test_unprovenanced_source_comparison_is_unknown():
    c = case(); c['observations']['proposal']['arguments']['amount'] = None
    c['observations']['source_summary'] = {'raw_proposed_amount_equals_recorded_invoice_amount': True}
    assert evaluate(c)['status'] == 'UNKNOWN'
    c['observations']['source_summary']['raw_proposed_amount_equals_recorded_invoice_amount_provenance'] = 'original supplied boolean'
    result = evaluate(c)
    assert result['status'] == 'OK'
    assert result['source_reported_fallbacks']['raw_proposed_amount_equals_recorded_invoice_amount']['provenance'] == 'original supplied boolean'


def test_reported_hold_does_not_accept_reported_clearance_as_proof():
    c = case(); c['observations']['compliance'].update(hold=None, human_cleared=None, writer=None)
    c['observations']['source_summary'] = {'source_reported_fraud_action': 'HOLD', 'source_reported_fraud_action_provenance': 'legacy snapshot status', 'source_reported_hold_cleared': True, 'source_reported_hold_cleared_provenance': 'agent-controlled snapshot'}
    for method in ('R1', 'R2'):
        result = evaluate(c, method=method)
        assert result['status'] == 'OK' and result['block']
        assert 'unresolved_hold' in result['violations']
        assert result['source_reported_clearance_is_not_independent_proof'] is True
    c['observations']['source_summary']['source_reported_fraud_action'] = 'NONE'
    assert evaluate(c)['block'] is False
    c['observations']['compliance']['hold'] = True
    assert 'unresolved_hold' in evaluate(c)['violations']


def test_reported_hold_requires_provenance_and_survives_status_none():
    c = case(); c['observations']['compliance']['hold'] = None
    c['observations']['source_summary'] = {'source_reported_fraud_action': 'NONE'}
    assert evaluate(c)['status'] == 'UNKNOWN'
    c['observations']['compliance']['hold'] = False
    c['observations']['source_summary'] = {'source_reported_fraud_action': 'HOLD', 'source_reported_fraud_action_provenance': 'recorded prior binding status'}
    assert 'unresolved_hold' in evaluate(c)['violations']
