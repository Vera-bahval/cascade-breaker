import gzip
import json
import pathlib
import tempfile
import unittest
import score

class ScoreTest(unittest.TestCase):
    def test_categories_and_cluster_bootstrap(self):
        rows = [
            ({'action_label': 'ALLOW', 'annotation_status': 'resolved', 'author_category': 'legit', 'scenario_intent': 'benign'}, 'ALLOW', 'g1'),
            ({'action_label': 'BLOCK', 'annotation_status': 'resolved', 'author_category': 'fraud', 'scenario_intent': 'attack'}, 'ALLOW', 'g1'),
            ({'action_label': 'INSUFFICIENT', 'annotation_status': 'resolved', 'author_category': 'unknown', 'scenario_intent': 'unknown'}, 'UNKNOWN', 'g2'),
            ({'action_label': None, 'annotation_status': 'unresolved', 'author_category': 'unknown', 'scenario_intent': 'unknown'}, 'BLOCK', 'g2'),
        ]
        result = score.summarize(rows)
        self.assertEqual(result['action']['correct_allow'], 1)
        self.assertEqual(result['action']['wrong_allow_known_block'], 1)
        self.assertEqual(result['action']['unknown'], 1)
        self.assertEqual(result['action']['unresolved_gold'], 1)
        self.assertEqual(result['author_category']['unknown']['UNKNOWN'], 1)
        self.assertEqual(result['scenario_intent']['benign']['ALLOW'], 1)
        self.assertEqual(result['bootstrap']['correct_decisive_coverage_all']['point'], 1/4)
        self.assertEqual(result['bootstrap']['correct_decisive_rate_resolved']['point'], 1/3)
        self.assertEqual(result['bootstrap'], score.summarize(rows)['bootstrap'])

    def test_unavailable_is_separate_from_saved_unknown(self):
        unavailable = {'decision': 'UNKNOWN', 'adapter_applicable': False}
        available = {'decision': 'UNKNOWN', 'adapter_applicable': True}
        unspecified = {'decision': 'UNKNOWN', 'adapter_applicable': None}
        self.assertEqual(unavailable['decision'], 'UNKNOWN')
        self.assertEqual(score.count_state(unavailable), 'ADAPTER_UNAVAILABLE')
        self.assertEqual(score.count_state(available), 'UNKNOWN')
        self.assertEqual(score.count_state(unspecified), 'UNKNOWN')
        label = {'action_label': 'INSUFFICIENT', 'annotation_status': 'resolved',
                 'author_category': 'unknown', 'scenario_intent': 'unknown'}
        result = score.summarize([(label, score.count_state(p), 'g')
                                  for p in (unavailable, available, unspecified)])
        self.assertEqual(result['action']['adapter_unavailable'], 1)
        self.assertEqual(result['action']['unknown'], 2)
        self.assertEqual(result['action']['correct_allow'] + result['action']['correct_block'], 0)
        self.assertEqual(result['author_category']['unknown']['ADAPTER_UNAVAILABLE'], 1)
        self.assertEqual(result['bootstrap']['correct_decisive_coverage_all']['point'], 0)

    def test_vector_event_seq_must_match_frozen_input(self):
        row = {'case_id': 'case', 'checkpoint': 'P4', 'event_seq': 3,
               'placement': 'p4', 'method': 'm', 'decision': 'ALLOW'}
        cases = {'case': ({}, 'group', 2)}
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'vector.jsonl.gz'
            with gzip.open(path, 'wt', encoding='utf8') as stream:
                stream.write(json.dumps(row) + '\n')
            with self.assertRaisesRegex(ValueError, 'event_seq mismatch'):
                score.read_vectors(path, cases)
            row['event_seq'] = 2
            with gzip.open(path, 'wt', encoding='utf8') as stream:
                stream.write(json.dumps(row) + '\n')
            self.assertEqual(score.read_vectors(path, cases)['m|p4|none']['case']['decision'], 'ALLOW')

if __name__ == '__main__': unittest.main()
