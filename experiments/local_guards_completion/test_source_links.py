from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from . import source_links
from .test_rules import row, tax
from .rules import prepare


def fixture():
    result = row()
    result['prefix_id'] = 'p'
    result['completion_evidence'] = {}
    result['bundle']['context'].pop('session_id')
    tax(result)
    raw = result['adapters']['native']['payload']['raw_context']
    raw['proposed_action'].update(event_seq=100, tool_name='finstripe__create_transfer')
    source_headers = {}
    for event in raw['events']:
        event.pop('session_id', None)
        event.pop('agent_name', None)
        source_headers[source_links.key(event)] = dict(source_links.header(event), session_id='private-source-session', agent_name='payments_agent')
    source_headers[100, 'before_tool', 'finstripe__create_transfer'] = dict(event_seq=100,
        hook_kind='before_tool', tool_name='finstripe__create_transfer', session_id='private-source-session',
        agent_name='payments_agent', subject={'invoice_id': 1, 'vendor_id': 2})
    source = dict(episode_id='ep', legacy=False, headers=source_headers)
    metadata = dict(prefix_id='p', checkpoint='P4', event_seq=100, episode_id='ep')
    return result, source, metadata


class SourceLinkTests(unittest.TestCase):
    def test_restored_tax_scope_preserves_financial_tokens_and_hides_raw_sessions(self):
        result, source, metadata = fixture()
        original = deepcopy(result)
        self.assertFalse(prepare(result)['facts']['tax_verification_satisfied'])
        restored = source_links.restore(result, source, metadata)
        self.assertTrue(prepare(restored)['facts']['tax_verification_satisfied'])
        before = result['adapters']['native']['payload']['raw_context']
        after = restored['adapters']['native']['payload']['raw_context']
        self.assertEqual(after['proposed_action']['session_id'], after['events'][0]['session_id'])
        self.assertNotIn('private-source-session', json.dumps(restored))
        for old, new in zip(before['events'], after['events'], strict=True):
            for field in ('tool_arguments', 'tool_result'):
                self.assertEqual(old.get(field), new.get(field))
        self.assertEqual(before['proposed_action']['tool_arguments'], after['proposed_action']['tool_arguments'])
        self.assertEqual(result, original)

    def test_existing_canonical_session_alias_is_reused(self):
        result, source, metadata = fixture()
        raw = result['adapters']['native']['payload']['raw_context']
        raw['events'][0]['session_id'] = 'session/existing-canonical'
        restored = source_links.restore(result, source, metadata)
        self.assertEqual(restored['adapters']['native']['payload']['raw_context']['proposed_action']['session_id'], 'session/existing-canonical')

    def test_future_coordinate_and_foreign_or_mismatched_anchor_rejected(self):
        result, source, metadata = fixture()
        wrong = deepcopy(source)
        wrong['episode_id'] = 'foreign'
        with self.assertRaisesRegex(ValueError, 'foreign'):
            source_links.restore(result, wrong, metadata)
        wrong = deepcopy(source)
        wrong['headers'][100, 'before_tool', 'finstripe__create_transfer']['subject']['invoice_id'] = 9
        with self.assertRaisesRegex(ValueError, 'foreign P4 source anchor'):
            source_links.restore(result, wrong, metadata)
        result['adapters']['native']['payload']['raw_context']['events'][0]['event_seq'] = 100
        with self.assertRaisesRegex(ValueError, 'future'):
            source_links.restore(result, source, metadata)

    def test_legacy_P4_header_restored_without_importing_payload_result(self):
        episode = {'episode_id': 'legacy'}
        journal = [dict(seq=4, kind='guard_context', point='P4.finstripe__create_transfer',
            agent='payments_agent', payload={'tool': 'finstripe__create_transfer',
                'arguments': {'invoice_id': 1, 'vendor_id': 2, 'vendor_account': 'DO_NOT_COPY'},
                'tool_result': 'FUTURE_RESULT'})]
        with patch.object(source_links.early, 'raw_episodes', return_value=iter([(episode, journal, {}, 'source')])) as read:
            sources = source_links.build_sources([episode], None)
        read.assert_called_once()
        value = sources['legacy']['headers'][9, 'before_tool', 'finstripe__create_transfer']
        self.assertEqual(value['agent_name'], 'payments_agent')
        self.assertNotIn('DO_NOT_COPY', json.dumps(list(sources['legacy']['headers'].values())))
        self.assertNotIn('FUTURE_RESULT', json.dumps(list(sources['legacy']['headers'].values())))


if __name__ == '__main__':
    unittest.main()
