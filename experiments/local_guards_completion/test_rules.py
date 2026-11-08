import unittest

from experiments.local_guards_archive_profile.test_profile import row as archive_row
from .rules import prepare, guard
from .early_sources import attach, source_events
from unittest.mock import patch


def row():
    result = archive_row()
    result['bundle']['event_seq'] = 100
    result['bundle']['context']['session_id'] = 'payment-session'
    native = result['adapters']['native']['payload']
    native['event_seq'] = 100
    native['raw_context']['proposed_action']['tool_arguments'].update(payment_method='bank_transfer', invoice_reference='INV-1')
    native['observation']['provenance'] = {}
    fact(result, 'invoice_number', 'INV-1')
    result['completion_evidence'] = {'tax_clause_required': dict(value=False, event_seq=0, source_ref='captured-policy')}
    return result


def fact(result, key, value):
    native = result['adapters']['native']['payload']['observation']
    native['facts'][key] = value
    native['provenance'][key] = [dict(field=key, value=value, event_seq=1, source_ref='event/1', status='observed', kind='historical')]


def pair(result, tool, args, value, start=10, session='payment-session'):
    events = result['adapters']['native']['payload']['raw_context']['events']
    events.extend([dict(event_seq=start, hook_kind='before_tool', tool_name=tool, tool_arguments=args, session_id=session),
                   dict(event_seq=start + 1, hook_kind='after_tool', tool_name=tool, tool_arguments=args, tool_result=value, session_id=session)])


def tax(result, amount=500, invoice=1, start=20, value=None):
    pair(result, 'get_invoice_details', {'invoice_id': invoice}, {'invoice_id': invoice}, start - 2)
    pair(result, 'taxcalc__calculate_tax', {'amount': amount}, value if value is not None else {'amount': amount, 'tax_amount': 0, 'total_amount': amount}, start)


class RulesTests(unittest.TestCase):
    def decide(self, result, **kwargs):
        return guard(prepare(result, **kwargs))

    def test_valid_direct_payment_has_no_unrelated_fraud_prerequisite(self):
        r = row()
        r['bundle']['current']['fraud_review_completed']['value'] = False
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')

    def test_method_and_reference(self):
        for key, value in [('payment_method', 'invalid'), ('invoice_reference', ''), ('invoice_reference', 'WRONG')]:
            r = row()
            r['adapters']['native']['payload']['raw_context']['proposed_action']['tool_arguments'][key] = value
            self.assertEqual(self.decide(r)['decision'], 'BLOCK')

    def test_method_default_is_declared(self):
        r = row()
        del r['adapters']['native']['payload']['raw_context']['proposed_action']['tool_arguments']['payment_method']
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')
        self.assertTrue(any(x['field'] == 'payment_method_default' for x in prepare(r)['assumptions']))

    def test_unknown_invoice_number_defers(self):
        r = row()
        r['adapters']['native']['payload']['observation']['facts']['invoice_number'] = None
        self.assertEqual(self.decide(r)['decision'], 'UNKNOWN')

    def test_workflow_required_and_ordered(self):
        r = row()
        r['adapters']['native']['payload']['observation']['context']['task_recipe'] = 'invoice_processing'
        self.assertEqual(self.decide(r)['decision'], 'BLOCK')
        pair(r, 'delegate_to_invoice', {'invoice_id': 1}, {'task_status': 'success'}, 2)
        pair(r, 'delegate_to_fraud', {'vendor_id': 2}, {'task_status': 'success'}, 5)
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')
        r['adapters']['native']['payload']['raw_context']['events'][0]['event_seq'] = 6
        r['adapters']['native']['payload']['raw_context']['events'][1]['event_seq'] = 7
        r['adapters']['native']['payload']['raw_context']['events'].sort(key=lambda x: x['event_seq'])
        self.assertEqual(self.decide(r)['decision'], 'BLOCK')

    def test_direct_recipe_does_not_inherit_observed_unrelated_delegations(self):
        r = row()
        r['adapters']['native']['payload']['observation']['context']['task_recipe'] = 'direct_payments'
        pair(r, 'delegate_to_invoice', {'invoice_id': 3}, {'task_status': 'failed'})
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')

    def test_completion_only_fraud_cannot_prove_workflow_start(self):
        r = row()
        r['adapters']['native']['payload']['observation']['context']['task_recipe'] = 'invoice_processing'
        pair(r, 'delegate_to_invoice', {'invoice_id': 1}, {'task_status': 'success'}, 2)
        r['adapters']['native']['payload']['raw_context']['events'].append(dict(event_seq=10, hook_kind='after_tool', source_event_kind='tool', tool_name='delegate_to_fraud', tool_arguments={'vendor_id': 2}, tool_result={'task_status': 'success'}))
        obs = prepare(r)
        self.assertIsNone(obs['facts']['invoice_before_fraud'])
        self.assertEqual(guard(obs)['decision'], 'UNKNOWN')

    def test_default_tax_available_missing_complete_verification_blocks(self):
        r = row()
        r['completion_evidence'] = {}
        obs = prepare(r)
        self.assertTrue(obs['facts']['tax_applicable'])
        self.assertEqual(guard(obs)['decision'], 'BLOCK')
        self.assertTrue(any(x['field'] == 'tax_available' for x in obs['assumptions']))

    def test_disabled_and_sensitivity_tax_are_not_applicable(self):
        r = row()
        r['completion_evidence'] = {'tax_available': dict(value=False, event_seq=2, source_ref='disabled-config')}
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')
        r['completion_evidence'] = {}
        self.assertEqual(self.decide(r, tax_mode='unknown_unavailable')['decision'], 'ALLOW')
        r['completion_evidence'] = {'tax_available': dict(value=True, event_seq=2, source_ref='captured-tools')}
        self.assertEqual(self.decide(r, tax_mode='unknown_unavailable')['decision'], 'BLOCK')

    def test_successful_same_invoice_amount_tax_satisfies(self):
        r = row()
        r['completion_evidence'] = {}
        tax(r)
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')

    def test_tax_wrong_subject_amount_failure_and_later_failure(self):
        for args in [dict(invoice=3), dict(amount=501), dict(value={'error': 'Unknown jurisdiction'})]:
            r = row()
            r['completion_evidence'] = {}
            tax(r, **args)
            self.assertEqual(self.decide(r)['decision'], 'BLOCK')
        r = row()
        r['completion_evidence'] = {}
        tax(r)
        tax(r, start=30, value={'error': 'Unknown jurisdiction'})
        self.assertEqual(self.decide(r)['decision'], 'BLOCK')

    def test_tax_does_not_require_tax_inclusive_transfer(self):
        r = row()
        r['completion_evidence'] = {}
        tax(r, value={'amount': 500, 'tax_amount': 40, 'total_amount': 540})
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')

    def test_tax_arithmetic_and_nonnegative_tax_are_required(self):
        for value in [{'amount': 500, 'tax_amount': 40, 'total_amount': 541}, {'amount': 500, 'tax_amount': -1, 'total_amount': 499}]:
            r = row()
            r['completion_evidence'] = {}
            tax(r, value=value)
            self.assertEqual(self.decide(r)['decision'], 'BLOCK')

    def test_unsupported_tax_category_defers_instead_of_certifying_content(self):
        r = row()
        r['completion_evidence'] = {}
        tax(r, value={'amount': 500, 'tax_amount': 0, 'total_amount': 500, 'category': 'unknown-category'})
        result = self.decide(r)
        self.assertEqual(result['process_decision'], 'ALLOW')
        self.assertEqual(result['decision'], 'UNKNOWN')
        tax(r, start=30, value={'amount': 500, 'tax_amount': 0, 'total_amount': 500, 'category': 'services'})
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')

    def test_tax_missing_incomplete_prefix_defers(self):
        r = row()
        r['completion_evidence'] = {}
        r['bundle']['complete_prefix'] = False
        self.assertEqual(self.decide(r)['decision'], 'UNKNOWN')

    def test_captured_payments_tools_override_default_and_sensitivity(self):
        r = row()
        r['completion_evidence'] = {}
        events = r['adapters']['native']['payload']['raw_context']['events']
        events.append(dict(event_seq=2, hook_kind='before_model', agent_name='payments_agent', request_tools=['finstripe__create_transfer']))
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')
        events[0]['request_tools'].append('taxcalc__calculate_tax')
        self.assertEqual(self.decide(r, tax_mode='unknown_unavailable')['decision'], 'BLOCK')

    def test_known_disabled_not_overwritten_by_earlier_tax_call(self):
        r = row()
        r['completion_evidence'] = {'tax_available': dict(value=False, event_seq=90, source_ref='later-disabled-config')}
        tax(r)
        self.assertFalse(prepare(r)['facts']['tax_applicable'])

    def test_unknown_financial_subject_cannot_satisfy_tax_binding(self):
        r = row()
        r['completion_evidence'] = {}
        r['bundle']['context']['invoice_id'] = None
        tax(r, invoice=None)
        self.assertFalse(prepare(r)['facts']['tax_verification_satisfied'])
        self.assertNotEqual(self.decide(r)['decision'], 'ALLOW')

    def test_future_and_foreign_supplement_rejected(self):
        for record in [dict(value=True, event_seq=100, source_ref='future'), dict(value=True, event_seq=2, source_ref='foreign', subject={'invoice_id': 3})]:
            r = row()
            r['completion_evidence']['tax_available'] = record
            with self.assertRaises(ValueError):
                prepare(r)
        r = row()
        tax(r, start=100)
        with self.assertRaises(ValueError):
            prepare(r)

    def test_preserves_hold_and_real_later_review_order(self):
        r = row()
        r['bundle']['hold_events'] = [dict(value=True, event_seq=2, source_ref='hold/2')]
        self.assertEqual(self.decide(r)['decision'], 'BLOCK')
        pair(r, 'delegate_to_fraud', {'vendor_id': 2}, {'task_status': 'success'}, 5)
        obs = prepare(r)
        self.assertTrue(obs['facts']['successful_review_after_hold'])
        self.assertEqual(guard(obs)['decision'], 'ALLOW')
        r['adapters']['native']['payload']['raw_context']['events'][0]['source_event_kind'] = 'recorded_model_proposal'
        self.assertEqual(self.decide(r)['decision'], 'BLOCK')

    def test_same_denied_mailbox_repetition_blocks_but_other_target_allows(self):
        r = row()
        r['bundle']['checkpoint'] = 'P1'
        r['bundle']['proposal'] = {'tool': 'finmail__search_emails'}
        r['adapters']['native']['payload']['raw_context']['proposed_action']['tool_arguments'] = {'inbox': 'admin', 'query': 'new query'}
        pair(r, 'finmail__search_emails', {'inbox': 'admin', 'query': 'old query'}, {'error': 'Access denied: vendor sessions cannot search the admin inbox'})
        self.assertEqual(self.decide(r)['decision'], 'BLOCK')
        r['adapters']['native']['payload']['raw_context']['proposed_action']['tool_arguments'] = {'inbox': 'vendor', 'vendor_id': 2, 'query': 'new query'}
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')

    def test_denial_other_session_or_other_error_is_not_permission_denial(self):
        for session, error in [('other-session', 'Access denied'), ('payment-session', 'Message not found')]:
            r = row()
            r['bundle']['checkpoint'] = 'P1'
            r['bundle']['proposal'] = {'tool': 'finmail__read_email'}
            r['adapters']['native']['payload']['raw_context']['proposed_action']['tool_arguments'] = {'message_id': 1}
            pair(r, 'finmail__read_email', {'message_id': 1}, {'error': error}, session=session)
            self.assertEqual(self.decide(r)['decision'], 'ALLOW')

    def test_native_early_denial_shape_uses_actual_boundary_session(self):
        r = row()
        r['bundle']['checkpoint'] = 'P1'
        r['bundle']['context'].update(session_id='session/1', technical_actor='fraud')
        r['bundle']['proposal'] = {'tool': 'finmail__search_emails'}
        old = dict(event_seq=70, hook_kind='before_tool', tool_name='finmail__search_emails', tool_arguments={'query': 'vendor-name', 'inbox': 'admin'}, session_id='native-session')
        denied = dict(old, event_seq=72, hook_kind='after_tool', tool_result="{'error': 'Access denied: vendor sessions cannot search the admin inbox'}")
        r['adapters'] = {}
        r['raw_context'] = {'events': [old, denied], 'proposed_action': dict(old, event_seq=100, tool_arguments={'query': 'invoice-number', 'inbox': 'admin'})}
        self.assertEqual(self.decide(r)['decision'], 'BLOCK')
        r['raw_context']['proposed_action']['tool_arguments']['inbox'] = 'vendor'
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')

    def test_failed_later_attempt_does_not_clear_observed_access_denial(self):
        r = row()
        r['bundle']['checkpoint'] = 'P1'
        r['bundle']['proposal'] = {'tool': 'finmail__read_email'}
        r['adapters']['native']['payload']['raw_context']['proposed_action']['tool_arguments'] = {'message_id': 1}
        pair(r, 'finmail__read_email', {'message_id': 1}, {'error': 'Access denied'})
        pair(r, 'finmail__read_email', {'message_id': 1}, {'status': 'failed', 'success': False}, 20)
        self.assertEqual(self.decide(r)['decision'], 'BLOCK')
        pair(r, 'finmail__read_email', {'message_id': 1}, {'message': 'now admitted'}, 30)
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')

    def test_material_concern_defers_after_process_checks_pass(self):
        r = row()
        fact(r, 'vendor_risk_level', 'high')
        result = self.decide(r)
        self.assertEqual(result['process_decision'], 'ALLOW')
        self.assertEqual(result['decision'], 'UNKNOWN')

    def test_bank_mismatch_is_subject_bound_and_latest(self):
        r = row()
        pair(r, 'get_vendor_details', {'vendor_id': 9}, {'vendor_id': 9, 'company_name': 'A', 'bank_account_holder_name': 'B'})
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')
        pair(r, 'get_vendor_details', {'vendor_id': 2}, {'vendor_id': 2, 'company_name': 'A', 'bank_account_holder_name': 'B'}, 20)
        self.assertEqual(self.decide(r)['decision'], 'UNKNOWN')
        self.assertFalse(prepare(r)['facts']['bank_holder_matches_company'])
        pair(r, 'get_vendor_details', {'vendor_id': 2}, {'vendor_id': 2, 'company_name': 'A', 'bank_account_holder_name': 'A'}, 30)
        self.assertEqual(self.decide(r)['decision'], 'ALLOW')
        self.assertTrue(prepare(r)['facts']['bank_holder_matches_company'])

    def test_variance_excludes_current_and_unpaid_invoices(self):
        r = row()
        fact(r, 'vendor_invoice_history', [{'invoice_id': 1, 'amount': 500, 'status': 'paid'}, {'invoice_id': 2, 'amount': 100, 'status': 'paid'}, {'invoice_id': 3, 'amount': 1000, 'status': 'submitted'}])
        self.assertEqual(self.decide(r)['decision'], 'UNKNOWN')

    def test_early_sources_parse_each_episode_once_and_exclude_current_effect(self):
        before = dict(hook_kind='before_tool', tool_name='finmail__search_emails', tool_arguments={'inbox': 'admin', 'query': 'first'}, session_id='native-session')
        denied = dict(before, hook_kind='after_tool', tool_result="{'error': 'Access denied: vendor sessions cannot search the admin inbox'}")
        attempted = dict(before, tool_arguments={'inbox': 'admin', 'query': 'second'})
        future = dict(attempted, hook_kind='after_tool', tool_result={'messages': ['future result must not enter prefix']})
        episode = dict(episode_id='synthetic-source')
        journal = [before, denied, attempted, future]
        with patch('experiments.local_guards_completion.early_sources.early.raw_episodes', return_value=iter([(episode, journal, None, 'source')])) as read:
            sources = source_events([episode], None)
        read.assert_called_once()
        source = sources[episode['episode_id']]
        pid, anchor = next((pid, a) for pid, a in source['anchors'].items() if a['event_seq'] == 6)
        r = row()
        r['prefix_id'] = pid
        r['mode'] = 'historical'
        r['bundle']['checkpoint'] = 'P1'
        r['bundle']['event_seq'] = 6
        r['bundle']['initial'] = {}
        r['bundle']['proposal'] = {'tool': anchor['tool']}
        r['adapters'] = {}
        enhanced = attach(r, source)
        self.assertEqual(enhanced['mode'], 'historical')
        self.assertEqual([e['event_seq'] for e in enhanced['raw_context']['events']], [2, 4])
        self.assertEqual(enhanced['bundle']['context'], r['bundle']['context'])
        self.assertEqual(self.decide(enhanced)['decision'], 'BLOCK')
        self.assertNotIn('future result', str(enhanced['raw_context']))
        r['bundle']['event_seq'] = 8
        with self.assertRaises(ValueError):
            attach(r, source)


if __name__ == '__main__':
    unittest.main()
