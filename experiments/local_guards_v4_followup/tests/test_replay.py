"""Tiny authored representation tests; no frozen gold or target methods imported."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location('followup_' + name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.replay = load('replay')
        self.normal = load('normalize')

    def row(self):
        return {'prefix_id': 'join-only', 'checkpoint': 'P4', 'event_seq': 20,
                'proposal': {'tool': 'finstripe__create_transfer', 'amount': '12', 'currency': 'EUR'},
                'facts': {'invoice_amount': '12', 'invoice_currency': 'EUR', 'binding_hold': False,
                          'human_approved': None},
                'provenance': {'invoice_amount': [{'source': 'native_tool', 'event_seq': 4,
                    'subject_matches': True, 'operation': 'get_invoice', 'writer': 'native_store'}],
                    'invoice_currency': [{'source': 'native_tool', 'event_seq': 4,
                    'subject_matches': True, 'operation': 'get_invoice', 'writer': 'native_store'}],
                    'binding_hold': [], 'human_approved': []}}

    def test_payment_conversion_never_reads_labels_and_preserves_unknown(self):
        class LabelTrap(dict):
            def get(self, key, *args):
                if key in {'gold', 'label', 'family', 'pair_member', 'decision'}:
                    raise AssertionError('label access')
                return super().get(key, *args)
        source = LabelTrap(self.row(), gold=object())
        observation = self.replay.adapt_payment320(source)
        self.assertEqual(observation['facts']['invoice_currency'], 'EUR')
        self.assertIsNone(observation['facts']['human_approved'])
        self.assertEqual(observation['provenance']['binding_hold'], [])
        proof = observation['provenance']['invoice_currency'][0]
        self.assertEqual((proof['source'], proof['evidence_kind']), ('initial_fixture', 'declared_fixture'))
        self.assertEqual(proof['event_seq'], 4)
        self.assertIsNone(observation['context']['approval'])
        self.assertIsNone(observation['context']['claim'])

    def test_conversion_preserves_foreign_future_and_invalid_sources(self):
        source = self.row()
        source['provenance']['invoice_amount'][0].update(subject_matches=False, event_seq=25,
                                                       namespace='foreign', source='narrative')
        proof = self.replay.adapt_payment320(source)['provenance']['invoice_amount'][0]
        self.assertEqual((proof['subject_matches'], proof['event_seq'], proof['namespace']), (False, 25, 'foreign'))
        self.assertEqual(proof['source'], 'narrative')
        self.assertNotIn('evidence_kind', proof)

    def test_strict_is_unchanged_and_retains_payment_baseline(self):
        row = {'prefix_id': 'original', 'observation': {'context': None, 'event_seq': -1},
               'payment_baseline': self.row()}
        before = copy.deepcopy(row)
        result = self.replay.archive_variant(row, {'source_intent': 'ignored'})
        self.assertEqual(result['observation'], before['observation'])
        self.assertEqual(result['payment_baseline'], before['payment_baseline'])
        self.assertEqual(result['assumptions'], [])
        result['observation']['event_seq'] = 99
        self.assertEqual(row, before)

    def test_session_adds_no_access_financial_or_workflow_fact(self):
        observation = {'checkpoint': 'P4', 'event_seq': 20, 'proposal': {},
            'context': {'session_id': None, 'namespace': None, 'user_id': None,
                        'origin_portal': None, 'record_id': None, 'workflow_id': None,
                        'invoice_id': None},
            'facts': {'session_valid': None, 'vendor_in_scope': None, 'invoice_amount': None},
            'provenance': {'session_valid': []}}
        result = self.replay.archive_variant({'prefix_id': 'x', 'observation': observation}, {}, 'session', 'admin')
        converted = result['observation']
        self.assertEqual(converted['context']['origin_portal'], 'admin')
        self.assertIsNone(converted['context']['workflow_id'])
        self.assertIsNone(converted['context']['invoice_id'])
        self.assertIsNone(converted['facts']['vendor_in_scope'])
        self.assertIsNone(converted['facts']['invoice_amount'])
        self.assertTrue(converted['facts']['session_valid'])
        observation['facts']['session_valid'] = False
        self.assertFalse(self.replay.archive_variant(observation, {}, 'session')['observation']['facts']['session_valid'])
        self.assertTrue(all({'field', 'old', 'new', 'basis'} <= a.keys() for a in result['assumptions']))

    def test_technical_does_not_invent_binding_or_parent(self):
        observation = {'checkpoint': 'P2', 'event_seq': 20, 'proposal': {},
            'context': {'workflow_id': 'owner', 'parent_workflow_id': None,
                        'delegation_succeeded': True, 'delegated_actor': 'payments',
                        'delegation_call_id': 'target', 'approval': None, 'claim': None},
            'facts': {'delegation_subject_matches': True},
            'provenance': {'delegation_subject_matches': [{'source': 'server_context',
                'subject_matches': True, 'event_seq': 4, 'operation': 'runner_completion_link_check'}]}}
        out = self.replay.archive_variant(observation, {'source_intent': 'legit'}, 'technical')['observation']
        self.assertIsNone(out['context']['approval'])
        self.assertIsNone(out['context']['claim'])
        self.assertIsNone(out['context']['parent_workflow_id'])
        self.assertNotIn('delegated_workflow_id', out['context'])

    def test_fixture_origin_additions_project_back_without_losing_known_parent(self):
        observation = {'checkpoint': 'P1', 'event_seq': 20, 'context': {'parent_workflow_id': 'parent'},
            'facts': {'binding_hold': False}, 'proposal': {},
            'provenance': {'binding_hold': [{'source': 'native_tool', 'event_seq': 3,
                'operation': 'get_invoice', 'subject_matches': True, 'record_id': 'proof'}]}}
        variant = self.replay.adapt_v41_fixture({'prefix_id': 'p', 'observation': observation})
        self.assertEqual(self.replay.project_v41(variant['observation']), observation)
        self.assertEqual(variant['observation']['context']['parent_workflow_id'], 'parent')

    def test_session_preserves_null_scoped_proofs_and_invalid_boolean(self):
        observation = {'event_seq': 8, 'context': {'namespace': 'known'},
            'facts': {'session_valid': 1, 'binding_hold': False},
            'provenance': {'session_valid': [], 'binding_hold': [{'source': 'native_tool',
                'event_seq': 3, 'subject_matches': True, 'operation': 'read', 'namespace': None}]}}
        out = self.replay.archive_variant(observation, {}, 'technical')['observation']
        self.assertEqual(type(out['facts']['session_valid']), int)
        self.assertEqual(out['provenance']['session_valid'], [])
        self.assertIsNone(out['provenance']['binding_hold'][0]['namespace'])

    def test_counterfactual_admission_requires_original_root_and_retains_its_key(self):
        registry = self.replay.ArchiveReplayRegistry()
        context = {'namespace': 'n', 'session_id': 's', 'workflow_id': 'owner',
            'vendor_id': 2, 'current_vendor_id': 2, 'invoice_id': 3, 'invoice_version': 'iv',
            'vendor_version': 'vv', 'call_id': 'root-call', 'claim': None}
        proofs = {}
        for field in ('vendor_in_scope', 'invoice_in_scope'):
            proof = {key: context[key] for key in ('namespace', 'session_id', 'workflow_id',
                'vendor_id', 'invoice_id', 'invoice_version', 'vendor_version', 'call_id')}
            proof.update(source='server_context', event_seq=1, subject_matches=True, value=True,
                         operation='verified_worker_fixture_scope', record_id=field)
            proofs[field] = [proof]
        root = {'checkpoint': 'P0', 'event_seq': 2, 'context': context, 'proposal': {},
            'facts': {'vendor_in_scope': True, 'invoice_in_scope': True}, 'provenance': proofs}
        no_root = copy.deepcopy(root); no_root['checkpoint'] = 'P4'
        self.assertIsNone(self.replay.archive_variant(no_root, {'episode_id': 'missing'},
            'technical', registry=registry)['observation']['context']['claim'])
        out = self.replay.archive_variant(root, {'episode_id': 'e'}, 'technical', registry=registry)
        claim = out['observation']['context']['claim']
        self.assertEqual(claim['owner_workflow_id'], 'owner')
        self.assertLess(claim['acquired_seq'], root['event_seq'])
        later = copy.deepcopy(no_root); later['event_seq'] = 8; later['context']['invoice_id'] = 99
        later_claim = self.replay.archive_variant(later, {'episode_id': 'e'}, 'technical',
            registry=registry)['observation']['context']['claim']
        self.assertEqual(later_claim, claim)
        later['context']['workflow_id'] = 'other'
        self.assertIsNone(self.replay.archive_variant(later, {'episode_id': 'e'}, 'technical',
            registry=registry)['observation']['context']['claim'])

    def test_fixture_delegation_requires_original_complete_scope(self):
        context = {'namespace': 'n', 'session_id': 's', 'workflow_id': 'owner',
            'vendor_id': 2, 'invoice_id': 3, 'invoice_version': 'iv', 'vendor_version': 'vv',
            'call_id': 'target', 'parent_workflow_id': 'parent', 'delegated_actor': 'fraud',
            'delegation_call_id': 'delegation', 'delegation_succeeded': True}
        proof = {key: context[key] for key in ('namespace', 'session_id', 'workflow_id',
            'vendor_id', 'invoice_id', 'invoice_version', 'vendor_version', 'call_id')}
        proof.update(source='server_context', event_seq=3, subject_matches=True,
                     value=True, operation='runner_completion_link_check', record_id='p')
        observation = {'event_seq': 10, 'context': context, 'proposal': {},
            'facts': {'delegation_subject_matches': True},
            'provenance': {'delegation_subject_matches': [proof]}}
        out = self.replay.adapt_v41_fixture(observation)['observation']
        self.assertEqual(out['provenance']['delegation_subject_matches'][0]['parent_workflow_id'], 'parent')
        self.assertEqual(out['provenance']['delegation_subject_matches'][0]['delegated_workflow_id'],
                         out['context']['delegated_workflow_id'])
        self.assertEqual(self.replay.project_v41(out), observation)
        observation['provenance']['delegation_subject_matches'][0]['namespace'] = 'foreign'
        out = self.replay.adapt_v41_fixture(observation)['observation']
        self.assertNotIn('delegated_workflow_id', out['context'])

    def test_normalization_strips_wrapper_and_metadata_and_preserves_equality(self):
        first = {'prefix_id': 'left', 'episode_id': 'e', 'event_seq': 20,
                 'context': {'workflow_id': 'a', 'parent_workflow_id': 'a', 'call_id': 'b'},
                 'provenance': {'x': [{'event_seq': 3, 'source_call_id': 'b', 'snapshot_id': 'c'}]},
                 'facts': {'x': False}}
        renamed = {'event_seq': 50, 'context': {'workflow_id': 'new', 'parent_workflow_id': 'new', 'call_id': 'other'},
                   'provenance': {'x': [{'event_seq': 7, 'source_call_id': 'other', 'snapshot_id': 'snap'}]},
                   'facts': {'x': False}}
        self.assertEqual(self.normal.normalize({'observation': first, 'prefix_id': 'outer'}), self.normal.normalize(renamed))
        renamed['context']['parent_workflow_id'] = 'different'
        self.assertNotEqual(self.normal.normalize(first), self.normal.normalize(renamed))

    def test_normalization_preserves_values_absence_shape_and_invalid_ids(self):
        base = {'facts': {'x': False}, 'context': {'vendor_id': 1}, 'provenance': {}}
        for changed in [{'facts': {'x': None}, 'context': {'vendor_id': 1}, 'provenance': {}},
                        {'facts': {}, 'context': {'vendor_id': 1}, 'provenance': {}},
                        {'facts': {'x': False}, 'context': {'vendor_id': -1}, 'provenance': {}},
                        {'facts': {'x': False}, 'context': {'vendor_id': [1]}, 'provenance': {}}]:
            self.assertNotEqual(self.normal.normalize(base), self.normal.normalize(changed))


if __name__ == '__main__':
    unittest.main()
